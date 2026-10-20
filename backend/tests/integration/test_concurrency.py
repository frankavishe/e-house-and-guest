"""Double booking is impossible (T066, SC-003, Principle IV, R1).

Each test commits a bookable listing, then fires 20 booking attempts on independent
connections at once. Exactly the allowed number succeed; the others get SLOT_TAKEN or
INSUFFICIENT_STOCK. `committed_sessions` truncates every table afterwards.
"""

import asyncio
from collections import Counter
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.availability.models import AvailabilityBlock
from app.bookings.schemas import BookingCreate
from app.bookings.service import create_booking
from app.core.errors import AppError
from tests.factories import Bookable, day_range, make_block, make_bookable, period_json

pytestmark = pytest.mark.usefixtures("frozen_clock")  # today = 2026-11-02 EAT

D = date(2026, 11, 10)
N = 20


async def _setup(
    sessions: async_sessionmaker[AsyncSession], mode: str, **fields: object
) -> Bookable:
    async with sessions() as s:
        b = await make_bookable(s, mode, **fields)
        if mode == "QUANTITY":
            await make_block(s, b.listing, *day_range(D, date(2026, 11, 13)), kind="stock",
                             quantity=7)
        await s.commit()
    return b


async def _race(
    sessions: async_sessionmaker[AsyncSession], b: Bookable, mode: str, quantity: int = 1
) -> Counter[str]:
    body = BookingCreate.model_validate(
        {"listing_id": str(b.listing.id), "period": period_json(mode, D, quantity=quantity)}
    )
    start = asyncio.Event()

    async def attempt() -> str:
        async with sessions() as s:
            await start.wait()
            try:
                await create_booking(s, b.renter, body)
                await s.commit()
                return "ok"
            except AppError as exc:
                await s.rollback()
                return exc.code

    tasks = [asyncio.create_task(attempt()) for _ in range(N)]
    await asyncio.sleep(0)
    start.set()
    return Counter(await asyncio.gather(*tasks))


async def _active_blocks(sessions: async_sessionmaker[AsyncSession], b: Bookable) -> int:
    async with sessions() as s:
        return (
            await s.execute(
                select(func.coalesce(func.sum(AvailabilityBlock.quantity), 0)).where(
                    AvailabilityBlock.listing_id == b.listing.id,
                    AvailabilityBlock.active.is_(True),
                    AvailabilityBlock.booking_id.is_not(None),
                )
            )
        ).scalar_one()


@pytest.mark.parametrize("mode", ["DATE_RANGE", "TIME_SLOT", "LEASE"])
async def test_exclusive_modes_book_once(
    committed_sessions: async_sessionmaker[AsyncSession], mode: str
) -> None:
    b = await _setup(committed_sessions, mode)
    results = await _race(committed_sessions, b, mode)
    assert results == Counter({"ok": 1, "SLOT_TAKEN": N - 1})
    assert await _active_blocks(committed_sessions, b) == 1


async def test_stock_sells_only_remaining_units(
    committed_sessions: async_sessionmaker[AsyncSession],
) -> None:
    b = await _setup(committed_sessions, "QUANTITY", stock=10)  # 7 already blocked
    results = await _race(committed_sessions, b, "QUANTITY")
    assert results == Counter({"ok": 3, "INSUFFICIENT_STOCK": N - 3})
    assert await _active_blocks(committed_sessions, b) == 3
