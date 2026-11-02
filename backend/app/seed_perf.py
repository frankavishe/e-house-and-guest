"""Search load data (T145, SC-002): N listings cloned from the demo listings.

    python -m app.seed --all              # first: locations, categories, demo listings
    python -m app.seed_perf --count 20000

Each clone copies a demo listing's category, attributes and prices (so attribute filters hit
real values), lands in a random district, varies its price by ±40 % and, for about a third,
gets an owner block in the next 60 days (not stock listings), so availability filters do
real work. Clones belong to a dedicated verified owner (`+255700000090`); a re-run deletes
that owner's listings first, so the count stays exact. Rows go in with bulk inserts in
batches of 1,000.
"""

import argparse
import asyncio
import random
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

import app.models  # noqa: F401  (registers every table for the bulk inserts)
from app.accounts.models import (
    Language,
    OwnerKind,
    OwnerProfile,
    User,
    UserStatus,
    VerificationStatus,
)
from app.availability.models import AvailabilityBlock, BlockKind, BlockSource
from app.catalog.models import BookingMode, Category, Location, LocationLevel
from app.core import clock
from app.core.db import dispose_engine, get_sessionmaker
from app.listings.models import Listing, ListingPhoto, ListingPrice, ListingStatus
from app.seed import DEMO_NAMESPACE

PERF_PHONE = "+255700000090"
BATCH = 1_000
BLOCKED_SHARE = 3  # one listing in three (not stock items) gets an owner block


