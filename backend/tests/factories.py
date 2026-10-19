"""Test data helpers. Each returns persisted (flushed) rows inside the test transaction."""

import itertools
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import (
    Language,
    OwnerKind,
    OwnerProfile,
    User,
    UserStatus,
    VerificationStatus,
)
from app.availability.models import AvailabilityBlock, BlockKind, BlockSource
from app.catalog.models import BookingMode, Category, Location, LocationLevel, PriceUnit
from app.core import security
from app.listings.models import (
    CancellationPolicy,
    DeliveryOption,
    Listing,
    ListingPhoto,
    ListingPrice,
    ListingStatus,
)

_phones = itertools.count(1)
_location_ids = itertools.count(980_001)
_slugs = itertools.count(1)


def next_phone() -> str:
    return f"+25571{next(_phones):07d}"


async def make_user(
    db: AsyncSession,
    *,
    phone: str | None = None,
    name: str | None = "Test User",
    is_admin: bool = False,
    status: str = "active",
    language: str = "sw",
) -> User:
    user = User(
        phone=phone or next_phone(),
        name=name,
        is_admin=is_admin,
        status=UserStatus(status),
        language=Language(language),
    )
    db.add(user)
    await db.flush()
    return user


def sign_in(client: httpx.AsyncClient, user: User) -> None:
    """Attach an access-token cookie for `user` to the client (skips the OTP flow)."""
    client.cookies.set(
        security.ACCESS_COOKIE, security.encode_access_token(user.id, is_admin=user.is_admin)
    )


async def make_owner(
    db: AsyncSession,
    *,
    user: User | None = None,
    verification: str = "verified",
    display_name: str = "Test Owner",
) -> OwnerProfile:
    user = user or await make_user(db)
    profile = OwnerProfile(
        user_id=user.id,
        kind=OwnerKind.INDIVIDUAL,
        display_name=display_name,
        verification_status=VerificationStatus(verification),
    )
    db.add(profile)
    await db.flush()
    return profile


async def make_location(
    db: AsyncSession, *, level: str = "region", parent: Location | None = None, name: str = ""
) -> Location:
    loc_id = next(_location_ids)
    loc = Location(
        id=loc_id,
        parent_id=parent.id if parent else None,
        level=LocationLevel(level),
        name=name or f"Loc {loc_id}",
        slug=f"loc-{loc_id}",
    )
    db.add(loc)
    await db.flush()
    return loc


async def make_place(db: AsyncSession, name: str = "") -> tuple[Location, Location]:
    """A region and one district in it."""
    region = await make_location(db, name=name)
    district = await make_location(db, level="district", parent=region, name=f"{name} district")
    return region, district


async def make_category(
    db: AsyncSession,
    *,
    mode: str | None = "DATE_RANGE",
    parent: Category | None = None,
    slug: str | None = None,
    price_units: list[str] | None = None,
    default_unit: str | None = "night",
    attribute_schema: list[dict[str, Any]] | None = None,
    renter_fee_bps: int = 0,
    commission_bps: int = 1000,
) -> Category:
    slug = slug or f"t-cat-{next(_slugs)}"
    category = Category(
        parent_id=parent.id if parent else None,
        path=f"{parent.path}.{slug}" if parent else slug,
        slug=slug,
        name={"sw": f"{slug} sw", "en": f"{slug} en"},
        booking_mode=BookingMode(mode) if mode else None,
        price_units=price_units if price_units is not None else ([default_unit] if mode else []),
        default_unit=default_unit if mode else None,
        attribute_schema=attribute_schema or [],
        renter_fee_bps=renter_fee_bps,
        commission_bps=commission_bps,
    )
    db.add(category)
    await db.flush()
    return category


async def make_listing(
    db: AsyncSession,
    *,
    owner: OwnerProfile,
    category: Category,
    region: Location,
    district: Location,
    price: int = 50_000,
    prices: list[dict[str, Any]] | None = None,
    status: str = "active",
    title_sw: str = "Tangazo",
    title_en: str = "Listing",
    attributes: dict[str, Any] | None = None,
    stock: int = 1,
    lat: float | None = None,
    lng: float | None = None,
    **fields: Any,
) -> Listing:
    """A listing with a base price in the category's default unit (plus `prices` rows)."""
    listing = Listing(
        owner_profile_id=owner.id,
        category_id=category.id,
        title_sw=title_sw,
        title_en=title_en,
        description_sw=f"{title_sw} maelezo",
        description_en=f"{title_en} description",
        attributes=attributes or {},
        region_id=region.id,
        district_id=district.id,
        stock=stock,
        lat=Decimal(str(lat)) if lat is not None else None,
        lng=Decimal(str(lng)) if lng is not None else None,
        base_price_tzs=price,
        status=ListingStatus(status),
        deposit_tzs=fields.pop("deposit_tzs", 0),
        delivery=DeliveryOption(fields.pop("delivery", "none")),
        cancellation_policy=CancellationPolicy(fields.pop("cancellation_policy", "moderate")),
        instant_book=fields.pop("instant_book", True),
        **fields,
    )
    db.add(listing)
    await db.flush()
    assert category.default_unit is not None
    rows = [{"unit": category.default_unit, "amount_tzs": price}, *(prices or [])]
    for row in rows:
        db.add(
            ListingPrice(
                listing_id=listing.id,
                unit=PriceUnit(row["unit"]),
                amount_tzs=row["amount_tzs"],
                season_start=row.get("season_start"),
                season_end=row.get("season_end"),
            )
        )
    db.add(ListingPhoto(listing_id=listing.id, storage_key=f"test/{listing.id}.jpg", position=0))
    await db.flush()
    return listing


async def make_block(
    db: AsyncSession,
    listing: Listing,
    start: datetime,
    end: datetime,
    *,
    kind: str = "exclusive",
    quantity: int = 1,
    active: bool = True,
    source: str = "owner_block",
    booking_id: uuid.UUID | None = None,
) -> AvailabilityBlock:
    block = AvailabilityBlock(
        listing_id=listing.id,
        period=Range(start, end, bounds="[)"),
        quantity=quantity,
        kind=BlockKind(kind),
        source=BlockSource(source),
        booking_id=booking_id,
        active=active,
    )
    db.add(block)
    await db.flush()
    return block


def day_range(start: date, end: date) -> tuple[datetime, datetime]:
    """EAT midnights for [start, end)."""
    from app.core.clock import to_eat_midnight

    return to_eat_midnight(start), to_eat_midnight(end)
