"""Renter-owner messaging (T129, US6, FR-028).

A renter starts one conversation per listing; later starts reuse it. Phone numbers in a
message are masked when it is sent unless the renter has a booking of that listing that
reveals phones (confirmed or later, R18), so earlier messages stay masked. Clients poll
`GET /conversations/{id}/messages?after=<seq>` every 10 s while a thread is open; reading
marks the counterpart's messages read.
"""

import re
import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User
from app.bookings.models import Booking
from app.bookings.service import REVEALED
from app.core import clock
from app.core.errors import AppError, not_found
from app.core.i18n import Locale
from app.listings.models import Listing
from app.listings.service import get_public_listing, photos_for, thumbnail_url
from app.messaging.models import Conversation, Message
from app.messaging.schemas import (
    ConversationListing,
    ConversationOut,
    ConversationParty,
    Inbox,
    MessageOut,
)
from app.notifications.models import Channel
from app.notifications.service import notify

PAGE_LIMIT = 100
MASK = "•••"
# Nine or more digits, optionally led by `+` and split by spaces, dots, dashes or brackets:
# `0712 345 678`, `+255712345678`, `255-754-111-222`. Prices and dates stay readable.
PHONE_RE = re.compile(r"\+?\d(?:[\s.\-()]{0,2}\d){8,}")


def mask_phones(body: str) -> tuple[str, bool]:
    masked, count = PHONE_RE.subn(MASK, body)
    return masked, count > 0


async def _owner_profile_id(session: AsyncSession, user: User) -> uuid.UUID | None:
    row = await session.execute(select(OwnerProfile.id).where(OwnerProfile.user_id == user.id))
    return row.scalar_one_or_none()


def _role(conv: Conversation, user: User, owner_profile_id: uuid.UUID | None) -> str | None:
    if conv.renter_id == user.id:
        return "renter"
    if owner_profile_id is not None and conv.owner_profile_id == owner_profile_id:
        return "owner"
    return None


async def get_for_participant(
    session: AsyncSession, user: User, conversation_id: uuid.UUID
) -> tuple[Conversation, str]:
    """The conversation and the viewer's side; 404 for anyone else."""
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise not_found("conversation")
    role = _role(conv, user, await _owner_profile_id(session, user))
    if role is None:
        raise not_found("conversation")
    return conv, role


