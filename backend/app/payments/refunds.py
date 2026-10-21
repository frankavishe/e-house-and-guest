"""Refunds to renters (T121, US5, FR-025, Principle III).

Deciding a refund and sending it are separate steps:

1. `issue` creates a `pending` refund and moves the amount into `renter_clearing`, taking
   it from the owner's payable, platform revenue and/or the held deposit, all in the
   caller's transaction. From then on the money cannot be paid out to the owner.
2. The `refunds.send` job asks the provider to return the money. On success the refund
   is `sent` and `renter_clearing` pays out to `provider_cash`. A failure is retried with
   backoff; after `MAX_ATTEMPTS` tries, or when the provider can only refund by hand, the refund
   is `failed`, the money stays in clearing and the admins are told. An admin can then retry
   it, or send it outside the platform and mark it sent.

    pending ─send ok→ sent
       └─send fails N times→ failed ─retry→ pending
                          └─mark-sent (admin) → sent
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.admin.moderation import audit
from app.bookings import notify
from app.bookings.models import Booking
from app.core import clock
from app.core.errors import AppError, not_found
from app.core.i18n import money
from app.integrations import get_payment_provider
from app.integrations.payments.base import Network, ProviderUnavailable, RefundResult
from app.jobs import service as jobs
from app.jobs.registry import handler
from app.ledger import service as ledger
from app.payments.models import Payment, PaymentStatus, Refund, RefundReason, RefundStatus

log = logging.getLogger(__name__)

SEND_JOB = "refunds.send"
MAX_ATTEMPTS = 5
# The provider cannot refund through its API (AzamPay until R6/R7 are verified).
MANUAL_REFUND = "manual_refund_required"
SENT_EVENTS = {
    RefundReason.DEPOSIT_RETURN: "refund.deposit_sent",
}


async def refunds_of(session: AsyncSession, booking_id: uuid.UUID) -> list[Refund]:
    rows = await session.execute(
        select(Refund).where(Refund.booking_id == booking_id).order_by(Refund.created_at)
    )
    return list(rows.scalars())


async def _paid_with(session: AsyncSession, booking_id: uuid.UUID) -> Payment | None:
    """The payment a refund goes back through: the booking's first successful one."""
    rows = await session.execute(
        select(Payment)
        .where(Payment.booking_id == booking_id, Payment.status == PaymentStatus.SUCCEEDED)
        .order_by(Payment.confirmed_at, Payment.created_at)
        .limit(1)
    )
    return rows.scalar_one_or_none()


async def _queue(session: AsyncSession, refund: Refund, *, at_once: bool = False) -> None:
    run_at = None if at_once or not refund.attempts else clock.now() + jobs.backoff(refund.attempts)
    await jobs.enqueue(
        session,
        SEND_JOB,
        {"refund_id": str(refund.id)},
        run_at=run_at,
        dedupe_key=f"refund:{refund.id}:{refund.attempts + 1}",
    )


async def issue(
    session: AsyncSession,
    booking: Booking,
    *,
    reason: RefundReason,
    created_by: uuid.UUID | None = None,
    from_owner_tzs: int = 0,
    from_commission_tzs: int = 0,
    from_service_fee_tzs: int = 0,
    from_deposit_tzs: int = 0,
) -> Refund | None:
    """Decide a refund and queue it for sending. None when there is nothing to refund."""
    amount = from_owner_tzs + from_commission_tzs + from_service_fee_tzs + from_deposit_tzs
    if amount <= 0:
        return None
    payment = await _paid_with(session, booking.id)
    if payment is None:
        log.error("refund for booking %s without a successful payment", booking.id)
        return None
    refund = Refund(
        booking_id=booking.id,
        payment_id=payment.id,
        amount_tzs=amount,
        reason=reason,
        status=RefundStatus.PENDING,
        created_by=created_by,
        attempts=0,
    )
    session.add(refund)
    await session.flush()
    await ledger.post_refund_due(
        session,
        booking,
        refund.id,
        from_owner_tzs=from_owner_tzs,
        from_commission_tzs=from_commission_tzs,
        from_service_fee_tzs=from_service_fee_tzs,
        from_deposit_tzs=from_deposit_tzs,
    )
    await _queue(session, refund)
    return refund


async def _locked(session: AsyncSession, refund_id: uuid.UUID) -> Refund | None:
    return await session.get(Refund, refund_id, with_for_update=True, populate_existing=True)


async def _sent(
    session: AsyncSession, refund: Refund, booking: Booking, provider_ref: str | None
) -> None:
    refund.status = RefundStatus.SENT
    refund.provider_ref = provider_ref
    refund.failure_reason = None
    await session.flush()
    await ledger.post_refund(session, booking, refund.amount_tzs, refund.payment_id, refund.id)
    event = SENT_EVENTS.get(refund.reason, "refund.sent")
    await notify.to_renter(session, booking, event, amount=money(refund.amount_tzs))


