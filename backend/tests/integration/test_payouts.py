"""Owner earnings and payouts (T109, US4-AS1/AS2, R7, SC-008)."""

import uuid
from datetime import date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import AdminAuditLog
from app.core import clock
from app.integrations import override_payouts
from app.integrations.payments.manual import ManualPayoutProvider
from app.jobs.models import Job
from app.jobs.registry import PERIODICS
from app.ledger import service as ledger
from app.ledger.models import EntryType, LedgerEntry
from app.notifications.models import Channel, Notification
from app.payouts import jobs as payout_jobs  # noqa: F401  (registers the sweeps)
from app.payouts.models import Payout, PayoutItem, PayoutStatus
from app.payouts.service import ELIGIBLE_AFTER, create_payouts, disburse, poll_processing
from tests.conftest import FrozenClock
from tests.factories import (
    Bookable,
    day_range,
    make_admin,
    make_bookable,
    make_booking,
    make_completed_booking,
    make_payout_method,
    make_user,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

OCT = day_range(date(2026, 10, 20), date(2026, 10, 23))
OCT_LATER = day_range(date(2026, 10, 25), date(2026, 10, 27))


def _ago(**kwargs: float) -> datetime:
    return clock.now() - timedelta(**kwargs)


async def _owner_with_booking(
    db: AsyncSession, *, msisdn: str | None = "+255700000001", hours_ago: float = 25
) -> tuple[Bookable, object]:
    b = await make_bookable(db)
    if msisdn:
        await make_payout_method(db, b.owner, msisdn=msisdn)
    booking = await make_completed_booking(db, b, *OCT, completed_at=_ago(hours=hours_ago))
    return b, booking


async def _payouts(db: AsyncSession, owner_id: uuid.UUID) -> list[Payout]:
    rows = await db.execute(
        select(Payout)
        .where(Payout.owner_profile_id == owner_id)
        .order_by(Payout.created_at)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


async def _sms(db: AsyncSession, user_id: uuid.UUID, event: str) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.event == event,
                Notification.channel == Channel.SMS,
            )
        )
    ).scalar_one()


async def _create_and_disburse(db: AsyncSession) -> list[Payout]:
    created = await create_payouts(db)
    for payout in created:
        await disburse(db, payout.id)
    return created


# --- earnings (US4-AS1) -------------------------------------------------------------------


