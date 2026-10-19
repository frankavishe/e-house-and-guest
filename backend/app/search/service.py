"""Listing search (R4): plain PostgreSQL over public listings.

Filters: category subtree, location, price, text, `attr.*` (from the category schemas),
bounding box and availability. A period is interpreted per leaf category, because nights vs
days and the booking mode are category settings (Principle I); only the returned page is
priced.
"""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Numeric, and_, case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.availability.periods import Period
from app.availability.service import availability_filter
from app.catalog.attributes import FieldDef
from app.catalog.models import Category
from app.catalog.service import active_categories, get_category_by_slug
from app.core.errors import AppError
from app.core.i18n import Locale
from app.listings import service as listings
from app.listings.models import Listing
from app.listings.schemas import ListingCard, Page
from app.search.schemas import SearchParams

ATTR_PREFIX = "attr."
TRUE, FALSE = {"true", "1"}, {"false", "0"}


class _FilterErrors:
    def __init__(self) -> None:
        self.fields: list[dict[str, Any]] = []

    def add(self, param: str, msg: str) -> None:
        self.fields.append({"loc": ["query", param], "msg": msg, "type": "attribute_filter"})

    def raise_if_any(self) -> None:
        if self.fields:
            raise AppError("VALIDATION_ERROR", 422, {"fields": self.fields})


# --- attribute filters (R3) ---------------------------------------------------------------


def _scalar(field: FieldDef, raw: str) -> Any:
    """Parse one filter value for `field`; ValueError when it does not fit."""
    match field.type:
        case "integer":
            return int(raw)
        case "decimal":
            return float(raw)
        case "boolean":
            if raw.lower() in TRUE:
                return True
            if raw.lower() in FALSE:
                return False
            raise ValueError("expected true or false")
        case _:
            if raw not in field.option_values:
                raise ValueError(f"unknown option {raw!r}")
            return raw


def _numeric(key: str) -> ColumnElement[Any]:
    """`attributes->>key` as numeric, NULL when the value is not a number."""
    value = Listing.attributes[key]
    return case((func.jsonb_typeof(value) == "number", value.astext.cast(Numeric)))


def attribute_filters(
    items: Sequence[tuple[str, str]], leaves: Sequence[Category]
) -> list[ColumnElement[bool]]:
    """SQL conditions for `attr.<key>[.min|.max]` query items, validated against the
    filterable fields of `leaves`. Raises VALIDATION_ERROR (422) listing every problem."""
    attr_items = [(k, v) for k, v in items if k.startswith(ATTR_PREFIX)]
    if not attr_items:
        return []
    errors = _FilterErrors()
    fields: dict[str, FieldDef] = {}
    for leaf in leaves:
        for field in listings.schema_fields(leaf):
            if field.filter != "none":
                fields.setdefault(field.key, field)

    exact: dict[str, Any] = {}
    bounds: dict[str, dict[str, float]] = defaultdict(dict)
    any_of: dict[str, list[Any]] = defaultdict(list)
    for param, raw in attr_items:
        key, _, bound = param.removeprefix(ATTR_PREFIX).partition(".")
        found = fields.get(key)
        if found is None:
            errors.add(param, "unknown attribute filter for this category")
            continue
        field = found
        try:
            if field.filter == "range":
                if bound not in ("min", "max"):
                    raise ValueError("use .min or .max for a range filter")
                bounds[key][bound] = float(raw)
            elif bound:
                raise ValueError("this attribute has no range filter")
            elif field.filter == "exact":
                exact[key] = _scalar(field, raw)
            else:
                any_of[key].extend(_scalar(field, v.strip()) for v in raw.split(",") if v.strip())
        except ValueError as err:
            errors.add(param, str(err))
    errors.raise_if_any()

    conditions: list[ColumnElement[bool]] = [
        Listing.attributes.contains({key: value}) for key, value in exact.items()
    ]
    for key, limits in bounds.items():
        if "min" in limits:
            conditions.append(_numeric(key) >= limits["min"])
        if "max" in limits:
            conditions.append(_numeric(key) <= limits["max"])
    for key, values in any_of.items():
        multi = fields[key].type == "multi_enum"
        conditions.append(
            or_(*(Listing.attributes.contains({key: [v] if multi else v}) for v in values))
        )
    return conditions


# --- periods per leaf ---------------------------------------------------------------------


