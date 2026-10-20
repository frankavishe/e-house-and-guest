"""Append-only, balanced ledger (T069, Principle III, R8)."""

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ledger import service as ledger
from app.ledger.models import EntryType, LedgerEntry
from tests.factories import day_range, make_bookable, make_booking

pytestmark = pytest.mark.usefixtures("frozen_clock")

D = date(2026, 11, 10)


async def test_post_rejects_unbalanced_entries(db: AsyncSession) -> None:
    with pytest.raises(ValueError, match="balance"):
        await ledger.post(
            db,
            [
                ledger.Line("provider_cash", 100, EntryType.PAYMENT),
                ledger.Line("platform_revenue", -90, EntryType.COMMISSION),
            ],
        )


async def test_database_rejects_unbalanced_txn(db: AsyncSession) -> None:
    """The balance trigger is deferred to commit; force it to run now."""
    sp = await db.begin_nested()
    await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    db.add(
        LedgerEntry(
            txn_id=uuid.uuid4(), account="provider_cash", amount_tzs=100,
            entry_type=EntryType.PAYMENT,
        )
    )
    with pytest.raises(DBAPIError, match="unbalanced"):
        await db.flush()
    await sp.rollback()


async def test_database_rejects_update_and_delete(db: AsyncSession) -> None:
    txn = await ledger.post(
        db,
        [
            ledger.Line("provider_cash", 100, EntryType.PAYMENT),
            ledger.Line("platform_revenue", -100, EntryType.COMMISSION),
        ],
    )
    for statement in (
        "UPDATE ledger_entries SET amount_tzs = 0 WHERE txn_id = :txn",
        "DELETE FROM ledger_entries WHERE txn_id = :txn",
    ):
        sp = await db.begin_nested()
        with pytest.raises(DBAPIError, match="append-only"):
            await db.execute(text(statement), {"txn": txn})
        await sp.rollback()


async def test_booking_payment_split_and_owner_balance(db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *day_range(D, date(2026, 11, 13)), total=0)
    # rental 200,000 · delivery 10,000 · service fee 6,000 · deposit 50,000 · 10% commission
    booking.rental_tzs, booking.delivery_fee_tzs = 200_000, 10_000
    booking.service_fee_tzs, booking.deposit_tzs = 6_000, 50_000
    booking.total_tzs, booking.commission_tzs = 266_000, 20_000
    await db.flush()

    txn = await ledger.post_booking_payment(db, booking, payment_id=None)
    rows = (
        (await db.execute(text("SELECT account, amount_tzs FROM ledger_entries WHERE txn_id = :t"),
                          {"t": txn}))
        .all()
    )
    assert dict(rows) == {
        "provider_cash": 266_000,
        "deposit_held": -50_000,
        "platform_revenue": -26_000,  # commission + renter service fee
        f"owner_payable:{b.owner.id}": -190_000,  # rental - commission + delivery
    }
    assert await ledger.balance(db, ledger.owner_account(b.owner.id)) == -190_000
    assert await ledger.balance(db, "deposit_held") == -50_000


async def test_refund_reverses_cash(db: AsyncSession) -> None:
    b = await make_bookable(db)
    booking = await make_booking(db, b, *day_range(D, date(2026, 11, 13)), total=80_000)
    await ledger.post_unmatched_payment(db, booking, 80_000, payment_id=None)
    await ledger.post_refund(db, booking, 80_000, payment_id=None, refund_id=None)
    assert await ledger.balance(db, "provider_cash") == 0
    assert await ledger.balance(db, "renter_clearing") == 0
