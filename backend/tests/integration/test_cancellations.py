"""Cancellations, refunds, deposits and claims (T117, US5-AS1..3, FR-026, FR-027, V13, V14)."""

import uuid
from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.admin.models import AdminAuditLog
from app.availability.models import AvailabilityBlock
from app.bookings import jobs as booking_jobs
from app.bookings.claims import resolve
from app.bookings.models import Booking, BookingStatus, Claim, ClaimResolution, ClaimStatus
from app.core import clock
from app.integrations.payments.mock import MockPaymentProvider
from app.jobs.models import Job
from app.ledger import service as ledger
from app.ledger.models import EntryType, LedgerEntry
from app.notifications.models import Channel, Notification
from app.payments import refunds
from app.payments.models import Refund, RefundReason, RefundStatus
from app.payouts.models import PayoutItem, PayoutItemKind
from app.payouts.service import create_payouts
from tests.conftest import FrozenClock
from tests.factories import (
    Bookable,
    day_range,
    make_admin,
    make_bookable,
    make_booking,
    make_paid_booking,
    make_payout_method,
    make_user,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

FAR = day_range(date(2026, 11, 20), date(2026, 11, 23))  # starts in 18 days
SOON = day_range(date(2026, 11, 5), date(2026, 11, 7))  # starts in 2 days 15 h
# Ended 1 Nov 00:00 EAT: 33 h ago, inside the 48 h claim window.
ENDED = day_range(date(2026, 10, 28), date(2026, 11, 1))
MONEY = {"total": 200_000, "deposit": 50_000, "service_fee": 10_000}


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


async def _refunds(db: AsyncSession, booking_id: uuid.UUID) -> list[Refund]:
    rows = await db.execute(
        select(Refund)
        .where(Refund.booking_id == booking_id)
        .order_by(Refund.created_at)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars())


async def _balance(db: AsyncSession, booking: Booking, account: str) -> int:
    return await ledger.booking_balance(db, booking.id, account)


async def _owner_net(db: AsyncSession, booking: Booking) -> int:
    return -(await _balance(db, booking, ledger.owner_account(booking.owner_profile_id)))


async def _assert_balanced(db: AsyncSession, booking: Booking) -> None:
    rows = await db.execute(
        select(LedgerEntry.txn_id, func.sum(LedgerEntry.amount_tzs))
        .where(LedgerEntry.booking_id == booking.id)
        .group_by(LedgerEntry.txn_id)
    )
    assert all(total == 0 for _, total in rows.all())


async def _cancel(
    client: httpx.AsyncClient, user: User, booking: Booking, reason: str | None = None
) -> httpx.Response:
    sign_in(client, user)
    return await client.post(
        f"/api/v1/bookings/{booking.id}/cancel", json={"reason": reason} if reason else None
    )


async def _send_all(db: AsyncSession, booking: Booking) -> list[Refund]:
    for refund in await _refunds(db, booking.id):
        await refunds.send(db, refund.id)
    return await _refunds(db, booking.id)


async def _active_blocks(db: AsyncSession, booking: Booking) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(AvailabilityBlock)
            .where(AvailabilityBlock.booking_id == booking.id, AvailabilityBlock.active.is_(True))
        )
    ).scalar_one()


async def _claim(
    client: httpx.AsyncClient, user: User, booking: Booking, **body: Any
) -> httpx.Response:
    sign_in(client, user)
    payload = {"kind": "damage", "description": "Broken table", **body}
    return await client.post(f"/api/v1/bookings/{booking.id}/claims", json=payload)


# --- US5-AS1: renter cancellation under the policy ----------------------------------------


async def test_flexible_cancel_before_24h_refunds_everything(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """V13: a flexible booking cancelled more than 24 h before the start is refunded in full."""
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *FAR, policy="flexible", **MONEY)

    res = await _cancel(client, b.renter, booking, "Plans changed")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_by"] == "renter" and body["cancel_reason"] == "Plans changed"
    assert body["can"]["cancel"] is False
    assert [(r["amount_tzs"], r["reason"], r["status"]) for r in body["refunds"]] == [
        (260_000, "cancellation", "pending")
    ]
    assert await _active_blocks(db, booking) == 0
    # Decided refund leaves nothing for the owner, the platform or the deposit.
    assert await _owner_net(db, booking) == 0
    assert await _balance(db, booking, ledger.PLATFORM_REVENUE) == 0
    assert await _balance(db, booking, ledger.DEPOSIT_HELD) == 0
    assert await _balance(db, booking, ledger.RENTER_CLEARING) == -260_000

    [refund] = await _send_all(db, booking)
    assert refund.status == RefundStatus.SENT and refund.provider_ref
    assert await _balance(db, booking, ledger.RENTER_CLEARING) == 0
    assert await _balance(db, booking, ledger.PROVIDER_CASH) == 0
    await _assert_balanced(db, booking)
    assert await _sms(db, b.owner_user.id, "booking.cancelled_by_renter") == 1
    assert await _sms(db, b.renter.id, "refund.sent") == 1


