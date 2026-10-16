"""Idempotent seed command (T038, T041).

    python -m app.seed --locations --categories --demo
    python -m app.seed --all

Every step upserts, so re-running updates rows instead of duplicating them.
"""

import argparse
import asyncio
import csv
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import (
    Language,
    OwnerKind,
    OwnerProfile,
    PaymentNetwork,
    PayoutKind,
    PayoutMethod,
    User,
    VerificationStatus,
)
from app.catalog.attributes import parse_schema, validate_values
from app.catalog.models import BookingMode, Category, Location, LocationLevel, PriceUnit
from app.core import clock, security
from app.core.db import dispose_engine, get_sessionmaker
from app.listings.models import (
    CancellationPolicy,
    DeliveryOption,
    Listing,
    ListingPhoto,
    ListingPrice,
    ListingStatus,
)

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
DEMO_NAMESPACE = uuid.UUID("6f1b2a64-7d0c-4c55-9a8e-3f0f6c1d2e01")


def _load_yaml(path: Path) -> Any:
    """Seed files are small; a blocking read is fine for this CLI."""
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- locations ---------------------------------------------------------------------------


async def seed_locations(session: AsyncSession, path: Path = SEED_DIR / "locations.csv") -> int:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    # Parents first so the self-referencing FK is always satisfied.
    order = {"region": 0, "district": 1, "ward": 2}
    rows.sort(key=lambda r: (order[r["level"]], int(r["id"])))
    for r in rows:
        values = {
            "id": int(r["id"]),
            "parent_id": int(r["parent_id"]) if r["parent_id"] else None,
            "level": LocationLevel(r["level"]),
            "name": r["name"],
            "slug": r["slug"],
            "lat": Decimal(r["lat"]) if r["lat"] else None,
            "lng": Decimal(r["lng"]) if r["lng"] else None,
        }
        stmt = insert(Location).values(**values)
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Location.id],
                set_={k: stmt.excluded[k] for k in values if k != "id"},
            )
        )
    # Keep the serial in step with explicit ids so admin-added locations don't collide.
    await session.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('locations', 'id'), GREATEST(MAX(id), 1))"
            " FROM locations"
        )
    )
    return len(rows)


# --- categories --------------------------------------------------------------------------


async def _upsert_category(
    session: AsyncSession, spec: dict[str, Any], parent: Category | None, sort_order: int
) -> Category:
    slug = spec["slug"]
    schema = spec.get("attribute_schema") or []
    parse_schema(schema)  # fail fast on an invalid seed schema
    mode = BookingMode(spec["booking_mode"]) if spec.get("booking_mode") else None
    category = (
        await session.execute(select(Category).where(Category.slug == slug))
    ).scalar_one_or_none()
    if category is None:
        category = Category(slug=slug, schema_version=1)
        session.add(category)
    elif category.attribute_schema != schema:
        category.schema_version += 1
    category.parent_id = parent.id if parent else None
    category.path = f"{parent.path}.{slug}" if parent else slug
    category.name = dict(spec["name"])
    category.booking_mode = mode
    category.price_units = list(spec.get("price_units") or [])
    category.default_unit = spec.get("default_unit")
    category.attribute_schema = schema
    category.commission_bps = int(spec.get("commission_bps", 1000))
    category.renter_fee_bps = int(spec.get("renter_fee_bps", 0))
    category.sort_order = int(spec.get("sort_order", sort_order))
    category.is_active = True
    await session.flush()
    return category


async def seed_categories(session: AsyncSession, path: Path = SEED_DIR / "categories.yaml") -> int:
    data = _load_yaml(path)
    count = 0
    for i, group in enumerate(data["groups"], 1):
        parent = await _upsert_category(session, group, None, i)
        count += 1
        for j, leaf in enumerate(group.get("children", []), 1):
            await _upsert_category(session, leaf, parent, j)
            count += 1
    return count


# --- demo data ---------------------------------------------------------------------------


