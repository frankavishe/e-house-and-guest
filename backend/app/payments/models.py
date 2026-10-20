"""Payments, raw provider events and refunds (data-model.md "Payments & money", R6)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import PaymentNetwork, pg_enum
from app.core.db import Base, Timestamps, UUIDPk


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class Payment(UUIDPk, Timestamps, Base):
    """`id` doubles as our external reference at the provider. Status only moves out of
    `pending`, through guarded updates in `payments.service`."""

    __tablename__ = "payments"

    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), nullable=False)
    lease_installment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lease_installments.id")
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    network: Mapped[PaymentNetwork] = mapped_column(
        pg_enum(PaymentNetwork, "payment_network"), nullable=False
    )
    msisdn: Mapped[str] = mapped_column(Text, nullable=False)
    amount_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        pg_enum(PaymentStatus, "payment_status"), nullable=False, default=PaymentStatus.PENDING
    )
    provider_txn_id: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_payments_booking_id", "booking_id"),
        # At most one pending payment per booking (the renter retries after a failure).
        Index(
            "uq_payments_one_pending",
            "booking_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        UniqueConstraint("provider", "provider_txn_id", name="uq_payments_provider_txn"),
        Index("ix_payments_status_created_at", "status", "created_at"),
    )


class PaymentEvent(UUIDPk, Base):
    """A raw callback. The unique key makes repeated callbacks no-ops (Principle III)."""

    __tablename__ = "payment_events"

    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_payment_events_provider_event"),
    )


class RefundReason(StrEnum):
    CANCELLATION = "cancellation"
    DEPOSIT_RETURN = "deposit_return"
    OWNER_CANCEL = "owner_cancel"
    ADMIN = "admin"
    LATE_PAYMENT = "late_payment"


class RefundStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class Refund(UUIDPk, Timestamps, Base):
    __tablename__ = "refunds"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id"), nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payments.id"), nullable=False, index=True
    )
    amount_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[RefundReason] = mapped_column(
        pg_enum(RefundReason, "refund_reason"), nullable=False
    )
    status: Mapped[RefundStatus] = mapped_column(
        pg_enum(RefundStatus, "refund_status"), nullable=False, default=RefundStatus.PENDING
    )
    provider_ref: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
