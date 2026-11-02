"""Postgres-backed rate limits on OTP, booking creation and messaging (T144)."""

from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.errors import AppError
from app.core.ratelimit import RateLimit, Rule
from tests.conftest import FrozenClock
from tests.factories import book, make_bookable, next_phone, sign_in

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 06:00 UTC

RULE = Rule("test", 3, timedelta(minutes=10))


async def test_limit_then_retry_after(db: AsyncSession, frozen_clock: FrozenClock) -> None:
    frozen_clock.advance(minutes=4)  # 06:04, the window started at 06:00
    for _ in range(3):
        await ratelimit.hit(db, RULE, "a")
    with pytest.raises(AppError) as err:
        await ratelimit.hit(db, RULE, "a")
    assert err.value.status == 429 and err.value.code == "RATE_LIMITED"
    assert err.value.details == {"retry_after": 360}

    await ratelimit.hit(db, RULE, "b")  # keys are counted separately

    frozen_clock.advance(minutes=6)  # a new window
    await ratelimit.hit(db, RULE, "a")


async def test_purge_drops_old_windows(db: AsyncSession, frozen_clock: FrozenClock) -> None:
    await ratelimit.hit(db, RULE, "old")
    frozen_clock.advance(days=1, minutes=10)
    await ratelimit.hit(db, RULE, "new")
    assert await ratelimit.purge(db) == 1
    keys = (await db.execute(select(RateLimit.key))).scalars().all()
    assert keys == ["test:new"]


async def test_otp_requests_per_ip(client: httpx.AsyncClient) -> None:
    limit = ratelimit.OTP_PER_IP.limit
    for _ in range(limit):  # distinct phones, so only the per-IP rule can trip
        r = await client.post("/api/v1/auth/otp/request", json={"phone": next_phone()})
        assert r.status_code == 202, r.text
    r = await client.post("/api/v1/auth/otp/request", json={"phone": next_phone()})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert int(r.headers["Retry-After"]) > 0


async def test_booking_creation_per_user(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    start = date(2026, 12, 1)
    for i in range(ratelimit.BOOKINGS_PER_USER.limit):
        # Failed attempts count too: every other one clashes with the previous booking.
        await book(client, b, start + timedelta(days=4 * (i // 2)))
    r = await book(client, b, date(2027, 3, 1))
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"


async def test_messages_per_user(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    sign_in(client, b.renter)
    r = await client.post(
        "/api/v1/conversations", json={"listing_id": str(b.listing.id), "body": "Habari"}
    )
    assert r.status_code == 201
    url = f"/api/v1/conversations/{r.json()['id']}/messages"
    for _ in range(ratelimit.MESSAGES_PER_USER.limit - 1):  # starting counted as one
        assert (await client.post(url, json={"body": "Bado ipo?"})).status_code == 201
    r = await client.post(url, json={"body": "Bado ipo?"})
    assert r.status_code == 429

    sign_in(client, b.owner_user)  # the owner has a budget of their own
    assert (await client.post(url, json={"body": "Ndiyo"})).status_code == 201
    count = await db.scalar(select(func.count()).select_from(RateLimit))
    assert count == 2
