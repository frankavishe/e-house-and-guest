"""Migrations match the models, and the database enforces the core invariants (R1)."""

from datetime import UTC, date, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.accounts.models import OwnerKind, OwnerProfile
from app.availability.models import AvailabilityBlock, BlockKind, BlockSource
from app.catalog.models import BookingMode, Category, Location, LocationLevel, PriceUnit
from app.core.db import Base
from app.listings.models import Listing, ListingPrice
from tests.factories import make_user


async def test_models_match_migrations(engine: AsyncEngine) -> None:
    def diff(conn) -> list:  # type: ignore[no-untyped-def]
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        return compare_metadata(ctx, Base.metadata)

    async with engine.connect() as conn:
        changes = await conn.run_sync(diff)
    assert changes == [], f"models and migrations differ: {changes}"


async def _listing(db: AsyncSession) -> Listing:
    user = await make_user(db)
    owner = OwnerProfile(user_id=user.id, kind=OwnerKind.INDIVIDUAL, display_name="Owner")
    region = Location(id=900001, level=LocationLevel.REGION, name="R", slug="r-test")
    district = Location(
        id=900002, parent_id=900001, level=LocationLevel.DISTRICT, name="D", slug="d-test"
    )
    category = Category(
        path="test-leaf",
        slug="test-leaf",
        name={"sw": "Jaribio", "en": "Test"},
        booking_mode=BookingMode.DATE_RANGE,
        price_units=["night"],
        default_unit="night",
    )
    db.add_all([owner, region, category])
    await db.flush()
    db.add(district)
    await db.flush()
    listing = Listing(
        owner_profile_id=owner.id,
        category_id=category.id,
        title_sw="Chumba",
        description_sw="Maelezo",
        region_id=region.id,
        district_id=district.id,
    )
    db.add(listing)
    await db.flush()
    return listing


def _range(d1: int, d2: int) -> Range[datetime]:
    return Range(datetime(2026, 12, d1, tzinfo=UTC), datetime(2026, 12, d2, tzinfo=UTC))


async def test_overlapping_exclusive_blocks_are_rejected(db: AsyncSession) -> None:
    listing = await _listing(db)

    def block(d1: int, d2: int, *, active: bool = True) -> AvailabilityBlock:
        return AvailabilityBlock(
            listing_id=listing.id,
            period=_range(d1, d2),
            kind=BlockKind.EXCLUSIVE,
            source=BlockSource.OWNER_BLOCK,
            active=active,
        )

    db.add(block(1, 4))
    await db.flush()
    db.add(block(4, 6))  # half-open: check-out day is free
    db.add(block(2, 3, active=False))  # inactive blocks never conflict
    await db.flush()

    async with db.begin_nested():
        db.add(block(3, 5))
        with pytest.raises(IntegrityError, match="ex_availability_blocks_no_overlap"):
            await db.flush()


async def test_seasonal_prices_cannot_overlap(db: AsyncSession) -> None:
    listing = await _listing(db)
    db.add_all(
        [
            ListingPrice(listing_id=listing.id, unit=PriceUnit.NIGHT, amount_tzs=50_000),
            ListingPrice(
                listing_id=listing.id,
                unit=PriceUnit.NIGHT,
                amount_tzs=80_000,
                season_start=date(2026, 12, 15),
                season_end=date(2027, 1, 5),
            ),
        ]
    )
    await db.flush()
    async with db.begin_nested():
        db.add(
            ListingPrice(
                listing_id=listing.id,
                unit=PriceUnit.NIGHT,
                amount_tzs=90_000,
                season_start=date(2027, 1, 5),
                season_end=date(2027, 1, 10),
            )
        )
        with pytest.raises(IntegrityError, match="ex_listing_prices_season_overlap"):
            await db.flush()
    async with db.begin_nested():
        db.add(ListingPrice(listing_id=listing.id, unit=PriceUnit.NIGHT, amount_tzs=1))
        with pytest.raises(IntegrityError, match="uq_listing_prices_base_unit"):
            await db.flush()
