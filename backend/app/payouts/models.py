"""Payouts of owners' net earnings (data-model.md "payouts / payout_items", R7).

A payout batches an owner's eligible bookings; `payout_items.booking_id` is unique, so a
booking is paid out once. The destination is snapshotted when the money is sent.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import pg_enum
from app.core.db import Base, CreatedAt, Timestamps, UUIDPk


class PayoutStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PAID = "paid"
    FAILED = "failed"


class Payout(UUIDPk, Timestamps, Base):
    __tablename__ = "payouts"

    owner_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("owner_profiles.id"), nullable=False
    )
    amount_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[PayoutStatus] = mapped_column(
        pg_enum(PayoutStatus, "payout_status"), nullable=False, default=PayoutStatus.PENDING
    )
    payout_method_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payout_methods.id", ondelete="SET NULL")
    )
    # Masked copy of the destination at the last send attempt (PayoutMethodOut fields).
    payout_method: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    provider: Mapped[str | None] = mapped_column(Text)
    provider_ref: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    marked_paid_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index("ix_payouts_owner_profile_id_created_at", "owner_profile_id", "created_at"),
        Index("ix_payouts_status_updated_at", "status", "updated_at"),
    )


class PayoutItem(UUIDPk, CreatedAt, Base):
    __tablename__ = "payout_items"

    payout_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payouts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id"), unique=True, nullable=False
    )
    amount_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
