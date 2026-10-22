"""Admin category management (T135, US7-AS1, FR-006): add rental types and their fields
without a release.

The attribute schema is validated with `parse_schema`; every schema change bumps
`schema_version`, which keys the parsed-schema and value-model caches, so they never serve
a stale schema. Edits that would orphan stored listing values are refused
(contracts/attribute-schema.md "Editing").
"""

import uuid
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import User
from app.admin.moderation import audit
from app.admin.schemas import AdminCategoryIn, AdminCategoryOut, AdminCategoryPatch
from app.catalog.attributes import CHOICE, FieldDef, SchemaError, parse_schema
from app.catalog.models import BookingMode, Category, PriceUnit
from app.catalog.schemas import LocalizedText
from app.core import clock
from app.core.errors import AppError, not_found
from app.listings.models import Listing, ListingPrice


def _state(c: Category) -> dict[str, Any]:
    return {
        "name": c.name,
        "price_units": list(c.price_units),
        "default_unit": c.default_unit,
        "attribute_schema": list(c.attribute_schema),
        "schema_version": c.schema_version,
        "commission_bps": c.commission_bps,
        "renter_fee_bps": c.renter_fee_bps,
        "is_active": c.is_active,
        "sort_order": c.sort_order,
    }


def _out(c: Category, listing_count: int) -> AdminCategoryOut:
    return AdminCategoryOut(
        id=c.id,
        parent_id=c.parent_id,
        path=c.path,
        slug=c.slug,
        name=LocalizedText(**c.name),
        booking_mode=c.booking_mode.value if c.booking_mode else None,
        price_units=list(c.price_units),
        default_unit=c.default_unit,
        attribute_schema=list(c.attribute_schema),
        schema_version=c.schema_version,
        commission_bps=c.commission_bps,
        renter_fee_bps=c.renter_fee_bps,
        is_active=c.is_active,
        sort_order=c.sort_order,
        is_leaf=c.is_leaf,
        listing_count=listing_count,
        updated_at=c.updated_at,
    )


async def _listing_count(session: AsyncSession, category_id: uuid.UUID) -> int:
    total = await session.execute(
        select(func.count()).select_from(Listing).where(Listing.category_id == category_id)
    )
    return int(total.scalar_one())


async def list_categories(session: AsyncSession) -> list[AdminCategoryOut]:
    """Every category, active or not, in tree order (by `path`)."""
    counts = (
        select(Listing.category_id, func.count().label("n"))
        .group_by(Listing.category_id)
        .subquery()
    )
    rows = await session.execute(
        select(Category, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.category_id == Category.id)
        .order_by(Category.path)
    )
    return [_out(c, int(n)) for c, n in rows.all()]