async def test_moderate_late_cancel_refunds_half_the_rental(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *SOON, policy="moderate", **MONEY)

    sign_in(client, b.renter)
    preview = (await client.get(f"/api/v1/bookings/{booking.id}/cancel-preview")).json()
    assert preview == {
        "policy": "moderate",
        "cancelled_by": "renter",
        "percent": 50,
        "paid_tzs": 260_000,
        "rental_refund_tzs": 100_000,
        "delivery_refund_tzs": 0,
        "service_fee_refund_tzs": 0,
        "deposit_refund_tzs": 50_000,
        "refund_tzs": 150_000,
        "deadline": None,
    }

    assert (await _cancel(client, b.renter, booking)).status_code == 200
    [refund] = await _send_all(db, booking)
    assert refund.amount_tzs == 150_000
    # The owner keeps 90% of the forfeited half; the platform its commission and the fee.
    assert await _owner_net(db, booking) == 90_000
    assert await _balance(db, booking, ledger.PLATFORM_REVENUE) == -(10_000 + 10_000)
    assert await _balance(db, booking, ledger.DEPOSIT_HELD) == 0
    await _assert_balanced(db, booking)


async def test_preview_shows_the_next_deadline(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *FAR, policy="moderate", **MONEY)
    sign_in(client, b.renter)
    preview = (await client.get(f"/api/v1/bookings/{booking.id}/cancel-preview")).json()
    assert preview["percent"] == 100
    assert datetime.fromisoformat(preview["deadline"]) == FAR[0] - timedelta(days=5)


async def test_unpaid_cancel_releases_dates_without_refund(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *FAR, status="awaiting_payment")
    res = await _cancel(client, b.renter, booking)
    assert res.status_code == 200 and res.json()["refunds"] == []
    assert await _active_blocks(db, booking) == 0


