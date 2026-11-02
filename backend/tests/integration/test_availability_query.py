"""Availability reads (T051, R1, R2): overlaps, owner blocks, stock per day, slots."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import service
from app.availability.periods import Period, PeriodParams, normalize
from app.catalog.models import BookingMode
from app.core.clock import EAT, to_eat_midnight
from app.listings.models import Listing
from tests.factories import (
    day_range,
    make_block,
    make_category,
    make_listing,
    make_owner,
    make_place,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # today = 2026-11-02 EAT

D = date(2026, 11, 10)


async def _listing(db: AsyncSession, mode: str, unit: str, **fields: object) -> Listing:
    category = await make_category(db, mode=mode, default_unit=unit)
    region, district = await make_place(db)
    owner = await make_owner(db)
    return await make_listing(
        db, owner=owner, category=category, region=region, district=district, **fields
    )


def nights(start: date, end: date) -> Period:
    return normalize(BookingMode.DATE_RANGE, "night", PeriodParams(start_date=start, end_date=end))


async def test_exclusive_overlap_is_half_open(db: AsyncSession) -> None:
    room = await _listing(db, "DATE_RANGE", "night")
    await make_block(db, room, *day_range(D, D + timedelta(days=3)))

    mode = BookingMode.DATE_RANGE
    assert not await service.is_available(db, room, mode, nights(D, D + timedelta(days=1)))
    assert not await service.is_available(
        db, room, mode, nights(D - timedelta(days=1), D + timedelta(days=1))
    )
    # Check-out day is free: a stay starting on it does not overlap.
    assert await service.is_available(
        db, room, mode, nights(D + timedelta(days=3), D + timedelta(days=5))
    )
    assert await service.is_available(db, room, mode, nights(D - timedelta(days=2), D))


async def test_owner_blocks_and_inactive_blocks(db: AsyncSession) -> None:
    room = await _listing(db, "DATE_RANGE", "night")
    other = await _listing(db, "DATE_RANGE", "night")
    await make_block(db, room, *day_range(D, D + timedelta(days=1)))  # owner block
    await make_block(
        db, room, *day_range(D + timedelta(days=5), D + timedelta(days=6)), active=False
    )
    mode = BookingMode.DATE_RANGE
    assert not await service.is_available(db, room, mode, nights(D, D + timedelta(days=1)))
    assert await service.is_available(
        db, room, mode, nights(D + timedelta(days=5), D + timedelta(days=6))
    )
    assert await service.is_available(db, other, mode, nights(D, D + timedelta(days=1)))


async def test_unavailable_ranges_are_merged_dates(db: AsyncSession) -> None:
    room = await _listing(db, "DATE_RANGE", "night")
    await make_block(db, room, *day_range(D, D + timedelta(days=2)))
    await make_block(db, room, *day_range(D + timedelta(days=2), D + timedelta(days=4)))
    await make_block(db, room, *day_range(D + timedelta(days=10), D + timedelta(days=11)))
    await make_block(
        db, room, *day_range(D + timedelta(days=20), D + timedelta(days=21)), active=False
    )

    spans = await service.unavailable_ranges(
        db, room, D - timedelta(days=5), D + timedelta(days=30)
    )
    assert [(s.start_date, s.end_date) for s in spans] == [
        (D, D + timedelta(days=4)),
        (D + timedelta(days=10), D + timedelta(days=11)),
    ]


async def test_stock_remaining_per_day(db: AsyncSession) -> None:
    tents = await _listing(db, "QUANTITY", "item_day", stock=10)
    await make_block(db, tents, *day_range(D, D + timedelta(days=2)), kind="stock", quantity=4)
    await make_block(
        db,
        tents,
        *day_range(D + timedelta(days=1), D + timedelta(days=3)),
        kind="stock",
        quantity=3,
    )
    await make_block(
        db, tents, *day_range(D, D + timedelta(days=3)), kind="stock", quantity=5, active=False
    )

    by_day = await service.available_quantity_by_day(db, tents, D, D + timedelta(days=3))
    assert [(d.date, d.available) for d in by_day] == [
        (D, 6),
        (D + timedelta(days=1), 3),
        (D + timedelta(days=2), 7),
        (D + timedelta(days=3), 10),
    ]

    def qty(n: int) -> Period:
        return normalize(
            BookingMode.QUANTITY,
            "item_day",
            PeriodParams(start_date=D, end_date=D + timedelta(days=1), quantity=n),
        )

    assert await service.is_available(db, tents, BookingMode.QUANTITY, qty(3))
    assert not await service.is_available(db, tents, BookingMode.QUANTITY, qty(4))
    assert await service.min_available(db, tents, qty(1)) == 3


async def test_free_slots_cross_midnight_in_eat(db: AsyncSession) -> None:
    hall = await _listing(
        db,
        "TIME_SLOT",
        "hour",
        slot_config={"open": "20:00", "close": "02:00", "slot_minutes": 120, "days": [2]},
    )
    # D (2026-11-10) is a Tuesday (ISO 2). Book 22:00-00:00.
    start = datetime(2026, 11, 10, 22, tzinfo=EAT)
    await make_block(db, hall, start, start + timedelta(hours=2))

    days = await service.free_slots(db, hall, D, D + timedelta(days=1))
    assert [d.date for d in days] == [D]  # Wednesday is closed
    slots = [(s.start.astimezone(EAT).hour, s.end.astimezone(EAT).hour) for s in days[0].slots]
    assert slots == [(20, 22), (0, 2)]
    assert days[0].slots[-1].end == to_eat_midnight(D + timedelta(days=1)) + timedelta(hours=2)


async def test_slot_availability_check(db: AsyncSession) -> None:
    hall = await _listing(db, "TIME_SLOT", "hour")
    start = datetime(2026, 11, 10, 23, tzinfo=EAT)
    await make_block(db, hall, start, start + timedelta(hours=2))

    def slot(h0: datetime, hours: int) -> Period:
        return normalize(
            BookingMode.TIME_SLOT, "hour", PeriodParams(start=h0, end=h0 + timedelta(hours=hours))
        )

    mode = BookingMode.TIME_SLOT
    assert not await service.is_available(db, hall, mode, slot(start + timedelta(hours=1), 1))
    assert await service.is_available(db, hall, mode, slot(start + timedelta(hours=2), 1))
    assert await service.is_available(db, hall, mode, slot(start - timedelta(hours=2), 2))


def test_block_kind_follows_mode() -> None:
    assert service.block_kind(BookingMode.QUANTITY).value == "stock"
    for mode in (BookingMode.DATE_RANGE, BookingMode.TIME_SLOT, BookingMode.LEASE):
        assert service.block_kind(mode).value == "exclusive"
