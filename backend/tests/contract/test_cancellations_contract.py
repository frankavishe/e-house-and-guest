"""Request/response shapes for cancellation, claims and admin bookings/refunds/claims (T118)."""

import uuid
from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from tests.factories import (
    day_range,
    make_admin,
    make_bookable,
    make_paid_booking,
    make_user,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")

US5_PATHS = {
    "/api/v1/bookings/{booking_id}/cancel": {"post"},
    "/api/v1/bookings/{booking_id}/cancel-preview": {"get"},
    "/api/v1/bookings/{booking_id}/claims": {"post"},
    "/api/v1/bookings/{booking_id}/claims/evidence-upload": {"post"},
    "/api/v1/admin/bookings": {"get"},
    "/api/v1/admin/bookings/{booking_id}": {"get"},
    "/api/v1/admin/bookings/{booking_id}/cancel": {"post"},
    "/api/v1/admin/bookings/{booking_id}/refund": {"post"},
    "/api/v1/admin/refunds/{refund_id}/retry": {"post"},
    "/api/v1/admin/refunds/{refund_id}/mark-sent": {"post"},
    "/api/v1/admin/claims": {"get"},
    "/api/v1/admin/claims/{claim_id}/resolve": {"post"},
}
PREVIEW_KEYS = {
    "policy",
    "cancelled_by",
    "percent",
    "paid_tzs",
    "rental_refund_tzs",
    "delivery_refund_tzs",
    "service_fee_refund_tzs",
    "deposit_refund_tzs",
    "refund_tzs",
    "deadline",
}
REFUND_KEYS = {
    "id",
    "amount_tzs",
    "reason",
    "status",
    "provider_ref",
    "failure_reason",
    "created_at",
}
CLAIM_KEYS = {
    "id",
    "booking_id",
    "kind",
    "opened_by",
    "description",
    "amount_claimed_tzs",
    "evidence_keys",
    "status",
    "resolution",
    "amount_awarded_tzs",
    "resolution_note",
    "created_at",
    "resolved_at",
}
ADMIN_CLAIM_KEYS = CLAIM_KEYS | {
    "booking_code",
    "booking_status",
    "deposit_tzs",
    "renter",
    "owner",
    "evidence",
}
PARTY_KEYS = {"id", "name", "phone"}
ADMIN_BOOKING_KEYS = {
    "id",
    "code",
    "status",
    "listing_id",
    "listing_title",
    "period",
    "total_tzs",
    "renter",
    "owner",
    "open_claim",
    "created_at",
}
UPLOAD_KEYS = {"upload_url", "storage_key", "headers"}
PAGE_KEYS = {"items", "page", "page_size", "total"}
FAR = day_range(date(2026, 11, 20), date(2026, 11, 23))
ENDED = day_range(date(2026, 10, 28), date(2026, 11, 1))
MONEY = {"total": 200_000, "deposit": 50_000}


def test_openapi_lists_us5_paths() -> None:
    paths = app.openapi()["paths"]
    for path, methods in US5_PATHS.items():
        assert path in paths, path
        assert methods <= set(paths[path]), (path, set(paths[path]))


async def test_cancel_preview_and_cancel_shapes(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *FAR, policy="flexible", **MONEY)
    sign_in(client, b.renter)

    preview = await client.get(f"/api/v1/bookings/{booking.id}/cancel-preview")
    assert preview.status_code == 200, preview.text
    assert set(preview.json()) == PREVIEW_KEYS

    too_long = await client.post(
        f"/api/v1/bookings/{booking.id}/cancel", json={"reason": "x" * 501}
    )
    assert too_long.status_code == 422
    res = await client.post(f"/api/v1/bookings/{booking.id}/cancel", json={"reason": "Sick"})
    assert res.status_code == 200, res.text
    [refund] = res.json()["refunds"]
    assert set(refund) == REFUND_KEYS
    again = await client.post(f"/api/v1/bookings/{booking.id}/cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "INVALID_TRANSITION"
    assert (await client.get(f"/api/v1/bookings/{booking.id}/cancel-preview")).status_code == 409


async def test_claim_shapes_and_validation(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(
        db, b, *ENDED, status="completed", completed_at=ENDED[1], **MONEY
    )
    sign_in(client, b.owner_user)
    base = f"/api/v1/bookings/{booking.id}/claims"

    upload = await client.post(f"{base}/evidence-upload", json={"content_type": "image/jpeg"})
    assert upload.status_code == 200, upload.text
    assert set(upload.json()) == UPLOAD_KEYS
    key = upload.json()["storage_key"]
    bad_type = await client.post(f"{base}/evidence-upload", json={"content_type": "text/html"})
    assert bad_type.status_code == 422

    for body in (
        {"kind": "theft", "description": "x"},
        {"kind": "damage", "description": "   "},
        {"kind": "damage", "description": "x", "amount_claimed_tzs": -1},
        {"kind": "damage", "description": "x", "evidence_keys": ["k"] * 11},
        {"kind": "damage", "description": "x", "evidence_keys": ["claims/other/a.jpg"]},
    ):
        assert (await client.post(base, json=body)).status_code == 422, body

    res = await client.post(
        base,
        json={"kind": "damage", "description": "Cracked screen", "evidence_keys": [key]},
    )
    assert res.status_code == 201, res.text
    assert set(res.json()) == CLAIM_KEYS
    assert res.json()["evidence_keys"] == [key]

    detail = (await client.get(f"/api/v1/bookings/{booking.id}")).json()
    assert detail["status"] == "disputed"
    assert [set(c) for c in detail["claims"]] == [CLAIM_KEYS]


async def test_party_endpoints_hide_bookings_from_others(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *FAR, **MONEY)
    sign_in(client, await make_user(db))
    for method, path, body in (
        ("GET", f"/api/v1/bookings/{booking.id}/cancel-preview", None),
        ("POST", f"/api/v1/bookings/{booking.id}/cancel", None),
        ("POST", f"/api/v1/bookings/{booking.id}/claims", {"kind": "dispute", "description": "x"}),
        ("POST", f"/api/v1/bookings/{uuid.uuid4()}/cancel", None),
    ):
        r = await client.request(method, path, json=body)
        assert r.status_code == 404, (path, r.status_code)


async def test_admin_bookings_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *FAR, **MONEY)
    sign_in(client, await make_admin(db))

    page = await client.get("/api/v1/admin/bookings", params={"q": booking.code})
    assert page.status_code == 200, page.text
    assert set(page.json()) == PAGE_KEYS
    [item] = page.json()["items"]
    assert set(item) == ADMIN_BOOKING_KEYS
    assert set(item["renter"]) == set(item["owner"]) == PARTY_KEYS
    by_phone = await client.get("/api/v1/admin/bookings", params={"q": b.renter.phone[-7:]})
    assert [i["id"] for i in by_phone.json()["items"]] == [str(booking.id)]
    assert (await client.get("/api/v1/admin/bookings", params={"status": "x"})).status_code == 422

    detail = await client.get(f"/api/v1/admin/bookings/{booking.id}")
    assert detail.status_code == 200 and detail.json()["role"] == "admin"
    assert (await client.get(f"/api/v1/admin/bookings/{uuid.uuid4()}")).status_code == 404

    url = f"/api/v1/admin/bookings/{booking.id}/refund"
    for body in (
        {"amount_tzs": 0, "reason": "x"},
        {"amount_tzs": 10, "reason": " "},
        {"amount_tzs": 10, "reason": "x", "source": "bank"},
    ):
        assert (await client.post(url, json=body)).status_code == 422, body
    refund = await client.post(url, json={"amount_tzs": 1_000, "reason": "Goodwill"})
    assert refund.status_code == 200, refund.text
    assert set(refund.json()) == REFUND_KEYS
    refund_id = refund.json()["id"]

    mark = f"/api/v1/admin/refunds/{refund_id}/mark-sent"
    assert (await client.post(mark, json={"provider_ref": "  "})).status_code == 422
    assert (await client.post(f"/api/v1/admin/refunds/{refund_id}/retry")).status_code == 409
    sent = await client.post(mark, json={"provider_ref": "MP-1"})
    assert sent.status_code == 200 and set(sent.json()) == REFUND_KEYS
    assert (await client.post(mark, json={"provider_ref": "MP-2"})).status_code == 409
    unknown = await client.post(f"/api/v1/admin/refunds/{uuid.uuid4()}/retry")
    assert unknown.status_code == 404

    cancel = await client.post(f"/api/v1/admin/bookings/{booking.id}/cancel")
    assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"
    # The goodwill refund already took 1,000 of platform revenue: never refund twice.
    amounts = sorted(r["amount_tzs"] for r in cancel.json()["refunds"])
    assert amounts == [1_000, 250_000 - 1_000]


async def test_admin_claims_shapes(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(
        db, b, *ENDED, status="completed", completed_at=ENDED[1], **MONEY
    )
    sign_in(client, b.renter)
    opened = await client.post(
        f"/api/v1/bookings/{booking.id}/claims",
        json={"kind": "dispute", "description": "Not as described"},
    )
    assert opened.status_code == 201, opened.text
    claim_id = opened.json()["id"]

    sign_in(client, await make_admin(db))
    page = await client.get("/api/v1/admin/claims")
    assert page.status_code == 200, page.text
    [claim] = page.json()["items"]
    assert set(claim) == ADMIN_CLAIM_KEYS
    assert set(claim["renter"]) == PARTY_KEYS
    assert (await client.get("/api/v1/admin/claims", params={"status": "x"})).status_code == 422

    url = f"/api/v1/admin/claims/{claim_id}/resolve"
    assert (await client.post(url, json={"resolution": "nope"})).status_code == 422
    assert (
        await client.post(url, json={"resolution": "split", "amount_awarded_tzs": 50_000})
    ).json()["error"]["code"] == "INVALID_AWARD"
    resolved = await client.post(url, json={"resolution": "renter_refunded"})
    assert resolved.status_code == 200, resolved.text
    assert set(resolved.json()) == ADMIN_CLAIM_KEYS
    unknown = await client.post(
        f"/api/v1/admin/claims/{uuid.uuid4()}/resolve", json={"resolution": "renter_refunded"}
    )
    assert unknown.status_code == 404


async def test_unauthenticated_and_non_admin(client: httpx.AsyncClient, db: AsyncSession) -> None:
    booking_id = uuid.uuid4()
    assert (await client.post(f"/api/v1/bookings/{booking_id}/cancel")).status_code == 401
    assert (await client.get(f"/api/v1/bookings/{booking_id}/cancel-preview")).status_code == 401
    for path in ("/api/v1/admin/bookings", "/api/v1/admin/claims"):
        assert (await client.get(path)).status_code == 401, path
    sign_in(client, await make_user(db))
    for path in ("/api/v1/admin/bookings", "/api/v1/admin/claims"):
        assert (await client.get(path)).status_code == 403, path
