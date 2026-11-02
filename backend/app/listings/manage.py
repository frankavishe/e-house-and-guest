"""Owner listing management (US3, FR-007, FR-009, FR-030).

Lifecycle: `draft → pending_review → active ⇄ paused`, `pending_review → rejected → (edit)
pending_review`, admin `suspended`, soft `deleted`. On a live (`active`/`paused`) listing a
material edit (texts, attributes, location, photos) does not touch the live columns: it
waits in `pending_changes` with `review_state = pending` until an admin approves it, so the
listing stays searchable and bookable with its approved values. Everything else applies at
once.
"""

import itertools
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, VerificationStatus
from app.catalog.attributes import ValuesError, validate_values
from app.catalog.models import BookingMode, Category, Location, LocationLevel, PriceUnit
from app.core import clock
from app.core.errors import AppError, not_found
from app.core.i18n import Locale
from app.integrations import get_storage
from app.listings.models import (
    CancellationPolicy,
    DeliveryOption,
    Listing,
    ListingPhoto,
    ListingPrice,
    ListingStatus,
    ReviewState,
)
from app.listings.owner_schemas import (
    ListingPatch,
    OwnerCategory,
    OwnerListingOut,
    OwnerPhoto,
    PriceRow,
)
from app.listings.schemas import Page
from app.listings.service import localized, photos_for, prices_for

LIVE = {ListingStatus.ACTIVE, ListingStatus.PAUSED}
EDITABLE_STATUSES = LIVE | {
    ListingStatus.DRAFT,
    ListingStatus.PENDING_REVIEW,
    ListingStatus.REJECTED,
}
MATERIAL = (
    "title_sw",
    "title_en",
    "description_sw",
    "description_en",
    "attributes",
    "region_id",
    "district_id",
    "ward_id",
    "address_hint",
    "lat",
    "lng",
)
PHOTOS_ADDED = "photos_added"
PHOTOS_REMOVED = "photos_removed"
PHOTO_KEYS = (PHOTOS_ADDED, PHOTOS_REMOVED)
PRIVATE_URL_TTL_S = 600


def invalid_transition(listing: Listing) -> AppError:
    return AppError("INVALID_TRANSITION", 409, {"status": listing.status.value})


# --- loading ------------------------------------------------------------------------------


async def get_owned(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID, *, lock: bool = False
) -> tuple[Listing, Category]:
    """The owner's own listing (404 for anyone else's, or a deleted one)."""
    query = (
        select(Listing, Category)
        .join(Category, Category.id == Listing.category_id)
        .where(
            Listing.id == listing_id,
            Listing.owner_profile_id == profile.id,
            Listing.status != ListingStatus.DELETED,
        )
    )
    if lock:
        query = query.with_for_update(of=Listing)
    row = (await session.execute(query)).first()
    if row is None:
        raise not_found("listing")
    return row[0], row[1]


async def get_any(session: AsyncSession, listing_id: uuid.UUID) -> tuple[Listing, Category]:
    row = (
        await session.execute(
            select(Listing, Category)
            .join(Category, Category.id == Listing.category_id)
            .where(Listing.id == listing_id, Listing.status != ListingStatus.DELETED)
            .with_for_update(of=Listing)
        )
    ).first()
    if row is None:
        raise not_found("listing")
    return row[0], row[1]


async def leaf_category(session: AsyncSession, category_id: uuid.UUID) -> Category:
    category = await session.get(Category, category_id)
    if category is None or not category.is_active:
        raise not_found("category")
    if category.booking_mode is None or category.default_unit is None:
        raise AppError("VALIDATION_ERROR", 422, {"category_id": "choose a leaf category"})
    return category


# --- presentation -------------------------------------------------------------------------


def _photo_url(photo: ListingPhoto, size: str) -> str:
    storage = get_storage()
    key = (photo.variants or {}).get(size)
    if key:
        return storage.public_url(key=key)
    # Not processed yet: the original sits in the private uploads bucket.
    return storage.presign_get(key=photo.storage_key, ttl_s=PRIVATE_URL_TTL_S)


