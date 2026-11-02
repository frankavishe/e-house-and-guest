"""Listings, photos and prices (data-model.md "listings", T039)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import pg_enum
from app.catalog.models import PriceUnit
from app.core.db import Base, CreatedAt, Timestamps, UUIDPk


class ListingStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    PAUSED = "paused"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class DeliveryOption(StrEnum):
    NONE = "none"
    OPTIONAL = "optional"
    REQUIRED = "required"


class CancellationPolicy(StrEnum):
    FLEXIBLE = "flexible"
    MODERATE = "moderate"
    STRICT = "strict"


class ReviewState(StrEnum):
    NONE = "none"
    PENDING = "pending"
    REJECTED = "rejected"


SEARCH_TSV_SQL = "to_tsvector('simple', coalesce(title_sw, '') || ' ' || coalesce(title_en, ''))"


class Listing(UUIDPk, Timestamps, Base):
    __tablename__ = "listings"

    owner_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("owner_profiles.id"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), nullable=False)
    title_sw: Mapped[str | None] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    description_sw: Mapped[str | None] = mapped_column(Text)
    description_en: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    # Required to submit; a fresh draft only has its category.
    region_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    ward_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    address_hint: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deposit_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    delivery: Mapped[DeliveryOption] = mapped_column(
        pg_enum(DeliveryOption, "delivery_option"), nullable=False, default=DeliveryOption.NONE
    )
    delivery_fee_tzs: Mapped[int | None] = mapped_column(BigInteger)
    delivery_area: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    min_duration: Mapped[int | None] = mapped_column(Integer)
    max_duration: Mapped[int | None] = mapped_column(Integer)
    slot_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    cancellation_policy: Mapped[CancellationPolicy] = mapped_column(
        pg_enum(CancellationPolicy, "cancellation_policy"),
        nullable=False,
        default=CancellationPolicy.MODERATE,
    )
    instant_book: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_price_tzs: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[ListingStatus] = mapped_column(
        pg_enum(ListingStatus, "listing_status"), nullable=False, default=ListingStatus.DRAFT
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    pending_changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    review_state: Mapped[ReviewState] = mapped_column(
        pg_enum(ReviewState, "review_state"), nullable=False, default=ReviewState.NONE
    )
    search_tsv: Mapped[Any] = mapped_column(TSVECTOR, Computed(SEARCH_TSV_SQL, persisted=True))
    rating_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ix_listings_active_category_district",
            "status",
            "category_id",
            "district_id",
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_listings_attributes",
            "attributes",
            postgresql_using="gin",
            postgresql_ops={"attributes": "jsonb_path_ops"},
        ),
        Index("ix_listings_base_price_tzs", "base_price_tzs"),
        Index("ix_listings_lat_lng", "lat", "lng"),
        Index("ix_listings_search_tsv", "search_tsv", postgresql_using="gin"),
    )

    def title(self, locale: str) -> str:
        """Localized title with fallback to the other language (R13)."""
        first, second = (
            (self.title_en, self.title_sw) if locale == "en" else (self.title_sw, self.title_en)
        )
        return first or second or ""


class ListingPhoto(UUIDPk, CreatedAt, Base):
    __tablename__ = "listing_photos"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    # {"320": key, "640": key, "1280": key} once the image job has run; empty before.
    variants: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alt_sw: Mapped[str | None] = mapped_column(Text)
    alt_en: Mapped[str | None] = mapped_column(Text)
    # Set when the owner confirms the upload; unconfirmed rows are invisible everywhere.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Added to a live listing and awaiting review: hidden from the public until approved.
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ListingPrice(UUIDPk, CreatedAt, Base):
    __tablename__ = "listing_prices"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit: Mapped[PriceUnit] = mapped_column(pg_enum(PriceUnit, "price_unit"), nullable=False)
    amount_tzs: Mapped[int] = mapped_column(BigInteger, nullable=False)
    season_start: Mapped[date | None] = mapped_column(Date)
    season_end: Mapped[date | None] = mapped_column(Date)

    # Seasons of one unit must not overlap: `ex_listing_prices_season_overlap` (gist
    # exclusion on a daterange expression) is created in migration 0005.
    __table_args__ = (
        # Exactly one non-seasonal (base) price per unit.
        Index(
            "uq_listing_prices_base_unit",
            "listing_id",
            "unit",
            unique=True,
            postgresql_where=text("season_start IS NULL"),
        ),
    )