async def test_who_may_cancel(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    requested = await make_booking(db, b, *FAR, status="requested")
    assert (await _cancel(client, b.owner_user, requested)).status_code == 409  # decline instead
    running = await make_paid_booking(
        db, b, *day_range(date(2026, 11, 1), date(2026, 11, 4)), status="in_progress"
    )
    assert (await _cancel(client, b.renter, running)).status_code == 409
    stranger = await make_user(db)
    assert (await _cancel(client, stranger, requested)).status_code == 404


# --- US5-AS2: owner cancellation ----------------------------------------------------------


async def test_owner_cancel_refunds_in_full_and_counts(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """V13: an owner cancellation refunds everything, even under strict, and is counted."""
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *SOON, policy="strict", delivery=15_000, **MONEY)

    res = await _cancel(client, b.owner_user, booking)
    assert res.status_code == 200, res.text
    assert res.json()["cancelled_by"] == "owner"
    [refund] = await _send_all(db, booking)
    assert (refund.amount_tzs, refund.reason) == (275_000, RefundReason.OWNER_CANCEL)
    await db.refresh(b.owner_user)
    assert b.owner_user.owner_cancellation_count == 1
    assert await _owner_net(db, booking) == 0
    assert await _balance(db, booking, ledger.PLATFORM_REVENUE) == 0
    assert await _sms(db, b.renter.id, "booking.cancelled_by_owner") == 1
    await _assert_balanced(db, booking)


# --- admin cancellation and refunds -------------------------------------------------------


async def test_admin_cancels_a_running_booking_with_full_refund(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    admin = await make_admin(db)
    booking = await make_paid_booking(
        db, b, *day_range(date(2026, 11, 1), date(2026, 11, 4)), status="in_progress", **MONEY
    )
    sign_in(client, admin)
    res = await client.post(
        f"/api/v1/admin/bookings/{booking.id}/cancel", json={"reason": "Unsafe premises"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["cancelled_by"] == "admin"
    [refund] = await _refunds(db, booking.id)
    assert (refund.amount_tzs, refund.reason) == (260_000, RefundReason.ADMIN)
    log = (
        await db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == booking.id))
    ).scalar_one()
    assert log.action == "booking.cancel"
    assert log.after == {"status": "cancelled", "reason": "Unsafe premises", "refund_tzs": 260_000}


async def test_admin_refund_is_capped_by_what_is_left(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    admin = await make_admin(db)
    booking = await make_paid_booking(db, b, *ENDED, status="completed", **MONEY)
    sign_in(client, admin)
    url = f"/api/v1/admin/bookings/{booking.id}/refund"

    too_much = await client.post(url, json={"amount_tzs": 30_001, "reason": "Goodwill"})
    assert too_much.status_code == 409
    assert too_much.json()["error"]["code"] == "REFUND_EXCEEDS_BALANCE"
    assert too_much.json()["error"]["details"] == {"available_tzs": 30_000}

    res = await client.post(
        url, json={"amount_tzs": 40_000, "source": "owner", "reason": "Dirty room"}
    )
    assert res.status_code == 200, res.text
    assert (res.json()["amount_tzs"], res.json()["reason"]) == (40_000, "admin")
    assert await _owner_net(db, booking) == 180_000 - 40_000
    log = (
        await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "booking.refund"))
    ).scalar_one()
    assert log.after is not None and log.after["source"] == "owner"


async def test_failed_refunds_retry_then_need_an_admin(
    client: httpx.AsyncClient, db: AsyncSession, mock_payments: MockPaymentProvider
) -> None:
    b = await make_bookable(db)
    admin = await make_admin(db)
    booking = await make_paid_booking(db, b, *FAR, policy="flexible", **MONEY)
    mock_payments.fail_refunds()
    await _cancel(client, b.renter, booking)
    [refund] = await _refunds(db, booking.id)

    for attempt in range(1, refunds.MAX_ATTEMPTS + 1):
        await refunds.send(db, refund.id)
        await db.refresh(refund)
        assert refund.attempts == attempt
    assert refund.status == RefundStatus.FAILED
    retries = (
        await db.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.kind == refunds.SEND_JOB, Job.dedupe_key.startswith(f"refund:{refund.id}:"))
        )
    ).scalar_one()
    assert retries == refunds.MAX_ATTEMPTS
    assert await _sms(db, admin.id, "refund.failed_admin") == 1
    # The money waits in clearing; nothing was paid out.
    assert await _balance(db, booking, ledger.RENTER_CLEARING) == -260_000

    mock_payments.fail_refunds(None)
    sign_in(client, admin)
    res = await client.post(f"/api/v1/admin/refunds/{refund.id}/retry")
    assert res.status_code == 200 and res.json()["status"] == "pending"
    queued = (
        await db.execute(
            select(Job).where(Job.dedupe_key == f"refund:{refund.id}:{refunds.MAX_ATTEMPTS + 1}")
        )
    ).scalar_one()
    assert queued.run_at == clock.now()
    await refunds.send(db, refund.id)
    await db.refresh(refund)
    assert refund.status == RefundStatus.SENT
    assert await _balance(db, booking, ledger.RENTER_CLEARING) == 0
    assert (await client.post(f"/api/v1/admin/refunds/{refund.id}/retry")).status_code == 409


async def test_manual_refunds_fail_at_once_and_can_be_marked_sent(
    client: httpx.AsyncClient, db: AsyncSession, mock_payments: MockPaymentProvider
) -> None:
    b = await make_bookable(db)
    admin = await make_admin(db)
    booking = await make_paid_booking(db, b, *FAR, policy="flexible", **MONEY)
    mock_payments.fail_refunds(refunds.MANUAL_REFUND)
    await _cancel(client, b.renter, booking)
    [refund] = await _send_all(db, booking)
    assert (refund.status, refund.attempts) == (RefundStatus.FAILED, 1)

    sign_in(client, admin)
    res = await client.post(
        f"/api/v1/admin/refunds/{refund.id}/mark-sent", json={"provider_ref": "MPESA-RF77"}
    )
    assert res.status_code == 200, res.text
    assert (res.json()["status"], res.json()["provider_ref"]) == ("sent", "MPESA-RF77")
    assert await _balance(db, booking, ledger.RENTER_CLEARING) == 0
    actions = (
        await db.execute(select(AdminAuditLog.action).where(AdminAuditLog.target_id == refund.id))
    ).scalars()
    assert list(actions) == ["refund.mark_sent"]


# --- US5-AS3: deposits --------------------------------------------------------------------