def photo_out(photo: ListingPhoto) -> OwnerPhoto:
    return OwnerPhoto(
        id=photo.id,
        url_320=_photo_url(photo, "320"),
        url_640=_photo_url(photo, "640"),
        url_1280=_photo_url(photo, "1280"),
        position=photo.position,
        alt_sw=photo.alt_sw,
        alt_en=photo.alt_en,
        pending=photo.pending,
    )


def _category_out(category: Category, locale: Locale) -> OwnerCategory:
    assert category.booking_mode is not None and category.default_unit is not None
    return OwnerCategory(
        id=category.id,
        slug=category.slug,
        name=localized(category.name, locale),
        booking_mode=category.booking_mode.value,
        price_units=list(category.price_units),
        default_unit=category.default_unit,
    )


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _visible_photos(listing: Listing, photos: list[ListingPhoto]) -> list[ListingPhoto]:
    removed = set((listing.pending_changes or {}).get(PHOTOS_REMOVED, []))
    return [p for p in photos if str(p.id) not in removed]


def missing(
    listing: Listing,
    category: Category,
    prices: list[ListingPrice],
    photos: list[ListingPhoto],
) -> list[str]:
    """What still blocks submitting the listing for review."""
    out = []
    if not (listing.title_sw or listing.title_en):
        out.append("title")
    if not (listing.description_sw or listing.description_en):
        out.append("description")
    if listing.region_id is None or listing.district_id is None:
        out.append("location")
    try:
        validate_values(
            category.id, category.schema_version, category.attribute_schema, listing.attributes
        )
    except ValuesError:
        out.append("attributes")
    if not any(p.unit.value == category.default_unit and p.season_start is None for p in prices):
        out.append("price")
    if not _visible_photos(listing, photos):
        out.append("photo")
    return out


async def listing_out(
    session: AsyncSession, listing: Listing, category: Category, locale: Locale
) -> OwnerListingOut:
    return (await listings_out(session, [(listing, category)], locale))[0]


async def listings_out(
    session: AsyncSession, rows: list[tuple[Listing, Category]], locale: Locale
) -> list[OwnerListingOut]:
    ids = [listing.id for listing, _ in rows]
    photos = await photos_for(session, ids, public=False)
    prices = await prices_for(session, ids)
    out = []
    for listing, category in rows:
        out.append(
            OwnerListingOut(
                id=listing.id,
                status=listing.status.value,
                review_state=listing.review_state.value,
                rejection_reason=listing.rejection_reason,
                pending_changes=listing.pending_changes,
                category=_category_out(category, locale),
                title_sw=listing.title_sw,
                title_en=listing.title_en,
                description_sw=listing.description_sw,
                description_en=listing.description_en,
                attributes=listing.attributes,
                region_id=listing.region_id,
                district_id=listing.district_id,
                ward_id=listing.ward_id,
                address_hint=listing.address_hint,
                lat=_float(listing.lat),
                lng=_float(listing.lng),
                stock=listing.stock,
                deposit_tzs=listing.deposit_tzs,
                delivery=listing.delivery.value,
                delivery_fee_tzs=listing.delivery_fee_tzs,
                delivery_area=listing.delivery_area,
                min_duration=listing.min_duration,
                max_duration=listing.max_duration,
                slot_config=listing.slot_config,
                cancellation_policy=listing.cancellation_policy.value,
                instant_book=listing.instant_book,
                prices=[
                    PriceRow(
                        unit=p.unit.value,
                        amount_tzs=p.amount_tzs,
                        season_start=p.season_start,
                        season_end=p.season_end,
                    )
                    for p in prices[listing.id]
                ],
                photos=[photo_out(p) for p in _visible_photos(listing, photos[listing.id])],
                base_price_tzs=listing.base_price_tzs,
                missing=missing(listing, category, prices[listing.id], photos[listing.id]),
                created_at=listing.created_at,
                updated_at=listing.updated_at,
            )
        )
    return out


