"""Owner calendar (US3-AS3): owner blocks on top of bookings, through the same reservation
path as bookings, so a block can never overlap a booking (or exceed the stock)."""

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import Select, delete, func, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User
from app.availability import service as availability
from app.availability.models import AvailabilityBlock, BlockSource
from app.availability.periods import Period
from app.bookings.models import Booking, BookingStatus
from app.catalog.models import BookingMode, Category
from app.core import clock
from app.core.errors import AppError, not_found
from app.core.i18n import Locale
from app.listings import manage
from app.listings.models import Listing, ListingStatus
from app.listings.owner_schemas import (
    BlockIn,
    BlockOut,
    Calendar,
    CalendarBooking,
    CalendarListing,
    SpanOut,
)

MAX_BLOCK_DAYS = 366
MAX_CALENDAR_DAYS = 366
CALENDAR_STATUSES = (
    BookingStatus.REQUESTED,
    BookingStatus.AWAITING_PAYMENT,
    BookingStatus.CONFIRMED,
    BookingStatus.IN_PROGRESS,
    BookingStatus.COMPLETED,
)


def _invalid(reason: str) -> AppError:
    return AppError("INVALID_PERIOD", 422, {"reason": reason})


def block_period(category: Category, body: BlockIn) -> Period:
    """The blocked span: whole EAT days for day-based modes, exact times for slots."""
    mode = category.booking_mode
    assert mode is not None
    quantity = body.quantity if mode == BookingMode.QUANTITY else 1
    if mode == BookingMode.TIME_SLOT:
        if body.start is None or body.end is None:
            raise _invalid("start_end_required")
        if body.start.tzinfo is None or body.end.tzinfo is None:
            raise _invalid("timezone_required")
        start, end = body.start, body.end
        if end <= start:
            raise _invalid("end_before_start")
        if end <= clock.now():
            raise _invalid("in_past")
        return Period(mode, start, end, "hour", 0, quantity)
    if body.start_date is None or body.end_date is None:
        raise _invalid("dates_required")
    first, last = body.start_date, body.end_date
    if last < first:
        raise _invalid("end_before_start")
    if last < clock.today_eat():
        raise _invalid("in_past")
    if (last - first).days >= MAX_BLOCK_DAYS:
        raise _invalid("too_long")
    days = tuple(first + timedelta(days=i) for i in range((last - first).days + 1))
    return Period(
        mode,
        clock.to_eat_midnight(first),
        clock.to_eat_midnight(last + timedelta(days=1)),
        "day",
        len(days),
        quantity,
        days,
    )


def block_out(block: AvailabilityBlock) -> BlockOut:
    assert block.period.lower is not None and block.period.upper is not None
    return BlockOut(
        id=block.id,
        listing_id=block.listing_id,
        period=SpanOut(start=block.period.lower, end=block.period.upper),
        quantity=block.quantity,
        note=block.note,
    )


async def add_block(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID, body: BlockIn
) -> AvailabilityBlock:
    listing, category = await manage.get_owned(session, profile, listing_id)
    assert category.booking_mode is not None
    period = block_period(category, body)
    if category.booking_mode == BookingMode.QUANTITY and period.quantity > listing.stock:
        raise AppError("INSUFFICIENT_STOCK", 409, {"available": listing.stock})
    return await availability.reserve(
        session, listing, category.booking_mode, period, None, note=body.note
    )


def _owner_blocks(listing_ids: Select[uuid.UUID]) -> Select[AvailabilityBlock]:
    return select(AvailabilityBlock).where(
        AvailabilityBlock.listing_id.in_(listing_ids),
        AvailabilityBlock.source == BlockSource.OWNER_BLOCK,
        AvailabilityBlock.active,
    )


async def list_blocks(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID
) -> list[AvailabilityBlock]:
    listing, _ = await manage.get_owned(session, profile, listing_id)
    rows = await session.execute(
        _owner_blocks(select(Listing.id).where(Listing.id == listing.id))
        .where(func.upper(AvailabilityBlock.period) > clock.now())
        .order_by(func.lower(AvailabilityBlock.period))
    )
    return list(rows.scalars())


async def remove_block(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID, block_id: uuid.UUID
) -> None:
    listing, _ = await manage.get_owned(session, profile, listing_id)
    result = await session.execute(
        delete(AvailabilityBlock).where(
            AvailabilityBlock.id == block_id,
            AvailabilityBlock.listing_id == listing.id,
            AvailabilityBlock.source == BlockSource.OWNER_BLOCK,
        )
    )
    if not getattr(result, "rowcount", 0):
        raise not_found("block")


async def calendar(
    session: AsyncSession, profile: OwnerProfile, first: date, last: date, locale: Locale
) -> Calendar:
    """Bookings and blocks overlapping the EAT days `first..last` across own listings."""
    if last < first or (last - first).days >= MAX_CALENDAR_DAYS:
        raise _invalid("range")
    span = Range(
        clock.to_eat_midnight(first), clock.to_eat_midnight(last + timedelta(days=1)), bounds="[)"
    )
    own = select(Listing.id).where(
        Listing.owner_profile_id == profile.id, Listing.status != ListingStatus.DELETED
    )
    listings = (
        await session.execute(
            select(Listing).where(Listing.id.in_(own)).order_by(Listing.created_at)
        )
    ).scalars()
    bookings = await session.execute(
        select(Booking, User.name)
        .join(User, User.id == Booking.renter_id)
        .where(
            Booking.owner_profile_id == profile.id,
            Booking.status.in_(CALENDAR_STATUSES),
            Booking.period.op("&&")(span),
        )
        .order_by(func.lower(Booking.period))
    )
    blocks = await session.execute(
        _owner_blocks(own)
        .where(AvailabilityBlock.period.op("&&")(span))
        .order_by(func.lower(AvailabilityBlock.period))
    )
    return Calendar(
        listings=[CalendarListing(id=row.id, title=row.title(locale)) for row in listings],
        bookings=[
            CalendarBooking(
                id=b.id,
                code=b.code,
                listing_id=b.listing_id,
                status=b.status.value,
                period=_span(b.period),
                quantity=b.quantity,
                renter_name=name or "",
            )
            for b, name in bookings.all()
        ],
        blocks=[block_out(block) for block in blocks.scalars()],
    )


def _span(period: Range[datetime]) -> SpanOut:
    assert period.lower is not None and period.upper is not None
    return SpanOut(start=period.lower, end=period.upper)
