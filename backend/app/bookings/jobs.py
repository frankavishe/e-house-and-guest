"""Booking sweeps (R9): expire unpaid holds and undecided requests, move confirmed bookings
through `in_progress` to `completed` on the clock, and refund deposits once the claim window
has passed (FR-027). Each sweep is idempotent and locks rows with SKIP LOCKED, so
overlapping runs never act on one booking twice."""

from datetime import timedelta

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import service as availability
from app.bookings.claims import CLAIM_WINDOW
from app.bookings.models import Booking, BookingStatus, CancelledBy, Claim, ClaimStatus
from app.bookings.state import Event, transition
from app.core import clock
from app.jobs.registry import periodic
from app.ledger import service as ledger
from app.ledger.models import LedgerEntry
from app.payments import refunds
from app.payments.models import RefundReason

BATCH = 200


async def _locked(session: AsyncSession, *where: object) -> list[Booking]:
    rows = await session.execute(
        select(Booking)
        .where(*where)  # type: ignore[arg-type]
        .order_by(Booking.created_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


@periodic("bookings.expire_holds", every=timedelta(minutes=1))
async def expire_holds(session: AsyncSession) -> int:
    """Unpaid bookings past `payment_due_at` and requests past `request_expires_at` are
    cancelled by the system and their dates released (FR-017, FR-018)."""
    now = clock.now()
    expired = await _locked(
        session,
        or_(
            and_(Booking.status == BookingStatus.AWAITING_PAYMENT, Booking.payment_due_at <= now),
            and_(Booking.status == BookingStatus.REQUESTED, Booking.request_expires_at <= now),
        ),
    )
    for booking in expired:
        await transition(session, booking, Event.EXPIRE, cancelled_by=CancelledBy.SYSTEM)
        await availability.release(session, booking.id)
    return len(expired)


@periodic("bookings.advance", every=timedelta(minutes=1))
async def advance_bookings(session: AsyncSession) -> int:
    """confirmed → in_progress at the period start; in_progress → completed at its end."""
    now = clock.now()
    moved = 0
    for booking in await _locked(
        session,
        Booking.status == BookingStatus.CONFIRMED,
        func.lower(Booking.period) <= now,
    ):
        await transition(session, booking, Event.START)
        moved += 1
    for booking in await _locked(
        session,
        Booking.status == BookingStatus.IN_PROGRESS,
        func.upper(Booking.period) <= now,
    ):
        booking.completed_at = now
        await transition(session, booking, Event.END)
        moved += 1
    return moved


def _deposit_held() -> object:
    """The deposit still held for the outer `Booking` (ledger credit, so negated)."""
    return (
        select(-func.coalesce(func.sum(LedgerEntry.amount_tzs), 0))
        .where(LedgerEntry.booking_id == Booking.id, LedgerEntry.account == ledger.DEPOSIT_HELD)
        .correlate(Booking)
        .scalar_subquery()
    )


@periodic("bookings.release_deposits", every=timedelta(minutes=15))
async def release_deposits(session: AsyncSession) -> int:
    """Completed bookings whose claim window closed with no open claim get their remaining
    deposit refunded (US5-AS3). The ledger balance makes this run once per booking."""
    held = _deposit_held()
    released = 0
    for booking in await _locked(
        session,
        Booking.status == BookingStatus.COMPLETED,
        Booking.deposit_tzs > 0,
        func.upper(Booking.period) <= clock.now() - CLAIM_WINDOW,
        ~exists().where(Claim.booking_id == Booking.id, Claim.status == ClaimStatus.OPEN),
        held > 0,  # type: ignore[operator]
    ):
        amount = -(await ledger.booking_balance(session, booking.id, ledger.DEPOSIT_HELD))
        if await refunds.issue(
            session, booking, reason=RefundReason.DEPOSIT_RETURN, from_deposit_tzs=amount
        ):
            released += 1
    return released