async def owner_listings(
    session: AsyncSession, profile: OwnerProfile, page: int, page_size: int, locale: Locale
) -> Page[OwnerListingOut]:
    where = (
        Listing.owner_profile_id == profile.id,
        Listing.status != ListingStatus.DELETED,
    )
    total = (
        await session.execute(select(func.count()).select_from(Listing).where(*where))
    ).scalar_one()
    rows = await session.execute(
        select(Listing, Category)
        .join(Category, Category.id == Listing.category_id)
        .where(*where)
        .order_by(Listing.updated_at.desc(), Listing.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = await listings_out(session, [(r[0], r[1]) for r in rows.all()], locale)
    return Page[OwnerListingOut](items=items, page=page, page_size=page_size, total=total)


# --- create & edit ------------------------------------------------------------------------


async def create(
    session: AsyncSession, profile: OwnerProfile, category_id: uuid.UUID
) -> tuple[Listing, Category]:
    category = await leaf_category(session, category_id)
    listing = Listing(
        owner_profile_id=profile.id,
        category_id=category.id,
        attributes={},
        stock=1,
        deposit_tzs=0,
        delivery=DeliveryOption.NONE,
        cancellation_policy=CancellationPolicy.MODERATE,
        instant_book=category.booking_mode != BookingMode.LEASE,
        status=ListingStatus.DRAFT,
        review_state=ReviewState.NONE,
    )
    if category.booking_mode == BookingMode.TIME_SLOT:
        listing.slot_config = {"open": "08:00", "close": "22:00", "slot_minutes": 60}
    session.add(listing)
    await session.flush()
    return listing, category


def _validated_attributes(category: Category, values: dict[str, Any]) -> dict[str, Any]:
    try:
        return validate_values(
            category.id, category.schema_version, category.attribute_schema, values
        )
    except ValuesError as exc:
        raise AppError("INVALID_ATTRIBUTES", 422, {"fields": exc.fields}) from exc


async def _check_location(session: AsyncSession, data: dict[str, Any], listing: Listing) -> None:
    """The district must lie in the region, and the ward in the district."""
    if not {"region_id", "district_id", "ward_id"} & data.keys():
        return
    region_id = data.get("region_id", listing.region_id)
    district_id = data.get("district_id", listing.district_id)
    ward_id = data.get("ward_id", listing.ward_id)
    wanted = [i for i in (region_id, district_id, ward_id) if i is not None]
    rows = await session.execute(select(Location).where(Location.id.in_(wanted)))
    found = {loc.id: loc for loc in rows.scalars()}

    def check(loc_id: int | None, level: LocationLevel, parent: int | None, field: str) -> None:
        if loc_id is None:
            return
        loc = found.get(loc_id)
        if loc is None or loc.level != level or (parent is not None and loc.parent_id != parent):
            raise AppError("VALIDATION_ERROR", 422, {field: "unknown or not in the parent area"})

    check(region_id, LocationLevel.REGION, None, "region_id")
    check(district_id, LocationLevel.DISTRICT, region_id, "district_id")
    check(ward_id, LocationLevel.WARD, district_id, "ward_id")


def _set(listing: Listing, field: str, value: Any) -> None:
    if field in ("lat", "lng"):
        value = Decimal(str(value)) if value is not None else None
    elif field == "delivery":
        value = DeliveryOption(value)
    elif field == "cancellation_policy":
        value = CancellationPolicy(value)
    setattr(listing, field, value)


def _mark_for_review(listing: Listing, changes: dict[str, Any]) -> None:
    listing.pending_changes = {**(listing.pending_changes or {}), **changes}
    listing.review_state = ReviewState.PENDING


async def patch(
    session: AsyncSession,
    profile: OwnerProfile,
    listing_id: uuid.UUID,
    body: ListingPatch,
) -> tuple[Listing, Category]:
    listing, category = await get_owned(session, profile, listing_id, lock=True)
    if listing.status not in EDITABLE_STATUSES:
        raise invalid_transition(listing)
    data = body.model_dump(exclude_unset=True)

    if "category_id" in data:
        new_id = data.pop("category_id")
        if new_id is not None and new_id != listing.category_id:
            if listing.status != ListingStatus.DRAFT:
                raise invalid_transition(listing)
            category = await leaf_category(session, new_id)
            listing.category_id = category.id
            listing.attributes = {}
            await session.execute(delete(ListingPrice).where(ListingPrice.listing_id == listing.id))
            listing.base_price_tzs = None
    if "attributes" in data:
        data["attributes"] = _validated_attributes(category, data["attributes"] or {})
    await _check_location(session, data, listing)

    material = {k: data.pop(k) for k in MATERIAL if k in data}
    if listing.status in LIVE:
        changed = {k: v for k, v in material.items() if v != _live_value(listing, k)}
        if changed:
            _mark_for_review(listing, changed)
    else:
        for field, value in material.items():
            _set(listing, field, value)
    for field, value in data.items():
        if value is not None or field in ("delivery_fee_tzs", "delivery_area", "slot_config"):
            _set(listing, field, value)
    _check_consistency(listing)
    if category.booking_mode == BookingMode.LEASE:
        listing.instant_book = False  # leases always need the owner's approval
    if category.booking_mode != BookingMode.QUANTITY:
        listing.stock = 1
    listing.updated_at = clock.now()
    await session.flush()
    return listing, category


def _check_consistency(listing: Listing) -> None:
    """Rules the table also enforces, answered with a 422 instead of a database error."""
    problems: dict[str, str] = {}
    pending = listing.pending_changes or {}
    lat, lng = pending.get("lat", listing.lat), pending.get("lng", listing.lng)
    if (lat is None) != (lng is None):
        problems["lat"] = "lat and lng go together"
    low, high = listing.min_duration, listing.max_duration
    if low is not None and high is not None and low > high:
        problems["min_duration"] = "min_duration is above max_duration"
    if problems:
        raise AppError("VALIDATION_ERROR", 422, problems)


def _live_value(listing: Listing, field: str) -> Any:
    value = getattr(listing, field)
    return float(value) if isinstance(value, Decimal) else value


async def replace_prices(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID, rows: list[PriceRow]
) -> tuple[Listing, Category]:
    """Replace the whole price list. Price edits never need review."""
    listing, category = await get_owned(session, profile, listing_id, lock=True)
    if listing.status not in EDITABLE_STATUSES:
        raise invalid_transition(listing)
    bad_units = sorted({r.unit for r in rows if r.unit not in category.price_units})
    if bad_units:
        raise AppError(
            "PRICE_UNIT_NOT_ALLOWED", 422, {"units": bad_units, "allowed": category.price_units}
        )
    base_units = [r.unit for r in rows if r.season_start is None]
    if len(base_units) != len(set(base_units)):
        raise AppError("VALIDATION_ERROR", 422, {"prices": "one base price per unit"})
    seasons = sorted(
        (r for r in rows if r.season_start is not None),
        key=lambda r: (r.unit, r.season_start or date.min),
    )
    for a, b in itertools.pairwise(seasons):
        if a.unit == b.unit and b.season_start and a.season_end and b.season_start <= a.season_end:
            raise AppError("SEASON_OVERLAP", 422, {"unit": a.unit})

    await session.execute(delete(ListingPrice).where(ListingPrice.listing_id == listing.id))
    for r in rows:
        session.add(
            ListingPrice(
                listing_id=listing.id,
                unit=PriceUnit(r.unit),
                amount_tzs=r.amount_tzs,
                season_start=r.season_start,
                season_end=r.season_end,
            )
        )
    listing.base_price_tzs = next(
        (r.amount_tzs for r in rows if r.unit == category.default_unit and r.season_start is None),
        None,
    )
    listing.updated_at = clock.now()
    await session.flush()
    return listing, category


# --- lifecycle ----------------------------------------------------------------------------


async def submit(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID
) -> tuple[Listing, Category]:
    """`draft | rejected → pending_review`. The owner must have submitted verification;
    an approved listing stays hidden from search until the owner is verified."""
    listing, category = await get_owned(session, profile, listing_id, lock=True)
    if listing.status not in (ListingStatus.DRAFT, ListingStatus.REJECTED):
        raise invalid_transition(listing)
    if profile.verification_status not in (VerificationStatus.PENDING, VerificationStatus.VERIFIED):
        raise AppError("OWNER_NOT_SUBMITTED", 409)
    prices = (await prices_for(session, [listing.id]))[listing.id]
    photos = (await photos_for(session, [listing.id], public=False))[listing.id]
    gaps = missing(listing, category, prices, photos)
    if gaps:
        raise AppError("LISTING_INCOMPLETE", 422, {"missing": gaps})
    listing.status = ListingStatus.PENDING_REVIEW
    listing.rejection_reason = None
    await session.flush()
    return listing, category


async def set_paused(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID, paused: bool
) -> tuple[Listing, Category]:
    listing, category = await get_owned(session, profile, listing_id, lock=True)
    expected = ListingStatus.ACTIVE if paused else ListingStatus.PAUSED
    if listing.status != expected:
        raise invalid_transition(listing)
    listing.status = ListingStatus.PAUSED if paused else ListingStatus.ACTIVE
    await session.flush()
    return listing, category


async def soft_delete(session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID) -> None:
    from app.bookings.models import Booking, BookingStatus

    listing, _ = await get_owned(session, profile, listing_id, lock=True)
    upcoming = await session.execute(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.listing_id == listing.id,
            Booking.status.in_((BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS)),
            func.upper(Booking.period) > clock.now(),
        )
    )
    if upcoming.scalar_one():
        raise AppError("LISTING_HAS_BOOKINGS", 409)
    listing.status = ListingStatus.DELETED
    await session.flush()


# --- review (used by admin moderation) ----------------------------------------------------


def review_diff(listing: Listing) -> dict[str, dict[str, Any]] | None:
    if not listing.pending_changes:
        return None
    diff: dict[str, dict[str, Any]] = {}
    for field, after in listing.pending_changes.items():
        before = None if field in PHOTO_KEYS else _live_value(listing, field)
        diff[field] = {"before": before, "after": after}
    return diff


async def apply_pending(session: AsyncSession, listing: Listing) -> None:
    """Publish approved changes: copy them to the live columns and show new photos."""
    changes = dict(listing.pending_changes or {})
    removed = [uuid.UUID(i) for i in changes.pop(PHOTOS_REMOVED, [])]
    changes.pop(PHOTOS_ADDED, None)
    for field, value in changes.items():
        _set(listing, field, value)
    if removed:
        await session.execute(delete(ListingPhoto).where(ListingPhoto.id.in_(removed)))
    await _set_pending_photos(session, listing, publish=True)
    listing.pending_changes = None
    listing.review_state = ReviewState.NONE
    listing.rejection_reason = None
    await session.flush()


async def reject_pending(session: AsyncSession, listing: Listing, reason: str) -> None:
    """Drop the proposed changes (and photos added with them); the live listing stays."""
    await _set_pending_photos(session, listing, publish=False)
    listing.pending_changes = None
    listing.review_state = ReviewState.REJECTED
    listing.rejection_reason = reason
    await session.flush()


async def _set_pending_photos(session: AsyncSession, listing: Listing, *, publish: bool) -> None:
    rows = await session.execute(
        select(ListingPhoto).where(
            ListingPhoto.listing_id == listing.id, ListingPhoto.pending.is_(True)
        )
    )
    for photo in rows.scalars():
        if publish:
            photo.pending = False
        else:
            await session.delete(photo)


# --- photos on live listings (called from photos.py) --------------------------------------


def note_photo_added(listing: Listing, photo_id: uuid.UUID) -> None:
    added = list((listing.pending_changes or {}).get(PHOTOS_ADDED, []))
    _mark_for_review(listing, {PHOTOS_ADDED: [*added, str(photo_id)]})


def note_photo_removed(listing: Listing, photo_id: uuid.UUID) -> None:
    removed = list((listing.pending_changes or {}).get(PHOTOS_REMOVED, []))
    _mark_for_review(listing, {PHOTOS_REMOVED: [*removed, str(photo_id)]})
