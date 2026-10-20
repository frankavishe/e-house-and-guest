"""Availability reads (R1). The SQL clauses here are shared with search, so a listing shown
as available is checked by exactly the rule bookings will use.

Reservation writes (`reserve`, `release`) run inside the booking transaction: exclusive modes
rely on the exclusion constraint, stock on a listing row lock (Principle IV)."""

import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import DateTime, Exists, Interval, and_, exists, func, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.availability.models import AvailabilityBlock, BlockKind, BlockSource
from app.availability.periods import Period
from app.availability.schemas import DateSpan, DaySlots, DayStock, Slot
from app.catalog.models import BookingMode
from app.core import clock
from app.core.errors import AppError
from app.listings.models import Listing

TZ = DateTime(timezone=True)
ONE_DAY = timedelta(days=1)
DEFAULT_SLOT_CONFIG: dict[str, Any] = {
    "open": "08:00",
    "close": "22:00",
    "slot_minutes": 60,
    "days": [1, 2, 3, 4, 5, 6, 7],
}


def block_kind(mode: BookingMode) -> BlockKind:
    return BlockKind.STOCK if mode == BookingMode.QUANTITY else BlockKind.EXCLUSIVE


def _range(start: Any, end: Any) -> ColumnElement[Any]:
    return func.tstzrange(start, end, literal("[)"))


def exclusive_conflict(listing_id: Any, start: datetime, end: datetime) -> Exists:
    """An active exclusive block overlaps `[start, end)`."""
    b = aliased(AvailabilityBlock)
    return exists().where(
        b.listing_id == listing_id,
        b.active.is_(True),
        b.kind == BlockKind.EXCLUSIVE,
        b.period.op("&&")(_range(literal(start, TZ), literal(end, TZ))),
    )


def stock_shortfall(
    listing_id: Any, stock: Any, start: datetime, end: datetime, quantity: int
) -> Exists:
    """Some day in `[start, end)` has fewer than `quantity` units left."""
    b = aliased(AvailabilityBlock)
    day = func.generate_series(
        literal(start, TZ), literal(end - ONE_DAY, TZ), literal(ONE_DAY, Interval()), type_=TZ
    ).column_valued("day")
    used = (
        select(func.coalesce(func.sum(b.quantity), 0))
        .where(
            b.listing_id == listing_id,
            b.active.is_(True),
            b.kind == BlockKind.STOCK,
            b.period.op("&&")(_range(day, day + literal(ONE_DAY, Interval()))),
        )
        .scalar_subquery()
    )
    return exists(select(day).where(used + quantity > stock))


def conflict(mode: BookingMode, listing_id: Any, stock: Any, period: Period) -> Exists:
    if mode == BookingMode.QUANTITY:
        return stock_shortfall(listing_id, stock, period.start, period.end, period.quantity)
    return exclusive_conflict(listing_id, period.start, period.end)


async def is_available(
    session: AsyncSession, listing: Listing, mode: BookingMode, period: Period
) -> bool:
    clash = conflict(mode, literal(listing.id), literal(listing.stock), period)
    return not (await session.execute(select(clash))).scalar_one()


async def _blocks(
    session: AsyncSession, listing_id: uuid.UUID, kind: BlockKind, start: datetime, end: datetime
) -> Sequence[AvailabilityBlock]:
    rows = await session.execute(
        select(AvailabilityBlock)
        .where(
            AvailabilityBlock.listing_id == listing_id,
            AvailabilityBlock.active.is_(True),
            AvailabilityBlock.kind == kind,
            AvailabilityBlock.period.op("&&")(_range(literal(start, TZ), literal(end, TZ))),
        )
        .order_by(func.lower(AvailabilityBlock.period))
    )
    return rows.scalars().all()


def _bounds(block: AvailabilityBlock) -> tuple[datetime, datetime]:
    lower, upper = block.period.lower, block.period.upper
    assert lower is not None and upper is not None
    return lower, upper


async def available_quantity_by_day(
    session: AsyncSession, listing: Listing, first: date, last: date
) -> list[DayStock]:
    """Units left per EAT day, `first`..`last` inclusive (QUANTITY)."""
    blocks = await _blocks(
        session,
        listing.id,
        BlockKind.STOCK,
        clock.to_eat_midnight(first),
        clock.to_eat_midnight(last + ONE_DAY),
    )
    out = []
    day = first
    while day <= last:
        start, end = clock.to_eat_midnight(day), clock.to_eat_midnight(day + ONE_DAY)
        used = 0
        for b in blocks:
            lower, upper = _bounds(b)
            if lower < end and start < upper:
                used += b.quantity
        out.append(DayStock(date=day, available=max(listing.stock - used, 0)))
        day += ONE_DAY
    return out


async def min_available(session: AsyncSession, listing: Listing, period: Period) -> int:
    """The smallest number of units left on any day of `period` (for INSUFFICIENT_STOCK)."""
    days = await available_quantity_by_day(session, listing, period.days[0], period.days[-1])
    return min(d.available for d in days)


def _eat_day_after(value: datetime) -> date:
    """The first EAT day fully after `value` (ceil to midnight)."""
    local = clock.to_eat(value)
    return local.date() if local.time() == time.min else local.date() + ONE_DAY


