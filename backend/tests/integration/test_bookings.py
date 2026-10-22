"""Booking API (T067, US2 acceptance scenarios 1-3 and 5)."""

from datetime import date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.availability.models import AvailabilityBlock
from app.bookings.models import Booking, BookingStatus
from app.listings.models import ListingPrice
from tests.conftest import FrozenClock
from tests.factories import book, make_bookable, make_user, pay, sign_in

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

D = date(2026, 11, 10)


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def test_instant_book_awaits_payment(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db, price=50_000, deposit_tzs=20_000, renter_fee_bps=500)
    r = await book(client, b, D, days=3)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "awaiting_payment"
    assert body["code"].startswith("EHG-")
    assert _ts(body["payment_due_at"]) == frozen_clock.current + timedelta(minutes=15)
    assert body["request_expires_at"] is None
    assert body["quote"]["rental_tzs"] == 150_000
    assert body["quote"]["service_fee_tzs"] == 7_500
    assert body["quote"]["total_tzs"] == 177_500
    assert body["amount_due_tzs"] == 177_500
    assert body["can"]["pay"] is True and body["can"]["accept"] is False
    assert body["role"] == "renter"

    block = (
        await db.execute(
            select(AvailabilityBlock).where(AvailabilityBlock.booking_id == body["id"])
        )
    ).scalar_one()
    assert block.active and block.kind == "exclusive"


async def test_request_listing_waits_for_owner(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db, instant_book=False)
    r = await book(client, b, D)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "requested"
    assert body["payment_due_at"] is None
    assert _ts(body["request_expires_at"]) == frozen_clock.current + timedelta(hours=24)
    assert body["can"]["pay"] is False

    # The dates are held while the owner decides.
    clash = await book(client, b, D + timedelta(days=1))
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "SLOT_TAKEN"

    r = await pay(client, b, body["id"])
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_TRANSITION"


async def test_stock_refusal_reports_available(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db, "QUANTITY", stock=10)
    assert (await book(client, b, D, days=1, quantity=7)).status_code == 201
    r = await book(client, b, D, days=1, quantity=5)
    assert r.status_code == 409
    error = r.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK" and error["details"]["available"] == 3


