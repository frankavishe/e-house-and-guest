"""Booking notifications (FR-019): who hears about which lifecycle step.

Templates are `notifications.<event>` in `app/i18n/{sw,en}.json`. Payload values are
formatted here (money, EAT times) and the listing title is picked in the recipient's
language; every payload carries `booking_id` so the in-app feed can link to the booking.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User, UserStatus
from app.bookings.models import Booking, BookingStatus, CancelledBy, LeaseInstallment
from app.bookings.state import Event
from app.core.i18n import eat_date, eat_datetime, money
from app.listings.models import Listing
from app.notifications.service import notify


async def _send(
    session: AsyncSession, user_id: uuid.UUID, event: str, booking: Booking, **extra: Any
) -> None:
    user = await session.get(User, user_id)
    listing = await session.get(Listing, booking.listing_id)
    assert user is not None and listing is not None
    payload = {
        "booking_id": str(booking.id),
        "code": booking.code,
        "title": listing.title(user.language),
        **extra,
    }
    await notify(session, user_id, event, payload)


async def owner_user_id(session: AsyncSession, booking: Booking) -> uuid.UUID:
    owner = await session.get(OwnerProfile, booking.owner_profile_id)
    assert owner is not None
    return owner.user_id


async def to_renter(session: AsyncSession, booking: Booking, event: str, **extra: Any) -> None:
    await _send(session, booking.renter_id, event, booking, **extra)


async def to_owner(session: AsyncSession, booking: Booking, event: str, **extra: Any) -> None:
    await _send(session, await owner_user_id(session, booking), event, booking, **extra)


async def to_admins(session: AsyncSession, booking: Booking, event: str, **extra: Any) -> None:
    admins = await session.execute(
        select(User.id).where(User.is_admin.is_(True), User.status == UserStatus.ACTIVE)
    )
    for admin_id in admins.scalars():
        await _send(session, admin_id, event, booking, **extra)


async def _awaiting_payment(session: AsyncSession, booking: Booking) -> None:
    from app.bookings.service import first_payment_amount, installments_of

    amount = first_payment_amount(booking, await installments_of(session, booking.id))
    due = eat_datetime(booking.payment_due_at) if booking.payment_due_at else ""
    await to_renter(session, booking, "booking.awaiting_payment", amount=money(amount), due=due)


async def on_created(session: AsyncSession, booking: Booking) -> None:
    if booking.status == BookingStatus.REQUESTED:
        await to_owner(session, booking, "booking.requested")
    else:
        await _awaiting_payment(session, booking)


async def on_status(session: AsyncSession, booking: Booking, event: Event) -> None:
    match booking.status, event:
        case BookingStatus.AWAITING_PAYMENT, _:
            await _awaiting_payment(session, booking)
        case BookingStatus.CONFIRMED, (Event.PAY | Event.LATE_PAYMENT):
            await to_renter(session, booking, "booking.confirmed")
            await to_owner(session, booking, "booking.confirmed_owner")
        case BookingStatus.CANCELLED, Event.DECLINE:
            await to_renter(session, booking, "booking.declined")
        case BookingStatus.CANCELLED, Event.EXPIRE:
            await to_renter(session, booking, "booking.expired")
        case BookingStatus.CANCELLED, Event.CANCEL:
            match booking.cancelled_by:
                case CancelledBy.RENTER:
                    await to_owner(session, booking, "booking.cancelled_by_renter")
                case CancelledBy.OWNER:
                    await to_renter(session, booking, "booking.cancelled_by_owner")
                case _:
                    await to_renter(session, booking, "booking.cancelled_by_admin")
                    await to_owner(session, booking, "booking.cancelled_by_admin")
        case _:
            pass


async def installment_event(
    session: AsyncSession, booking: Booking, inst: LeaseInstallment, event: str, *, who: str
) -> None:
    extra = {"seq": inst.seq, "amount": money(inst.amount_tzs), "due": eat_date(inst.due_at)}
    match who:
        case "renter":
            await to_renter(session, booking, event, **extra)
        case "owner":
            await to_owner(session, booking, event, **extra)
        case _:
            await to_admins(session, booking, event, **extra)
