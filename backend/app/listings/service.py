"""Public listing reads: cards, detail, availability and quotes (US1).

A listing is public when it is `active`, its category is active and its owner is verified.
"""

import uuid
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, VerificationStatus
from app.availability import service as availability
from app.availability.periods import Period, PeriodParams, check_duration, normalize
from app.availability.schemas import Availability
from app.catalog.attributes import FieldDef, parse_schema
from app.catalog.models import BookingMode, Category, Location
from app.core import clock
from app.core.errors import AppError, not_found
from app.core.i18n import Locale, t
from app.integrations import get_storage
from app.listings.models import Listing, ListingPhoto, ListingPrice, ListingStatus
from app.listings.schemas import (
    AttributeOut,
    BasePrice,
    CategoryRef,
    DetailPhoto,
    Highlight,
    ListingCard,
    ListingDetail,
    ListingSummary,
    LocationRef,
    OwnerOut,
    Photo,
    PriceOut,
    QuoteRequest,
)
from app.pricing.schemas import Quote
from app.pricing.service import quote

MAX_AVAILABILITY_DAYS = 366
DEFAULT_AVAILABILITY_DAYS = 60


def public_listings() -> Select[Listing, Category]:
    """Listings anyone may see, with their category."""
    return (
        select(Listing, Category)
        .join(Category, Category.id == Listing.category_id)
        .join(OwnerProfile, OwnerProfile.id == Listing.owner_profile_id)
        .where(
            Listing.status == ListingStatus.ACTIVE,
            Category.is_active.is_(True),
            OwnerProfile.verification_status == VerificationStatus.VERIFIED,
        )
    )


async def get_public_listing(
    session: AsyncSession, listing_id: uuid.UUID
) -> tuple[Listing, Category]:
    row = (await session.execute(public_listings().where(Listing.id == listing_id))).first()
    if row is None:
        raise not_found("listing")
    return row[0], row[1]


# --- loading helpers ----------------------------------------------------------------------


async def prices_for(
    session: AsyncSession, listing_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, list[ListingPrice]]:
    out: dict[uuid.UUID, list[ListingPrice]] = {i: [] for i in listing_ids}
    if listing_ids:
        rows = await session.execute(
            select(ListingPrice)
            .where(ListingPrice.listing_id.in_(listing_ids))
            .order_by(ListingPrice.unit, ListingPrice.season_start.nulls_first())
        )
        for price in rows.scalars():
            out[price.listing_id].append(price)
    return out


async def photos_for(
    session: AsyncSession, listing_ids: Sequence[uuid.UUID], *, public: bool = True
) -> dict[uuid.UUID, list[ListingPhoto]]:
    """Confirmed photos in display order; `public` also hides those awaiting review."""
    out: dict[uuid.UUID, list[ListingPhoto]] = {i: [] for i in listing_ids}
    if listing_ids:
        query = select(ListingPhoto).where(
            ListingPhoto.listing_id.in_(listing_ids), ListingPhoto.confirmed_at.is_not(None)
        )
        if public:
            query = query.where(ListingPhoto.pending.is_(False))
        rows = await session.execute(query.order_by(ListingPhoto.position, ListingPhoto.created_at))
        for photo in rows.scalars():
            out[photo.listing_id].append(photo)
    return out


