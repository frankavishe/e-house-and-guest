"""Seed files load, validate against their own schemas, and re-run idempotently (T037-T041)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import (
    OwnerKind,
    OwnerProfile,
    PaymentNetwork,
    PayoutMethod,
    User,
    VerificationStatus,
)
from app.catalog.models import Category, Location, LocationLevel
from app.listings.models import Listing
from app.seed import reset_data, seed_categories, seed_demo, seed_locations


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

    # Starter accounts only: an admin and one verified owner, no listings.
    assert await _count(db, User) == 2
    assert await _count(db, Listing) == 0

    admin = (await db.execute(select(User).where(User.phone == "+255774861380"))).scalar_one()
    assert admin.is_admin and admin.name == "Frank Kavishe"

    owner_user = (await db.execute(select(User).where(User.phone == "+255793403553"))).scalar_one()
    assert not owner_user.is_admin
    profile = (
        await db.execute(select(OwnerProfile).where(OwnerProfile.user_id == owner_user.id))
    ).scalar_one()
    assert profile.kind == OwnerKind.INDIVIDUAL
    assert profile.verification_status == VerificationStatus.VERIFIED
    payout = (
        await db.execute(select(PayoutMethod).where(PayoutMethod.owner_profile_id == profile.id))
    ).scalar_one()
    assert payout.is_default
    assert payout.network == PaymentNetwork.MPESA and payout.msisdn == "+255793403553"


async def test_reset_keeps_reference_data(db: AsyncSession) -> None:
    await seed_locations(db)
    await seed_categories(db)
    await seed_demo(db)
    locations, categories = await _count(db, Location), await _count(db, Category)

    await reset_data(db)

    assert await _count(db, User) == 0
    assert await _count(db, OwnerProfile) == 0
    assert await _count(db, Location) == locations
    assert await _count(db, Category) == categories


async def test_changed_schema_bumps_version(db: AsyncSession) -> None:
    await seed_categories(db)
    rooms = (await db.execute(select(Category).where(Category.slug == "rooms"))).scalar_one()
    rooms.attribute_schema = []
    await db.flush()
    await seed_categories(db)
    await db.refresh(rooms)
    assert rooms.schema_version == 2
