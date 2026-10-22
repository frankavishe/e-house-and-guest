"""Account deletion (T141, FR-033, R18).

`DELETE /me` refuses while the user still has bookings in progress, or (as an owner) payouts
on their way. Otherwise, in one transaction, it:

- marks the user `deleted` and tombstones the identity: name "Deleted user", the phone
  replaced by a hash (frees the number for a fresh sign-up and stops OTP sign-in at once),
  email null;
- drops their refresh tokens and OTP codes; access tokens of a deleted user are refused (core.deps);
- schedules the `accounts.anonymise` job for the slower part.

The job deletes the verification files and identity numbers, payout methods, conversations
the user took part in (with every message in them) and notifications, and takes
their listings off the marketplace. Bookings, payments, ledger rows, payouts and reviews are
kept for financial and legal retention; they now point at the anonymised user.
"""

import hashlib
import logging
import uuid
from typing import Any

from sqlalchemy import delete, exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OtpCode, OwnerProfile, PayoutMethod, RefreshToken, User, UserStatus
from app.bookings.models import Booking, BookingStatus
from app.core.errors import AppError
from app.integrations import get_storage
from app.jobs.registry import handler
from app.jobs.service import enqueue
from app.listings.models import Listing, ListingStatus
from app.messaging.models import Conversation
from app.notifications.models import Notification
from app.payouts.models import Payout, PayoutStatus

log = logging.getLogger(__name__)

ANONYMISE_JOB = "accounts.anonymise"
DELETED_NAME = "Deleted user"
ACTIVE_BOOKING = (
    BookingStatus.REQUESTED,
    BookingStatus.AWAITING_PAYMENT,
    BookingStatus.CONFIRMED,
    BookingStatus.IN_PROGRESS,
    BookingStatus.DISPUTED,
)
OPEN_PAYOUT = (PayoutStatus.PENDING, PayoutStatus.PROCESSING)


def tombstone(phone: str) -> str:
    """Unique and not a dialable number, so the original can sign up again."""
    return "deleted:" + hashlib.sha256(phone.encode()).hexdigest()[:32]


async def _owner(session: AsyncSession, user_id: uuid.UUID) -> OwnerProfile | None:
    return (
        await session.execute(select(OwnerProfile).where(OwnerProfile.user_id == user_id))
    ).scalar_one_or_none()


async def request_deletion(session: AsyncSession, user: User) -> None:
    owner = await _owner(session, user.id)
    parties = [Booking.renter_id == user.id]
    if owner is not None:
        parties.append(Booking.owner_profile_id == owner.id)
    active = await session.scalar(
        select(exists().where(or_(*parties), Booking.status.in_(ACTIVE_BOOKING)))
    )
    if active:
        raise AppError("ACTIVE_BOOKINGS", 409)
    if owner is not None and await session.scalar(
        select(exists().where(Payout.owner_profile_id == owner.id, Payout.status.in_(OPEN_PAYOUT)))
    ):
        raise AppError("PAYOUT_IN_PROGRESS", 409)

    await session.execute(delete(OtpCode).where(OtpCode.phone == user.phone))
    user.status = UserStatus.DELETED
    user.name = DELETED_NAME
    user.phone = tombstone(user.phone)
    user.email = None
    await session.execute(delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await enqueue(
        session, ANONYMISE_JOB, {"user_id": str(user.id)}, dedupe_key=f"anonymise:{user.id}"
    )
    await session.commit()


@handler(ANONYMISE_JOB)
async def anonymise(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Idempotent: a re-run after a crash finds nothing left to delete."""
    user = await session.get(User, uuid.UUID(payload["user_id"]))
    if user is None or user.status != UserStatus.DELETED:
        return
    owner = await _owner(session, user.id)
    conversations = [Conversation.renter_id == user.id]

    if owner is not None:
        storage = get_storage()
        for key in owner.documents:
            await storage.delete(key, private=True)
        owner.documents = []
        owner.nida_number_enc = None
        owner.tin_enc = None
        owner.brela_reg_no = None
        owner.display_name = DELETED_NAME
        await session.execute(delete(PayoutMethod).where(PayoutMethod.owner_profile_id == owner.id))
        await session.execute(
            update(Listing)
            .where(Listing.owner_profile_id == owner.id, Listing.status != ListingStatus.DELETED)
            .values(status=ListingStatus.DELETED)
        )
        conversations.append(Conversation.owner_profile_id == owner.id)

    # Messages cascade with their conversation.
    await session.execute(delete(Conversation).where(or_(*conversations)))
    await session.execute(delete(Notification).where(Notification.user_id == user.id))
    log.info("account %s anonymised", user.id)
