"""Locations (region > district > ward) and the category tree (data-model.md "Catalogue")."""

import uuid
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import pg_enum
from app.core.db import Base, Timestamps, UUIDPk


class LocationLevel(StrEnum):
    REGION = "region"
    DISTRICT = "district"
    WARD = "ward"


class BookingMode(StrEnum):
    DATE_RANGE = "DATE_RANGE"
    TIME_SLOT = "TIME_SLOT"
    LEASE = "LEASE"
    QUANTITY = "QUANTITY"


class PriceUnit(StrEnum):
    HOUR = "hour"
    NIGHT = "night"
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ITEM_DAY = "item_day"


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), index=True)
    level: Mapped[LocationLevel] = mapped_column(pg_enum(LocationLevel, "location_level"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    __table_args__ = (
        UniqueConstraint(
            "parent_id", "slug", name="uq_locations_parent_slug", postgresql_nulls_not_distinct=True
        ),
    )


class Category(UUIDPk, Timestamps, Base):
    __tablename__ = "categories"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    booking_mode: Mapped[BookingMode | None] = mapped_column(pg_enum(BookingMode, "booking_mode"))
    price_units: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    default_unit: Mapped[str | None] = mapped_column(Text)
    attribute_schema: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    commission_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    renter_fee_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_categories_path", "path", postgresql_ops={"path": "text_pattern_ops"}),
    )

    @property
    def is_leaf(self) -> bool:
        """Leaves carry a booking mode; only leaves can hold listings."""
        return self.booking_mode is not None