async def location_names(session: AsyncSession, ids: Iterable[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.execute(select(Location.id, Location.name).where(Location.id.in_(wanted)))
    return {loc_id: name for loc_id, name in rows.all()}


# --- presentation -------------------------------------------------------------------------


def localized(values: dict[str, str] | None, locale: Locale) -> str:
    if not values:
        return ""
    other = "sw" if locale == "en" else "en"
    return values.get(locale) or values.get(other) or ""


def _pick(sw: str | None, en: str | None, locale: Locale) -> str:
    first, second = (en, sw) if locale == "en" else (sw, en)
    return first or second or ""


def _url(key: str) -> str:
    return get_storage().public_url(key=key)


def thumbnail_url(photo: ListingPhoto) -> str:
    return _url((photo.variants or {}).get("320") or photo.storage_key)


def _photo(photo: ListingPhoto, locale: Locale, title: str) -> DetailPhoto:
    variants = photo.variants or {}

    def size(px: str) -> str:
        return _url(variants.get(px) or photo.storage_key)

    return DetailPhoto(
        url_320=size("320"),
        url_640=size("640"),
        url_1280=size("1280"),
        alt=_pick(photo.alt_sw, photo.alt_en, locale) or title,
    )


def _format(field: FieldDef, value: Any, locale: Locale) -> str:
    match field.type:
        case "boolean":
            return t("labels.yes" if value else "labels.no", locale)
        case "enum":
            return next(
                (
                    localized(o.label.model_dump(), locale)
                    for o in field.options or []
                    if o.value == value
                ),
                str(value),
            )
        case "multi_enum":
            labels = {o.value: localized(o.label.model_dump(), locale) for o in field.options or []}
            return ", ".join(labels.get(v, str(v)) for v in value)
        case _:
            return str(value)


_FIELDS: dict[tuple[uuid.UUID, int], list[FieldDef]] = {}


def schema_fields(category: Category) -> list[FieldDef]:
    """The category's parsed schema, cached per version (every edit bumps it)."""
    key = (category.id, category.schema_version)
    if key not in _FIELDS:
        if len(_FIELDS) > 1024:
            _FIELDS.clear()
        try:
            _FIELDS[key] = parse_schema(category.attribute_schema)
        except ValueError:
            _FIELDS[key] = []
    return _FIELDS[key]


def _attributes(category: Category, values: dict[str, Any], locale: Locale) -> list[AttributeOut]:
    out = []
    for field in schema_fields(category):
        if field.key not in values:
            continue
        value = values[field.key]
        out.append(
            AttributeOut(
                key=field.key,
                label=localized(field.label.model_dump(), locale),
                value=value,
                display=_format(field, value, locale),
                unit=localized(field.unit.model_dump(), locale) if field.unit else None,
                group=localized(field.group.model_dump(), locale) if field.group else None,
            )
        )
    return out


def _highlights(category: Category, values: dict[str, Any], locale: Locale) -> list[Highlight]:
    shown = {f.key for f in schema_fields(category) if f.show_on_card}
    return [
        Highlight(key=a.key, label=a.label, value=f"{a.display} {a.unit}" if a.unit else a.display)
        for a in _attributes(category, values, locale)
        if a.key in shown
    ]


def _summary(
    listing: Listing,
    category: Category,
    photos: list[ListingPhoto],
    names: dict[int, str],
    locale: Locale,
) -> dict[str, Any]:
    assert category.booking_mode is not None
    title = listing.title(locale)
    cover = _photo(photos[0], locale, title) if photos else None
    return {
        "id": listing.id,
        "title": title,
        "category": CategoryRef(
            id=category.id, slug=category.slug, name=localized(category.name, locale)
        ),
        "location": LocationRef(
            region=names.get(listing.region_id or 0, ""),
            district=names.get(listing.district_id or 0, ""),
        ),
        "cover_photo": Photo(url_320=cover.url_320, url_640=cover.url_640, alt=cover.alt)
        if cover
        else None,
        "base_price": BasePrice(unit=category.default_unit, amount_tzs=listing.base_price_tzs)
        if listing.base_price_tzs is not None and category.default_unit
        else None,
        "rating_avg": float(listing.rating_avg) if listing.rating_avg is not None else None,
        "rating_count": listing.rating_count,
        "instant_book": listing.instant_book,
        "lat": float(listing.lat) if listing.lat is not None else None,
        "lng": float(listing.lng) if listing.lng is not None else None,
        "booking_mode": category.booking_mode.value,
        "highlights": _highlights(category, listing.attributes, locale),
    }


async def cards(
    session: AsyncSession,
    rows: Sequence[tuple[Listing, Category]],
    locale: Locale,
    periods: dict[uuid.UUID, Period] | None = None,
) -> list[ListingCard]:
    """Cards for a page of listings; `periods` (by category id) adds `total_tzs`."""
    ids = [listing.id for listing, _ in rows]
    photos = await photos_for(session, ids)
    prices = await prices_for(session, ids) if periods else {}
    names = await location_names(
        session, [i for listing, _ in rows for i in (listing.region_id, listing.district_id)]
    )
    out = []
    for listing, category in rows:
        total = None
        period = (periods or {}).get(category.id)
        if period is not None:
            try:
                total = quote(listing, prices[listing.id], category, period).total_tzs
            except AppError:
                total = None
        out.append(
            ListingCard(
                **_summary(listing, category, photos[listing.id], names, locale), total_tzs=total
            )
        )
    return out


async def detail(session: AsyncSession, listing_id: uuid.UUID, locale: Locale) -> ListingDetail:
    from app.reviews.service import recent_reviews

    listing, category = await get_public_listing(session, listing_id)
    owner = await session.get(OwnerProfile, listing.owner_profile_id)
    assert owner is not None and category.default_unit is not None
    photos = (await photos_for(session, [listing.id]))[listing.id]
    prices = (await prices_for(session, [listing.id]))[listing.id]
    names = await location_names(session, [listing.region_id, listing.district_id])
    summary = ListingSummary(**_summary(listing, category, photos, names, locale))
    title = summary.title
    return ListingDetail(
        **summary.model_dump(),
        description=_pick(listing.description_sw, listing.description_en, locale),
        photos=[_photo(p, locale, title) for p in photos],
        attributes=_attributes(category, listing.attributes, locale),
        prices=[
            PriceOut(
                unit=p.unit.value,
                amount_tzs=p.amount_tzs,
                season_start=p.season_start,
                season_end=p.season_end,
            )
            for p in prices
        ],
        default_unit=category.default_unit,
        deposit_tzs=listing.deposit_tzs,
        delivery=listing.delivery.value,
        delivery_fee_tzs=listing.delivery_fee_tzs,
        delivery_area=listing.delivery_area,
        min_duration=listing.min_duration,
        max_duration=listing.max_duration,
        slot_config=listing.slot_config,
        stock=listing.stock,
        cancellation_policy=listing.cancellation_policy.value,
        owner=OwnerOut(
            user_id=owner.user_id,
            display_name=owner.display_name,
            rating_avg=float(owner.rating_avg) if owner.rating_avg is not None else None,
            rating_count=owner.rating_count,
            verified=owner.verification_status == VerificationStatus.VERIFIED,
        ),
        reviews=await recent_reviews(session, listing.id),
    )


async def listing_availability(
    session: AsyncSession, listing_id: uuid.UUID, first: date | None, last: date | None
) -> Availability:
    listing, category = await get_public_listing(session, listing_id)
    mode = category.booking_mode
    assert mode is not None
    first = first or clock.today_eat()
    last = last or first + timedelta(days=DEFAULT_AVAILABILITY_DAYS - 1)
    if last < first or (last - first).days >= MAX_AVAILABILITY_DAYS:
        raise AppError("INVALID_PERIOD", 400, {"reason": "window"})
    match mode:
        case BookingMode.QUANTITY:
            stock = await availability.available_quantity_by_day(session, listing, first, last)
            return Availability(booking_mode=mode.value, stock=stock)
        case BookingMode.TIME_SLOT:
            slots = await availability.free_slots(session, listing, first, last)
            return Availability(booking_mode=mode.value, slots=slots)
        case _:
            spans = await availability.unavailable_ranges(session, listing, first, last)
            return Availability(booking_mode=mode.value, unavailable=spans)


def period_for(category: Category, listing: Listing | None, params: PeriodParams) -> Period:
    assert category.booking_mode is not None and category.default_unit is not None
    slot_minutes = int(((listing.slot_config if listing else None) or {}).get("slot_minutes", 60))
    return normalize(
        category.booking_mode, category.default_unit, params, slot_minutes=slot_minutes
    )


async def quote_listing(session: AsyncSession, listing_id: uuid.UUID, body: QuoteRequest) -> Quote:
    """Price a period after checking it is valid and free (409 when it is not)."""
    listing, category = await get_public_listing(session, listing_id)
    mode = category.booking_mode
    assert mode is not None
    if not body.fits(mode):
        raise AppError("INVALID_PERIOD", 400, {"reason": "wrong_mode", "booking_mode": mode.value})
    period = period_for(category, listing, body)
    check_duration(period, listing)
    if not await availability.is_available(session, listing, mode, period):
        if mode == BookingMode.QUANTITY:
            available = await availability.min_available(session, listing, period)
            raise AppError("INSUFFICIENT_STOCK", 409, {"available": available})
        raise AppError("SLOT_TAKEN", 409)
    prices = (await prices_for(session, [listing.id]))[listing.id]
    return quote(
        listing,
        prices,
        category,
        period,
        delivery=body.delivery,
        delivery_district_id=body.delivery_district_id,
    )
