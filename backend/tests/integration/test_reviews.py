"""Reviews, rating averages and abuse reports (T126, US6-AS1..2, FR-029, FR-030, V15)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User
from app.listings.models import Listing
from app.notifications.models import Channel, Notification
from app.reviews.models import AbuseReport, ReportStatus
from tests.factories import (
    Bookable,
    day_range,
    make_admin,
    make_bookable,
    make_booking,
    make_user,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

PAST = day_range(date(2026, 10, 20), date(2026, 10, 23))
EARLIER = day_range(date(2026, 10, 10), date(2026, 10, 12))
FAR = day_range(date(2026, 11, 20), date(2026, 11, 23))


async def _review(
    client: httpx.AsyncClient, user: User, booking_id: uuid.UUID, rating: int, body: str = ""
) -> httpx.Response:
    sign_in(client, user)
    payload: dict[str, Any] = {"rating": rating}
    if body:
        payload["body"] = body
    return await client.post(f"/api/v1/bookings/{booking_id}/reviews", json=payload)


async def _fresh[T](db: AsyncSession, model: type[T], id_: uuid.UUID) -> T:
    row = await db.get(model, id_, populate_existing=True)
    assert row is not None
    return row


async def _can_review(client: httpx.AsyncClient, user: User, booking_id: uuid.UUID) -> bool:
    sign_in(client, user)
    r = await client.get(f"/api/v1/bookings/{booking_id}")
    assert r.status_code == 200, r.text
    can: bool = r.json()["can"]["review"]
    return can


async def test_renter_review_updates_listing_and_owner(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *PAST, status="completed")
    assert await _can_review(client, b.renter, booking.id)

    r = await _review(client, b.renter, booking.id, 4, "Safi sana")
    assert r.status_code == 201, r.text
    assert r.json()["rating"] == 4
    assert r.json()["comment"] == "Safi sana"

    listing = await _fresh(db, Listing, b.listing.id)
    assert (listing.rating_avg, listing.rating_count) == (Decimal("4.00"), 1)
    owner = await _fresh(db, OwnerProfile, b.owner.id)
    assert (owner.rating_avg, owner.rating_count) == (Decimal("4.00"), 1)
    assert not await _can_review(client, b.renter, booking.id)

    detail = (await client.get(f"/api/v1/listings/{b.listing.id}")).json()
    assert detail["rating_avg"] == 4.0
    assert [(x["rating"], x["comment"]) for x in detail["reviews"]] == [(4, "Safi sana")]
    page = (await client.get(f"/api/v1/listings/{b.listing.id}/reviews")).json()
    assert page["total"] == 1
    assert page["items"][0]["author"] == "Renter"  # first name only


async def test_averages_across_bookings(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    first = await make_booking(db, b, *EARLIER, status="completed")
    other_renter = await make_user(db, name="Second Renter")
    b2 = Bookable()
    b2.__dict__.update(b.__dict__)
    b2.renter = other_renter
    second = await make_booking(db, b2, *PAST, status="completed")

    assert (await _review(client, b.renter, first.id, 4)).status_code == 201
    assert (await _review(client, other_renter, second.id, 5)).status_code == 201
    listing = await _fresh(db, Listing, b.listing.id)
    assert (listing.rating_avg, listing.rating_count) == (Decimal("4.50"), 2)


async def test_owner_reviews_renter(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *PAST, status="completed")
    assert await _can_review(client, b.owner_user, booking.id)
    r = await _review(client, b.owner_user, booking.id, 5, "Mpangaji mzuri")
    assert r.status_code == 201, r.text
    assert r.json()["author"] == b.owner.display_name

    renter = await _fresh(db, User, b.renter.id)
    assert (renter.rating_avg, renter.rating_count) == (Decimal("5.00"), 1)
    listing = await _fresh(db, Listing, b.listing.id)
    assert listing.rating_count == 0  # an owner's review is about the renter, not the listing

    reviews = (await client.get(f"/api/v1/users/{b.renter.id}/reviews")).json()
    assert [(x["rating"], x["about"]) for x in reviews["items"]] == [(5, "renter")]
    assert reviews["profile"]["renter_rating_avg"] == 5.0

    # The renter's review is about the owner's listing, so it shows on the owner's profile.
    assert (await _review(client, b.renter, booking.id, 3)).status_code == 201
    owner_reviews = (await client.get(f"/api/v1/users/{b.owner_user.id}/reviews")).json()
    assert [(x["rating"], x["about"]) for x in owner_reviews["items"]] == [(3, "owner")]
    assert owner_reviews["profile"]["owner"]["display_name"] == b.owner.display_name
    assert owner_reviews["profile"]["owner"]["rating_avg"] == 3.0


async def test_one_review_per_author_per_booking(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *PAST, status="completed")
    assert (await _review(client, b.renter, booking.id, 4)).status_code == 201
    again = await _review(client, b.renter, booking.id, 1)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "ALREADY_REVIEWED"


@pytest.mark.parametrize("status", ["confirmed", "requested", "cancelled", "disputed"])
async def test_review_requires_completed_booking(
    client: httpx.AsyncClient, db: AsyncSession, status: str
) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *FAR, status=status)
    assert not await _can_review(client, b.renter, booking.id)
    r = await _review(client, b.renter, booking.id, 4)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "REVIEW_NOT_ALLOWED"


async def test_review_requires_a_party(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *PAST, status="completed")
    stranger = await make_user(db)
    assert (await _review(client, stranger, booking.id, 4)).status_code == 404
    admin = await make_admin(db)
    assert (await _review(client, admin, booking.id, 4)).status_code == 403
    client.cookies.clear()
    r = await client.post(f"/api/v1/bookings/{booking.id}/reviews", json={"rating": 4})
    assert r.status_code == 401


async def test_review_notifies_the_subject(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *PAST, status="completed")
    await _review(client, b.renter, booking.id, 4)
    rows = await db.execute(
        select(Notification).where(
            Notification.user_id == b.owner_user.id,
            Notification.event == "review.received",
            Notification.channel == Channel.IN_APP,
        )
    )
    note = rows.scalars().one()
    assert note.payload["booking_id"] == str(booking.id)
    assert note.payload["rating"] == 4


async def test_unknown_or_hidden_review_targets(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    assert (await client.get(f"/api/v1/listings/{uuid.uuid4()}/reviews")).status_code == 404
    assert (await client.get(f"/api/v1/users/{uuid.uuid4()}/reviews")).status_code == 404
    suspended = await make_user(db, status="suspended")
    assert (await client.get(f"/api/v1/users/{suspended.id}/reviews")).status_code == 404


# --- abuse reports (FR-030) ---------------------------------------------------------------


async def _report(
    client: httpx.AsyncClient, kind: str, target: uuid.UUID, reason: str = "Tangazo la uongo"
) -> httpx.Response:
    return await client.post(
        "/api/v1/reports", json={"target_kind": kind, "target_id": str(target), "reason": reason}
    )


async def test_report_listing_and_user(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    sign_in(client, b.renter)
    r = await _report(client, "listing", b.listing.id)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "open"
    report = await db.get(AbuseReport, uuid.UUID(r.json()["id"]))
    assert report is not None
    assert report.reporter_id == b.renter.id and report.status == ReportStatus.OPEN

    assert (await _report(client, "user", b.owner_user.id, "Matusi")).status_code == 201
    dup = await _report(client, "listing", b.listing.id)
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "ALREADY_REPORTED"


async def test_report_validation(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    assert (await _report(client, "listing", b.listing.id)).status_code == 401
    sign_in(client, b.renter)
    assert (await _report(client, "listing", uuid.uuid4())).status_code == 404
    assert (await _report(client, "user", uuid.uuid4())).status_code == 404
    assert (await _report(client, "user", b.renter.id)).status_code == 422  # yourself
    assert (await _report(client, "listing", b.listing.id, "")).status_code == 422
    assert (await _report(client, "booking", b.listing.id)).status_code == 422
