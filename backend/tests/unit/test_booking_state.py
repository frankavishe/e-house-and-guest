"""Booking state machine (T065, R17): allowed transitions, guards and the event log."""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import BookingEvent, BookingStatus, CancelledBy
from app.bookings.state import Event, next_status, transition
from app.core.errors import AppError
from tests.factories import day_range, make_bookable, make_booking

S = BookingStatus
E = Event

ALLOWED: dict[tuple[BookingStatus, Event], BookingStatus] = {
    (S.REQUESTED, E.ACCEPT): S.AWAITING_PAYMENT,
    (S.REQUESTED, E.DECLINE): S.CANCELLED,
    (S.REQUESTED, E.EXPIRE): S.CANCELLED,
    (S.REQUESTED, E.CANCEL): S.CANCELLED,
    (S.AWAITING_PAYMENT, E.PAY): S.CONFIRMED,
    (S.AWAITING_PAYMENT, E.EXPIRE): S.CANCELLED,
    (S.AWAITING_PAYMENT, E.CANCEL): S.CANCELLED,
    (S.CONFIRMED, E.START): S.IN_PROGRESS,
    (S.CONFIRMED, E.CANCEL): S.CANCELLED,
    (S.CONFIRMED, E.DISPUTE): S.DISPUTED,
    (S.IN_PROGRESS, E.END): S.COMPLETED,
    (S.IN_PROGRESS, E.CANCEL): S.CANCELLED,
    (S.IN_PROGRESS, E.DISPUTE): S.DISPUTED,
    (S.COMPLETED, E.DISPUTE): S.DISPUTED,
    (S.DISPUTED, E.RESOLVE_COMPLETE): S.COMPLETED,
    (S.DISPUTED, E.RESOLVE_CANCEL): S.CANCELLED,
    (S.CANCELLED, E.LATE_PAYMENT): S.CONFIRMED,
}


@pytest.mark.parametrize(
    ("status", "event"), [(s, e) for s in BookingStatus for e in Event], ids=str
)
def test_transition_table(status: BookingStatus, event: Event) -> None:
    if (status, event) in ALLOWED:
        assert next_status(status, event) == ALLOWED[(status, event)]
    else:
        with pytest.raises(AppError) as err:
            next_status(status, event)
        assert err.value.code == "INVALID_TRANSITION" and err.value.status == 409


@pytest.mark.usefixtures("frozen_clock")
async def test_transition_records_event(db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *day_range(date(2026, 11, 10), date(2026, 11, 12)))

    await transition(db, booking, Event.PAY, actor_kind="provider", note="payment x")
    await transition(db, booking, Event.START)

    assert booking.status == S.IN_PROGRESS
    events = (
        (
            await db.execute(
                select(BookingEvent)
                .where(BookingEvent.booking_id == booking.id)
                .order_by(BookingEvent.created_at, BookingEvent.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(e.from_status, e.to_status, e.actor_kind) for e in events] == [
        (S.AWAITING_PAYMENT, S.CONFIRMED, "provider"),
        (S.CONFIRMED, S.IN_PROGRESS, "system"),
    ]
    assert events[0].note == "payment x"


@pytest.mark.usefixtures("frozen_clock")
async def test_disallowed_transition_changes_nothing(db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(
        db, b, *day_range(date(2026, 11, 10), date(2026, 11, 12)), status="requested"
    )
    with pytest.raises(AppError):
        await transition(db, booking, Event.PAY)
    assert booking.status == S.REQUESTED
    count = (
        await db.execute(select(BookingEvent).where(BookingEvent.booking_id == booking.id))
    ).all()
    assert count == []


@pytest.mark.usefixtures("frozen_clock")
async def test_late_payment_only_revives_system_cancellations(db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(
        db, b, *day_range(date(2026, 11, 10), date(2026, 11, 12)), status="cancelled"
    )
    booking.cancelled_by = CancelledBy.RENTER
    with pytest.raises(AppError):
        await transition(db, booking, Event.LATE_PAYMENT)
    booking.cancelled_by = CancelledBy.SYSTEM
    await transition(db, booking, Event.LATE_PAYMENT)
    assert booking.status == S.CONFIRMED and booking.cancelled_by is None


@pytest.mark.usefixtures("frozen_clock")
async def test_only_an_admin_cancels_a_running_booking(db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(
        db, b, *day_range(date(2026, 11, 1), date(2026, 11, 5)), status="in_progress"
    )
    for who in (CancelledBy.RENTER, CancelledBy.OWNER, None):
        with pytest.raises(AppError):
            await transition(db, booking, Event.CANCEL, cancelled_by=who)
    await transition(db, booking, Event.CANCEL, cancelled_by=CancelledBy.ADMIN)
    assert booking.status == S.CANCELLED
    assert booking.cancelled_by == CancelledBy.ADMIN and booking.cancelled_at is not None
