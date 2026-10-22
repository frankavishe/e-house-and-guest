"""Owner listing management and listing moderation (T095, US3-AS1..3, FR-007, FR-009)."""

import io
import uuid
from datetime import date
from typing import Any

import httpx
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User, VerificationStatus
from app.admin.models import AdminAuditLog
from app.catalog.models import Category, Location
from app.integrations import get_storage
from app.jobs.models import Job
from app.listings.jobs import process_image
from app.listings.models import Listing, ListingPhoto
from app.listings.photos import PHOTO_MAX_BYTES
from tests.factories import (
    WAREHOUSE_SCHEMA,
    day_range,
    jpeg_with_exif,
    make_admin,
    make_bookable,
    make_booking,
    make_category,
    make_owner,
    make_place,
    make_user,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT


class World:
    owner_user: User
    owner: OwnerProfile
    admin: User
    category: Category
    region: Location
    district: Location


async def _world(db: AsyncSession, verification: str = "verified") -> World:
    w = World()
    w.owner_user = await make_user(db, name="Warehouse Owner")
    w.owner = await make_owner(db, user=w.owner_user, verification=verification)
    w.admin = await make_admin(db)
    w.category = await make_category(
        db,
        mode="LEASE",
        default_unit="month",
        price_units=["month"],
        attribute_schema=WAREHOUSE_SCHEMA,
    )
    w.region, w.district = await make_place(db, "Pwani")
    return w


async def _draft(client: httpx.AsyncClient, w: World) -> dict[str, Any]:
    sign_in(client, w.owner_user)
    r = await client.post("/api/v1/owner/listings", json={"category_id": str(w.category.id)})
    assert r.status_code == 201, r.text
    return r.json()


async def _upload_photo(client: httpx.AsyncClient, listing_id: str) -> dict[str, Any]:
    r = await client.post(
        f"/api/v1/owner/listings/{listing_id}/photos", json={"content_type": "image/jpeg"}
    )
    assert r.status_code == 201, r.text
    upload = r.json()
    await get_storage().put(upload["storage_key"], jpeg_with_exif(), "image/jpeg", private=True)
    r = await client.patch(
        f"/api/v1/owner/listings/{listing_id}/photos/{upload['photo_id']}",
        json={"confirmed": True, "alt_sw": "Ghala", "alt_en": "Warehouse"},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _complete(client: httpx.AsyncClient, w: World, listing_id: str) -> dict[str, Any]:
    """Fill in everything submit needs: text, location, attributes, a price and a photo."""
    r = await client.patch(
        f"/api/v1/owner/listings/{listing_id}",
        json={
            "title_sw": "Ghala A",
            "title_en": "Warehouse A",
            "description_sw": "Ghala kubwa karibu na barabara.",
            "region_id": w.region.id,
            "district_id": w.district.id,
            "attributes": {"floor_area": 450.5, "loading_bay": True},
            "deposit_tzs": 500_000,
            "cancellation_policy": "strict",
        },
    )
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/api/v1/owner/listings/{listing_id}/prices",
        json=[{"unit": "month", "amount_tzs": 1_200_000}],
    )
    assert r.status_code == 200, r.text
    await _upload_photo(client, listing_id)
    return (await client.get(f"/api/v1/owner/listings/{listing_id}")).json()


async def _approved(client: httpx.AsyncClient, w: World) -> str:
    listing_id = (await _draft(client, w))["id"]
    await _complete(client, w, listing_id)
    assert (await client.post(f"/api/v1/owner/listings/{listing_id}/submit")).is_success
    sign_in(client, w.admin)
    r = await client.post(f"/api/v1/admin/listings/{listing_id}/approve")
    assert r.status_code == 200, r.text
    sign_in(client, w.owner_user)
    return listing_id


async def _search_ids(client: httpx.AsyncClient, query: str) -> list[str]:
    r = await client.get(f"/api/v1/listings/search?{query}")
    assert r.status_code == 200, r.text
    return [item["id"] for item in r.json()["items"]]


# --- drafts, attributes, prices -----------------------------------------------------------


async def test_draft_validates_attributes_against_the_category_schema(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db)
    draft = await _draft(client, w)
    assert draft["status"] == "draft"
    assert draft["category"]["booking_mode"] == "LEASE"
    assert draft["instant_book"] is False
    assert set(draft["missing"]) >= {"title", "description", "location", "price", "photo"}

    r = await client.patch(
        f"/api/v1/owner/listings/{draft['id']}",
        json={"attributes": {"floor_area": "big", "colour": "red"}},
    )
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "INVALID_ATTRIBUTES"
    assert set(error["details"]["fields"]) == {"floor_area", "colour"}

    r = await client.patch(
        f"/api/v1/owner/listings/{draft['id']}", json={"attributes": {"loading_bay": True}}
    )
    assert r.status_code == 422 and set(r.json()["error"]["details"]["fields"]) == {"floor_area"}

    r = await client.patch(
        f"/api/v1/owner/listings/{draft['id']}",
        json={"attributes": {"floor_area": 300}, "instant_book": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["attributes"] == {"floor_area": 300}
    assert body["instant_book"] is False  # leases always need the owner's approval


async def test_draft_needs_a_leaf_category(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _world(db)
    group = await make_category(db, mode=None)
    sign_in(client, w.owner_user)
    r = await client.post("/api/v1/owner/listings", json={"category_id": str(group.id)})
    assert r.status_code == 422


async def test_prices_replace_with_unit_and_season_checks(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db)
    listing_id = (await _draft(client, w))["id"]
    url = f"/api/v1/owner/listings/{listing_id}/prices"

    r = await client.put(url, json=[{"unit": "night", "amount_tzs": 10_000}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "PRICE_UNIT_NOT_ALLOWED"

    overlapping = [
        {"unit": "month", "amount_tzs": 1_000_000},
        {
            "unit": "month",
            "amount_tzs": 1_500_000,
            "season_start": "2026-12-01",
            "season_end": "2027-01-31",
        },
        {
            "unit": "month",
            "amount_tzs": 1_400_000,
            "season_start": "2027-01-15",
            "season_end": "2027-02-28",
        },
    ]
    r = await client.put(url, json=overlapping)
    assert r.status_code == 422 and r.json()["error"]["code"] == "SEASON_OVERLAP"

    r = await client.put(url, json=overlapping[:2])
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["prices"]) == 2 and body["base_price_tzs"] == 1_000_000

    r = await client.put(url, json=[{"unit": "month", "amount_tzs": 0}])
    assert r.status_code == 422


# --- photos -------------------------------------------------------------------------------


async def test_photo_upload_confirm_and_image_job(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db)
    listing_id = (await _draft(client, w))["id"]

    r = await client.post(
        f"/api/v1/owner/listings/{listing_id}/photos", json={"content_type": "image/gif"}
    )
    assert r.status_code == 422  # jpeg, png or webp only

    r = await client.post(
        f"/api/v1/owner/listings/{listing_id}/photos", json={"content_type": "image/jpeg"}
    )
    upload = r.json()
    assert "/private/" in upload["upload_url"]
    not_uploaded = await client.patch(
        f"/api/v1/owner/listings/{listing_id}/photos/{upload['photo_id']}",
        json={"confirmed": True},
    )
    assert not_uploaded.status_code == 422  # nothing in storage yet

    photo = await _upload_photo(client, listing_id)
    assert photo["alt_en"] == "Warehouse" and photo["pending"] is False

    job = (await db.execute(select(Job).where(Job.kind == "image.process"))).scalars().all()
    assert [j.payload["photo_id"] for j in job] == [photo["id"]]

    await process_image(db, {"photo_id": photo["id"]})
    row = await db.get_one(ListingPhoto, uuid.UUID(photo["id"]))
    await db.refresh(row)
    assert set(row.variants) == {"320", "640", "1280"}
    storage = get_storage()
    for width, key in row.variants.items():
        image = Image.open(io.BytesIO(await storage.get(key)))
        assert image.format == "WEBP"
        assert image.width <= int(width)
        assert not image.getexif()  # EXIF (incl. GPS) stripped

    listed = (await client.get(f"/api/v1/owner/listings/{listing_id}")).json()
    assert listed["photos"][0]["url_640"].endswith(row.variants["640"])

    r = await client.delete(f"/api/v1/owner/listings/{listing_id}/photos/{photo['id']}")
    assert r.status_code == 204
    assert (await client.get(f"/api/v1/owner/listings/{listing_id}")).json()["photos"] == []


# --- submit & review ----------------------------------------------------------------------


async def test_submit_needs_photo_and_price(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _world(db)
    listing_id = (await _draft(client, w))["id"]
    r = await client.post(f"/api/v1/owner/listings/{listing_id}/submit")
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "LISTING_INCOMPLETE"
    assert {"price", "photo"} <= set(error["details"]["missing"])

    listing = await _complete(client, w, listing_id)
    assert listing["missing"] == []
    r = await client.post(f"/api/v1/owner/listings/{listing_id}/submit")
    assert r.status_code == 200 and r.json()["status"] == "pending_review"


async def test_owner_must_have_submitted_verification(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db, verification="draft")
    listing_id = (await _draft(client, w))["id"]
    await _complete(client, w, listing_id)
    r = await client.post(f"/api/v1/owner/listings/{listing_id}/submit")
    assert r.status_code == 409 and r.json()["error"]["code"] == "OWNER_NOT_SUBMITTED"


async def test_pending_listing_hidden_until_approved_and_owner_verified(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db, verification="pending")
    listing_id = (await _draft(client, w))["id"]
    await _complete(client, w, listing_id)
    assert (await client.post(f"/api/v1/owner/listings/{listing_id}/submit")).is_success
    slug = f"category={w.category.slug}"

    assert listing_id not in await _search_ids(client, slug)
    assert (await client.get(f"/api/v1/listings/{listing_id}")).status_code == 404

    sign_in(client, w.admin)
    queue = (await client.get("/api/v1/admin/listings")).json()["items"]
    item = next(i for i in queue if i["listing"]["id"] == listing_id)
    assert item["owner"]["verification_status"] == "pending" and item["diff"] is None
    r = await client.post(f"/api/v1/admin/listings/{listing_id}/approve")
    assert r.status_code == 200 and r.json()["status"] == "active"

    # Approved, but the owner is not verified yet: still hidden (queued until verified).
    assert listing_id not in await _search_ids(client, slug)
    w.owner.verification_status = VerificationStatus.VERIFIED
    await db.flush()
    assert listing_id in await _search_ids(client, slug)

    audit = (
        (
            await db.execute(
                select(AdminAuditLog.action).where(AdminAuditLog.target_id == uuid.UUID(listing_id))
            )
        )
        .scalars()
        .all()
    )
    assert audit == ["listing.approve"]


async def test_rejected_listing_can_be_fixed_and_resubmitted(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db)
    listing_id = (await _draft(client, w))["id"]
    await _complete(client, w, listing_id)
    await client.post(f"/api/v1/owner/listings/{listing_id}/submit")

    sign_in(client, w.admin)
    assert (await client.post(f"/api/v1/admin/listings/{listing_id}/reject")).status_code == 422
    r = await client.post(
        f"/api/v1/admin/listings/{listing_id}/reject", json={"reason": "Photos are blurry"}
    )
    assert r.status_code == 200 and r.json()["status"] == "rejected"

    sign_in(client, w.owner_user)
    mine = (await client.get(f"/api/v1/owner/listings/{listing_id}")).json()
    assert mine["rejection_reason"] == "Photos are blurry"
    r = await client.patch(f"/api/v1/owner/listings/{listing_id}", json={"title_sw": "Ghala B"})
    assert r.json()["title_sw"] == "Ghala B" and r.json()["status"] == "rejected"
    r = await client.post(f"/api/v1/owner/listings/{listing_id}/submit")
    assert r.json()["status"] == "pending_review"


async def test_material_edit_waits_for_review_while_approved_values_stay_live(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db)
    listing_id = await _approved(client, w)

    r = await client.patch(
        f"/api/v1/owner/listings/{listing_id}",
        json={"title_sw": "Ghala Jipya", "deposit_tzs": 250_000},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "active" and body["review_state"] == "pending"
    assert body["title_sw"] == "Ghala A"  # live value unchanged
    assert body["pending_changes"] == {"title_sw": "Ghala Jipya"}
    assert body["deposit_tzs"] == 250_000  # non-material: applied immediately

    public = (await client.get(f"/api/v1/listings/{listing_id}")).json()
    assert public["title"] == "Ghala A" and public["deposit_tzs"] == 250_000
    assert listing_id in await _search_ids(client, f"category={w.category.slug}")

    sign_in(client, w.admin)
    queue = (await client.get("/api/v1/admin/listings")).json()["items"]
    item = next(i for i in queue if i["listing"]["id"] == listing_id)
    assert item["diff"] == {"title_sw": {"before": "Ghala A", "after": "Ghala Jipya"}}
    assert (await client.post(f"/api/v1/admin/listings/{listing_id}/approve")).is_success

    public = (await client.get(f"/api/v1/listings/{listing_id}")).json()
    assert public["title"] == "Ghala Jipya"

    # A second material edit, rejected: the change is dropped and the reason kept.
    sign_in(client, w.owner_user)
    await client.patch(
        f"/api/v1/owner/listings/{listing_id}", json={"attributes": {"floor_area": 9000}}
    )
    sign_in(client, w.admin)
    r = await client.post(
        f"/api/v1/admin/listings/{listing_id}/reject", json={"reason": "Area looks wrong"}
    )
    assert r.status_code == 200 and r.json()["status"] == "active"
    sign_in(client, w.owner_user)
    mine = (await client.get(f"/api/v1/owner/listings/{listing_id}")).json()
    assert mine["review_state"] == "rejected" and mine["pending_changes"] is None
    assert mine["rejection_reason"] == "Area looks wrong"
    assert mine["attributes"]["floor_area"] == 450.5


async def test_price_only_edit_applies_immediately(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db)
    listing_id = await _approved(client, w)
    r = await client.put(
        f"/api/v1/owner/listings/{listing_id}/prices",
        json=[{"unit": "month", "amount_tzs": 900_000}],
    )
    assert r.status_code == 200
    assert r.json()["review_state"] == "none" and r.json()["base_price_tzs"] == 900_000
    public = (await client.get(f"/api/v1/listings/{listing_id}")).json()
    assert public["base_price"]["amount_tzs"] == 900_000


async def test_new_photo_on_live_listing_needs_review(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    w = await _world(db)
    listing_id = await _approved(client, w)
    photo = await _upload_photo(client, listing_id)
    assert photo["pending"] is True
    mine = (await client.get(f"/api/v1/owner/listings/{listing_id}")).json()
    assert mine["review_state"] == "pending"
    assert len((await client.get(f"/api/v1/listings/{listing_id}")).json()["photos"]) == 1

    sign_in(client, w.admin)
    assert (await client.post(f"/api/v1/admin/listings/{listing_id}/approve")).is_success
    assert len((await client.get(f"/api/v1/listings/{listing_id}")).json()["photos"]) == 2


async def test_suspend_and_unsuspend(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _world(db)
    listing_id = await _approved(client, w)
    sign_in(client, w.admin)
    assert (await client.post(f"/api/v1/admin/listings/{listing_id}/suspend")).status_code == 422
    r = await client.post(
        f"/api/v1/admin/listings/{listing_id}/suspend", json={"reason": "Reported as fake"}
    )
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    assert (await client.get(f"/api/v1/listings/{listing_id}")).status_code == 404

    sign_in(client, w.owner_user)
    resume = await client.post(f"/api/v1/owner/listings/{listing_id}/resume")
    assert resume.status_code == 409  # only an admin lifts a suspension

    sign_in(client, w.admin)
    r = await client.post(f"/api/v1/admin/listings/{listing_id}/unsuspend")
    assert r.status_code == 200 and r.json()["status"] == "active"


# --- pause, delete, ownership -------------------------------------------------------------


async def test_pause_and_resume(client: httpx.AsyncClient, db: AsyncSession) -> None:
    w = await _world(db)
    listing_id = await _approved(client, w)
    slug = f"category={w.category.slug}"
    r = await client.post(f"/api/v1/owner/listings/{listing_id}/pause")
    assert r.status_code == 200 and r.json()["status"] == "paused"
    assert listing_id not in await _search_ids(client, slug)
    r = await client.post(f"/api/v1/owner/listings/{listing_id}/resume")
    assert r.json()["status"] == "active"
    assert listing_id in await _search_ids(client, slug)


async def test_delete_refused_with_future_confirmed_bookings(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db, "DATE_RANGE", unit="day")
    await make_booking(
        db, b, *day_range(date(2026, 12, 10), date(2026, 12, 12)), status="confirmed"
    )
    sign_in(client, b.owner_user)
    r = await client.delete(f"/api/v1/owner/listings/{b.listing.id}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "LISTING_HAS_BOOKINGS"

    other = await make_bookable(db, "DATE_RANGE", unit="day")
    sign_in(client, other.owner_user)
    assert (await client.delete(f"/api/v1/owner/listings/{other.listing.id}")).status_code == 204
    row = await db.get_one(Listing, other.listing.id)
    await db.refresh(row)
    assert row.status.value == "deleted"
    mine = (await client.get("/api/v1/owner/listings")).json()["items"]
    assert str(other.listing.id) not in [m["id"] for m in mine]


async def test_other_owners_listing_is_not_found(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    sign_in(client, await make_user(db))
    assert (await client.get(f"/api/v1/owner/listings/{b.listing.id}")).status_code == 403
    intruder = await make_owner(db)
    sign_in(client, await db.get_one(User, intruder.user_id))
    for r in (
        await client.get(f"/api/v1/owner/listings/{b.listing.id}"),
        await client.patch(f"/api/v1/owner/listings/{b.listing.id}", json={"stock": 2}),
        await client.post(f"/api/v1/owner/listings/{b.listing.id}/pause"),
    ):
        assert r.status_code == 404


# --- blocks & calendar --------------------------------------------------------------------


async def test_owner_block_makes_dates_unavailable(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db, "DATE_RANGE", unit="day")
    sign_in(client, b.owner_user)
    url = f"/api/v1/owner/listings/{b.listing.id}/blocks"
    r = await client.post(
        url, json={"start_date": "2026-12-01", "end_date": "2026-12-05", "note": "Repairs"}
    )
    assert r.status_code == 201, r.text
    block = r.json()
    assert block["note"] == "Repairs"

    category = f"category={b.category.slug}"
    blocked = f"{category}&start_date=2026-12-01&end_date=2026-12-05"
    later = f"{category}&start_date=2026-12-06&end_date=2026-12-08"
    assert str(b.listing.id) not in await _search_ids(client, blocked)
    assert str(b.listing.id) in await _search_ids(client, later)
    availability = (
        await client.get(
            f"/api/v1/listings/{b.listing.id}/availability?from=2026-11-28&to=2026-12-10"
        )
    ).json()
    assert {"start_date": "2026-12-01", "end_date": "2026-12-06"} in availability["unavailable"]

    assert len((await client.get(url)).json()) == 1
    assert (await client.delete(f"{url}/{block['id']}")).status_code == 204
    assert str(b.listing.id) in await _search_ids(client, blocked)


async def test_block_over_a_booking_is_refused(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db, "DATE_RANGE", unit="day")
    await make_booking(
        db, b, *day_range(date(2026, 12, 10), date(2026, 12, 12)), status="confirmed"
    )
    sign_in(client, b.owner_user)
    r = await client.post(
        f"/api/v1/owner/listings/{b.listing.id}/blocks",
        json={"start_date": "2026-12-11", "end_date": "2026-12-11"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "SLOT_TAKEN"


async def test_quantity_block_reserves_stock(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db, "QUANTITY", stock=5)
    sign_in(client, b.owner_user)
    url = f"/api/v1/owner/listings/{b.listing.id}/blocks"
    span = {"start_date": "2026-12-01", "end_date": "2026-12-02"}
    assert (await client.post(url, json={**span, "quantity": 2})).status_code == 201
    stock = (
        await client.get(
            f"/api/v1/listings/{b.listing.id}/availability?from=2026-12-01&to=2026-12-01"
        )
    ).json()["stock"]
    assert stock == [{"date": "2026-12-01", "available": 3}]
    r = await client.post(url, json={**span, "quantity": 4})
    assert r.status_code == 409 and r.json()["error"]["code"] == "INSUFFICIENT_STOCK"


async def test_calendar_lists_bookings_and_blocks(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db, "DATE_RANGE", unit="day")
    booking = await make_booking(
        db, b, *day_range(date(2026, 12, 10), date(2026, 12, 12)), status="confirmed"
    )
    await make_booking(  # outside the range
        db, b, *day_range(date(2027, 2, 10), date(2027, 2, 12)), status="confirmed"
    )
    sign_in(client, b.owner_user)
    await client.post(
        f"/api/v1/owner/listings/{b.listing.id}/blocks",
        json={"start_date": "2026-12-01", "end_date": "2026-12-03"},
    )
    r = await client.get("/api/v1/owner/calendar?from=2026-12-01&to=2026-12-31")
    assert r.status_code == 200, r.text
    cal = r.json()
    assert [entry["id"] for entry in cal["listings"]] == [str(b.listing.id)]
    assert [entry["code"] for entry in cal["bookings"]] == [booking.code]
    assert cal["bookings"][0]["renter_name"] == "Renter Person"
    assert len(cal["blocks"]) == 1 and cal["blocks"][0]["listing_id"] == str(b.listing.id)


async def test_photo_confirm_checks_the_upload(client: httpx.AsyncClient, db: AsyncSession) -> None:
    listing = await _draft(client, await _world(db))
    r = await client.post(
        f"/api/v1/owner/listings/{listing['id']}/photos", json={"content_type": "image/jpeg"}
    )
    upload = r.json()
    confirm = f"/api/v1/owner/listings/{listing['id']}/photos/{upload['photo_id']}"
    r = await client.patch(confirm, json={"confirmed": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "PHOTO_NOT_UPLOADED"

    storage = get_storage()
    big = b"x" * (PHOTO_MAX_BYTES + 1)
    await storage.put(upload["storage_key"], big, "image/jpeg", private=True)
    r = await client.patch(confirm, json={"confirmed": True})
    assert r.status_code == 422 and r.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert r.json()["error"]["details"] == {"max_mb": 15}
    assert await storage.size(upload["storage_key"], private=True) is None