async def test_deposit_is_refunded_48h_after_the_end(
    db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    """V14: no claim within 48 h after the end → the deposit goes back (`deposit_release`)."""
    b = await make_bookable(db)
    booking = await make_paid_booking(
        db, b, *ENDED, status="completed", completed_at=ENDED[1], **MONEY
    )
    assert await booking_jobs.release_deposits(db) == 0  # 33 h after the end

    frozen_clock.set(ENDED[1] + timedelta(hours=48))
    assert await booking_jobs.release_deposits(db) == 1
    assert await booking_jobs.release_deposits(db) == 0  # once only
    [refund] = await _send_all(db, booking)
    assert (refund.amount_tzs, refund.reason, refund.status) == (
        50_000,
        RefundReason.DEPOSIT_RETURN,
        RefundStatus.SENT,
    )
    release = (
        await db.execute(
            select(LedgerEntry).where(
                LedgerEntry.booking_id == booking.id,
                LedgerEntry.entry_type == EntryType.DEPOSIT_RELEASE,
            )
        )
    ).scalar_one()
    assert (release.account, release.amount_tzs) == (ledger.DEPOSIT_HELD, 50_000)
    assert await _balance(db, booking, ledger.DEPOSIT_HELD) == 0
    assert await _owner_net(db, booking) == 180_000  # earnings untouched
    assert await _sms(db, b.renter.id, "refund.deposit_sent") == 1
    await _assert_balanced(db, booking)


async def test_damage_claim_after_48h_is_rejected(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(
        db, b, *ENDED, status="completed", completed_at=ENDED[1], **MONEY
    )
    frozen_clock.set(ENDED[1] + timedelta(hours=48))
    res = await _claim(client, b.owner_user, booking)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CLAIM_WINDOW_CLOSED"


async def test_open_claim_blocks_deposit_refund_and_payout(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db)
    await make_payout_method(db, b.owner)
    admin = await make_admin(db)
    booking = await make_paid_booking(
        db, b, *ENDED, status="completed", completed_at=ENDED[1], **MONEY
    )
    assert (await _claim(client, b.renter, booking)).status_code == 403  # damage: owner only

    res = await _claim(client, b.owner_user, booking, amount_claimed_tzs=40_000)
    assert res.status_code == 201, res.text
    claim = res.json()
    assert (claim["kind"], claim["opened_by"], claim["status"]) == ("damage", "owner", "open")
    await db.refresh(booking)
    assert booking.status == BookingStatus.DISPUTED
    assert await _sms(db, b.renter.id, "claim.opened") == 1
    assert await _sms(db, admin.id, "claim.opened_admin") == 1
    second = await _claim(client, b.renter, booking, kind="dispute")
    assert second.json()["error"]["code"] == "CLAIM_OPEN"

    frozen_clock.advance(days=3)
    assert await booking_jobs.release_deposits(db) == 0
    assert await create_payouts(db) == []
    assert await _refunds(db, booking.id) == []


async def _disputed(client: httpx.AsyncClient, db: AsyncSession, b: Bookable) -> Booking:
    booking = await make_paid_booking(
        db, b, *ENDED, status="completed", completed_at=ENDED[1], **MONEY
    )
    assert (await _claim(client, b.owner_user, booking)).status_code == 201
    return booking


@pytest.mark.parametrize(
    ("resolution", "award", "owner_gets", "renter_gets"),
    [
        ("owner_awarded", None, 50_000, 0),
        ("split", 20_000, 20_000, 30_000),
        ("renter_refunded", None, 0, 50_000),
    ],
)
async def test_admin_resolution_posts_the_deposit(
    client: httpx.AsyncClient,
    db: AsyncSession,
    resolution: str,
    award: int | None,
    owner_gets: int,
    renter_gets: int,
) -> None:
    b = await make_bookable(db)
    admin = await make_admin(db)
    booking = await _disputed(client, db, b)
    [claim] = (await db.execute(select(Claim).where(Claim.booking_id == booking.id))).scalars()

    sign_in(client, admin)
    res = await client.post(
        f"/api/v1/admin/claims/{claim.id}/resolve",
        json={"resolution": resolution, "amount_awarded_tzs": award, "note": "Checked photos"},
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["status"], out["resolution"], out["amount_awarded_tzs"]) == (
        "resolved",
        resolution,
        owner_gets,
    )
    assert out["booking_status"] == "completed"
    assert await _owner_net(db, booking) == 180_000 + owner_gets
    assert await _balance(db, booking, ledger.DEPOSIT_HELD) == 0
    refunded = [(r.amount_tzs, r.reason) for r in await _refunds(db, booking.id)]
    assert refunded == ([(renter_gets, RefundReason.DEPOSIT_RETURN)] if renter_gets else [])
    await _send_all(db, booking)
    await _assert_balanced(db, booking)
    log = (
        await db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == claim.id))
    ).scalar_one()
    assert log.action == "claim.resolve" and log.before == {
        "status": "open",
        "resolution": None,
        "amount_awarded_tzs": None,
    }
    assert await _sms(db, b.renter.id, "claim.resolved") == 1
    # Nothing is left to release afterwards.
    assert await booking_jobs.release_deposits(db) == 0
    again = await client.post(
        f"/api/v1/admin/claims/{claim.id}/resolve", json={"resolution": "renter_refunded"}
    )
    assert again.status_code == 409


