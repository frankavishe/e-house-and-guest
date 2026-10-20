"""Payments, webhooks and reconciliation (T068, Principle III, R6, contracts/providers.md)."""

import uuid
from datetime import date

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.jobs import expire_holds
from app.bookings.models import Booking, BookingEvent, BookingStatus
from app.integrations.payments.mock import MockPaymentProvider
from app.ledger.models import LedgerEntry
from app.notifications.models import Channel, Notification
from app.payments.models import Payment, PaymentEvent, Refund
from app.payments.service import reconcile_pending
from tests.conftest import FrozenClock
from tests.factories import (
    Bookable,
    book,
    deliver_callbacks,
    make_bookable,
    make_user,
    pay,
    sign_in,
    webhook_url,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

D = date(2026, 11, 10)


async def _booked(client: httpx.AsyncClient, db: AsyncSession, **fields: object) -> tuple[
    Bookable, str
]:
    b = await make_bookable(db, price=50_000, deposit_tzs=20_000, **fields)
    r = await book(client, b, D, days=3)
    assert r.status_code == 201, r.text
    return b, r.json()["id"]


async def _status(db: AsyncSession, booking_id: str) -> BookingStatus:
    booking = await db.get(Booking, uuid.UUID(booking_id), populate_existing=True)
    assert booking is not None
    return booking.status


async def _ledger(db: AsyncSession, booking_id: str) -> list[LedgerEntry]:
    rows = await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.booking_id == uuid.UUID(booking_id))
        .order_by(LedgerEntry.id)
    )
    return list(rows.scalars())


async def _notifications(db: AsyncSession, user_id: uuid.UUID, event: str) -> int:
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


async def test_successful_payment_confirms_and_posts_ledger(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b, booking_id = await _booked(client, db)
    r = await pay(client, b, booking_id, msisdn="+255700000001")
    assert r.status_code == 202, r.text
    payment = r.json()
    assert payment["status"] == "pending" and payment["amount_tzs"] == 170_000

    responses = await deliver_callbacks(client)
    assert [x.status_code for x in responses] == [200]
    assert await _status(db, booking_id) == BookingStatus.CONFIRMED

    entries = await _ledger(db, booking_id)
    assert sum(e.amount_tzs for e in entries) == 0
    assert {e.account: e.amount_tzs for e in entries} == {
        "provider_cash": 170_000,
        "deposit_held": -20_000,
        "platform_revenue": -15_000,
        f"owner_payable:{b.owner.id}": -135_000,
    }
    assert len({e.txn_id for e in entries}) == 1
    assert await _notifications(db, b.renter.id, "booking.confirmed") == 1
    assert await _notifications(db, b.owner_user.id, "booking.confirmed_owner") == 1

    sign_in(client, b.renter)
    got = (await client.get(f"/api/v1/payments/{payment['id']}")).json()
    assert got["status"] == "succeeded"
    receipt = (await client.get(f"/api/v1/bookings/{booking_id}/receipt")).json()
    assert receipt["code"] and receipt["paid_tzs"] == 170_000
    assert receipt["total_tzs"] == 170_000


async def test_failed_payment_can_be_retried_on_another_network(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b, booking_id = await _booked(client, db)
    payment_id = (await pay(client, b, booking_id, msisdn="+255700000002")).json()["id"]
    await deliver_callbacks(client)

    got = (await client.get(f"/api/v1/payments/{payment_id}")).json()
    assert got == {**got, "status": "failed", "failure_reason": "insufficient_funds"}
    assert await _status(db, booking_id) == BookingStatus.AWAITING_PAYMENT
    assert await _notifications(db, b.renter.id, "payment.failed") == 1
    detail = (await client.get(f"/api/v1/bookings/{booking_id}")).json()
    assert detail["can"]["pay"] is True

    retry = await pay(client, b, booking_id, msisdn="+255780000001", network="airtel")
    assert retry.status_code == 202
    await deliver_callbacks(client)
    assert await _status(db, booking_id) == BookingStatus.CONFIRMED
    assert await _ledger(db, booking_id)  # posted once, for the successful payment


async def test_only_one_pending_payment(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b, booking_id = await _booked(client, db)
    assert (await pay(client, b, booking_id, msisdn="+255700000003")).status_code == 202
    second = await pay(client, b, booking_id, msisdn="+255700000001")
    assert second.status_code == 409 and second.json()["error"]["code"] == "PAYMENT_PENDING"


async def test_only_renter_can_pay(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b, booking_id = await _booked(client, db)
    sign_in(client, b.owner_user)
    r = await client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"network": "mpesa", "msisdn": "+255700000001"},
    )
    assert r.status_code == 403
    sign_in(client, await make_user(db))
    r = await client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"network": "mpesa", "msisdn": "+255700000001"},
    )
    assert r.status_code == 404


async def test_duplicate_callback_confirms_once(client: httpx.AsyncClient, db: AsyncSession) -> None:
    b, booking_id = await _booked(client, db)
    await pay(client, b, booking_id, msisdn="+255700000004")
    responses = await deliver_callbacks(client)
    assert [x.status_code for x in responses] == [200, 200]

    assert await _status(db, booking_id) == BookingStatus.CONFIRMED
    assert len(await _ledger(db, booking_id)) == 4
    assert await _notifications(db, b.renter.id, "booking.confirmed") == 1
    confirmations = (
        await db.execute(
            select(func.count())
            .select_from(BookingEvent)
            .where(
                BookingEvent.booking_id == uuid.UUID(booking_id),
                BookingEvent.to_status == BookingStatus.CONFIRMED,
            )
        )
    ).scalar_one()
    assert confirmations == 1
    events = (await db.execute(select(func.count()).select_from(PaymentEvent))).scalar_one()
    assert events == 1


