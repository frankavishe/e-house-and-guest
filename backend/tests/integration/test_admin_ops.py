"""Admin operations (T133, FR-030, FR-031, FR-032): user suspension, abuse reports, the
attention flag on bookings, stats by month/category/region, and the audit trail."""

import csv
import io
from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User, UserStatus
from app.admin.models import AdminAuditLog
from app.bookings.models import Booking, BookingStatus
from app.ledger import service as ledger
from app.ledger.models import EntryType, LedgerEntry
from app.reviews.models import AbuseReport, ReportStatus, ReportTarget
from tests.conftest import FrozenClock
from tests.factories import (
    Bookable,
    day_range,
    make_admin,
    make_bookable,
    make_paid_booking,
    make_user,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

FUTURE = day_range(date(2026, 11, 20), date(2026, 11, 23))


async def _audit_count(db: AsyncSession, action: str) -> int:
    total = await db.execute(
        select(func.count()).select_from(AdminAuditLog).where(AdminAuditLog.action == action)
    )
    return int(total.scalar_one())


# --- users --------------------------------------------------------------------------------


async def test_suspend_and_unsuspend_user(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *FUTURE)
    admin = await make_admin(db)
    sign_in(client, admin)

    found = (await client.get("/api/v1/admin/users", params={"q": b.renter.phone[-7:]})).json()
    assert [u["id"] for u in found["items"]] == [str(b.renter.id)]
    assert found["items"][0]["status"] == "active"

    r = await client.post(f"/api/v1/admin/users/{b.renter.id}/suspend", json={"reason": "Ulaghai"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "suspended"
    again = await client.post(f"/api/v1/admin/users/{b.renter.id}/suspend", json={"reason": "x"})
    assert again.status_code == 409

    # The suspended user is locked out; their future booking is kept but flagged.
    sign_in(client, b.renter)
    me = await client.get("/api/v1/me")
    assert me.status_code == 403
    assert me.json()["error"]["code"] == "ACCOUNT_SUSPENDED"
    await db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED

    sign_in(client, admin)
    flagged = (await client.get("/api/v1/admin/bookings", params={"attention": "true"})).json()
    assert [i["id"] for i in flagged["items"]] == [str(booking.id)]
    assert flagged["items"][0]["attention"] is True

    r = await client.post(f"/api/v1/admin/users/{b.renter.id}/unsuspend")
    assert r.status_code == 200
    assert r.json()["status"] == "active"
    flagged = (await client.get("/api/v1/admin/bookings", params={"attention": "true"})).json()
    assert flagged["items"] == []
    assert await _audit_count(db, "user.suspend") == 1
    assert await _audit_count(db, "user.unsuspend") == 1


async def test_suspended_owner_listings_leave_search(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    admin = await make_admin(db)
    sign_in(client, admin)
    await client.post(f"/api/v1/admin/users/{b.owner_user.id}/suspend", json={"reason": "x"})
    client.cookies.clear()
    assert (await client.get(f"/api/v1/listings/{b.listing.id}")).status_code == 404


async def test_admins_cannot_be_suspended(client: httpx.AsyncClient, db: AsyncSession) -> None:
    admin = await make_admin(db)
    other = await make_admin(db)
    sign_in(client, admin)
    r = await client.post(f"/api/v1/admin/users/{other.id}/suspend", json={"reason": "x"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "INVALID_TRANSITION"


async def test_listing_suspension_flags_future_bookings(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *FUTURE)
    past = await make_paid_booking(
        db, b, *day_range(date(2026, 10, 1), date(2026, 10, 3)), status="completed"
    )
    sign_in(client, await make_admin(db))
    r = await client.post(
        f"/api/v1/admin/listings/{b.listing.id}/suspend", json={"reason": "Picha za uongo"}
    )
    assert r.status_code == 200, r.text
    await db.refresh(booking)
    assert booking.status == BookingStatus.CONFIRMED

    rows = (await client.get("/api/v1/admin/bookings")).json()["items"]
    attention = {i["id"]: i["attention"] for i in rows}
    assert attention[str(booking.id)] is True
    assert attention[str(past.id)] is False


# --- abuse reports ------------------------------------------------------------------------


async def test_abuse_report_queue_and_actions(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    reporters = [await make_user(db) for _ in range(2)]
    listing_reports = []
    for reporter in reporters:
        sign_in(client, reporter)
        r = await client.post(
            "/api/v1/reports",
            json={"target_kind": "listing", "target_id": str(b.listing.id), "reason": "Uongo"},
        )
        assert r.status_code == 201
        listing_reports.append(r.json()["id"])
    sign_in(client, reporters[0])
    user_report = (
        await client.post(
            "/api/v1/reports",
            json={"target_kind": "user", "target_id": str(b.owner_user.id), "reason": "Matusi"},
        )
    ).json()["id"]

    admin = await make_admin(db)
    sign_in(client, admin)
    queue = (await client.get("/api/v1/admin/reports-abuse")).json()
    assert queue["total"] == 3
    first = queue["items"][0]
    assert first["id"] == listing_reports[0]  # oldest first
    assert first["target_label"] == b.listing.title_sw
    assert first["target_status"] == "active"
    assert first["open_reports_on_target"] == 2
    assert first["reporter"]["id"] == str(reporters[0].id)

    # Dismiss the user report.
    r = await client.post(
        f"/api/v1/admin/reports-abuse/{user_report}/action", json={"decision": "dismissed"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dismissed"
    owner = await db.get(User, b.owner_user.id)
    assert owner is not None and owner.status == UserStatus.ACTIVE

    # Action a listing report with suspension: every open report on the listing closes.
    r = await client.post(
        f"/api/v1/admin/reports-abuse/{listing_reports[0]}/action",
        json={"decision": "actioned", "suspend_target": True, "note": "Tangazo la uongo"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "actioned"
    assert r.json()["target_status"] == "suspended"
    statuses = (
        await db.execute(
            select(AbuseReport.status).where(
                AbuseReport.target_kind == ReportTarget.LISTING,
                AbuseReport.target_id == b.listing.id,
            )
        )
    ).scalars()
    assert set(statuses) == {ReportStatus.ACTIONED}

    again = await client.post(
        f"/api/v1/admin/reports-abuse/{listing_reports[1]}/action", json={"decision": "dismissed"}
    )
    assert again.status_code == 409
    assert (await client.get("/api/v1/admin/reports-abuse")).json()["total"] == 0
    handled = (
        await client.get("/api/v1/admin/reports-abuse", params={"status": "actioned"})
    ).json()
    assert handled["total"] == 2
    assert await _audit_count(db, "report.actioned") == 1
    assert await _audit_count(db, "report.dismissed") == 1
    assert await _audit_count(db, "listing.suspend") == 1


async def test_actioning_a_user_report_can_suspend_the_user(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    sign_in(client, b.renter)
    report = (
        await client.post(
            "/api/v1/reports",
            json={"target_kind": "user", "target_id": str(b.owner_user.id), "reason": "Matusi"},
        )
    ).json()["id"]
    sign_in(client, await make_admin(db))
    r = await client.post(
        f"/api/v1/admin/reports-abuse/{report}/action",
        json={"decision": "actioned", "suspend_target": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["target_status"] == "suspended"
    owner = await db.get(User, b.owner_user.id)
    assert owner is not None and owner.status == UserStatus.SUSPENDED


# --- stats --------------------------------------------------------------------------------


async def test_stats_match_the_ledger(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    a = await make_bookable(db, price=100_000)
    c = await make_bookable(db, "QUANTITY", price=20_000, renter_fee_bps=500)
    frozen_clock.set(datetime(2026, 10, 5, 8, 0, tzinfo=UTC))
    oct_booking = await make_paid_booking(
        db, a, *day_range(date(2026, 10, 10), date(2026, 10, 12)), total=200_000, deposit=50_000
    )
    frozen_clock.set(datetime(2026, 11, 1, 8, 0, tzinfo=UTC))
    await make_paid_booking(
        db, c, *day_range(date(2026, 11, 10), date(2026, 11, 12)), total=40_000, service_fee=2_000
    )
    await make_paid_booking(db, a, *FUTURE, total=300_000)
    # A refund out of platform revenue on the October booking, sent in November.
    await ledger.post_refund(db, oct_booking, 10_000, None, None, source=ledger.PLATFORM_REVENUE)
    frozen_clock.set(datetime(2026, 11, 2, 6, 0, tzinfo=UTC))
    await db.flush()

    sign_in(client, await make_admin(db))
    params = {"from": "2026-10-01", "to": "2026-11-30"}
    by_month = await client.get("/api/v1/admin/stats", params={**params, "group_by": "month"})
    assert by_month.status_code == 200, by_month.text
    body = by_month.json()
    months = {row["key"]: row for row in body["rows"]}
    assert set(months) == {"2026-10", "2026-11"}
    assert months["2026-10"]["bookings"] == 1
    assert months["2026-10"]["gbv_tzs"] == 200_000
    assert months["2026-10"]["commission_tzs"] == 20_000
    assert months["2026-11"]["bookings"] == 2
    assert months["2026-11"]["gbv_tzs"] == 342_000
    assert months["2026-11"]["refunds_tzs"] == 10_000
    # Commission is net platform revenue: commission + service fee - refunds it paid.
    assert months["2026-11"]["commission_tzs"] == 4_000 + 2_000 + 30_000 - 10_000

    # Totals equal the ledger, whatever the grouping.
    ledger_revenue = -(
        await db.execute(
            select(func.sum(LedgerEntry.amount_tzs)).where(
                LedgerEntry.account == ledger.PLATFORM_REVENUE,
                LedgerEntry.booking_id.in_([b.id for b in await _bookings_of(db, a, c)]),
            )
        )
    ).scalar_one()
    for group_by in ("month", "category", "region"):
        data = (
            await client.get("/api/v1/admin/stats", params={**params, "group_by": group_by})
        ).json()
        assert data["totals"]["commission_tzs"] == ledger_revenue, group_by
        assert data["totals"]["gbv_tzs"] == 542_000
        assert data["totals"]["bookings"] == 3
        assert sum(row["gbv_tzs"] for row in data["rows"]) == 542_000

    by_category = (
        await client.get("/api/v1/admin/stats", params={**params, "group_by": "category"})
    ).json()
    assert {row["gbv_tzs"] for row in by_category["rows"]} == {500_000, 42_000}

    # Range filters by when the money moved (EAT dates, `to` inclusive).
    oct_only = (
        await client.get("/api/v1/admin/stats", params={"from": "2026-10-01", "to": "2026-10-31"})
    ).json()
    assert oct_only["totals"]["gbv_tzs"] == 200_000

    bad = await client.get("/api/v1/admin/stats", params={"from": "2026-11-30", "to": "2026-10-01"})
    assert bad.status_code == 422


async def _bookings_of(db: AsyncSession, *bookables: Bookable) -> list[Booking]:
    listing_ids = [b.listing.id for b in bookables]
    rows = await db.execute(select(Booking).where(Booking.listing_id.in_(listing_ids)))
    return list(rows.scalars())


async def test_stats_payouts_and_csv(client: httpx.AsyncClient, db: AsyncSession) -> None:
    from app.payouts.models import Payout, PayoutItem, PayoutItemKind, PayoutStatus

    b = await make_bookable(db)
    booking = await make_paid_booking(
        db, b, *day_range(date(2026, 10, 25), date(2026, 10, 27)), status="completed"
    )
    payout = Payout(
        owner_profile_id=b.owner.id,
        amount_tzs=90_000,
        status=PayoutStatus.PAID,
        paid_at=datetime(2026, 11, 2, 6, 0, tzinfo=UTC),
    )
    db.add(payout)
    await db.flush()
    db.add(
        PayoutItem(
            payout_id=payout.id,
            booking_id=booking.id,
            kind=PayoutItemKind.EARNINGS,
            amount_tzs=90_000,
        )
    )
    await ledger.post_payout(db, b.owner.id, 90_000, payout.id)

    sign_in(client, await make_admin(db))
    params = {"from": "2026-10-01", "to": "2026-11-30", "group_by": "region"}
    data = (await client.get("/api/v1/admin/stats", params=params)).json()
    assert data["totals"]["payouts_tzs"] == 90_000
    assert len(data["rows"]) == 1

    r = await client.get("/api/v1/admin/stats", params={**params, "format": "csv"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == [
        "key",
        "label",
        "bookings",
        "gbv_tzs",
        "commission_tzs",
        "refunds_tzs",
        "payouts_tzs",
    ]
    assert rows[1][6] == "90000"
    assert rows[-1][0] == "total"


async def test_entry_types_cover_stats() -> None:
    """Guard: stats read these entry types; renaming one must break this test."""
    assert {EntryType.PAYMENT, EntryType.COMMISSION, EntryType.REFUND, EntryType.PAYOUT} <= set(
        EntryType
    )
