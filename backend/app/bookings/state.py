"""Booking state machine (R17), as a transition table with guards (see `TRANSITIONS`).

Instant book creates a booking in `awaiting_payment`, a request in `requested`; a confirmed
booking runs `in_progress` → `completed` on the clock. A payment that succeeds after the
hold expired revives a system-cancelled booking (`late_payment`).

`transition()` is the only way a booking changes status: it checks the table and guards,
writes a `booking_events` row and queues the notifications for the new status.
"""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import ActorKind, Booking, BookingEvent, BookingStatus, CancelledBy
from app.core import clock
from app.core.errors import AppError

S = BookingStatus


class Event(StrEnum):
    ACCEPT = "accept"
    DECLINE = "decline"
    EXPIRE = "expire"
    CANCEL = "cancel"
    PAY = "pay"
    START = "start"
    END = "end"
    DISPUTE = "dispute"
    RESOLVE_COMPLETE = "resolve_complete"
    RESOLVE_CANCEL = "resolve_cancel"
    LATE_PAYMENT = "late_payment"


TRANSITIONS: dict[tuple[BookingStatus, Event], BookingStatus] = {
    (S.REQUESTED, Event.ACCEPT): S.AWAITING_PAYMENT,
    (S.REQUESTED, Event.DECLINE): S.CANCELLED,
    (S.REQUESTED, Event.EXPIRE): S.CANCELLED,
    (S.REQUESTED, Event.CANCEL): S.CANCELLED,
    (S.AWAITING_PAYMENT, Event.PAY): S.CONFIRMED,
    (S.AWAITING_PAYMENT, Event.EXPIRE): S.CANCELLED,
    (S.AWAITING_PAYMENT, Event.CANCEL): S.CANCELLED,
    (S.CONFIRMED, Event.START): S.IN_PROGRESS,
    (S.CONFIRMED, Event.CANCEL): S.CANCELLED,
    (S.CONFIRMED, Event.DISPUTE): S.DISPUTED,
    (S.IN_PROGRESS, Event.END): S.COMPLETED,
    # Only an admin cancels a running booking (guarded below).
    (S.IN_PROGRESS, Event.CANCEL): S.CANCELLED,
    (S.IN_PROGRESS, Event.DISPUTE): S.DISPUTED,
    # A damage claim or dispute raised within 48 h after the end (FR-027).
    (S.COMPLETED, Event.DISPUTE): S.DISPUTED,
    (S.DISPUTED, Event.RESOLVE_COMPLETE): S.COMPLETED,
    (S.DISPUTED, Event.RESOLVE_CANCEL): S.CANCELLED,
    # A payment that succeeds after its hold expired revives the booking (R6, edge case).
    (S.CANCELLED, Event.LATE_PAYMENT): S.CONFIRMED,
}

# Who cancelled, when the event itself says so.
_CANCELLED_BY = {
    Event.DECLINE: CancelledBy.OWNER,
    Event.EXPIRE: CancelledBy.SYSTEM,
}


def invalid_transition(status: BookingStatus, event: Event) -> AppError:
    return AppError("INVALID_TRANSITION", 409, {"status": status.value, "event": event.value})


def next_status(status: BookingStatus, event: Event) -> BookingStatus:
    target = TRANSITIONS.get((status, event))
    if target is None:
        raise invalid_transition(status, event)
    return target


def _guard(booking: Booking, event: Event, cancelled_by: CancelledBy | None) -> None:
    if event == Event.LATE_PAYMENT and booking.cancelled_by != CancelledBy.SYSTEM:
        raise invalid_transition(booking.status, event)
    if (
        event == Event.CANCEL
        and booking.status == S.IN_PROGRESS
        and cancelled_by != CancelledBy.ADMIN
    ):
        raise invalid_transition(booking.status, event)


async def record(
    session: AsyncSession,
    booking: Booking,
    from_status: BookingStatus | None,
    *,
    actor_kind: str = ActorKind.SYSTEM,
    actor_user_id: uuid.UUID | None = None,
    note: str | None = None,
) -> None:
    session.add(
        BookingEvent(
            booking_id=booking.id,
            from_status=from_status,
            to_status=booking.status,
            actor_kind=ActorKind(actor_kind),
            actor_user_id=actor_user_id,
            note=note,
        )
    )
    await session.flush()


async def transition(
    session: AsyncSession,
    booking: Booking,
    event: Event,
    *,
    actor_kind: str = ActorKind.SYSTEM,
    actor_user_id: uuid.UUID | None = None,
    cancelled_by: CancelledBy | None = None,
    note: str | None = None,
    notify: bool = True,
) -> None:
    """Move `booking` by `event` (409 `INVALID_TRANSITION` if not allowed)."""
    target = next_status(booking.status, event)
    _guard(booking, event, cancelled_by)
    before = booking.status
    booking.status = target
    if target == S.CANCELLED:
        booking.cancelled_by = cancelled_by or _CANCELLED_BY.get(event, CancelledBy.SYSTEM)
        booking.cancelled_at = clock.now()
    elif event == Event.LATE_PAYMENT:
        booking.cancelled_by = None
        booking.cancel_reason = None
    await record(
        session, booking, before, actor_kind=actor_kind, actor_user_id=actor_user_id, note=note
    )
    if notify:
        from app.bookings.notify import on_status

        await on_status(session, booking, event)


def notification_payload(booking: Booking, **extra: Any) -> dict[str, Any]:
    return {"booking_id": str(booking.id), "code": booking.code, **extra}