async def _upsert_user(session: AsyncSession, spec: dict[str, Any]) -> User:
    phone = security.normalize_phone(spec["phone"])
    user = (await session.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    if user is None:
        user = User(phone=phone)
        session.add(user)
    user.name = spec.get("name")
    user.language = Language(spec.get("language", "sw"))
    user.is_admin = bool(spec.get("is_admin", False))
    await session.flush()
    return user


async def _upsert_owner(session: AsyncSession, spec: dict[str, Any]) -> OwnerProfile:
    phone = security.normalize_phone(spec["phone"])
    user = (await session.execute(select(User).where(User.phone == phone))).scalar_one()
    profile = (
        await session.execute(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        profile = OwnerProfile(user_id=user.id)
        session.add(profile)
    profile.kind = OwnerKind(spec["kind"])
    profile.display_name = spec["display_name"]
    profile.nida_number_enc = (
        security.encrypt(spec["nida_number"]) if spec.get("nida_number") else None
    )
    profile.business_name = spec.get("business_name")
    profile.brela_reg_no = spec.get("brela_reg_no")
    profile.tin_enc = security.encrypt(spec["tin"]) if spec.get("tin") else None
    profile.verification_status = VerificationStatus.VERIFIED
    profile.rejection_reason = None
    profile.verified_at = profile.verified_at or clock.now()
    await session.flush()

    payout = spec.get("payout")
    if payout:
        await session.execute(
            delete(PayoutMethod).where(PayoutMethod.owner_profile_id == profile.id)
        )
        session.add(
            PayoutMethod(
                owner_profile_id=profile.id,
                kind=PayoutKind(payout["kind"]),
                network=PaymentNetwork(payout["network"]) if payout.get("network") else None,
                msisdn=payout.get("msisdn"),
                account_name=payout["account_name"],
                is_default=True,
            )
        )
        await session.flush()
    return profile


async def _city_locations(
    session: AsyncSession, cities: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, c in cities.items():
        region = (
            await session.execute(
                select(Location).where(
                    Location.level == LocationLevel.REGION, Location.slug == c["region"]
                )
            )
        ).scalar_one()
        district = (
            await session.execute(
                select(Location).where(
                    Location.parent_id == region.id, Location.slug == c["district"]
                )
            )
        ).scalar_one()
        ward = (
            await session.execute(
                select(Location).where(
                    Location.parent_id == district.id, Location.slug == c["ward"]
                )
            )
        ).scalar_one_or_none()
        out[key] = {
            "region_id": region.id,
            "district_id": district.id,
            "ward_id": ward.id if ward else None,
            "lat": Decimal(str(c["lat"])),
            "lng": Decimal(str(c["lng"])),
        }
    return out


async def seed_demo(session: AsyncSession, path: Path = SEED_DIR / "demo.yaml") -> int:
    data = _load_yaml(path)
    for spec in data["users"]:
        await _upsert_user(session, spec)
    owners = {
        security.normalize_phone(spec["phone"]): await _upsert_owner(session, spec)
        for spec in data["owners"]
    }
    cities = await _city_locations(session, data["cities"])

    count = 0
    for leaf_slug, group in data["listings"].items():
        category = (
            await session.execute(select(Category).where(Category.slug == leaf_slug))
        ).scalar_one()
        assert category.booking_mode is not None and category.default_unit is not None
        owner = owners[security.normalize_phone(group["owner"])]
        for i, raw in enumerate(group["items"], 1):
            item = {**group.get("defaults", {}), **raw}
            await _upsert_listing(
                session, category, owner, cities[item["city"]], leaf_slug, i, item
            )
            count += 1
    return count


async def _upsert_listing(
    session: AsyncSession,
    category: Category,
    owner: OwnerProfile,
    location: dict[str, Any],
    leaf_slug: str,
    index: int,
    item: dict[str, Any],
) -> Listing:
    assert category.booking_mode is not None and category.default_unit is not None
    listing_id = uuid.uuid5(DEMO_NAMESPACE, f"demo:{leaf_slug}:{index}")
    attributes = validate_values(
        category.id, category.schema_version, category.attribute_schema, item["attributes"]
    )
    is_quantity = category.booking_mode == BookingMode.QUANTITY
    listing = await session.get(Listing, listing_id)
    if listing is None:
        listing = Listing(id=listing_id)
        session.add(listing)
    listing.owner_profile_id = owner.id
    listing.category_id = category.id
    listing.title_sw = item["title_sw"]
    listing.title_en = item["title_en"]
    listing.description_sw = item.get("description_sw") or (
        f"{item['title_sw']}. Tangazo la mfano kwa majaribio."
    )
    listing.description_en = item.get("description_en") or (
        f"{item['title_en']}. Demo listing for testing."
    )
    listing.attributes = attributes
    listing.region_id = location["region_id"]
    listing.district_id = location["district_id"]
    listing.ward_id = location["ward_id"]
    # Spread pins a little so map markers don't stack.
    listing.lat = location["lat"] + Decimal(index) / 500
    listing.lng = location["lng"] + Decimal(index) / 500
    listing.address_hint = item.get("address_hint")
    listing.stock = int(item.get("stock", 1)) if is_quantity else 1
    listing.deposit_tzs = int(item.get("deposit_tzs", 0))
    if is_quantity:
        listing.delivery = DeliveryOption.OPTIONAL
        listing.delivery_fee_tzs = 20_000
        listing.delivery_area = [location["district_id"]]
    else:
        listing.delivery = DeliveryOption.NONE
        listing.delivery_fee_tzs = None
        listing.delivery_area = None
    listing.min_duration = item.get("min_duration")
    listing.max_duration = item.get("max_duration")
    listing.slot_config = (
        item.get("slot_config") if category.booking_mode == BookingMode.TIME_SLOT else None
    )
    listing.cancellation_policy = CancellationPolicy(item.get("cancellation_policy", "moderate"))
    listing.instant_book = bool(item.get("instant_book", False)) and (
        category.booking_mode != BookingMode.LEASE
    )
    listing.base_price_tzs = int(item["price"])
    listing.status = ListingStatus.ACTIVE
    await session.flush()

    await session.execute(delete(ListingPrice).where(ListingPrice.listing_id == listing.id))
    prices = {category.default_unit: int(item["price"]), **(item.get("prices") or {})}
    for unit, amount in prices.items():
        if unit not in category.price_units:
            raise ValueError(f"{leaf_slug}: unit {unit!r} not allowed for this category")
        session.add(
            ListingPrice(listing_id=listing.id, unit=PriceUnit(unit), amount_tzs=int(amount))
        )

    await session.execute(delete(ListingPhoto).where(ListingPhoto.listing_id == listing.id))
    session.add(
        ListingPhoto(
            listing_id=listing.id,
            storage_key=f"demo/{leaf_slug}-{index}.jpg",
            position=0,
            alt_sw=item["title_sw"],
            alt_en=item["title_en"],
        )
    )
    await session.flush()
    return listing


# --- CLI ---------------------------------------------------------------------------------


async def run(locations: bool, categories: bool, demo: bool) -> None:
    async with get_sessionmaker()() as session:
        if locations:
            print(f"locations: {await seed_locations(session)} rows")
        if categories:
            print(f"categories: {await seed_categories(session)} rows")
        if demo:
            print(f"demo: {await seed_demo(session)} listings")
        await session.commit()
        total = (await session.execute(select(func.count()).select_from(Listing))).scalar_one()
        print(f"done ({total} listings in database)")
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed reference and demo data.")
    parser.add_argument("--locations", action="store_true")
    parser.add_argument("--categories", action="store_true")
    parser.add_argument("--demo", action="store_true", help="demo users, owners and listings")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not (args.locations or args.categories or args.demo or args.all):
        parser.error("choose at least one of --locations --categories --demo --all")
    asyncio.run(
        run(
            locations=args.locations or args.all,
            categories=args.categories or args.all,
            demo=args.demo or args.all,
        )
    )


if __name__ == "__main__":
    main()
