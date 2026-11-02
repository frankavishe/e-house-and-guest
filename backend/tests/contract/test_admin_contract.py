"""Request/response shapes for admin categories, users, abuse reports and stats (T134)."""

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from tests.factories import make_admin, make_bookable, make_user, sign_in

pytestmark = pytest.mark.usefixtures("frozen_clock")

US7_PATHS = {
    "/api/v1/admin/categories": {"get", "post"},
    "/api/v1/admin/categories/{category_id}": {"patch"},
    "/api/v1/admin/users": {"get"},
    "/api/v1/admin/users/{user_id}/suspend": {"post"},
    "/api/v1/admin/users/{user_id}/unsuspend": {"post"},
    "/api/v1/admin/reports-abuse": {"get"},
    "/api/v1/admin/reports-abuse/{report_id}/action": {"post"},
    "/api/v1/admin/stats": {"get"},
}
CATEGORY_KEYS = {
    "id",
    "parent_id",
    "path",
    "slug",
    "name",
    "booking_mode",
    "price_units",
    "default_unit",
    "attribute_schema",
    "schema_version",
    "commission_bps",
    "renter_fee_bps",
    "is_active",
    "sort_order",
    "is_leaf",
    "listing_count",
    "updated_at",
}
USER_KEYS = {"id", "name", "phone", "email", "status", "is_admin", "owner", "created_at"}
REPORT_KEYS = {
    "id",
    "target_kind",
    "target_id",
    "target_label",
    "target_status",
    "reason",
    "status",
    "reporter",
    "open_reports_on_target",
    "handled_at",
    "created_at",
}
STATS_ROW_KEYS = {
    "key",
    "label",
    "bookings",
    "gbv_tzs",
    "commission_tzs",
    "refunds_tzs",
    "payouts_tzs",
}
PAGE_KEYS = {"items", "page", "page_size", "total"}


def test_openapi_lists_us7_paths() -> None:
    paths = app.openapi()["paths"]
    for path, methods in US7_PATHS.items():
        assert path in paths, path
        assert methods <= set(paths[path]), (path, set(paths[path]))


async def test_admin_endpoints_require_an_admin(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    calls = [
        ("GET", "/api/v1/admin/categories"),
        ("POST", "/api/v1/admin/categories"),
        ("GET", "/api/v1/admin/users"),
        ("GET", "/api/v1/admin/reports-abuse"),
        ("GET", "/api/v1/admin/stats"),
    ]
    for method, path in calls:
        r = await client.request(method, path, json={})
        assert r.status_code == 401, (method, path)
    sign_in(client, await make_user(db))
    for method, path in calls:
        r = await client.request(method, path, json={})
        assert r.status_code == 403, (method, path)
        assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_category_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    sign_in(client, await make_admin(db))
    r = await client.post(
        "/api/v1/admin/categories",
        json={
            "slug": "t-contract",
            "name": {"sw": "Kundi", "en": "Group"},
        },
    )
    assert r.status_code == 201, r.text
    assert set(r.json()) == CATEGORY_KEYS
    assert r.json()["is_leaf"] is False

    listed = (await client.get("/api/v1/admin/categories")).json()
    assert isinstance(listed, list)
    assert set(listed[0]) == CATEGORY_KEYS

    patched = await client.patch(f"/api/v1/admin/categories/{r.json()['id']}", json={})
    assert patched.status_code == 200
    assert set(patched.json()) == CATEGORY_KEYS

    for body in (
        {"slug": "t-x", "name": {"sw": "x"}},  # missing en
        {"slug": "t-x", "name": {"sw": "x", "en": "x"}, "commission_bps": 10_001},
        {"slug": "t-x", "name": {"sw": "x", "en": "x"}, "price_units": ["fortnight"]},
    ):
        bad = await client.post("/api/v1/admin/categories", json=body)
        assert bad.status_code == 422, body
    missing = await client.patch(
        "/api/v1/admin/categories/00000000-0000-0000-0000-000000000000", json={}
    )
    assert missing.status_code == 404


async def test_user_report_and_stats_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    sign_in(client, b.renter)
    await client.post(
        "/api/v1/reports",
        json={"target_kind": "listing", "target_id": str(b.listing.id), "reason": "Uongo"},
    )
    sign_in(client, await make_admin(db))

    users = (await client.get("/api/v1/admin/users", params={"q": b.owner_user.phone})).json()
    assert set(users) == PAGE_KEYS
    assert set(users["items"][0]) == USER_KEYS
    assert set(users["items"][0]["owner"]) == {"id", "display_name", "verification_status"}
    suspended = await client.post(
        f"/api/v1/admin/users/{b.owner_user.id}/suspend", json={"reason": "x"}
    )
    assert set(suspended.json()) == USER_KEYS
    no_reason = await client.post(f"/api/v1/admin/users/{b.renter.id}/suspend", json={})
    assert no_reason.status_code == 422

    reports = (await client.get("/api/v1/admin/reports-abuse")).json()
    assert set(reports) == PAGE_KEYS
    assert set(reports["items"][0]) == REPORT_KEYS
    assert set(reports["items"][0]["reporter"]) == {"id", "name", "phone"}
    bad = await client.post(
        f"/api/v1/admin/reports-abuse/{reports['items'][0]['id']}/action",
        json={"decision": "maybe"},
    )
    assert bad.status_code == 422

    stats = await client.get("/api/v1/admin/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert set(body) == {"from", "to", "group_by", "rows", "totals"}
    assert body["group_by"] == "month"
    assert set(body["totals"]) == STATS_ROW_KEYS
    for params in ({"group_by": "week"}, {"format": "xml"}, {"from": "yesterday"}):
        assert (await client.get("/api/v1/admin/stats", params=params)).status_code == 422
