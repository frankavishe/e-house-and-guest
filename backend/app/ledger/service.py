"""Ledger postings (R8, Principle III). Every money event is one balanced `txn_id`.

Accounts: `provider_cash` (money held at the payment provider), `renter_clearing` (money
received that belongs to no booking line, e.g. a late payment being refunded),
`deposit_held`, `platform_revenue` (commission + renter service fee) and
`owner_payable:<owner_profile_id>`. Sign convention: debit +, credit -.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bookings.models import Booking, LeaseInstallment
from app.ledger.models import EntryType, LedgerEntry

PROVIDER_CASH = "provider_cash"
RENTER_CLEARING = "renter_clearing"
DEPOSIT_HELD = "deposit_held"
PLATFORM_REVENUE = "platform_revenue"


def owner_account(owner_profile_id: uuid.UUID) -> str:
    return f"owner_payable:{owner_profile_id}"


@dataclass(frozen=True)
class Line:
    account: str
    amount_tzs: int
    entry_type: EntryType


async def post(
    session: AsyncSession,
    lines: Sequence[Line],
    *,
    booking_id: uuid.UUID | None = None,
    payment_id: uuid.UUID | None = None,
    refund_id: uuid.UUID | None = None,
    payout_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Write one balanced transaction; zero-amount lines are skipped."""
    if sum(line.amount_tzs for line in lines) != 0:
        raise ValueError("ledger lines must balance to 0")
    txn = uuid.uuid4()
    for line in lines:
        if line.amount_tzs == 0:
            continue
        session.add(
            LedgerEntry(
                txn_id=txn,
                account=line.account,
                amount_tzs=line.amount_tzs,
                entry_type=line.entry_type,
                booking_id=booking_id,
                payment_id=payment_id,
                refund_id=refund_id,
                payout_id=payout_id,
            )
        )
    await session.flush()
    return txn


async def post_booking_payment(
    session: AsyncSession,
    booking: Booking,
    payment_id: uuid.UUID | None,
    installment: LeaseInstallment | None = None,
) -> uuid.UUID:
    """Money in for a booking (or one lease installment), split to its accounts.

    The first payment of a booking carries the deposit and delivery fee; a lease installment
    carries only its own rental, service fee and commission share.
    """
    if installment is None:
        rental, service_fee = booking.rental_tzs, booking.service_fee_tzs
        commission = booking.commission_tzs
        deposit, delivery = booking.deposit_tzs, booking.delivery_fee_tzs
    else:
        rental, service_fee = installment.rental_tzs, installment.service_fee_tzs
        commission = installment.commission_tzs
        first = installment.seq == 1
        deposit = booking.deposit_tzs if first else 0
        delivery = booking.delivery_fee_tzs if first else 0
    total = rental + service_fee + deposit + delivery
    return await post(
        session,
        [
            Line(PROVIDER_CASH, total, EntryType.PAYMENT),
            Line(DEPOSIT_HELD, -deposit, EntryType.DEPOSIT_HOLD),
            Line(PLATFORM_REVENUE, -(commission + service_fee), EntryType.COMMISSION),
            Line(
                owner_account(booking.owner_profile_id),
                -(rental - commission + delivery),
                EntryType.PAYMENT,
            ),
        ],
        booking_id=booking.id,
        payment_id=payment_id,
    )


async def post_unmatched_payment(
    session: AsyncSession, booking: Booking, amount_tzs: int, payment_id: uuid.UUID | None
) -> uuid.UUID:
    """Money in that will be refunded (e.g. a payment after the hold was given away)."""
    return await post(
        session,
        [
            Line(PROVIDER_CASH, amount_tzs, EntryType.PAYMENT),
            Line(RENTER_CLEARING, -amount_tzs, EntryType.PAYMENT),
        ],
        booking_id=booking.id,
        payment_id=payment_id,
    )


async def post_refund(
    session: AsyncSession,
    booking: Booking,
    amount_tzs: int,
    payment_id: uuid.UUID | None,
    refund_id: uuid.UUID | None,
    *,
    source: str = RENTER_CLEARING,
) -> uuid.UUID:
    """Money out to the renter, taken from `source` (clearing, deposit or owner payable)."""
    return await post(
        session,
        [
            Line(source, amount_tzs, EntryType.REFUND),
            Line(PROVIDER_CASH, -amount_tzs, EntryType.REFUND),
        ],
        booking_id=booking.id,
        payment_id=payment_id,
        refund_id=refund_id,
    )


async def post_refund_due(
    session: AsyncSession,
    booking: Booking,
    refund_id: uuid.UUID,
    *,
    from_owner_tzs: int = 0,
    from_commission_tzs: int = 0,
    from_service_fee_tzs: int = 0,
    from_deposit_tzs: int = 0,
) -> uuid.UUID:
    """Money the renter is owed moves into `renter_clearing` as soon as the refund is decided
    (US5), so it can no longer be paid out; `post_refund` later sends it from there."""
    total = from_owner_tzs + from_commission_tzs + from_service_fee_tzs + from_deposit_tzs
    return await post(
        session,
        [
            Line(owner_account(booking.owner_profile_id), from_owner_tzs, EntryType.ADJUSTMENT),
            # Commission handed back is a (positive) `commission` line, kept apart from the
            # service fee so earnings can tell what commission the booking kept.
            Line(PLATFORM_REVENUE, from_commission_tzs, EntryType.COMMISSION),
            Line(PLATFORM_REVENUE, from_service_fee_tzs, EntryType.ADJUSTMENT),
            Line(DEPOSIT_HELD, from_deposit_tzs, EntryType.DEPOSIT_RELEASE),
            Line(RENTER_CLEARING, -total, EntryType.ADJUSTMENT),
        ],
        booking_id=booking.id,
        refund_id=refund_id,
    )


async def post_deposit_award(session: AsyncSession, booking: Booking, amount_tzs: int) -> uuid.UUID:
    """Part of the held deposit goes to the owner after a damage claim (US5)."""
    return await post(
        session,
        [
            Line(DEPOSIT_HELD, amount_tzs, EntryType.DEPOSIT_RELEASE),
            Line(owner_account(booking.owner_profile_id), -amount_tzs, EntryType.ADJUSTMENT),
        ],
        booking_id=booking.id,
    )


async def booking_balance(session: AsyncSession, booking_id: uuid.UUID, account: str) -> int:
    """Signed balance of `account` for one booking's entries."""
    total = await session.execute(
        select(func.coalesce(func.sum(LedgerEntry.amount_tzs), 0)).where(
            LedgerEntry.booking_id == booking_id, LedgerEntry.account == account
        )
    )
    return int(total.scalar_one())


async def post_payout(
    session: AsyncSession, owner_profile_id: uuid.UUID, amount_tzs: int, payout_id: uuid.UUID
) -> uuid.UUID:
    """Money out to the owner: settles their payable (US4)."""
    return await post(
        session,
        [
            Line(owner_account(owner_profile_id), amount_tzs, EntryType.PAYOUT),
            Line(PROVIDER_CASH, -amount_tzs, EntryType.PAYOUT),
        ],
        payout_id=payout_id,
    )


async def balance(session: AsyncSession, account: str) -> int:
    """Signed balance (debit +). An owner's earnings are `-balance(owner_account(id))`."""
    total = await session.execute(
        select(func.coalesce(func.sum(LedgerEntry.amount_tzs), 0)).where(
            LedgerEntry.account == account
        )
    )
    return int(total.scalar_one())