async def send(session: AsyncSession, refund_id: uuid.UUID) -> Refund | None:
    """Send a pending refund once. Idempotent: anything but `pending` is left alone."""
    refund = await _locked(session, refund_id)
    if refund is None or refund.status != RefundStatus.PENDING:
        return refund
    booking = await session.get(Booking, refund.booking_id)
    payment = await session.get(Payment, refund.payment_id)
    assert booking is not None and payment is not None
    refund.attempts += 1
    try:
        result = await get_payment_provider().refund(
            payment_id=payment.id,
            amount_tzs=refund.amount_tzs,
            msisdn=payment.msisdn,
            network=Network(payment.network.value),
        )
    except ProviderUnavailable:
        result = RefundResult(ok=False, failure_reason="provider_unavailable")
    if result.ok:
        await _sent(session, refund, booking, result.provider_ref)
        return refund
    refund.failure_reason = result.failure_reason or "unknown"
    # Attempts keep counting across admin retries (they key the job dedupe), so a round
    # ends every MAX_ATTEMPTS tries.
    if refund.failure_reason == MANUAL_REFUND or refund.attempts % MAX_ATTEMPTS == 0:
        refund.status = RefundStatus.FAILED
        await session.flush()
        await notify.to_admins(
            session, booking, "refund.failed_admin", amount=money(refund.amount_tzs)
        )
    else:
        await _queue(session, refund)
    await session.flush()
    return refund


@handler(SEND_JOB)
async def send_job(session: AsyncSession, payload: dict[str, Any]) -> None:
    await send(session, uuid.UUID(payload["refund_id"]))


# --- admin (FR-031) -----------------------------------------------------------------------


def _state(refund: Refund) -> dict[str, Any]:
    return {
        "status": refund.status.value,
        "provider_ref": refund.provider_ref,
        "failure_reason": refund.failure_reason,
    }


async def _admin_refund(session: AsyncSession, refund_id: uuid.UUID) -> Refund:
    refund = await _locked(session, refund_id)
    if refund is None:
        raise not_found("refund")
    return refund


def _invalid(refund: Refund) -> AppError:
    return AppError("INVALID_TRANSITION", 409, {"status": refund.status.value})


async def retry(session: AsyncSession, admin: User, refund_id: uuid.UUID) -> Refund:
    refund = await _admin_refund(session, refund_id)
    if refund.status != RefundStatus.FAILED:
        raise _invalid(refund)
    before = _state(refund)
    refund.status = RefundStatus.PENDING
    await _queue(session, refund, at_once=True)
    await session.flush()
    await audit(session, admin, "refund.retry", "refund", refund.id, before, _state(refund))
    return refund


async def mark_sent(
    session: AsyncSession, admin: User, refund_id: uuid.UUID, provider_ref: str
) -> Refund:
    """An admin returned the money outside the platform and records the reference."""
    refund = await _admin_refund(session, refund_id)
    if refund.status == RefundStatus.SENT:
        raise _invalid(refund)
    booking = await session.get(Booking, refund.booking_id)
    assert booking is not None
    before = _state(refund)
    await _sent(session, refund, booking, provider_ref)
    await audit(session, admin, "refund.mark_sent", "refund", refund.id, before, _state(refund))
    return refund


async def refundable(session: AsyncSession, booking: Booking, source: str) -> int:
    """What is left to take from the owner's share or platform revenue for this booking."""
    account = (
        ledger.owner_account(booking.owner_profile_id)
        if source == "owner"
        else ledger.PLATFORM_REVENUE
    )
    return max(-(await ledger.booking_balance(session, booking.id, account)), 0)


async def admin_refund(
    session: AsyncSession,
    admin: User,
    booking_id: uuid.UUID,
    amount_tzs: int,
    source: str,
    note: str | None,
) -> Refund:
    """A discretionary refund (FR-031), taken from the owner's share or from platform revenue
    and capped at what the booking still holds there."""
    booking = await session.get(Booking, booking_id, with_for_update=True, populate_existing=True)
    if booking is None:
        raise not_found("booking")
    available = await refundable(session, booking, source)
    if amount_tzs > available:
        raise AppError("REFUND_EXCEEDS_BALANCE", 409, {"available_tzs": available})
    refund = await issue(
        session,
        booking,
        reason=RefundReason.ADMIN,
        created_by=admin.id,
        from_owner_tzs=amount_tzs if source == "owner" else 0,
        from_service_fee_tzs=amount_tzs if source == "platform" else 0,
    )
    if refund is None:
        raise AppError("BOOKING_NOT_PAID", 409)
    await audit(
        session,
        admin,
        "booking.refund",
        "booking",
        booking.id,
        None,
        {"refund_id": str(refund.id), "amount_tzs": amount_tzs, "source": source, "note": note},
    )
    return refund
