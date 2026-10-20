"""Payments (R6, Principle III).

- `start_payment` creates one pending payment per booking and sends the USSD push.
- `handle_callback` stores the raw callback idempotently, then asks the provider for the
  real status: a callback is a trigger and never trusted on its own.
- `apply_status` moves a payment out of `pending` with a guarded UPDATE, so a second
  success can never confirm twice. On success it confirms the booking (or pays a lease
  installment), posts the ledger and queues notifications, in the caller's transaction.
- A success after the hold expired re-reserves the dates when they are still free and
  refunds the renter otherwise.
- `reconcile_pending` re-checks payments whose callback never came.

Only `start_payment` commits (the push must not go out before the payment row exists);
everything else leaves the commit to the router or the worker.
"""

import logging
import uuid
from collections.abc import Mapping
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import PaymentNetwork, User
from app.availability import service as availability
from app.availability.periods import Period
from app.bookings import notify
from app.bookings.models import (
    ActorKind,
    Booking,
    BookingStatus,
    CancelledBy,
    InstallmentStatus,
    LeaseInstallment,
)
from app.bookings.service import (
    OPEN_LEASE,
    first_payment_amount,
    get_for_party,
    installment_payable,
    installments_of,
)
from app.bookings.state import Event, invalid_transition, transition
from app.core import clock
from app.core.errors import AppError, forbidden, not_found
from app.core.i18n import money
from app.integrations import get_payment_provider
from app.integrations.payments.base import (
    Network,
    PaymentProvider,
    ProviderUnavailable,
)
from app.integrations.payments.base import (
    PaymentStatus as ProviderStatus,
)
from app.ledger import service as ledger
from app.listings.models import Listing
from app.payments.models import (
    Payment,
    PaymentEvent,
    PaymentStatus,
    Refund,
    RefundReason,
    RefundStatus,
)
from app.payments.schemas import PaymentCreate

log = logging.getLogger(__name__)

RECONCILE_AFTER = timedelta(minutes=2)
STATUS_CHECK_AFTER = timedelta(seconds=60)
# A push nobody answered for this long is given up on (the renter can pay again).
ABANDON_AFTER = timedelta(minutes=30)


def payment_pending() -> AppError:
    return AppError("PAYMENT_PENDING", 409)


# --- starting a payment -------------------------------------------------------------------


async def _has_pending(session: AsyncSession, booking_id: uuid.UUID) -> bool:
    count = await session.execute(
        select(func.count())
        .select_from(Payment)
        .where(Payment.booking_id == booking_id, Payment.status == PaymentStatus.PENDING)
    )
    return count.scalar_one() > 0


async def start_payment(
    session: AsyncSession, user: User, booking_id: uuid.UUID, body: PaymentCreate
) -> Payment:
    provider = get_payment_provider()
    booking, role = await get_for_party(session, user, booking_id, lock=True)
    if role != "renter":
        raise forbidden()
    installments = await installments_of(session, booking.id)
    installment: LeaseInstallment | None
    if body.installment_id is not None:
        installment = next((i for i in installments if i.id == body.installment_id), None)
        if installment is None:
            raise not_found("installment")
        if not installment_payable(booking, installment):
            raise AppError("INSTALLMENT_NOT_DUE", 409)
        amount = installment.amount_tzs
    else:
        due = booking.payment_due_at
        if booking.status != BookingStatus.AWAITING_PAYMENT or (due and due <= clock.now()):
            raise invalid_transition(booking.status, Event.PAY)
        installment = installments[0] if installments else None
        amount = first_payment_amount(booking, installments)
    if await _has_pending(session, booking.id):
        raise payment_pending()

    payment = Payment(
        booking_id=booking.id,
        lease_installment_id=installment.id if installment else None,
        provider=provider.name,
        network=PaymentNetwork(body.network),
        msisdn=body.msisdn,
        amount_tzs=amount,
        status=PaymentStatus.PENDING,
    )
    try:
        async with session.begin_nested():
            session.add(payment)
            await session.flush()
    except IntegrityError as exc:  # a concurrent request created the pending payment
        raise payment_pending() from exc
    await session.commit()

    try:
        started = await provider.start_checkout(
            payment_id=payment.id,
            amount_tzs=amount,
            msisdn=payment.msisdn,
            network=Network(body.network),
        )
    except ProviderUnavailable:
        log.warning("payment provider unavailable for payment %s", payment.id)
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "provider_unavailable"
        await session.commit()
        return payment
    payment.provider_txn_id = started.provider_txn_id
    await session.commit()
    return payment


