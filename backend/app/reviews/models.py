"""Reviews after completed bookings and abuse reports (data-model.md "Trust & communication",
FR-029, FR-030)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import pg_enum
from app.core.db import Base, CreatedAt, Timestamps, UUIDPk

REVIEW_MAX = 1000
REASON_MAX = 1000


class ReviewSubject(StrEnum):
    LISTING = "listing"  # written by the renter; counts for the listing and its owner
    RENTER = "renter"  # written by the owner; counts for the renter


class Review(UUIDPk, CreatedAt, Base):
    __tablename__ = "reviews"

    booking_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bookings.id"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    subject: Mapped[ReviewSubject] = mapped_column(
        pg_enum(ReviewSubject, "review_subject"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # One review per author per booking (FR-029).
        Index("uq_reviews_booking_id_author_id", "booking_id", "author_id", unique=True),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint(f"char_length(body) <= {REVIEW_MAX}", name="body_length"),
    )


class ReportTarget(StrEnum):
    LISTING = "listing"
    USER = "user"


class ReportStatus(StrEnum):
    OPEN = "open"
    ACTIONED = "actioned"
    DISMISSED = "dismissed"


class AbuseReport(UUIDPk, Timestamps, Base):
    """A user's report of a listing or user, handled by an admin (US7)."""

    __tablename__ = "abuse_reports"

    reporter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    target_kind: Mapped[ReportTarget] = mapped_column(
        pg_enum(ReportTarget, "report_target"), nullable=False
    )
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        pg_enum(ReportStatus, "report_status"), nullable=False, default=ReportStatus.OPEN
    )
    handled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_abuse_reports_status_created_at", "status", "created_at"),
        Index("ix_abuse_reports_target", "target_kind", "target_id"),
        # A reporter has at most one open report per target.
        Index(
            "uq_abuse_reports_one_open",
            "reporter_id",
            "target_kind",
            "target_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
    )