def _normalized_schema(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        fields = parse_schema(raw)
    except SchemaError as err:
        raise AppError("INVALID_SCHEMA", 422, {"problems": err.problems}) from None
    return [f.model_dump(exclude_none=True) for f in fields]


def _check_shape(
    booking_mode: BookingMode | None,
    price_units: list[str],
    default_unit: str | None,
    schema: list[dict[str, Any]],
) -> None:
    """Leaves need price units and a default among them; groups carry none of that."""
    if booking_mode is None:
        if price_units or default_unit or schema:
            raise AppError(
                "INVALID_CATEGORY", 422, {"reason": "a group has no price units or fields"}
            )
        return
    if not price_units or len(set(price_units)) != len(price_units):
        raise AppError("INVALID_CATEGORY", 422, {"reason": "price units must be unique"})
    if default_unit not in price_units:
        raise AppError("INVALID_CATEGORY", 422, {"reason": "default unit must be a price unit"})


async def create_category(
    session: AsyncSession, admin: User, body: AdminCategoryIn
) -> AdminCategoryOut:
    parent = None
    if body.parent_id is not None:
        parent = await session.get(Category, body.parent_id)
        if parent is None:
            raise not_found("category")
        if parent.is_leaf:
            raise AppError("INVALID_CATEGORY", 422, {"reason": "a leaf cannot have children"})
    taken = await session.execute(select(Category.id).where(Category.slug == body.slug))
    if taken.first() is not None:
        raise AppError("SLUG_TAKEN", 409)
    mode = BookingMode(body.booking_mode) if body.booking_mode else None
    units: list[str] = list(body.price_units)
    schema = _normalized_schema(body.attribute_schema)
    _check_shape(mode, units, body.default_unit, schema)
    category = Category(
        parent_id=parent.id if parent else None,
        path=f"{parent.path}.{body.slug}" if parent else body.slug,
        slug=body.slug,
        name=body.name.model_dump(),
        booking_mode=mode,
        price_units=units,
        default_unit=body.default_unit,
        attribute_schema=schema,
        schema_version=1,
        commission_bps=body.commission_bps,
        renter_fee_bps=body.renter_fee_bps,
        is_active=body.is_active,
        sort_order=body.sort_order,
    )
    session.add(category)
    await session.flush()
    await audit(session, admin, "category.create", "category", category.id, None, _state(category))
    return _out(category, 0)


async def _check_in_use(
    session: AsyncSession, category: Category, old: list[FieldDef], new: list[FieldDef]
) -> None:
    """409 when a field listings use changes type, or an option in use is removed."""
    in_category = Listing.category_id == category.id
    new_by_key = {f.key: f for f in new}
    for before in old:
        after = new_by_key.get(before.key)
        if after is None:
            continue  # removing a field only hides it
        value = Listing.attributes[before.key]
        if after.type != before.type:
            condition = Listing.attributes.has_key(before.key)
            details: dict[str, Any] = {"field": before.key}
        elif before.type in CHOICE:
            removed = sorted(set(before.option_values) - set(after.option_values))
            if not removed:
                continue
            condition = (
                value.astext.in_(removed)
                if before.type == "enum"
                else value.has_any(array(removed))
            )
            details = {"field": before.key, "options": removed}
        else:
            continue
        if (await session.execute(select(exists().where(in_category, condition)))).scalar():
            raise AppError("SCHEMA_FIELD_IN_USE", 409, details)


async def _check_units(session: AsyncSession, category: Category, units: list[str]) -> None:
    dropped = [PriceUnit(u) for u in set(category.price_units) - set(units)]
    if not dropped:
        return
    used = await session.execute(
        select(
            exists().where(
                ListingPrice.listing_id == Listing.id,
                Listing.category_id == category.id,
                ListingPrice.unit.in_(dropped),
            )
        )
    )
    if used.scalar():
        raise AppError("PRICE_UNIT_IN_USE", 409, {"units": sorted(u.value for u in dropped)})


async def update_category(
    session: AsyncSession, admin: User, category_id: uuid.UUID, patch: AdminCategoryPatch
) -> AdminCategoryOut:
    category = await session.get(Category, category_id, with_for_update=True)
    if category is None:
        raise not_found("category")
    before = _state(category)
    sent = patch.model_fields_set

    units = list(patch.price_units) if patch.price_units is not None else category.price_units
    default_unit = patch.default_unit if "default_unit" in sent else category.default_unit
    schema = list(category.attribute_schema)
    schema_changed = False
    if patch.attribute_schema is not None:
        schema = _normalized_schema(patch.attribute_schema)
        schema_changed = schema != list(category.attribute_schema)
    _check_shape(category.booking_mode, list(units), default_unit, schema)
    if schema_changed:
        try:
            old_fields = parse_schema(category.attribute_schema)
        except SchemaError:
            old_fields = []
        await _check_in_use(session, category, old_fields, parse_schema(schema))
    await _check_units(session, category, list(units))

    if patch.name is not None:
        category.name = patch.name.model_dump()
    category.price_units = list(units)
    category.default_unit = default_unit
    if schema_changed:
        category.attribute_schema = schema
        category.schema_version += 1
    for field in ("commission_bps", "renter_fee_bps", "is_active", "sort_order"):
        value = getattr(patch, field)
        if value is not None:
            setattr(category, field, value)
    after = _state(category)
    if after != before:
        category.updated_at = clock.now()
    await session.flush()
    await audit(session, admin, "category.update", "category", category.id, before, after)
    return _out(category, await _listing_count(session, category.id))