async def test_earnings_show_gross_commission_net(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b, booking = await _owner_with_booking(db)
    sign_in(client, b.owner_user)
    r = await client.get("/api/v1/owner/earnings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totals"] == {
        "gross_tzs": 200_000,
        "commission_tzs": 20_000,
        "net_tzs": 180_000,
        "paid_out_tzs": 0,
        "pending_tzs": 180_000,
    }
    [item] = body["items"]
    assert item["booking_code"] == booking.code  # type: ignore[attr-defined]
    assert (item["gross_tzs"], item["commission_tzs"], item["net_tzs"]) == (
        200_000,
        20_000,
        180_000,
    )
    assert item["status"] == "available"


async def test_earnings_cover_only_own_paid_bookings_and_date_range(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b, _ = await _owner_with_booking(db)
    await make_completed_booking(db, b, *OCT_LATER, completed_at=_ago(hours=2), total=100_000)
    # An unpaid booking has no ledger entries and earns nothing yet.
    await make_booking(db, b, *day_range(date(2026, 11, 20), date(2026, 11, 22)))
    await _owner_with_booking(db)  # another owner's booking is not listed

    sign_in(client, b.owner_user)
    body = (await client.get("/api/v1/owner/earnings")).json()
    assert body["totals"]["net_tzs"] == 180_000 + 90_000
    statuses = sorted(i["status"] for i in body["items"])
    assert statuses == ["available", "upcoming"]  # completed < 24 h ago is not yet available

    ranged = await client.get("/api/v1/owner/earnings", params={"from": "2026-10-24"})
    assert [i["net_tzs"] for i in ranged.json()["items"]] == [90_000]

    sign_in(client, await make_user(db))
    assert (await client.get("/api/v1/owner/earnings")).status_code == 403


# --- the payout job -----------------------------------------------------------------------


async def test_payout_job_groups_eligible_bookings_once(
    db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b, first = await _owner_with_booking(db)
    second = await make_completed_booking(
        db, b, *OCT_LATER, completed_at=_ago(hours=30), total=100_000
    )
    recent = await make_completed_booking(
        db,
        b,
        *day_range(date(2026, 10, 28), date(2026, 10, 29)),
        completed_at=_ago(hours=3),
        total=50_000,
    )
    await make_booking(
        db, b, *day_range(date(2026, 11, 20), date(2026, 11, 22)), status="confirmed"
    )

    [payout] = await create_payouts(db)
    assert payout.status == PayoutStatus.PENDING
    assert payout.amount_tzs == 180_000 + 90_000
    items = (
        await db.execute(select(PayoutItem).where(PayoutItem.payout_id == payout.id))
    ).scalars()
    assert {i.booking_id: i.amount_tzs for i in items} == {
        first.id: 180_000,  # type: ignore[attr-defined]
        second.id: 90_000,
    }
    jobs = await db.execute(select(Job).where(Job.kind == "payouts.disburse"))
    assert [j.payload for j in jobs.scalars()] == [{"payout_id": str(payout.id)}]

    assert await create_payouts(db) == []  # already batched bookings are never paid twice

    frozen_clock.advance(hours=22)
    [later] = await create_payouts(db)
    assert later.amount_tzs == 45_000
    later_items = (
        await db.execute(select(PayoutItem.booking_id).where(PayoutItem.payout_id == later.id))
    ).scalars()
    assert list(later_items) == [recent.id]


async def test_payouts_are_per_owner(db: AsyncSession) -> None:
    a, _ = await _owner_with_booking(db)
    b, _ = await _owner_with_booking(db)
    created = await create_payouts(db)
    assert sorted(p.owner_profile_id for p in created) == sorted([a.owner.id, b.owner.id])


async def test_eligible_after_24h_and_job_runs_daily_so_payout_starts_within_48h(
    db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    """SC-008: eligible 24 h after completion and the sweep runs at least daily."""
    assert timedelta(hours=24) == ELIGIBLE_AFTER
    assert PERIODICS["payouts.create"].every <= timedelta(hours=24)
    b = await make_bookable(db)
    await make_payout_method(db, b.owner)
    await make_completed_booking(db, b, *OCT, completed_at=clock.now())
    frozen_clock.advance(hours=23, minutes=59)
    assert await create_payouts(db) == []
    frozen_clock.advance(minutes=1)
    [payout] = await create_payouts(db)
    assert payout.created_at - (clock.now() - timedelta(hours=24)) <= timedelta(hours=48)


# --- disbursement (US4-AS2) ---------------------------------------------------------------


async def test_successful_disbursement_marks_paid_posts_ledger_and_sends_sms(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b, _ = await _owner_with_booking(db)
    [payout] = await _create_and_disburse(db)
    await db.refresh(payout)
    assert payout.status == PayoutStatus.PAID
    assert payout.provider_ref and payout.paid_at == clock.now()
    assert payout.payout_method is not None
    assert payout.payout_method["msisdn"] == "+255700000001"

    rows = (
        await db.execute(
            select(LedgerEntry.account, LedgerEntry.amount_tzs).where(
                LedgerEntry.payout_id == payout.id, LedgerEntry.entry_type == EntryType.PAYOUT
            )
        )
    ).all()
    assert dict(rows) == {ledger.owner_account(b.owner.id): 180_000, "provider_cash": -180_000}
    assert await ledger.balance(db, ledger.owner_account(b.owner.id)) == 0
    assert await _sms(db, b.owner_user.id, "payout.paid") == 1

    sign_in(client, b.owner_user)
    earnings = (await client.get("/api/v1/owner/earnings")).json()
    assert earnings["totals"]["paid_out_tzs"] == 180_000
    assert earnings["totals"]["pending_tzs"] == 0
    assert earnings["items"][0]["status"] == "paid"

    page = (await client.get("/api/v1/owner/payouts")).json()
    assert page["total"] == 1
    assert page["items"][0]["status"] == "paid"
    assert page["items"][0]["items"][0]["amount_tzs"] == 180_000

    await disburse(db, payout.id)  # a re-run job does nothing
    assert await _sms(db, b.owner_user.id, "payout.paid") == 1


async def test_failed_disbursement_then_admin_retry(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    method = await make_payout_method(db, b.owner, msisdn="+255700000002")  # mock: invalid
    await make_completed_booking(db, b, *OCT, completed_at=_ago(hours=25))
    [payout] = await _create_and_disburse(db)
    await db.refresh(payout)
    assert payout.status == PayoutStatus.FAILED
    assert payout.failure_reason == "invalid_account"
    assert await _sms(db, b.owner_user.id, "payout.failed") == 1
    assert await ledger.balance(db, ledger.owner_account(b.owner.id)) == -180_000

    # The owner fixes their number; the admin retries.
    method.msisdn = "+255700000001"
    await db.flush()

    admin = await make_admin(db)
    sign_in(client, admin)
    r = await client.post(f"/api/v1/admin/payouts/{payout.id}/retry")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    await disburse(db, payout.id)
    await db.refresh(payout)
    assert payout.status == PayoutStatus.PAID
    assert payout.attempts == 2

    again = await client.post(f"/api/v1/admin/payouts/{payout.id}/retry")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "INVALID_TRANSITION"
    actions = (
        await db.execute(select(AdminAuditLog.action).where(AdminAuditLog.target_id == payout.id))
    ).scalars()
    assert list(actions) == ["payout.retry"]


async def test_processing_payout_is_polled_until_paid(db: AsyncSession) -> None:
    b, _ = await _owner_with_booking(db, msisdn="+255700000003")  # mock: settles later
    [payout] = await _create_and_disburse(db)
    await db.refresh(payout)
    assert payout.status == PayoutStatus.PROCESSING
    assert await poll_processing(db) == 1
    await db.refresh(payout)
    assert payout.status == PayoutStatus.PAID
    assert await _sms(db, b.owner_user.id, "payout.paid") == 1


async def test_no_payout_method_fails_and_next_run_retries(
    db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b, _ = await _owner_with_booking(db, msisdn=None)
    [payout] = await _create_and_disburse(db)
    await db.refresh(payout)
    assert payout.status == PayoutStatus.FAILED
    assert payout.failure_reason == "no_payout_method"

    frozen_clock.advance(days=1)
    assert await _create_and_disburse(db) == []  # still no method: nothing new to do
    await make_payout_method(db, b.owner)
    frozen_clock.advance(days=1)
    assert await create_payouts(db) == []  # the failed payout is re-queued, not duplicated
    await disburse(db, payout.id)
    await db.refresh(payout)
    assert payout.status == PayoutStatus.PAID


# --- manual fallback (R7) -----------------------------------------------------------------


async def test_manual_provider_waits_for_admin_mark_paid(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    override_payouts(ManualPayoutProvider())
    b, _ = await _owner_with_booking(db)
    [payout] = await _create_and_disburse(db)
    await db.refresh(payout)
    assert payout.status == PayoutStatus.PENDING
    assert payout.payout_method is not None  # the admin sees where to send the money

    admin = await make_admin(db)
    sign_in(client, admin)
    queue = (await client.get("/api/v1/admin/payouts", params={"status": "pending"})).json()
    assert [p["id"] for p in queue["items"]] == [str(payout.id)]
    assert queue["items"][0]["owner"]["display_name"] == b.owner.display_name

    r = await client.post(
        f"/api/v1/admin/payouts/{payout.id}/mark-paid", json={"provider_ref": "MPESA-QX12"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"
    assert r.json()["provider_ref"] == "MPESA-QX12"
    assert await ledger.balance(db, ledger.owner_account(b.owner.id)) == 0
    assert await _sms(db, b.owner_user.id, "payout.paid") == 1
    audit = (
        await db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == payout.id))
    ).scalar_one()
    assert audit.action == "payout.mark_paid"
    assert audit.before == {"status": "pending", "provider_ref": None}
    assert audit.after == {"status": "paid", "provider_ref": "MPESA-QX12"}

    twice = await client.post(
        f"/api/v1/admin/payouts/{payout.id}/mark-paid", json={"provider_ref": "MPESA-QX12"}
    )
    assert twice.status_code == 409


async def test_admin_payout_endpoints_require_admin(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b, _ = await _owner_with_booking(db)
    [payout] = await create_payouts(db)
    sign_in(client, b.owner_user)
    assert (await client.get("/api/v1/admin/payouts")).status_code == 403
    r = await client.post(
        f"/api/v1/admin/payouts/{payout.id}/mark-paid", json={"provider_ref": "X"}
    )
    assert r.status_code == 403
