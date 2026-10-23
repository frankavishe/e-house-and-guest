"""Request/response shapes for bookings, payments, receipts and notifications (T071)."""

from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from tests.factories import book, deliver_callbacks, make_bookable, pay, sign_in

pytestmark = pytest.mark.usefixtures("frozen_clock")

D = date(2026, 11, 10)

BOOKING_KEYS = {
    "id",
    "code",
    "status",
    "role",
    "listing",
    "period",
    "quantity",
    "quote",
    "amount_due_tzs",
    "payment_due_at",
    "request_expires_at",
    "cancellation_policy",
    "delivery_requested",
    "delivery_address",
    "lease_months",
    "can",
    "counterpart",
    "events",
    "payments",
    "installments",
    "refunds",
    "claims",
    "cancelled_by",
    "cancel_reason",
    "request_message",
    "created_at",
}
SUMMARY_KEYS = {
    "id",
    "code",
    "status",
    "role",
    "listing",
    "period",
    "quantity",
    "total_tzs",
    "payment_due_at",
    "request_expires_at",
    "counterpart_name",
    "request_message",
    "created_at",
}
PAYMENT_KEYS = {
    "id",
    "booking_id",
    "installment_id",
    "status",
    "network",
    "msisdn",
    "amount_tzs",
    "failure_reason",
    "created_at",
    "confirmed_at",
}
RECEIPT_KEYS = {
    "code",
    "status",
    "listing_title",
    "owner_name",
    "renter_name",
    "period",
    "quantity",
    "quote",
    "total_tzs",
    "paid_tzs",
    "payments",
    "issued_at",
}


def test_openapi_lists_us2_paths_and_hides_webhooks() -> None:
    paths = app.openapi()["paths"]
    for path, method in [
        ("/api/v1/bookings", "post"),
        ("/api/v1/bookings", "get"),
        ("/api/v1/bookings/{booking_id}", "get"),
        ("/api/v1/bookings/{booking_id}/accept", "post"),
        ("/api/v1/bookings/{booking_id}/decline", "post"),
        ("/api/v1/bookings/{booking_id}/receipt", "get"),
        ("/api/v1/bookings/{booking_id}/payments", "post"),
        ("/api/v1/payments/{payment_id}", "get"),
        ("/api/v1/notifications", "get"),
        ("/api/v1/notifications/read", "post"),
    ]:
        assert method in paths.get(path, {}), (method, path)
    assert not [p for p in paths if p.startswith(("/api/v1/webhooks", "/api/v1/dev"))]
    post = paths["/api/v1/bookings"]["post"]
    assert any(p["name"] == "Idempotency-Key" for p in post.get("parameters", []))


async def test_booking_payment_and_receipt_shapes(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    r = await book(client, b, D)
    assert r.status_code == 201
    booking = r.json()
    assert set(booking) == BOOKING_KEYS
    assert set(booking["can"]) == {"pay", "cancel", "accept", "decline", "review", "claim"}
    assert set(booking["period"]) == {"start", "end"}
    assert set(booking["counterpart"]) == {"name", "phone"}
    assert set(booking["events"][0]) == {"from_status", "to_status", "actor_kind", "created_at"}

    early = await client.get(f"/api/v1/bookings/{booking['id']}/receipt")
    assert early.status_code == 409 and early.json()["error"]["code"] == "BOOKING_NOT_PAID"

    r = await pay(client, b, booking["id"])
    assert r.status_code == 202
    payment = r.json()
    assert set(payment) == PAYMENT_KEYS
    assert payment["msisdn"].endswith("0001") and "*" in payment["msisdn"]
    await deliver_callbacks(client)

    sign_in(client, b.renter)
    assert set((await client.get(f"/api/v1/payments/{payment['id']}")).json()) == PAYMENT_KEYS
    receipt = (await client.get(f"/api/v1/bookings/{booking['id']}/receipt")).json()
    assert set(receipt) == RECEIPT_KEYS

    page = (await client.get("/api/v1/bookings")).json()
    assert set(page) == {"items", "page", "page_size", "total"}
    assert set(page["items"][0]) == SUMMARY_KEYS


async def test_payment_body_validation(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking_id = (await book(client, b, D)).json()["id"]
    r = await client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"network": "paypal", "msisdn": "+255700000001"},
    )
    assert r.status_code == 422
    r = await client.post(
        f"/api/v1/bookings/{booking_id}/payments", json={"network": "mpesa", "msisdn": "12"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_PHONE"


async def test_notification_feed(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking_id = (await book(client, b, D)).json()["id"]

    feed = (await client.get("/api/v1/notifications")).json()
    assert set(feed) == {"items", "page", "page_size", "total", "unread_count"}
    assert feed["unread_count"] == 1
    item = feed["items"][0]
    assert set(item) == {"id", "event", "text", "booking_id", "read_at", "created_at"}
    assert item["event"] == "booking.awaiting_payment" and item["booking_id"] == booking_id
    assert item["text"]

    r = await client.post("/api/v1/notifications/read", json={"ids": [item["id"]]})
    assert r.status_code == 200 and r.json() == {"unread_count": 0}
    feed = (await client.get("/api/v1/notifications")).json()
    assert feed["items"][0]["read_at"] is not None

    await client.post("/api/v1/notifications/read", json={})
    assert (await client.get("/api/v1/notifications")).json()["unread_count"] == 0

    client.cookies.clear()
    assert (await client.get("/api/v1/notifications")).status_code == 401