async def _revealing_booking(session: AsyncSession, conv: Conversation) -> uuid.UUID | None:
    row = await session.execute(
        select(Booking.id)
        .where(
            Booking.listing_id == conv.listing_id,
            Booking.renter_id == conv.renter_id,
            Booking.status.in_(REVEALED),
        )
        .order_by(Booking.created_at.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def _unread(
    session: AsyncSession, user: User, conversation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not conversation_ids:
        return {}
    rows = await session.execute(
        select(Message.conversation_id, func.count())
        .where(
            Message.conversation_id.in_(conversation_ids),
            Message.sender_id != user.id,
            Message.read_at.is_(None),
        )
        .group_by(Message.conversation_id)
    )
    return {conv_id: n for conv_id, n in rows.all()}


async def _last_bodies(
    session: AsyncSession, conversation_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not conversation_ids:
        return {}
    rows = await session.execute(
        select(Message.conversation_id, Message.body)
        .where(Message.conversation_id.in_(conversation_ids))
        .distinct(Message.conversation_id)
        .order_by(Message.conversation_id, Message.seq.desc())
    )
    return {conv_id: body for conv_id, body in rows.all()}


async def _outs(
    session: AsyncSession, user: User, convs: Sequence[Conversation], locale: Locale
) -> list[ConversationOut]:
    ids = [c.id for c in convs]
    listing_ids = list({c.listing_id for c in convs})
    listings = {
        listing.id: listing
        for listing in (
            await session.execute(select(Listing).where(Listing.id.in_(listing_ids)))
        ).scalars()
    }
    photos = await photos_for(session, listing_ids)
    owners = {
        o.id: o
        for o in (
            await session.execute(
                select(OwnerProfile).where(OwnerProfile.id.in_({c.owner_profile_id for c in convs}))
            )
        ).scalars()
    }
    renters = {
        u.id: u
        for u in (
            await session.execute(select(User).where(User.id.in_({c.renter_id for c in convs})))
        ).scalars()
    }
    unread = await _unread(session, user, ids)
    last = await _last_bodies(session, ids)
    out = []
    for conv in convs:
        listing = listings[conv.listing_id]
        is_renter = conv.renter_id == user.id
        counterpart = (
            owners[conv.owner_profile_id].display_name
            if is_renter
            else renters[conv.renter_id].name or ""
        )
        cover = photos[listing.id]
        out.append(
            ConversationOut(
                id=conv.id,
                listing=ConversationListing(
                    id=listing.id,
                    title=listing.title(locale),
                    photo_url=thumbnail_url(cover[0]) if cover else None,
                ),
                role="renter" if is_renter else "owner",
                counterpart=ConversationParty(name=counterpart),
                booking_id=conv.booking_id,
                last_message=last.get(conv.id),
                last_message_at=conv.last_message_at,
                unread_count=unread.get(conv.id, 0),
            )
        )
    return out


async def conversation_out(
    session: AsyncSession, user: User, conv: Conversation, locale: Locale
) -> ConversationOut:
    return (await _outs(session, user, [conv], locale))[0]


async def inbox(
    session: AsyncSession, user: User, locale: Locale, page: int, page_size: int
) -> Inbox:
    """The viewer's conversations as renter and as owner, most recent first."""
    owner_profile_id = await _owner_profile_id(session, user)
    sides = [Conversation.renter_id == user.id]
    if owner_profile_id is not None:
        sides.append(Conversation.owner_profile_id == owner_profile_id)
    mine = or_(*sides)
    total = (
        await session.execute(select(func.count()).select_from(Conversation).where(mine))
    ).scalar_one()
    rows = await session.execute(
        select(Conversation)
        .where(mine)
        .order_by(Conversation.last_message_at.desc().nulls_last(), Conversation.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    unread_total = (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(mine, Message.sender_id != user.id, Message.read_at.is_(None))
        )
    ).scalar_one()
    return Inbox(
        items=await _outs(session, user, list(rows.scalars()), locale),
        page=page,
        page_size=page_size,
        total=total,
        unread_total=unread_total,
    )


async def _post(
    session: AsyncSession, user: User, conv: Conversation, role: str, body: str
) -> Message:
    booking_id = await _revealing_booking(session, conv)
    conv.booking_id = booking_id
    masked = False
    if booking_id is None:
        body, masked = mask_phones(body)
    recipient_id = conv.renter_id
    if role == "renter":
        owner = await session.get(OwnerProfile, conv.owner_profile_id)
        assert owner is not None
        recipient_id = owner.user_id
    already_unread = (
        await session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.sender_id != recipient_id,
                Message.read_at.is_(None),
            )
        )
    ).scalar_one()
    message = Message(conversation_id=conv.id, sender_id=user.id, body=body, body_masked=masked)
    session.add(message)
    conv.last_message_at = clock.now()
    await session.flush()
    if not already_unread:
        # One in-app nudge per batch of unread messages, not one per message.
        recipient = await session.get(User, recipient_id)
        listing = await session.get(Listing, conv.listing_id)
        assert recipient is not None and listing is not None
        sender_name = user.name or ""
        if role == "owner":
            owner = await session.get(OwnerProfile, conv.owner_profile_id)
            assert owner is not None
            sender_name = owner.display_name
        await notify(
            session,
            recipient_id,
            "message.received",
            {
                "conversation_id": str(conv.id),
                "name": sender_name,
                "title": listing.title(recipient.language),
            },
            channels=(Channel.IN_APP,),
        )
    return message


async def start(
    session: AsyncSession, user: User, listing_id: uuid.UUID, body: str
) -> tuple[Conversation, bool]:
    """The renter's conversation about a public listing (created if new) with `body` added.
    Returns whether it was created."""
    listing, _ = await get_public_listing(session, listing_id)
    owner = await session.get(OwnerProfile, listing.owner_profile_id)
    assert owner is not None
    if owner.user_id == user.id:
        raise AppError("OWN_LISTING", 422)
    conv = (
        await session.execute(
            select(Conversation)
            .where(Conversation.listing_id == listing.id, Conversation.renter_id == user.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    created = conv is None
    if conv is None:
        conv = Conversation(listing_id=listing.id, renter_id=user.id, owner_profile_id=owner.id)
        session.add(conv)
        await session.flush()
    await _post(session, user, conv, "renter", body)
    return conv, created


async def send(session: AsyncSession, user: User, conversation_id: uuid.UUID, body: str) -> Message:
    conv, role = await get_for_participant(session, user, conversation_id)
    return await _post(session, user, conv, role, body)


def message_out(message: Message, user: User) -> MessageOut:
    return MessageOut(
        id=message.id,
        seq=message.seq,
        mine=message.sender_id == user.id,
        body=message.body,
        masked=message.body_masked,
        read_at=message.read_at,
        created_at=message.created_at,
    )


async def messages(
    session: AsyncSession, user: User, conversation_id: uuid.UUID, after: int | None
) -> list[MessageOut]:
    """Up to 100 messages oldest first: those after `after`, else the latest ones. Marks the
    counterpart's messages read."""
    conv, _ = await get_for_participant(session, user, conversation_id)
    query = select(Message).where(Message.conversation_id == conv.id)
    if after is not None:
        query = query.where(Message.seq > after).order_by(Message.seq).limit(PAGE_LIMIT)
        rows = list((await session.execute(query)).scalars())
    else:
        query = query.order_by(Message.seq.desc()).limit(PAGE_LIMIT)
        rows = list(reversed((await session.execute(query)).scalars().all()))
    now = clock.now()
    for m in rows:
        if m.sender_id != user.id and m.read_at is None:
            m.read_at = now
    await session.flush()
    return [message_out(m, user) for m in rows]
