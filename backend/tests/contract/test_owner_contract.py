"""Request/response shapes for owner onboarding, owner listings and moderation (T096)."""

from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import get_storage
from app.main import app
from tests.factories import (
    WAREHOUSE_SCHEMA,
    book,
    jpeg_with_exif,
    make_admin,
    make_bookable,
    make_category,
    make_owner,
    make_place,
    make_user,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")

US3_PATHS = {
    "/api/v1/owner-profile": {"get", "post", "patch"},
    "/api/v1/owner-profile/documents": {"post"},
    "/api/v1/owner-profile/submit": {"post"},
    "/api/v1/owner-profile/payout-methods": {"get", "post"},
    "/api/v1/owner-profile/payout-methods/{method_id}": {"delete"},
    "/api/v1/owner/listings": {"get", "post"},
    "/api/v1/owner/listings/{listing_id}": {"get", "patch", "delete"},
    "/api/v1/owner/listings/{listing_id}/photos": {"post"},
    "/api/v1/owner/listings/{listing_id}/photos/{photo_id}": {"patch", "delete"},
    "/api/v1/owner/listings/{listing_id}/prices": {"put"},
    "/api/v1/owner/listings/{listing_id}/submit": {"post"},
    "/api/v1/owner/listings/{listing_id}/pause": {"post"},
    "/api/v1/owner/listings/{listing_id}/resume": {"post"},
    "/api/v1/owner/listings/{listing_id}/blocks": {"get", "post"},
    "/api/v1/owner/listings/{listing_id}/blocks/{block_id}": {"delete"},
    "/api/v1/owner/calendar": {"get"},
    "/api/v1/admin/owner-verifications": {"get"},
    "/api/v1/admin/owner-verifications/{profile_id}/approve": {"post"},
    "/api/v1/admin/owner-verifications/{profile_id}/reject": {"post"},
    "/api/v1/admin/listings": {"get"},
    "/api/v1/admin/listings/{listing_id}/approve": {"post"},
    "/api/v1/admin/listings/{listing_id}/reject": {"post"},
    "/api/v1/admin/listings/{listing_id}/suspend": {"post"},
    "/api/v1/admin/listings/{listing_id}/unsuspend": {"post"},
    "/api/v1/bookings/{booking_id}/accept": {"post"},
    "/api/v1/bookings/{booking_id}/decline": {"post"},
}

PROFILE_KEYS = {
    "id",
    "kind",
    "display_name",
    "business_name",
    "brela_reg_no",
    "nida_number_masked",
    "tin_masked",
    "documents",
    "verification_status",
    "rejection_reason",
    "verified_at",
}
PAYOUT_METHOD_KEYS = {
    "id",
    "kind",
    "network",
    "msisdn",
    "bank_name",
    "account_name",
    "account_number_masked",
    "is_default",
}
UPLOAD_KEYS = {"upload_url", "storage_key", "headers"}
OWNER_LISTING_KEYS = {
    "id",
    "status",
    "review_state",
    "rejection_reason",
    "pending_changes",
    "category",
    "title_sw",
    "title_en",
    "description_sw",
    "description_en",
    "attributes",
    "region_id",
    "district_id",
    "ward_id",
    "address_hint",
    "lat",
    "lng",
    "stock",
    "deposit_tzs",
    "delivery",
    "delivery_fee_tzs",
    "delivery_area",
    "min_duration",
    "max_duration",
    "slot_config",
    "cancellation_policy",
    "instant_book",
    "prices",
    "photos",
    "base_price_tzs",
    "missing",
    "created_at",
    "updated_at",
}
OWNER_CATEGORY_KEYS = {"id", "slug", "name", "booking_mode", "price_units", "default_unit"}
OWNER_PHOTO_KEYS = {
    "id",
    "url_320",
    "url_640",
    "url_1280",
    "position",
    "alt_sw",
    "alt_en",
    "pending",
}
PRICE_KEYS = {"unit", "amount_tzs", "season_start", "season_end"}
BLOCK_KEYS = {"id", "listing_id", "period", "quantity", "note"}
CALENDAR_KEYS = {"listings", "bookings", "blocks"}
CALENDAR_BOOKING_KEYS = {"id", "code", "listing_id", "status", "period", "quantity", "renter_name"}
VERIFICATION_KEYS = {
    "id",
    "user",
    "kind",
    "display_name",
    "business_name",
    "brela_reg_no",
    "nida_number",
    "tin",
    "documents",
    "verification_status",
    "rejection_reason",
    "updated_at",
}
ADMIN_LISTING_KEYS = {"listing", "owner", "diff"}


def test_openapi_lists_us3_paths() -> None:
    paths = app.openapi()["paths"]
    for path, methods in US3_PATHS.items():
        assert path in paths, path
        assert methods <= set(paths[path]), (path, set(paths[path]))


async def test_owner_profile_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    sign_in(client, await make_user(db))
    r = await client.post(
        "/api/v1/owner-profile",
        json={"kind": "individual", "display_name": "Shape", "nida_number": "19900101123450000123"},
    )
    assert r.status_code == 201 and set(r.json()) == PROFILE_KEYS

    r = await client.post(
        "/api/v1/owner-profile/documents", json={"content_type": "application/pdf"}
    )
    assert set(r.json()) == UPLOAD_KEYS

    r = await client.post(
        "/api/v1/owner-profile/payout-methods",
        json={
            "kind": "mobile_money",
            "network": "airtel",
            "msisdn": "0687000000",
            "account_name": "Shape",
        },
    )
    assert set(r.json()) == PAYOUT_METHOD_KEYS
    listed = (await client.get("/api/v1/owner-profile/payout-methods")).json()
    assert isinstance(listed, list) and set(listed[0]) == PAYOUT_METHOD_KEYS

    sign_in(client, await make_admin(db))
    page = (await client.get("/api/v1/admin/owner-verifications?status=draft")).json()
    assert {"items", "page", "page_size", "total"} <= set(page)
    assert set(page["items"][0]) >= VERIFICATION_KEYS


async def test_owner_listing_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    owner_user = await make_user(db)
    await make_owner(db, user=owner_user)
    category = await make_category(
        db, mode="LEASE", default_unit="month", attribute_schema=WAREHOUSE_SCHEMA
    )
    region, district = await make_place(db)
    sign_in(client, owner_user)

    r = await client.post("/api/v1/owner/listings", json={"category_id": str(category.id)})
    assert r.status_code == 201
    listing = r.json()
    assert set(listing) == OWNER_LISTING_KEYS
    assert set(listing["category"]) == OWNER_CATEGORY_KEYS
    lid = listing["id"]

    await client.patch(
        f"/api/v1/owner/listings/{lid}",
        json={
            "title_sw": "Ghala",
            "description_sw": "Maelezo",
            "region_id": region.id,
            "district_id": district.id,
            "attributes": {"floor_area": 100},
        },
    )
    r = await client.put(
        f"/api/v1/owner/listings/{lid}/prices", json=[{"unit": "month", "amount_tzs": 500_000}]
    )
    assert set(r.json()["prices"][0]) == PRICE_KEYS

    r = await client.post(
        f"/api/v1/owner/listings/{lid}/photos", json={"content_type": "image/png"}
    )
    upload = r.json()
    assert set(upload) == UPLOAD_KEYS | {"photo_id"}
    await get_storage().put(upload["storage_key"], jpeg_with_exif(), "image/png", private=True)
    r = await client.patch(
        f"/api/v1/owner/listings/{lid}/photos/{upload['photo_id']}", json={"confirmed": True}
    )
    assert set(r.json()) == OWNER_PHOTO_KEYS

    page = (await client.get("/api/v1/owner/listings")).json()
    assert {"items", "page", "page_size", "total"} <= set(page)
    assert set(page["items"][0]) == OWNER_LISTING_KEYS

    await client.post(f"/api/v1/owner/listings/{lid}/submit")
    sign_in(client, await make_admin(db))
    queue = (await client.get("/api/v1/admin/listings")).json()
    assert set(queue["items"][0]) == ADMIN_LISTING_KEYS
    assert set(queue["items"][0]["listing"]) == OWNER_LISTING_KEYS


async def test_block_and_calendar_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db, "DATE_RANGE", unit="day", instant_book=False)
    booking_id = (await book(client, b, date(2026, 12, 10))).json()["id"]
    sign_in(client, b.owner_user)
    r = await client.post(
        f"/api/v1/owner/listings/{b.listing.id}/blocks",
        json={"start_date": "2026-12-01", "end_date": "2026-12-02"},
    )
    assert set(r.json()) == BLOCK_KEYS
    assert set(r.json()["period"]) == {"start", "end"}

    cal = (await client.get("/api/v1/owner/calendar?from=2026-12-01&to=2026-12-31")).json()
    assert set(cal) == CALENDAR_KEYS
    assert set(cal["bookings"][0]) == CALENDAR_BOOKING_KEYS
    assert set(cal["blocks"][0]) == BLOCK_KEYS

    r = await client.post(f"/api/v1/bookings/{booking_id}/accept")
    assert r.status_code == 200 and r.json()["status"] == "awaiting_payment"


