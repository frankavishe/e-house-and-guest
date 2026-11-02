"""Public catalogue endpoints (T036)."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import BookingMode, Category, Location, LocationLevel

SCHEMA = [
    {
        "key": "bedrooms",
        "type": "integer",
        "label": {"sw": "Vyumba", "en": "Bedrooms"},
        "filter": "range",
    }
]


async def _tree(db: AsyncSession) -> None:
    group = Category(
        path="t-acc", slug="t-acc", name={"sw": "Malazi", "en": "Accommodation"}, sort_order=1
    )
    db.add(group)
    await db.flush()
    db.add_all(
        [
            Category(
                parent_id=group.id,
                path="t-acc.t-rooms",
                slug="t-rooms",
                name={"sw": "Vyumba", "en": "Rooms"},
                booking_mode=BookingMode.DATE_RANGE,
                price_units=["night", "week"],
                default_unit="night",
                attribute_schema=SCHEMA,
            ),
            Category(
                parent_id=group.id,
                path="t-acc.t-hidden",
                slug="t-hidden",
                name={"sw": "Siri", "en": "Hidden"},
                booking_mode=BookingMode.DATE_RANGE,
                price_units=["night"],
                default_unit="night",
                is_active=False,
            ),
        ]
    )
    await db.flush()


async def test_category_tree(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _tree(db)
    res = await client.get("/api/v1/categories")
    assert res.status_code == 200
    assert "max-age=300" in res.headers["cache-control"]
    group = next(c for c in res.json() if c["slug"] == "t-acc")
    assert group["booking_mode"] is None
    assert [c["slug"] for c in group["children"]] == ["t-rooms"]  # inactive leaf hidden
    rooms = group["children"][0]
    assert rooms["name"] == {"sw": "Vyumba", "en": "Rooms"}
    assert rooms["booking_mode"] == "DATE_RANGE" and rooms["price_units"] == ["night", "week"]


async def test_category_detail_includes_schema(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _tree(db)
    res = await client.get("/api/v1/categories/t-rooms")
    assert res.status_code == 200
    body = res.json()
    assert body["attribute_schema"] == SCHEMA
    assert body["is_leaf"] is True and body["parent_slug"] == "t-acc"
    assert (await client.get("/api/v1/categories/t-hidden")).status_code == 404
    assert (await client.get("/api/v1/categories/nope")).status_code == 404


async def test_locations(client: httpx.AsyncClient, db: AsyncSession) -> None:
    db.add(Location(id=990001, level=LocationLevel.REGION, name="Zzz Region", slug="zzz"))
    await db.flush()
    db.add_all(
        [
            Location(id=990002, parent_id=990001, level=LocationLevel.DISTRICT, name="B", slug="b"),
            Location(
                id=990003,
                parent_id=990001,
                level=LocationLevel.DISTRICT,
                name="A",
                slug="a",
                lat=-6.8,
                lng=39.28,
            ),
        ]
    )
    await db.flush()

    regions = (await client.get("/api/v1/locations")).json()
    assert any(r["id"] == 990001 for r in regions)
    assert all(r["level"] == "region" for r in regions)

    districts = (await client.get("/api/v1/locations?parent_id=990001")).json()
    assert [d["name"] for d in districts] == ["A", "B"]
    assert districts[0]["lat"] == -6.8 and districts[1]["lat"] is None

    res = await client.get("/api/v1/locations?level=district&parent_id=990001")
    assert len(res.json()) == 2
    assert (await client.get("/api/v1/locations?level=planet")).status_code == 422
