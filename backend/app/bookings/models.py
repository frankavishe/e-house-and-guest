"""Bookings (data-model.md "bookings", R17). Lifecycle logic lives in `state.py` (US2)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TSTZRANGE, Range
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import pg_enum
from app.catalog.models import BookingMode
from app.core.db import Base, Timestamps, UUIDPk
from app.listings.models import CancellationPolicy


class BookingStatus(StrEnum):
    REQUESTED = "requested"
    AWAITING_PAYMENT = "awaiting_payment"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class CancelledBy(StrEnum):
    RENTER = "renter"
    OWNER = "owner"
    ADMIN = "admin"
    SYSTEM = "system"


class Booking(UUIDPk, Timestamps, Base):
    __tablename__ = "bookings"

    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id"), nullable=False, index=True
    )
    renter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    owner_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("owner_profiles.id"), nullable=False
    )
    booking_mode: Mapped[BookingMode] = mapped_column(
        pg_enum(BookingMode, "booking_mode"), nullable=False
    )
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[BookingStatus] = mapped_column(
        pg_enum(BookingStatus, "booking_status"), nullable=False
    )
    quote: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rental_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delivery_fee_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    service_fee_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    deposit_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commission_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cancellation_policy: Mapped[CancellationPolicy] = mapped_column(
        pg_enum(CancellationPolicy, "cancellation_policy"), nullable=False
    )
    delivery_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    delivery_address: Mapped[str | None] = mapped_column(Text)
    payment_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_months: Mapped[int | None] = mapped_column(Integer)
    cancelled_by: Mapped[CancelledBy | None] = mapped_column(pg_enum(CancelledBy, "cancelled_by"))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_bookings_status_payment_due_at", "status", "payment_due_at"),
        Index("ix_bookings_status_request_expires_at", "status", "request_expires_at"),
        Index("ix_bookings_renter_id_created_at", "renter_id", "created_at"),
        Index("ix_bookings_owner_profile_id_status", "owner_profile_id", "status"),
    )