def leaf_periods(
    leaves: Sequence[Category], params: SearchParams
) -> tuple[dict[Any, Period], list[Any]] | None:
    """`({leaf_id: period}, [leaf ids the period does not apply to])`, or None without a
    period. A period that is invalid for every leaf it applies to raises its error."""
    period_params = params.period()
    if period_params.is_empty():
        return None
    periods: dict[Any, Period] = {}
    unfiltered: list[Any] = []
    first_error: AppError | None = None
    for leaf in leaves:
        assert leaf.booking_mode is not None
        if not period_params.fits(leaf.booking_mode):
            unfiltered.append(leaf.id)
            continue
        try:
            periods[leaf.id] = listings.period_for(leaf, None, period_params)
        except AppError as err:
            first_error = first_error or err
    if first_error is not None and not periods:
        raise first_error
    return periods, unfiltered


def _availability_clause(
    leaves: Sequence[Category], resolved: tuple[dict[Any, Period], list[Any]] | None
) -> ColumnElement[bool]:
    if resolved is None:
        return Listing.category_id.in_([leaf.id for leaf in leaves]) if leaves else false()
    periods, unfiltered = resolved
    groups: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for leaf_id, p in periods.items():
        groups[(p.mode, p.start, p.end, p.quantity, p.unit, p.count)].append(leaf_id)
    clauses: list[ColumnElement[bool]] = []
    for leaf_ids in groups.values():
        p = periods[leaf_ids[0]]
        clauses.append(
            and_(
                Listing.category_id.in_(leaf_ids),
                or_(Listing.min_duration.is_(None), Listing.min_duration <= p.count),
                or_(Listing.max_duration.is_(None), Listing.max_duration >= p.count),
                availability_filter(p.mode, p),
            )
        )
    if unfiltered:
        clauses.append(Listing.category_id.in_(unfiltered))
    return or_(*clauses) if clauses else false()


# --- search -------------------------------------------------------------------------------


def _bbox(raw: str) -> ColumnElement[bool]:
    min_lng, min_lat, max_lng, max_lat = (float(v) for v in raw.split(","))
    return and_(
        Listing.lat.is_not(None),
        Listing.lng.is_not(None),
        Listing.lat.between(min_lat, max_lat),
        Listing.lng.between(min_lng, max_lng),
    )


async def scope_leaves(session: AsyncSession, slug: str | None) -> list[Category]:
    """Active leaf categories in `slug`'s subtree (every leaf without a slug)."""
    categories = await active_categories(session)
    if slug is None:
        return [c for c in categories if c.is_leaf]
    root = await get_category_by_slug(session, slug)
    return [
        c
        for c in categories
        if c.is_leaf and (c.path == root.path or c.path.startswith(root.path + "."))
    ]


async def search(
    session: AsyncSession,
    params: SearchParams,
    query_items: Sequence[tuple[str, str]],
    locale: Locale,
) -> Page[ListingCard]:
    leaves = await scope_leaves(session, params.category)
    if params.category is None and any(k.startswith(ATTR_PREFIX) for k, _ in query_items):
        errors = _FilterErrors()
        for key, _ in query_items:
            if key.startswith(ATTR_PREFIX):
                errors.add(key, "attribute filters need a category")
        errors.raise_if_any()
    conditions = attribute_filters(query_items, leaves)
    resolved = leaf_periods(leaves, params)
    conditions.append(_availability_clause(leaves, resolved))

    if params.region is not None:
        conditions.append(Listing.region_id == params.region)
    if params.district is not None:
        conditions.append(Listing.district_id == params.district)
    if params.ward is not None:
        conditions.append(Listing.ward_id == params.ward)
    if params.price_min is not None:
        conditions.append(Listing.base_price_tzs >= params.price_min)
    if params.price_max is not None:
        conditions.append(Listing.base_price_tzs <= params.price_max)
    if params.q and params.q.strip():
        conditions.append(
            Listing.search_tsv.op("@@")(func.plainto_tsquery("simple", params.q.strip()))
        )
    if params.bbox:
        conditions.append(_bbox(params.bbox))

    base = listings.public_listings().where(*conditions)
    total = (
        await session.execute(
            select(func.count()).select_from(base.with_only_columns(Listing.id).subquery())
        )
    ).scalar_one()

    orders: dict[str, list[Any]] = {
        "newest": [Listing.created_at.desc(), Listing.id.desc()],
        "price_asc": [Listing.base_price_tzs.asc().nulls_last(), Listing.id],
        "price_desc": [Listing.base_price_tzs.desc().nulls_last(), Listing.id],
        "rating": [
            Listing.rating_avg.desc().nulls_last(),
            Listing.rating_count.desc(),
            Listing.id,
        ],
    }
    order = orders[params.sort]
    rows = (
        await session.execute(
            base.order_by(*order)
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
    ).all()
    periods = resolved[0] if resolved else None
    items = await listings.cards(session, [(lst, cat) for lst, cat in rows], locale, periods)
    return Page[ListingCard](items=items, page=params.page, page_size=params.page_size, total=total)
