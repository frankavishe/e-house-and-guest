"""Owner request handling (T072, FR-018, US2-AS5, US3-AS4)."""

import uuid
from datetime import date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability.models import AvailabilityBlock
from app.bookings.jobs import expire_holds
from app.bookings.models import Booking, BookingStatus, CancelledBy, LeaseInstallment
from tests.conftest import FrozenClock
from tests.factories import book, make_bookable, make_owner, make_user, sign_in

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

D = date(2026, 11, 10)


async def _block_active(db: AsyncSession, booking_id: str) -> bool:
    block = (
        await db.execute(
            select(AvailabilityBlock)
            .where(AvailabilityBlock.booking_id == uuid.UUID(booking_id))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return block.active


async def test_accept_starts_24h_payment_window(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db, instant_book=False)
    booking_id = (await book(client, b, D)).json()["id"]

    sign_in(client, b.owner_user)
    r = await client.post(f"/api/v1/bookings/{booking_id}/accept")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "awaiting_payment"
    due = datetime.fromisoformat(body["payment_due_at"])
    assert due == frozen_clock.current + timedelta(hours=24)

    sign_in(client, b.renter)
    assert (await client.get(f"/api/v1/bookings/{booking_id}")).json()["can"]["pay"] is True

    sign_in(client, b.owner_user)
    again = await client.post(f"/api/v1/bookings/{booking_id}/accept")
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_TRANSITION"


async def test_decline_releases_hold(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db, instant_book=False)
    booking_id = (await book(client, b, D)).json()["id"]

    sign_in(client, b.owner_user)
    r = await client.post(
        f"/api/v1/bookings/{booking_id}/decline", json={"reason": "Not available"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    booking = await db.get(Booking, uuid.UUID(booking_id), populate_existing=True)
    assert booking is not None
    assert booking.cancelled_by == CancelledBy.OWNER and booking.cancel_reason == "Not available"
    assert not await _block_active(db, booking_id)


async def test_undecided_request_expires_after_24h(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db, instant_book=False)
    booking_id = (await book(client, b, D)).json()["id"]
    frozen_clock.advance(hours=24, seconds=1)
    assert await expire_holds(db) == 1
    booking = await db.get(Booking, uuid.UUID(booking_id), populate_existing=True)
    assert booking is not None and booking.status == BookingStatus.CANCELLED
    assert not await _block_active(db, booking_id)


async def test_only_listing_owner_decides(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db, instant_book=False)
    booking_id = (await book(client, b, D)).json()["id"]

    # The renter, and an owner of other listings, may not accept.
    assert (await client.post(f"/api/v1/bookings/{booking_id}/accept")).status_code == 403
    other_owner_user = await make_user(db)
    await make_owner(db, user=other_owner_user)
    sign_in(client, other_owner_user)
    for action in ("accept", "decline"):
        r = await client.post(f"/api/v1/bookings/{booking_id}/{action}")
        assert r.status_code == 403


async def test_lease_accept_asks_first_month_and_deposit(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db, "LEASE", price=800_000, deposit_tzs=1_600_000, instant_book=False)
    booking_id = (await book(client, b, date(2026, 12, 1), days=6)).json()["id"]

    sign_in(client, b.owner_user)
    body = (await client.post(f"/api/v1/bookings/{booking_id}/accept")).json()
    assert body["status"] == "awaiting_payment"
    assert body["amount_due_tzs"] == 2_400_000
    assert body["quote"]["total_tzs"] == 6 * 800_000 + 1_600_000

    installments = (
        await db.execute(
            select(LeaseInstallment)
            .where(LeaseInstallment.booking_id == uuid.UUID(booking_id))
            .order_by(LeaseInstallment.seq)
        )
    ).scalars().all()
    assert [i.seq for i in installments] == [1, 2, 3, 4, 5, 6]
    assert {i.amount_tzs for i in installments} == {800_000}
    assert [i.due_at.date().isoformat() for i in installments[:2]] == [
        "2026-11-30",  # midnight EAT is 21:00 UTC the day before
        "2026-12-31",
    ]

    sign_in(client, b.renter)
    r = await client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"network": "mpesa", "msisdn": "+255700000001"},
    )
    assert r.status_code == 202 and r.json()["amount_tzs"] == 2_400_000