async def test_webhook_rejects_wrong_secret_and_bad_auth(
    client: httpx.AsyncClient, db: AsyncSession, mock_payments: MockPaymentProvider
) -> None:
    b, booking_id = await _booked(client, db)
    await pay(client, b, booking_id, msisdn="+255700000001")
    [cb] = mock_payments.take_callbacks()

    wrong = await client.post(
        "/api/v1/webhooks/payments/mock/not-the-secret", content=cb.body, headers=cb.headers
    )
    assert wrong.status_code == 404
    unknown = await client.post(
        webhook_url("nope"), content=cb.body, headers=cb.headers
    )
    assert unknown.status_code == 404
    forged = await client.post(
        webhook_url(), content=cb.body, headers={**cb.headers, "x-mock-signature": "forged"}
    )
    assert forged.status_code == 401
    assert await _status(db, booking_id) == BookingStatus.AWAITING_PAYMENT


async def test_reconciliation_recovers_lost_callback(
    client: httpx.AsyncClient,
    db: AsyncSession,
    frozen_clock: FrozenClock,
    mock_payments: MockPaymentProvider,
) -> None:
    b, booking_id = await _booked(client, db)
    payment_id = (await pay(client, b, booking_id, msisdn="+255700000003")).json()["id"]
    assert mock_payments.take_callbacks() == []  # …0003 never calls back

    mock_payments.force(uuid.UUID(payment_id), "succeeded")
    frozen_clock.advance(minutes=1)
    assert await reconcile_pending(db) == 0  # too recent
    frozen_clock.advance(minutes=2)
    assert await reconcile_pending(db) == 1
    assert await _status(db, booking_id) == BookingStatus.CONFIRMED


async def test_payment_status_poll_forces_check_after_60s(
    client: httpx.AsyncClient,
    db: AsyncSession,
    frozen_clock: FrozenClock,
    mock_payments: MockPaymentProvider,
) -> None:
    b, booking_id = await _booked(client, db)
    payment_id = (await pay(client, b, booking_id, msisdn="+255700000003")).json()["id"]
    mock_payments.force(uuid.UUID(payment_id), "succeeded")

    assert (await client.get(f"/api/v1/payments/{payment_id}")).json()["status"] == "pending"
    frozen_clock.advance(seconds=61)
    assert (await client.get(f"/api/v1/payments/{payment_id}")).json()["status"] == "succeeded"
    assert await _status(db, booking_id) == BookingStatus.CONFIRMED


async def test_dev_endpoint_settles_mock_payment(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b, booking_id = await _booked(client, db)
    payment_id = (await pay(client, b, booking_id, msisdn="+255700000003")).json()["id"]
    r = await client.post(f"/api/v1/dev/mock-payments/{payment_id}/succeed")
    assert r.status_code == 200
    assert await _status(db, booking_id) == BookingStatus.CONFIRMED


async def test_late_success_reserves_again_when_free(
    client: httpx.AsyncClient,
    db: AsyncSession,
    frozen_clock: FrozenClock,
    mock_payments: MockPaymentProvider,
) -> None:
    b, booking_id = await _booked(client, db)
    payment_id = (await pay(client, b, booking_id, msisdn="+255700000003")).json()["id"]
    frozen_clock.advance(minutes=16)
    await expire_holds(db)
    assert await _status(db, booking_id) == BookingStatus.CANCELLED

    mock_payments.force(uuid.UUID(payment_id), "succeeded")
    await reconcile_pending(db)
    assert await _status(db, booking_id) == BookingStatus.CONFIRMED
    assert sum(e.amount_tzs for e in await _ledger(db, booking_id)) == 0


async def test_late_success_refunds_when_taken(
    client: httpx.AsyncClient,
    db: AsyncSession,
    frozen_clock: FrozenClock,
    mock_payments: MockPaymentProvider,
) -> None:
    b, booking_id = await _booked(client, db)
    payment_id = (await pay(client, b, booking_id, msisdn="+255700000003")).json()["id"]
    frozen_clock.advance(minutes=16)
    await expire_holds(db)

    other = await make_user(db)
    b.renter, first_renter = other, b.renter
    assert (await book(client, b, D, days=3)).status_code == 201

    mock_payments.force(uuid.UUID(payment_id), "succeeded")
    await reconcile_pending(db)
    assert await _status(db, booking_id) == BookingStatus.CANCELLED

    payment = await db.get(Payment, uuid.UUID(payment_id), populate_existing=True)
    assert payment is not None and payment.status == "succeeded"
    refund = (
        await db.execute(select(Refund).where(Refund.payment_id == payment.id))
    ).scalar_one()
    assert refund.amount_tzs == 170_000 and refund.reason == "late_payment"
    assert refund.status == "sent"
    entries = await _ledger(db, booking_id)
    assert sum(e.amount_tzs for e in entries) == 0
    assert {e.entry_type for e in entries} == {"payment", "refund"}
    cash = sum(e.amount_tzs for e in entries if e.account == "provider_cash")
    assert cash == 0
    assert await _notifications(db, first_renter.id, "payment.refunded") == 1
