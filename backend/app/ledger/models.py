"""Append-only double-entry ledger (data-model.md "ledger_entries", R8).

Sign convention: debit +, credit -. The rows of one `txn_id` sum to 0 (deferred trigger),
and UPDATE/DELETE are rejected by a trigger; corrections are new reversing entries.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import pg_enum
from app.core import clock
from app.core.db import Base


class EntryType(StrEnum):
    PAYMENT = "payment"
    COMMISSION = "commission"
    DEPOSIT_HOLD = "deposit_hold"
    DEPOSIT_RELEASE = "deposit_release"
    REFUND = "refund"
    PAYOUT = "payout"
    ADJUSTMENT = "adjustment"


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    txn_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    account: Mapped[str] = mapped_column(Text, nullable=False)
    amount_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entry_type: Mapped[EntryType] = mapped_column(
        pg_enum(EntryType, "ledger_entry_type"), nullable=False
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id"), index=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    refund_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("refunds.id"))
    payout_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payouts.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_ledger_entries_account", "account"),)
