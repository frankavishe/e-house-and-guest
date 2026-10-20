"""Lease installments after the first (FR-020): billed 7 days before they are due, a
reminder 2 days before, and overdue 7 days after, which tells the owner and the admins.
Termination stays a manual admin action in the MVP (R17)."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings import notify
from app.bookings.models import Booking, InstallmentStatus, LeaseInstallment
from app.bookings.service import OPEN_LEASE
from app.core import clock
from app.jobs.registry import periodic

BILL_BEFORE = timedelta(days=7)
REMIND_BEFORE = timedelta(days=2)
OVERDUE_AFTER = timedelta(days=7)
BATCH = 200


async def _due(session: AsyncSession, *where: object) -> list[tuple[LeaseInstallment, Booking]]:
    rows = await session.execute(
        select(LeaseInstallment, Booking)
        .join(Booking, Booking.id == LeaseInstallment.booking_id)
        .where(
            LeaseInstallment.seq > 1,
            LeaseInstallment.status == InstallmentStatus.PENDING,
            Booking.status.in_(OPEN_LEASE),
            *where,  # type: ignore[arg-type]
        )
        .order_by(LeaseInstallment.due_at)
        .limit(BATCH)
        .with_for_update(of=LeaseInstallment, skip_locked=True)
        .execution_options(populate_existing=True)
    )
    return [(inst, booking) for inst, booking in rows.all()]


@periodic("leases.billing", every=timedelta(minutes=15))
async def run_lease_billing(session: AsyncSession) -> None:
    now = clock.now()
    for inst, booking in await _due(
        session, LeaseInstallment.billed_at.is_(None), LeaseInstallment.due_at <= now + BILL_BEFORE
    ):
        inst.billed_at = now
        await notify.installment_event(
            session, booking, inst, "lease.installment_due", who="renter"
        )
    for inst, booking in await _due(
        session,
        LeaseInstallment.billed_at.is_not(None),
        LeaseInstallment.reminded_at.is_(None),
        LeaseInstallment.due_at <= now + REMIND_BEFORE,
    ):
        inst.reminded_at = now
        await notify.installment_event(
            session, booking, inst, "lease.installment_reminder", who="renter"
        )
    for inst, booking in await _due(session, LeaseInstallment.due_at <= now - OVERDUE_AFTER):
        inst.status = InstallmentStatus.OVERDUE
        inst.overdue_at = now
        await notify.installment_event(
            session, booking, inst, "lease.installment_overdue", who="owner"
        )
        await notify.installment_event(
            session, booking, inst, "lease.installment_overdue_admin", who="admins"
        )
    await session.flush()