async def test_cannot_book_own_listing(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    b.renter = b.owner_user
    r = await book(client, b, D)
    assert r.status_code == 422 and r.json()["error"]["code"] == "OWN_LISTING"


async def test_requires_sign_in(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    period = {"start_date": "2026-11-10", "end_date": "2026-11-12"}
    r = await client.post(
        "/api/v1/bookings", json={"listing_id": str(b.listing.id), "period": period}
    )
    assert r.status_code == 401


async def test_wrong_period_shape_and_unknown_listing(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    sign_in(client, b.renter)
    r = await client.post(
        "/api/v1/bookings",
        json={"listing_id": str(b.listing.id), "period": {"start_date": "2026-11-10", "months": 2}},
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_PERIOD"
    r = await client.post(
        "/api/v1/bookings",
        json={
            "listing_id": "00000000-0000-0000-0000-000000000000",
            "period": {"start_date": "2026-11-10", "end_date": "2026-11-12"},
        },
    )
    assert r.status_code == 404


async def test_quote_snapshot_survives_price_change(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db, price=50_000)
    booking_id = (await book(client, b, D, days=2)).json()["id"]
    await db.execute(
        update(ListingPrice)
        .where(ListingPrice.listing_id == b.listing.id)
        .values(amount_tzs=99_000)
    )
    r = await client.get(f"/api/v1/bookings/{booking_id}")
    assert r.status_code == 200
    assert r.json()["quote"]["rental_tzs"] == 100_000
    row = await db.get(Booking, booking_id)
    assert row is not None and row.total_tzs == 100_000


async def test_idempotency_key_replays(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    headers = {"Idempotency-Key": "abc-123"}
    first = await book(client, b, D, headers=headers)
    again = await book(client, b, D, headers=headers)
    assert first.status_code == again.status_code == 201
    assert first.json()["id"] == again.json()["id"]
    rows = (await db.execute(select(Booking).where(Booking.listing_id == b.listing.id))).all()
    assert len(rows) == 1

    other = await book(client, b, D + timedelta(days=5), headers=headers)
    assert other.status_code == 422
    assert other.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


async def test_detail_access_and_counterpart_privacy(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking_id = (await book(client, b, D)).json()["id"]

    renter_view = (await client.get(f"/api/v1/bookings/{booking_id}")).json()
    assert renter_view["counterpart"]["name"] == "Test Owner"
    assert renter_view["counterpart"]["phone"] is None
    assert [e["to_status"] for e in renter_view["events"]] == ["awaiting_payment"]

    sign_in(client, b.owner_user)
    owner_view = (await client.get(f"/api/v1/bookings/{booking_id}")).json()
    assert owner_view["role"] == "owner"
    assert owner_view["counterpart"] == {"name": "Renter Person", "phone": None}

    stranger = await make_user(db)
    sign_in(client, stranger)
    assert (await client.get(f"/api/v1/bookings/{booking_id}")).status_code == 404

    admin = await make_user(db, is_admin=True)
    sign_in(client, admin)
    assert (await client.get(f"/api/v1/bookings/{booking_id}")).status_code == 200

    booking = await db.get(Booking, booking_id)
    assert booking is not None
    booking.status = BookingStatus.CONFIRMED
    await db.flush()
    sign_in(client, b.renter)
    confirmed = (await client.get(f"/api/v1/bookings/{booking_id}")).json()
    assert confirmed["counterpart"]["phone"] == b.owner_user.phone


async def test_list_by_role(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking_id = (await book(client, b, D)).json()["id"]

    page = (await client.get("/api/v1/bookings", params={"role": "renter"})).json()
    assert [i["id"] for i in page["items"]] == [booking_id]
    assert page["total"] == 1
    assert page["items"][0]["listing"]["id"] == str(b.listing.id)

    filtered = (
        await client.get("/api/v1/bookings", params={"role": "renter", "status": "confirmed"})
    ).json()
    assert filtered["items"] == []

    sign_in(client, b.owner_user)
    owner_page = (await client.get("/api/v1/bookings", params={"role": "owner"})).json()
    assert [i["id"] for i in owner_page["items"]] == [booking_id]
    renter_page = (await client.get("/api/v1/bookings", params={"role": "renter"})).json()
    assert renter_page["items"] == []


@pytest.mark.parametrize("mode", ["DATE_RANGE", "TIME_SLOT", "LEASE", "QUANTITY"])
async def test_each_mode_can_be_booked(
    client: httpx.AsyncClient, db: AsyncSession, mode: str
) -> None:
    b = await make_bookable(db, mode, stock=5)
    r = await book(client, b, D, days=2)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["listing"]["booking_mode"] == mode
    if mode == "LEASE":
        assert [i["seq"] for i in body["installments"]] == [1, 2]
        assert body["amount_due_tzs"] == 50_000  # first month, no deposit
    else:
        assert body["installments"] is None


async def test_delivery_must_be_inside_the_area(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db, delivery="optional", delivery_fee_tzs=10_000)
    b.listing.delivery_area = [b.listing.district_id]
    await db.flush()

    r = await book(client, b, D, delivery=True)
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "OUTSIDE_DELIVERY_AREA"
    assert error["details"] == {"reason": "district_required"}

    r = await book(client, b, D, delivery=True, delivery_district_id=b.listing.district_id + 1)
    assert r.status_code == 422 and r.json()["error"]["code"] == "OUTSIDE_DELIVERY_AREA"

    r = await book(client, b, D, delivery=True, delivery_district_id=b.listing.district_id)
    assert r.status_code == 201, r.text
    assert r.json()["quote"]["delivery_fee_tzs"] == 10_000