@pytest.mark.parametrize(
    ("resolution", "award"),
    [("split", 50_000), ("split", 0), ("owner_awarded", 50_001), ("renter_refunded", 10)],
)
async def test_invalid_awards_are_rejected(
    db: AsyncSession, client: httpx.AsyncClient, resolution: str, award: int
) -> None:
    from app.core.errors import AppError

    b = await make_bookable(db)
    admin = await make_admin(db)
    booking = await _disputed(client, db, b)
    [claim] = (await db.execute(select(Claim).where(Claim.booking_id == booking.id))).scalars()
    with pytest.raises(AppError) as err:
        await resolve(db, admin, claim.id, ClaimResolution(resolution), award, None)
    assert err.value.code == "INVALID_AWARD"
    await db.refresh(claim)
    assert claim.status == ClaimStatus.OPEN


async def test_award_after_payout_is_paid_as_a_claim_award(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    """Earnings went out 24 h after completion; the claim came later, within 48 h."""
    b = await make_bookable(db)
    await make_payout_method(db, b.owner)
    admin = await make_admin(db)
    booking = await make_paid_booking(
        db, b, *ENDED, status="completed", completed_at=ENDED[1], **MONEY
    )
    [first] = await create_payouts(db)
    assert first.amount_tzs == 180_000

    assert (await _claim(client, b.owner_user, booking)).status_code == 201
    [claim] = (await db.execute(select(Claim).where(Claim.booking_id == booking.id))).scalars()
    await resolve(db, admin, claim.id, ClaimResolution.SPLIT, 20_000, None)

    [second] = await create_payouts(db)
    assert second.amount_tzs == 20_000
    items = (
        await db.execute(
            select(PayoutItem.kind, PayoutItem.amount_tzs)
            .where(PayoutItem.booking_id == booking.id)
            .order_by(PayoutItem.created_at)
        )
    ).all()
    assert [tuple(i) for i in items] == [
        (PayoutItemKind.EARNINGS, 180_000),
        (PayoutItemKind.CLAIM_AWARD, 20_000),
    ]
    frozen_clock.advance(days=1)
    assert await create_payouts(db) == []


async def test_cancelled_booking_pays_the_owner_what_they_kept(
    client: httpx.AsyncClient, db: AsyncSession, frozen_clock: FrozenClock
) -> None:
    b = await make_bookable(db)
    await make_payout_method(db, b.owner)
    booking = await make_paid_booking(db, b, *SOON, policy="moderate", **MONEY)
    await _cancel(client, b.renter, booking)
    assert await create_payouts(db) == []  # not yet 24 h

    frozen_clock.advance(hours=24)
    [payout] = await create_payouts(db)
    assert payout.amount_tzs == 90_000

    sign_in(client, b.owner_user)
    earnings = (await client.get("/api/v1/owner/earnings")).json()
    [item] = [i for i in earnings["items"] if i["booking_id"] == str(booking.id)]
    assert (item["gross_tzs"], item["commission_tzs"], item["net_tzs"]) == (
        100_000,
        10_000,
        90_000,
    )


async def test_fully_refunded_cancellation_is_not_in_earnings(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db)
    booking = await make_paid_booking(db, b, *FAR, policy="flexible", **MONEY)
    await _cancel(client, b.renter, booking)
    sign_in(client, b.owner_user)
    earnings = (await client.get("/api/v1/owner/earnings")).json()
    assert all(i["booking_id"] != str(booking.id) for i in earnings["items"])


async def test_can_flags_follow_the_rules(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b = await make_bookable(db)
    confirmed = await make_paid_booking(db, b, *FAR, **MONEY)
    ended = await make_paid_booking(
        db, b, *ENDED, status="completed", completed_at=ENDED[1], **MONEY
    )

    async def can(user: User, booking: Booking) -> dict[str, bool]:
        sign_in(client, user)
        flags: dict[str, bool] = (await client.get(f"/api/v1/bookings/{booking.id}")).json()["can"]
        return flags

    assert (await can(b.renter, confirmed))["cancel"] is True
    assert (await can(b.owner_user, confirmed))["cancel"] is True
    assert (await can(b.renter, confirmed))["claim"] is False  # not started yet
    assert (await can(b.renter, ended))["cancel"] is False
    assert (await can(b.renter, ended))["claim"] is True  # dispute
    assert (await can(b.owner_user, ended))["claim"] is True
