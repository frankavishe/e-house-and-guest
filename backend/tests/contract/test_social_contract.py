"""Request/response shapes for messaging, reviews, reports and notifications (T127)."""

from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from tests.factories import day_range, make_bookable, make_booking, sign_in

pytestmark = pytest.mark.usefixtures("frozen_clock")

US6_PATHS = {
    "/api/v1/conversations": {"get", "post"},
    "/api/v1/conversations/{conversation_id}": {"get"},
    "/api/v1/conversations/{conversation_id}/messages": {"get", "post"},
    "/api/v1/bookings/{booking_id}/reviews": {"post"},
    "/api/v1/listings/{listing_id}/reviews": {"get"},
    "/api/v1/users/{user_id}/reviews": {"get"},
    "/api/v1/reports": {"post"},
    "/api/v1/notifications": {"get"},
    "/api/v1/notifications/read": {"post"},
}
CONVERSATION_KEYS = {
    "id",
    "listing",
    "role",
    "counterpart",
    "booking_id",
    "last_message",
    "last_message_at",
    "unread_count",
}
MESSAGE_KEYS = {"id", "seq", "mine", "body", "masked", "read_at", "created_at"}
REVIEW_KEYS = {"rating", "comment", "author", "created_at"}
REPORT_KEYS = {"id", "target_kind", "target_id", "reason", "status", "created_at"}
PROFILE_KEYS = {"id", "name", "renter_rating_avg", "renter_rating_count", "owner"}
PAGE_KEYS = {"items", "page", "page_size", "total"}
PAST = day_range(date(2026, 10, 20), date(2026, 10, 23))


def test_openapi_lists_us6_paths() -> None:
    paths = app.openapi()["paths"]
    for path, methods in US6_PATHS.items():
        assert path in paths, path
        assert methods <= set(paths[path]), (path, set(paths[path]))


async def test_signed_in_endpoints_require_auth(client: httpx.AsyncClient) -> None:
    for method, path in [
        ("GET", "/api/v1/conversations"),
        ("POST", "/api/v1/conversations"),
        ("POST", "/api/v1/reports"),
        ("GET", "/api/v1/notifications"),
        ("POST", "/api/v1/notifications/read"),
    ]:
        r = await client.request(method, path, json={})
        assert r.status_code == 401, (method, path, r.status_code)
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_conversation_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    sign_in(client, b.renter)
    created = await client.post(
        "/api/v1/conversations", json={"listing_id": str(b.listing.id), "body": "Habari"}
    )
    assert created.status_code == 201, created.text
    conv = created.json()
    assert set(conv) == CONVERSATION_KEYS
    assert set(conv["listing"]) == {"id", "title", "photo_url"}
    assert set(conv["counterpart"]) == {"name"}

    inbox = (await client.get("/api/v1/conversations")).json()
    assert set(inbox) == PAGE_KEYS | {"unread_total"}
    assert set(inbox["items"][0]) == CONVERSATION_KEYS
    one = await client.get(f"/api/v1/conversations/{conv['id']}")
    assert set(one.json()) == CONVERSATION_KEYS

    sent = await client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"body": "Uko?"})
    assert sent.status_code == 201
    assert set(sent.json()) == MESSAGE_KEYS
    listed = (await client.get(f"/api/v1/conversations/{conv['id']}/messages")).json()
    assert set(listed) == {"items"}
    assert set(listed["items"][0]) == MESSAGE_KEYS

    bad = await client.get(f"/api/v1/conversations/{conv['id']}/messages?after=-1")
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_review_and_profile_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *PAST, status="completed")
    sign_in(client, b.renter)
    for rating in (0, 6):
        r = await client.post(f"/api/v1/bookings/{booking.id}/reviews", json={"rating": rating})
        assert r.status_code == 422
    too_long = await client.post(
        f"/api/v1/bookings/{booking.id}/reviews", json={"rating": 4, "body": "x" * 1001}
    )
    assert too_long.status_code == 422

    created = await client.post(f"/api/v1/bookings/{booking.id}/reviews", json={"rating": 4})
    assert created.status_code == 201, created.text
    assert set(created.json()) == REVIEW_KEYS

    client.cookies.clear()  # public
    listing_page = (await client.get(f"/api/v1/listings/{b.listing.id}/reviews")).json()
    assert set(listing_page) == PAGE_KEYS
    assert set(listing_page["items"][0]) == REVIEW_KEYS
    user_page = (await client.get(f"/api/v1/users/{b.owner_user.id}/reviews")).json()
    assert set(user_page) == PAGE_KEYS | {"profile"}
    assert set(user_page["profile"]) == PROFILE_KEYS
    assert set(user_page["profile"]["owner"]) == {
        "display_name",
        "rating_avg",
        "rating_count",
        "verified",
    }
    assert set(user_page["items"][0]) == REVIEW_KEYS | {"about"}

    detail = (await client.get(f"/api/v1/listings/{b.listing.id}")).json()
    assert "user_id" in detail["owner"]


async def test_report_shape(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    sign_in(client, b.renter)
    r = await client.post(
        "/api/v1/reports",
        json={"target_kind": "listing", "target_id": str(b.listing.id), "reason": "Uongo"},
    )
    assert r.status_code == 201, r.text
    assert set(r.json()) == REPORT_KEYS
    too_long = await client.post(
        "/api/v1/reports",
        json={"target_kind": "user", "target_id": str(b.owner_user.id), "reason": "x" * 1001},
    )
    assert too_long.status_code == 422


async def test_notification_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *PAST, status="completed")
    sign_in(client, b.renter)
    await client.post(f"/api/v1/bookings/{booking.id}/reviews", json={"rating": 5})

    sign_in(client, b.owner_user)
    feed = (await client.get("/api/v1/notifications")).json()
    assert set(feed) == PAGE_KEYS | {"unread_count"}
    assert feed["unread_count"] >= 1
    assert set(feed["items"][0]) == {"id", "event", "text", "booking_id", "read_at", "created_at"}
    read = await client.post("/api/v1/notifications/read", json={})
    assert read.status_code == 200
    assert read.json() == {"unread_count": 0}
