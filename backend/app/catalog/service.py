"""Catalogue reads: category tree, category by slug, locations. Other modules call these."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Location, LocationLevel
from app.catalog.schemas import CategoryDetail, CategoryNode, LocalizedText, LocationOut
from app.core.errors import not_found


def _node(c: Category) -> CategoryNode:
    return CategoryNode(
        id=c.id,
        slug=c.slug,
        name=LocalizedText(**c.name),
        booking_mode=c.booking_mode.value if c.booking_mode else None,
        price_units=list(c.price_units),
        default_unit=c.default_unit,
    )


async def active_categories(session: AsyncSession) -> list[Category]:
    rows = await session.execute(
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.sort_order, Category.slug)
    )
    return list(rows.scalars().all())


def build_tree(categories: list[Category]) -> list[CategoryNode]:
    """Nest categories under their parents. Children of inactive parents are dropped."""
    nodes = {c.id: _node(c) for c in categories}
    roots: list[CategoryNode] = []
    for c in categories:
        node = nodes[c.id]
        if c.parent_id is None:
            roots.append(node)
        elif c.parent_id in nodes:
            nodes[c.parent_id].children.append(node)
    return roots


async def category_tree(session: AsyncSession) -> list[CategoryNode]:
    return build_tree(await active_categories(session))


async def get_category_by_slug(session: AsyncSession, slug: str) -> Category:
    category = (
        await session.execute(
            select(Category).where(Category.slug == slug, Category.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if category is None:
        raise not_found("category")
    return category


async def subtree_ids(session: AsyncSession, category: Category) -> list[uuid.UUID]:
    """The category and all its descendants (via the materialised `path`)."""
    rows = await session.execute(
        select(Category.id).where(
            (Category.path == category.path) | Category.path.startswith(category.path + ".")
        )
    )
    return list(rows.scalars().all())


async def category_detail(session: AsyncSession, slug: str) -> CategoryDetail:
    category = await get_category_by_slug(session, slug)
    parent_slug = None
    if category.parent_id is not None:
        parent = await session.get(Category, category.parent_id)
        parent_slug = parent.slug if parent else None
    children = [_node(c) for c in await active_categories(session) if c.parent_id == category.id]
    return CategoryDetail(
        id=category.id,
        slug=category.slug,
        path=category.path,
        parent_slug=parent_slug,
        name=LocalizedText(**category.name),
        booking_mode=category.booking_mode.value if category.booking_mode else None,
        price_units=list(category.price_units),
        default_unit=category.default_unit,
        is_leaf=category.is_leaf,
        schema_version=category.schema_version,
        attribute_schema=list(category.attribute_schema),
        children=children,
    )


async def list_locations(
    session: AsyncSession, parent_id: int | None, level: LocationLevel | None
) -> list[LocationOut]:
    stmt = select(Location)
    if parent_id is not None:
        stmt = stmt.where(Location.parent_id == parent_id)
    elif level is None:
        stmt = stmt.where(Location.level == LocationLevel.REGION)
    if level is not None:
        stmt = stmt.where(Location.level == level)
    rows = (await session.execute(stmt.order_by(Location.name))).scalars().all()
    return [
        LocationOut(
            id=loc.id,
            parent_id=loc.parent_id,
            level=loc.level.value,
            name=loc.name,
            slug=loc.slug,
            lat=float(loc.lat) if loc.lat is not None else None,
            lng=float(loc.lng) if loc.lng is not None else None,
        )
        for loc in rows
    ]
