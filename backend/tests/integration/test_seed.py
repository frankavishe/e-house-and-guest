"""Seed files load, validate against their own schemas, and re-run idempotently (T037-T041)."""

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User, VerificationStatus
from app.catalog.models import Category, Location, LocationLevel
from app.core import security
from app.listings.models import Listing, ListingPrice, ListingStatus
from app.seed import seed_categories, seed_demo, seed_locations


async def _count(db: AsyncSession, model: type, *where: object) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def test_seed_all_is_idempotent(db: AsyncSession) -> None:
    for _ in range(2):
        await seed_locations(db)
        await seed_categories(db)
        await seed_demo(db)

    assert await _count(db, Location, Location.level == LocationLevel.REGION) == 31
    assert await _count(db, Location, Location.level == LocationLevel.DISTRICT) >= 180

    groups = (
        (await db.execute(select(Category).where(Category.parent_id.is_(None)))).scalars().all()
    )
    assert {g.slug for g in groups} >= {
        "accommodation",
        "workspace",
        "venues",
        "storage-property",
        "vehicles",
        "equipment",
    }
    leaves = (
        (await db.execute(select(Category).where(Category.booking_mode.is_not(None))))
        .scalars()
        .all()
    )
    assert len(leaves) == 26
    assert all(leaf.schema_version == 1 for leaf in leaves), "unchanged schema must not bump"
    assert all("." in leaf.path for leaf in leaves)

    # ≥ 3 active listings per leaf category, across the launch cities.
    listings = (await db.execute(select(Listing))).scalars().all()
    per_leaf = Counter(listing.category_id for listing in listings)
    assert all(per_leaf[leaf.id] >= 3 for leaf in leaves)
    assert all(listing.status == ListingStatus.ACTIVE for listing in listings)
    assert len({listing.region_id for listing in listings}) == 5
    assert await _count(db, ListingPrice) >= len(listings)

    tent = next(listing for listing in listings if listing.title_en == "100-guest tent")
    assert tent.stock == 10

    owner_user = (await db.execute(select(User).where(User.phone == "+255700000002"))).scalar_one()
    profile = (
        await db.execute(select(OwnerProfile).where(OwnerProfile.user_id == owner_user.id))
    ).scalar_one()
    assert profile.verification_status == VerificationStatus.VERIFIED
    assert profile.nida_number_enc and security.decrypt(profile.nida_number_enc).startswith("1990")
    admin = (await db.execute(select(User).where(User.phone == "+255700000009"))).scalar_one()
    assert admin.is_admin


async def test_changed_schema_bumps_version(db: AsyncSession) -> None:
    await seed_categories(db)
    rooms = (await db.execute(select(Category).where(Category.slug == "rooms"))).scalar_one()
    rooms.attribute_schema = []
    await db.flush()
    await seed_categories(db)
    await db.refresh(rooms)
    assert rooms.schema_version == 2
