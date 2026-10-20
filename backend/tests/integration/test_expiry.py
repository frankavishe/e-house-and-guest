"""Hold expiry and status sweeps (T070, US2-AS4, FR-017, R9), on a frozen clock."""

import uuid
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability import service as availability
from app.bookings.jobs import advance_bookings, expire_holds
from app.bookings.models import Booking, BookingStatus, CancelledBy
from app.listings.schemas import QuoteRequest
from app.listings.service import period_for
from tests.conftest import FrozenClock
from tests.factories import Bookable, book, day_range, make_bookable, make_booking, sign_in

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

D = date(2026, 11, 10)


async def _get(db: AsyncSession, booking_id: str | uuid.UUID) -> Booking:
    booking = await db.get(Booking, uuid.UUID(str(booking_id)), populate_existing=True)
    assert booking is not None
    return booking


async def _free(db: AsyncSession, b: Bookable) -> bool:
    period = period_for(
        b.category, b.listing, QuoteRequest(start_date=D, end_date=D + timedelta(3))
    )
    assert b.category.booking_mode is not None
    return await availability.is_available(db, b.listing, b.category.booking_mode, period)


async def test_unpaid_instant_booking_expires_hold_expiry(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db)
    booking_id = (await book(client, b, D, days=3)).json()["id"]
    assert not await _free(db, b)

    frozen_clock.advance(minutes=14)
    assert await expire_holds(db) == 0
    assert (await _get(db, booking_id)).status == BookingStatus.AWAITING_PAYMENT

    frozen_clock.advance(minutes=2)
    assert await expire_holds(db) == 1
    booking = await _get(db, booking_id)
    assert booking.status == BookingStatus.CANCELLED
    assert booking.cancelled_by == CancelledBy.SYSTEM
    assert await _free(db, b)
    assert await expire_holds(db) == 0  # idempotent


async def test_accepted_request_unpaid_after_24h(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db, instant_book=False)
    booking_id = (await book(client, b, D)).json()["id"]
    sign_in(client, b.owner_user)
    assert (await client.post(f"/api/v1/bookings/{booking_id}/accept")).status_code == 200

    frozen_clock.advance(hours=23)
    await expire_holds(db)
    assert (await _get(db, booking_id)).status == BookingStatus.AWAITING_PAYMENT
    frozen_clock.advance(hours=1, seconds=1)
    await expire_holds(db)
    assert (await _get(db, booking_id)).status == BookingStatus.CANCELLED
    assert await _free(db, b)


async def test_confirmed_moves_to_in_progress_then_completed(
    db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db)
    start, end = day_range(D, D + timedelta(days=2))
    booking = await make_booking(db, b, start, end, status="confirmed")

    assert await advance_bookings(db) == 0
    frozen_clock.set(start)
    await advance_bookings(db)
    assert (await _get(db, booking.id)).status == BookingStatus.IN_PROGRESS

    frozen_clock.set(end - timedelta(seconds=1))
    await advance_bookings(db)
    assert (await _get(db, booking.id)).status == BookingStatus.IN_PROGRESS
    frozen_clock.set(end)
    await advance_bookings(db)
    done = await _get(db, booking.id)
    assert done.status == BookingStatus.COMPLETED and done.completed_at == end


async def test_short_booking_past_its_end_completes_in_one_sweep(
    db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db)
    start, end = day_range(D, D + timedelta(days=1))
    booking = await make_booking(db, b, start, end, status="confirmed")
    frozen_clock.set(end + timedelta(hours=1))
    await advance_bookings(db)
    assert (await _get(db, booking.id)).status == BookingStatus.COMPLETED