# --- settling -----------------------------------------------------------------------------


def _booking_period(booking: Booking) -> Period:
    """Enough of a `Period` to re-reserve a booking's own dates."""
    start, end = booking.period.lower, booking.period.upper
    assert start is not None and end is not None
    first, last = clock.to_eat(start).date(), clock.to_eat(end - timedelta(seconds=1)).date()
    days = tuple(first + timedelta(days=i) for i in range((last - first).days + 1))
    return Period(booking.booking_mode, start, end, "", len(days), booking.quantity, days)


async def _reserve_again(session: AsyncSession, booking: Booking) -> bool:
    listing = await session.get(Listing, booking.listing_id)
    assert listing is not None
    try:
        await availability.reserve(
            session, listing, booking.booking_mode, _booking_period(booking), booking.id
        )
    except AppError:
        return False
    return True


async def _refund_late(
    session: AsyncSession, provider: PaymentProvider, booking: Booking, payment: Payment
) -> None:
    """Money arrived for dates we no longer hold: keep it in clearing and send it back."""
    await ledger.post_unmatched_payment(session, booking, payment.amount_tzs, payment.id)
    refund = Refund(
        booking_id=booking.id,
        payment_id=payment.id,
        amount_tzs=payment.amount_tzs,
        reason=RefundReason.LATE_PAYMENT,
        status=RefundStatus.PENDING,
    )
    session.add(refund)
    await session.flush()
    try:
        result = await provider.refund(
            payment_id=payment.id,
            amount_tzs=payment.amount_tzs,
            msisdn=payment.msisdn,
            network=Network(payment.network.value),
        )
    except ProviderUnavailable:
        result = None
    if result is not None and result.ok:
        refund.status = RefundStatus.SENT
        refund.provider_ref = result.provider_ref
        await ledger.post_refund(session, booking, payment.amount_tzs, payment.id, refund.id)
    else:
        # Stays in renter_clearing until an admin refunds by hand (US5/US7 tooling).
        refund.status = RefundStatus.FAILED
        refund.failure_reason = result.failure_reason if result else "provider_unavailable"
    await notify.to_renter(session, booking, "payment.refunded", amount=money(payment.amount_tzs))


async def _settle(
    session: AsyncSession, provider: PaymentProvider, booking: Booking, payment: Payment
) -> None:
    installment = (
        await session.get(LeaseInstallment, payment.lease_installment_id)
        if payment.lease_installment_id
        else None
    )
    first = installment is None or installment.seq == 1
    note = f"payment {payment.id}"

    async def mark_paid() -> None:
        if installment is not None:
            installment.status = InstallmentStatus.PAID
            installment.payment_id = payment.id
        await ledger.post_booking_payment(session, booking, payment.id, installment)

    if first and booking.status == BookingStatus.AWAITING_PAYMENT:
        booking.payment_due_at = None
        await mark_paid()
        await transition(session, booking, Event.PAY, actor_kind=ActorKind.PROVIDER, note=note)
    elif (
        installment is not None
        and not first
        and booking.status in OPEN_LEASE
        and installment.status in (InstallmentStatus.PENDING, InstallmentStatus.OVERDUE)
    ):
        await mark_paid()
        await notify.installment_event(
            session, booking, installment, "lease.installment_paid", who="renter"
        )
    elif (
        first
        and booking.status == BookingStatus.CANCELLED
        and booking.cancelled_by == CancelledBy.SYSTEM
        and await _reserve_again(session, booking)
    ):
        booking.payment_due_at = None
        await mark_paid()
        await transition(
            session, booking, Event.LATE_PAYMENT, actor_kind=ActorKind.PROVIDER, note=note
        )
    else:
        await _refund_late(session, provider, booking, payment)


