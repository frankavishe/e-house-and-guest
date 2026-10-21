"""Request/response shapes for owner earnings, owner payouts and admin payouts (T110)."""

import uuid
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.main import app
from app.payouts.service import create_payouts
from tests.factories import (
    day_range,
    make_admin,
    make_bookable,
    make_completed_booking,
    make_payout_method,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")

US4_PATHS = {
    "/api/v1/owner/earnings": {"get"},
    "/api/v1/owner/payouts": {"get"},
    "/api/v1/admin/payouts": {"get"},
    "/api/v1/admin/payouts/{payout_id}/mark-paid": {"post"},
    "/api/v1/admin/payouts/{payout_id}/retry": {"post"},
}
EARNINGS_KEYS = {"totals", "items"}
TOTALS_KEYS = {"gross_tzs", "commission_tzs", "net_tzs", "paid_out_tzs", "pending_tzs"}
EARNING_ITEM_KEYS = {
    "booking_id",
    "booking_code",
    "listing_id",
    "listing_title",
    "period",
    "completed_at",
    "gross_tzs",
    "commission_tzs",
    "net_tzs",
    "status",
    "payout_id",
}
PAYOUT_KEYS = {
    "id",
    "amount_tzs",
    "status",
    "provider",
    "provider_ref",
    "failure_reason",
    "destination",
    "paid_at",
    "created_at",
    "items",
}
PAYOUT_ITEM_KEYS = {"booking_id", "booking_code", "amount_tzs"}
ADMIN_PAYOUT_KEYS = PAYOUT_KEYS | {"owner", "attempts"}
ADMIN_OWNER_KEYS = {"id", "display_name", "phone"}
PAGE_KEYS = {"items", "page", "page_size", "total"}


def test_openapi_lists_us4_paths() -> None:
    paths = app.openapi()["paths"]
    for path, methods in US4_PATHS.items():
        assert path in paths, path
        assert methods <= set(paths[path]), (path, set(paths[path]))


async def _paid_out(db: AsyncSession) -> tuple[object, uuid.UUID]:
    b = await make_bookable(db)
    await make_payout_method(db, b.owner)
    await make_completed_booking(
        db,
        b,
        *day_range(date(2026, 10, 20), date(2026, 10, 23)),
        completed_at=clock.now() - timedelta(days=2),
    )
    [payout] = await create_payouts(db)
    return b, payout.id


async def test_earnings_shape(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b, _ = await _paid_out(db)
    sign_in(client, b.owner_user)  # type: ignore[attr-defined]
    r = await client.get(
        "/api/v1/owner/earnings", params={"from": "2026-10-01", "to": "2026-10-31"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == EARNINGS_KEYS
    assert set(body["totals"]) == TOTALS_KEYS
    [item] = body["items"]
    assert set(item) == EARNING_ITEM_KEYS
    assert set(item["period"]) == {"start", "end"}
    assert item["status"] in {"upcoming", "available", "pending", "processing", "paid", "failed"}


async def test_earnings_rejects_inverted_range(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b, _ = await _paid_out(db)
    sign_in(client, b.owner_user)  # type: ignore[attr-defined]
    r = await client.get(
        "/api/v1/owner/earnings", params={"from": "2026-10-31", "to": "2026-10-01"}
    )
    assert r.status_code == 422


async def test_owner_payouts_shape(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b, _ = await _paid_out(db)
    sign_in(client, b.owner_user)  # type: ignore[attr-defined]
    r = await client.get("/api/v1/owner/payouts")
    assert r.status_code == 200, r.text
    page = r.json()
    assert set(page) == PAGE_KEYS
    [payout] = page["items"]
    assert set(payout) == PAYOUT_KEYS
    assert set(payout["items"][0]) == PAYOUT_ITEM_KEYS


async def test_admin_payouts_shape_and_errors(client: httpx.AsyncClient, db: AsyncSession) -> None:
    _, payout_id = await _paid_out(db)
    sign_in(client, await make_admin(db))

    r = await client.get("/api/v1/admin/payouts")
    assert r.status_code == 200, r.text
    [payout] = r.json()["items"]
    assert set(payout) == ADMIN_PAYOUT_KEYS
    assert set(payout["owner"]) == ADMIN_OWNER_KEYS

    assert (await client.get("/api/v1/admin/payouts", params={"status": "nope"})).status_code == 422
    missing_ref = await client.post(f"/api/v1/admin/payouts/{payout_id}/mark-paid", json={})
    assert missing_ref.status_code == 422
    blank_ref = await client.post(
        f"/api/v1/admin/payouts/{payout_id}/mark-paid", json={"provider_ref": "  "}
    )
    assert blank_ref.status_code == 422
    unknown = await client.post(
        f"/api/v1/admin/payouts/{uuid.uuid4()}/mark-paid", json={"provider_ref": "X1"}
    )
    assert unknown.status_code == 404
    assert (await client.post(f"/api/v1/admin/payouts/{uuid.uuid4()}/retry")).status_code == 404

    paid = await client.post(
        f"/api/v1/admin/payouts/{payout_id}/mark-paid", json={"provider_ref": "X1"}
    )
    assert paid.status_code == 200
    assert set(paid.json()) == ADMIN_PAYOUT_KEYS


async def test_unauthenticated_requests_get_401(client: httpx.AsyncClient) -> None:
    for path in ("/api/v1/owner/earnings", "/api/v1/owner/payouts", "/api/v1/admin/payouts"):
        assert (await client.get(path)).status_code == 401, path
