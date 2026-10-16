"""Availability blocks (R1): every hold, booking and owner block on a listing's calendar."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import TSTZRANGE, ExcludeConstraint, Range
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import pg_enum
from app.core.db import Base, Timestamps, UUIDPk


class BlockKind(StrEnum):
    EXCLUSIVE = "exclusive"
    STOCK = "stock"


class BlockSource(StrEnum):
    BOOKING = "booking"
    OWNER_BLOCK = "owner_block"


class AvailabilityBlock(UUIDPk, Timestamps, Base):
    __tablename__ = "availability_blocks"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    period: Mapped[Range[datetime]] = mapped_column(TSTZRANGE, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    kind: Mapped[BlockKind] = mapped_column(pg_enum(BlockKind, "block_kind"), nullable=False)
    source: Mapped[BlockSource] = mapped_column(
        pg_enum(BlockSource, "block_source"), nullable=False
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        # The double-booking guarantee (Principle IV): overlapping active exclusive blocks
        # on one listing cannot exist, however many API workers race.
        ExcludeConstraint(
            ("listing_id", "="),
            ("period", "&&"),
            name="ex_availability_blocks_no_overlap",
            using="gist",
            where=text("kind = 'exclusive' AND active"),
        ),
        Index(
            "ix_availability_blocks_listing_period",
            "listing_id",
            "period",
            postgresql_using="gist",
            postgresql_where=text("active"),
        ),
    )
