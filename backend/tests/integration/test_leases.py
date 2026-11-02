"""Lease installment billing, reminders and overdue handling (T073, FR-020), frozen clock."""

import uuid
from datetime import date, datetime, time

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.leases import run_lease_billing
from app.bookings.models import Booking, BookingStatus, InstallmentStatus, LeaseInstallment
from app.core.clock import EAT
from app.notifications.models import Channel, Notification
from tests.conftest import FrozenClock
from tests.factories import (
    Bookable,
    book,
    deliver_callbacks,
    make_bookable,
    make_user,
    pay,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT


def eat(day: date, hour: int = 0) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=EAT)


async def _count(db: AsyncSession, user_id: uuid.UUID, event: str) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.event == event,
                Notification.channel == Channel.SMS,
            )
        )
    ).scalar_one()


async def _second(db: AsyncSession, booking_id: str) -> LeaseInstallment:
    return (
        await db.execute(
            select(LeaseInstallment)
            .where(LeaseInstallment.booking_id == uuid.UUID(booking_id), LeaseInstallment.seq == 2)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _confirmed_lease(client: httpx.AsyncClient, db: AsyncSession) -> tuple[Bookable, str]:
    b = await make_bookable(db, "LEASE", price=800_000)
    booking_id = (await book(client, b, date(2026, 12, 1), days=3)).json()["id"]
    assert (await pay(client, b, booking_id)).status_code == 202
    await deliver_callbacks(client)
    booking = await db.get(Booking, uuid.UUID(booking_id), populate_existing=True)
    assert booking is not None and booking.status == BookingStatus.CONFIRMED
    return b, booking_id


async def test_first_installment_paid_with_booking(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    _, booking_id = await _confirmed_lease(client, db)
    rows = (
        await db.execute(
            select(LeaseInstallment.seq, LeaseInstallment.status)
            .where(LeaseInstallment.booking_id == uuid.UUID(booking_id))
            .order_by(LeaseInstallment.seq)
        )
    ).all()
    assert [tuple(r) for r in rows] == [
        (1, InstallmentStatus.PAID),
        (2, InstallmentStatus.PENDING),
        (3, InstallmentStatus.PENDING),
    ]


async def test_billing_reminder_and_overdue(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b, booking_id = await _confirmed_lease(client, db)
    admin = await make_user(db, is_admin=True)
    # Installment 2 is due 2027-01-01 00:00 EAT.

    frozen_clock.set(eat(date(2026, 12, 24), 23))
    await run_lease_billing(db)
    assert (await _second(db, booking_id)).billed_at is None

    frozen_clock.set(eat(date(2026, 12, 25)))
    await run_lease_billing(db)
    await run_lease_billing(db)
    assert (await _second(db, booking_id)).billed_at is not None
    assert await _count(db, b.renter.id, "lease.installment_due") == 1
    assert await _count(db, b.renter.id, "lease.installment_reminder") == 0

    frozen_clock.set(eat(date(2026, 12, 30)))
    await run_lease_billing(db)
    await run_lease_billing(db)
    assert (await _second(db, booking_id)).reminded_at is not None
    assert await _count(db, b.renter.id, "lease.installment_reminder") == 1

    frozen_clock.set(eat(date(2027, 1, 7), 23))
    await run_lease_billing(db)
    assert (await _second(db, booking_id)).status == InstallmentStatus.PENDING

    frozen_clock.set(eat(date(2027, 1, 8)))
    await run_lease_billing(db)
    await run_lease_billing(db)
    assert (await _second(db, booking_id)).status == InstallmentStatus.OVERDUE
    assert await _count(db, b.owner_user.id, "lease.installment_overdue") == 1
    assert await _count(db, admin.id, "lease.installment_overdue_admin") == 1


async def test_billed_installment_can_be_paid(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b, booking_id = await _confirmed_lease(client, db)
    second = await _second(db, booking_id)

    early = await pay(client, b, booking_id, installment_id=str(second.id))
    assert early.status_code == 409  # not billed yet

    frozen_clock.set(eat(date(2026, 12, 25)))
    await run_lease_billing(db)
    r = await pay(client, b, booking_id, installment_id=str(second.id))
    assert r.status_code == 202, r.text
    assert r.json()["amount_tzs"] == 800_000
    await deliver_callbacks(client)

    assert (await _second(db, booking_id)).status == InstallmentStatus.PAID
    booking = await db.get(Booking, uuid.UUID(booking_id), populate_existing=True)
    assert booking is not None and booking.status == BookingStatus.CONFIRMED