async def unavailable_ranges(
    session: AsyncSession, listing: Listing, from_day: date, to_day: date
) -> list[DateSpan]:
    """Merged unavailable EAT days `[start_date, end_date)` overlapping the window."""
    blocks = await _blocks(
        session,
        listing.id,
        BlockKind.EXCLUSIVE,
        clock.to_eat_midnight(from_day),
        clock.to_eat_midnight(to_day + ONE_DAY),
    )
    spans: list[DateSpan] = []
    for b in blocks:
        lower, upper = _bounds(b)
        start, end = clock.to_eat(lower).date(), _eat_day_after(upper)
        if spans and start <= spans[-1].end_date:
            spans[-1].end_date = max(spans[-1].end_date, end)
        else:
            spans.append(DateSpan(start_date=start, end_date=end))
    return spans


def _clock_time(value: str) -> timedelta:
    hours, minutes = (int(part) for part in value.split(":"))
    return timedelta(hours=hours, minutes=minutes)


async def free_slots(
    session: AsyncSession, listing: Listing, from_day: date, to_day: date
) -> list[DaySlots]:
    """Bookable slots per open EAT day from `slot_config` (TIME_SLOT). A closing time at or
    before the opening time means the day's slots run past midnight."""
    config = {**DEFAULT_SLOT_CONFIG, **(listing.slot_config or {})}
    step = timedelta(minutes=int(config["slot_minutes"]))
    opens, closes = _clock_time(config["open"]), _clock_time(config["close"])
    if closes <= opens:
        closes += ONE_DAY
    open_days = {int(d) for d in config["days"]}

    window_start = clock.to_eat_midnight(from_day) + opens
    window_end = clock.to_eat_midnight(to_day) + closes
    busy = [
        _bounds(b)
        for b in await _blocks(session, listing.id, BlockKind.EXCLUSIVE, window_start, window_end)
    ]
    now = clock.now()

    out: list[DaySlots] = []
    day = from_day
    while day <= to_day:
        if day.isoweekday() in open_days:
            midnight = clock.to_eat_midnight(day)
            slots = []
            start, close = midnight + opens, midnight + closes
            while start + step <= close:
                end = start + step
                if start >= now and not any(lo < end and start < hi for lo, hi in busy):
                    slots.append(Slot(start=start, end=end))
                start = end
            out.append(DaySlots(date=day, slots=slots))
        day += ONE_DAY
    return out


def availability_filter(mode: BookingMode, period: Period) -> ColumnElement[bool]:
    """Search: the listing (outer `Listing` row) is free for `period`."""
    return and_(~conflict(mode, Listing.id, Listing.stock, period))


# --- reservation (US2) --------------------------------------------------------------------

EXCLUSION_VIOLATION = "23P01"


def _sqlstate(exc: IntegrityError) -> str | None:
    orig = exc.orig
    return getattr(orig, "sqlstate", None) or getattr(orig.__cause__, "sqlstate", None)


async def unavailable_error(
    session: AsyncSession, listing: Listing, mode: BookingMode, period: Period
) -> AppError:
    if mode == BookingMode.QUANTITY:
        return AppError(
            "INSUFFICIENT_STOCK", 409, {"available": await min_available(session, listing, period)}
        )
    return AppError("SLOT_TAKEN", 409)


async def lock_listing(session: AsyncSession, listing_id: uuid.UUID) -> None:
    """Serialise stock bookings of one listing. Take it before inserting the booking: the
    booking's foreign key share-locks the listing row, and upgrading that lock later lets
    two racing bookings deadlock."""
    await session.execute(select(Listing.id).where(Listing.id == listing_id).with_for_update())


async def reserve(
    session: AsyncSession,
    listing: Listing,
    mode: BookingMode,
    period: Period,
    booking_id: uuid.UUID,
) -> AvailabilityBlock:
    """Hold `period` for a booking, or raise SLOT_TAKEN / INSUFFICIENT_STOCK (409).

    Exclusive modes insert under the exclusion constraint, so of two racing inserts the
    second fails in the database. Stock locks the listing row first (`FOR UPDATE`), which
    serialises bookings of one item, then checks every day before inserting.
    """
    block = AvailabilityBlock(
        listing_id=listing.id,
        period=period.range,
        quantity=period.quantity,
        kind=block_kind(mode),
        source=BlockSource.BOOKING,
        booking_id=booking_id,
        active=True,
    )
    if mode == BookingMode.QUANTITY:
        await lock_listing(session, listing.id)
        if not await is_available(session, listing, mode, period):
            raise await unavailable_error(session, listing, mode, period)
        session.add(block)
        await session.flush()
        return block
    try:
        async with session.begin_nested():
            session.add(block)
            await session.flush()
    except IntegrityError as exc:
        if _sqlstate(exc) == EXCLUSION_VIOLATION:
            raise AppError("SLOT_TAKEN", 409) from exc
        raise
    return block


async def release(session: AsyncSession, booking_id: uuid.UUID) -> None:
    """Free a booking's hold (cancelled, declined or expired)."""
    await session.execute(
        update(AvailabilityBlock)
        .where(AvailabilityBlock.booking_id == booking_id, AvailabilityBlock.active.is_(True))
        .values(active=False, updated_at=clock.now())
        .execution_options(synchronize_session="fetch")
    )
