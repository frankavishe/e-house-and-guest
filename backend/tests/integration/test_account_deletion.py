"""Account deletion and anonymisation (T141, FR-033, R18)."""

from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.deletion import ANONYMISE_JOB, DELETED_NAME, anonymise, tombstone
from app.accounts.models import OwnerProfile, PayoutMethod, RefreshToken, User, UserStatus
from app.bookings.models import Booking
from app.core import security
from app.integrations import get_storage
from app.jobs.models import Job
from app.ledger.models import LedgerEntry
from app.listings.models import Listing, ListingStatus
from app.messaging.models import Conversation, Message
from tests.factories import (
    day_range,
    make_bookable,
    make_booking,
    make_completed_booking,
    make_payout_method,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

PAST = day_range(date(2026, 10, 1), date(2026, 10, 4))
FUTURE = day_range(date(2026, 11, 20), date(2026, 11, 23))


async def _delete_me(client: httpx.AsyncClient, user: User) -> httpx.Response:
    sign_in(client, user)
    return await client.delete("/api/v1/me")


async def test_active_booking_blocks_deletion(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    await make_booking(db, b, *FUTURE, status="confirmed")
    for user in (b.renter, b.owner_user):  # either party
        r = await _delete_me(client, user)
        assert r.status_code == 409 and r.json()["error"]["code"] == "ACTIVE_BOOKINGS"
        await db.refresh(user)
        assert user.status == UserStatus.ACTIVE


async def test_renter_deletion_anonymises_and_keeps_records(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_completed_booking(
        db, b, *PAST, completed_at=datetime(2026, 10, 4, 8, tzinfo=UTC)
    )
    sign_in(client, b.renter)
    r = await client.post(
        "/api/v1/conversations", json={"listing_id": str(b.listing.id), "body": "Habari"}
    )
    assert r.status_code == 201
    renter, phone = b.renter, b.renter.phone
    renter.email = "renter@example.com"
    db.add(RefreshToken(user_id=renter.id, token_hash="h", family_id=renter.id, expires_at=PAST[1]))
    await db.flush()

    r = await _delete_me(client, renter)
    assert r.status_code == 202, r.text
    cleared = {c.split("=")[0] for c in r.headers.get_list("set-cookie")}
    assert cleared == {security.ACCESS_COOKIE, security.REFRESH_COOKIE}

    await db.refresh(renter)
    assert renter.status == UserStatus.DELETED
    assert (renter.name, renter.phone, renter.email) == (DELETED_NAME, tombstone(phone), None)
    assert await db.scalar(select(func.count()).select_from(RefreshToken)) == 0
    assert (await client.get("/api/v1/me")).status_code == 401
    job = (await db.execute(select(Job).where(Job.kind == ANONYMISE_JOB))).scalar_one()

    await anonymise(db, job.payload)
    await anonymise(db, job.payload)  # a re-run is harmless
    assert await db.scalar(select(func.count()).select_from(Conversation)) == 0
    assert await db.scalar(select(func.count()).select_from(Message)) == 0
    # Financial records stay, pointing at the anonymised user.
    kept = await db.get(Booking, booking.id)
    assert kept is not None and kept.renter_id == renter.id
    ledger_rows = await db.scalar(
        select(func.count()).select_from(LedgerEntry).where(LedgerEntry.booking_id == booking.id)
    )
    assert ledger_rows

    # The phone number is free for a new account.
    r = await client.post("/api/v1/auth/otp/request", json={"phone": phone})
    assert r.status_code == 202


async def test_owner_deletion_removes_documents_and_listings(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    storage = get_storage()
    key = f"owner-docs/{b.owner.id}/nida.jpg"
    await storage.put(key, b"jpg", "image/jpeg", private=True)
    b.owner.documents = [key]
    b.owner.nida_number_enc = b"secret"
    await make_payout_method(db, b.owner)
    await db.flush()

    r = await _delete_me(client, b.owner_user)
    assert r.status_code == 202, r.text
    job = (await db.execute(select(Job).where(Job.kind == ANONYMISE_JOB))).scalar_one()
    await anonymise(db, job.payload)

    owner = await db.get(OwnerProfile, b.owner.id)
    assert owner is not None
    await db.refresh(owner)
    assert owner.documents == [] and owner.nida_number_enc is None
    assert owner.display_name == DELETED_NAME
    assert await storage.size(key, private=True) is None
    assert await db.scalar(select(func.count()).select_from(PayoutMethod)) == 0
    listing = await db.get(Listing, b.listing.id)
    assert listing is not None
    await db.refresh(listing)
    assert listing.status == ListingStatus.DELETED
    r = await client.get(f"/api/v1/listings/{b.listing.id}")
    assert r.status_code == 404