async def _perf_owner(session: AsyncSession) -> OwnerProfile:
    user = (
        await session.execute(select(User).where(User.phone == PERF_PHONE))
    ).scalar_one_or_none()
    if user is None:
        user = User(phone=PERF_PHONE, name="Perf Owner", language=Language.SW)
        session.add(user)
        await session.flush()
    user.status = UserStatus.ACTIVE
    owner = (
        await session.execute(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    ).scalar_one_or_none()
    if owner is None:
        owner = OwnerProfile(user_id=user.id, kind=OwnerKind.BUSINESS, display_name="Perf Rentals")
        session.add(owner)
    owner.verification_status = VerificationStatus.VERIFIED
    await session.flush()
    return owner


async def _templates(session: AsyncSession) -> list[tuple[Listing, list[ListingPrice]]]:
    demo = (
        (await session.execute(select(Listing).where(Listing.status == ListingStatus.ACTIVE)))
        .scalars()
        .all()
    )
    demo = [lst for lst in demo if lst.id.version == 5]  # uuid5 ids = seeded demo listings
    if not demo:
        raise SystemExit("no demo listings: run `python -m app.seed --all` first")
    prices = (
        (
            await session.execute(
                select(ListingPrice).where(ListingPrice.listing_id.in_([d.id for d in demo]))
            )
        )
        .scalars()
        .all()
    )
    by_listing: dict[uuid.UUID, list[ListingPrice]] = {}
    for price in prices:
        by_listing.setdefault(price.listing_id, []).append(price)
    return [(d, by_listing.get(d.id, [])) for d in demo]


async def _districts(session: AsyncSession) -> list[tuple[int, int]]:
    rows = (
        await session.execute(
            select(Location.id, Location.parent_id).where(Location.level == LocationLevel.DISTRICT)
        )
    ).all()
    return [(district_id, region_id) for district_id, region_id in rows if region_id]


async def seed_perf(session: AsyncSession, count: int, seed: int = 20_000) -> int:
    rng = random.Random(seed)  # noqa: S311 (load data, not secrets)
    owner = await _perf_owner(session)
    await session.execute(delete(Listing).where(Listing.owner_profile_id == owner.id))
    templates = await _templates(session)
    # Clones reuse their template's demo photo, which exists in storage.
    template_photos = {
        listing_id: (key, variants)
        for listing_id, key, variants in await session.execute(
            select(ListingPhoto.listing_id, ListingPhoto.storage_key, ListingPhoto.variants).where(
                ListingPhoto.listing_id.in_([t.id for t, _ in templates]),
                ListingPhoto.position == 0,
            )
        )
    }
    stock_categories = set(
        (
            await session.execute(
                select(Category.id).where(Category.booking_mode == BookingMode.QUANTITY)
            )
        ).scalars()
    )
    districts = await _districts(session)
    now = clock.now()
    today = clock.to_eat_midnight(clock.today_eat())

    for offset in range(0, count, BATCH):
        listings: list[dict[str, Any]] = []
        prices: list[dict[str, Any]] = []
        photos: list[dict[str, Any]] = []
        blocks: list[dict[str, Any]] = []
        for i in range(offset, min(offset + BATCH, count)):
            template, template_prices = templates[i % len(templates)]
            district_id, region_id = rng.choice(districts)
            factor = Decimal(str(round(rng.uniform(0.6, 1.4), 2)))
            listing_id = uuid.uuid5(DEMO_NAMESPACE, f"perf:{i}")
            base = int((template.base_price_tzs or 10_000) * factor) // 500 * 500 or 500
            listings.append(
                {
                    "id": listing_id,
                    "owner_profile_id": owner.id,
                    "category_id": template.category_id,
                    "title_sw": f"{template.title_sw} #{i}",
                    "title_en": f"{template.title_en} #{i}",
                    "description_sw": template.description_sw,
                    "description_en": template.description_en,
                    "attributes": template.attributes,
                    "region_id": region_id,
                    "district_id": district_id,
                    "lat": Decimal(str(round(rng.uniform(-11.5, -1.0), 6))),
                    "lng": Decimal(str(round(rng.uniform(29.5, 40.0), 6))),
                    "stock": template.stock,
                    "deposit_tzs": template.deposit_tzs,
                    "delivery": template.delivery,
                    "delivery_fee_tzs": template.delivery_fee_tzs,
                    "delivery_area": [district_id] if template.delivery_area else None,
                    "min_duration": template.min_duration,
                    "max_duration": template.max_duration,
                    "slot_config": template.slot_config,
                    "cancellation_policy": template.cancellation_policy,
                    "instant_book": template.instant_book,
                    "base_price_tzs": base,
                    "status": ListingStatus.ACTIVE,
                    "rating_avg": Decimal(str(round(rng.uniform(3, 5), 2)))
                    if rng.random() < 0.5
                    else None,
                    "rating_count": rng.randint(0, 40),
                    "created_at": now - timedelta(minutes=count - i),
                    "updated_at": now,
                }
            )
            for p in template_prices:
                prices.append(
                    {
                        "listing_id": listing_id,
                        "unit": p.unit,
                        "amount_tzs": max(500, int(p.amount_tzs * factor) // 500 * 500),
                    }
                )
            photo_key, photo_variants = template_photos.get(template.id, (f"perf/{i}.jpg", {}))
            photos.append(
                {
                    "listing_id": listing_id,
                    "storage_key": photo_key,
                    "variants": photo_variants,
                    "position": 0,
                    "confirmed_at": now,
                }
            )
            if i % BLOCKED_SHARE == 0 and template.category_id not in stock_categories:
                start = today + timedelta(days=rng.randint(0, 60))
                blocks.append(
                    {
                        "listing_id": listing_id,
                        "period": Range(
                            start, start + timedelta(days=rng.randint(1, 7)), bounds="[)"
                        ),
                        "quantity": 1,
                        "kind": BlockKind.EXCLUSIVE,
                        "source": BlockSource.OWNER_BLOCK,
                        "active": True,
                    }
                )
        await session.execute(insert(Listing), listings)
        await session.execute(insert(ListingPrice), prices)
        await session.execute(insert(ListingPhoto), photos)
        if blocks:
            await session.execute(insert(AvailabilityBlock), blocks)
        await session.commit()
        print(f"  {min(offset + BATCH, count)}/{count}", flush=True)
    return count


async def run(count: int) -> None:
    async with get_sessionmaker()() as session:
        await seed_perf(session, count)
    async with get_sessionmaker()() as session:
        conn = await session.connection()
        await conn.exec_driver_sql("ANALYZE listings, listing_prices, availability_blocks")
        await session.commit()
        total = (await session.execute(select(func.count()).select_from(Listing))).scalar_one()
        print(f"done ({total} listings in database)")
    await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed N listings for search load tests.")
    parser.add_argument("--count", type=int, default=20_000)
    args = parser.parse_args()
    asyncio.run(run(args.count))


if __name__ == "__main__":
    main()