async def test_access_levels(client: httpx.AsyncClient, db: AsyncSession) -> None:
    owner_routes = [("get", "/api/v1/owner/listings"), ("get", "/api/v1/owner/calendar")]
    admin_routes = [("get", "/api/v1/admin/listings"), ("get", "/api/v1/admin/owner-verifications")]
    for method, path in owner_routes + admin_routes:
        r = await client.request(method, path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"

    sign_in(client, await make_user(db))  # signed in, no owner profile, not admin
    for method, path in owner_routes + admin_routes:
        r = await client.request(method, path)
        assert r.status_code == 403, path
        assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_error_envelopes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    owner_user = await make_user(db)
    await make_owner(db, user=owner_user)
    category = await make_category(
        db, mode="LEASE", default_unit="month", attribute_schema=WAREHOUSE_SCHEMA
    )
    sign_in(client, owner_user)
    lid = (
        await client.post("/api/v1/owner/listings", json={"category_id": str(category.id)})
    ).json()["id"]

    r = await client.patch(f"/api/v1/owner/listings/{lid}", json={"attributes": {"nope": 1}})
    error = r.json()["error"]
    assert r.status_code == 422 and error["code"] == "INVALID_ATTRIBUTES"
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"]["fields"], dict)

    r = await client.post(f"/api/v1/owner/listings/{lid}/submit")
    error = r.json()["error"]
    assert r.status_code == 422 and error["code"] == "LISTING_INCOMPLETE"
    assert isinstance(error["details"]["missing"], list) and error["message"]