async def apply_status(
    session: AsyncSession, provider: PaymentProvider, payment_id: uuid.UUID, status: ProviderStatus
) -> bool:
    """Apply an authoritative provider status. Returns whether the payment changed."""
    if status.state == "pending":
        return False
    now = clock.now()
    values: dict[str, object] = {"status": PaymentStatus(status.state), "updated_at": now}
    if status.state == "succeeded":
        values["confirmed_at"] = now
    else:
        values["failure_reason"] = status.failure_reason or status.state
    if status.provider_txn_id:
        values["provider_txn_id"] = func.coalesce(Payment.provider_txn_id, status.provider_txn_id)
    changed = await session.execute(
        update(Payment)
        .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
        .values(**values)
        .returning(Payment.id)
    )
    if changed.scalar_one_or_none() is None:
        return False  # already settled: a duplicate callback or a racing check
    payment = await session.get(Payment, payment_id, populate_existing=True)
    assert payment is not None
    booking = await session.get(
        Booking, payment.booking_id, with_for_update=True, populate_existing=True
    )
    assert booking is not None
    if status.state == "succeeded":
        await _settle(session, provider, booking, payment)
    elif status.state == "failed":
        await notify.to_renter(session, booking, "payment.failed")
    return True


# --- callbacks and checks -----------------------------------------------------------------


async def handle_callback(
    session: AsyncSession, provider: PaymentProvider, headers: Mapping[str, str], body: bytes
) -> None:
    """Raises InvalidCallback when authentication or parsing fails (→ 401)."""
    event = provider.parse_callback(headers=headers, body=body)
    payment: Payment | None = None
    if event.payment_id is not None:
        payment = await session.get(Payment, event.payment_id)
    if payment is None and event.provider_txn_id:
        payment = (
            await session.execute(
                select(Payment).where(
                    Payment.provider == provider.name,
                    Payment.provider_txn_id == event.provider_txn_id,
                )
            )
        ).scalar_one_or_none()
    inserted = await session.execute(
        insert(PaymentEvent)
        .values(
            id=uuid.uuid4(),
            provider=provider.name,
            provider_event_id=event.provider_event_id,
            payment_id=payment.id if payment else None,
            payload=dict(event.raw),
            received_at=clock.now(),
        )
        .on_conflict_do_nothing(constraint="uq_payment_events_provider_event")
        .returning(PaymentEvent.id)
    )
    event_row = inserted.scalar_one_or_none()
    if event_row is None:
        return  # seen before
    if payment is not None and payment.status == PaymentStatus.PENDING:
        status = await provider.get_status(
            payment_id=payment.id,
            provider_txn_id=payment.provider_txn_id or event.provider_txn_id,
        )
        await apply_status(session, provider, payment.id, status)
    await session.execute(
        update(PaymentEvent).where(PaymentEvent.id == event_row).values(processed_at=clock.now())
    )


async def check(session: AsyncSession, payment: Payment) -> bool:
    """Ask the provider about one pending payment and apply the answer."""
    provider = get_payment_provider()
    try:
        status = await provider.get_status(
            payment_id=payment.id, provider_txn_id=payment.provider_txn_id
        )
    except ProviderUnavailable:
        return False
    if status.state == "pending" and payment.created_at <= clock.now() - ABANDON_AFTER:
        status = ProviderStatus(state="expired", failure_reason="no_response")
    return await apply_status(session, provider, payment.id, status)


async def get_payment(session: AsyncSession, user: User, payment_id: uuid.UUID) -> Payment:
    """The renter's payment; a pending one older than 60 s is re-checked first."""
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise not_found("payment")
    _, role = await get_for_party(session, user, payment.booking_id)
    if role == "owner":
        raise not_found("payment")
    if (
        payment.status == PaymentStatus.PENDING
        and payment.created_at <= clock.now() - STATUS_CHECK_AFTER
        and await check(session, payment)
    ):
        await session.commit()
        await session.refresh(payment)
    return payment


async def reconcile_pending(session: AsyncSession) -> int:
    """Re-check pending payments older than 2 minutes (lost callbacks, R6)."""
    rows = await session.execute(
        select(Payment)
        .where(
            Payment.status == PaymentStatus.PENDING,
            Payment.created_at <= clock.now() - RECONCILE_AFTER,
        )
        .order_by(Payment.created_at)
        .limit(100)
    )
    changed = 0
    for payment in rows.scalars().all():
        if await check(session, payment):
            changed += 1
    return changed
