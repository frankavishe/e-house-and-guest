"""`GET /listings/search` (T052, US1 acceptance scenarios 1-3, R4)."""

from datetime import date, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Category, Location
from app.listings.models import Listing
from tests.conftest import FrozenClock
from tests.factories import (
    day_range,
    make_block,
    make_category,
    make_listing,
    make_owner,
    make_place,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # today = 2026-11-02 EAT

URL = "/api/v1/listings/search"
D = date(2026, 11, 10)

LABEL = {"sw": "x", "en": "x"}
SCHEMA: list[dict[str, Any]] = [
    {"key": "bedrooms", "type": "integer", "label": LABEL, "filter": "range", "show_on_card": True},
    {"key": "furnished", "type": "boolean", "label": LABEL, "filter": "exact"},
    {
        "key": "view",
        "type": "enum",
        "label": LABEL,
        "filter": "exact",
        "options": [{"value": "sea", "label": LABEL}, {"value": "city", "label": LABEL}],
    },
    {
        "key": "kind",
        "type": "enum",
        "label": LABEL,
        "filter": "any_of",
        "options": [{"value": v, "label": LABEL} for v in ("flat", "villa", "hut")],
    },
    {
        "key": "amenities",
        "type": "multi_enum",
        "label": LABEL,
        "filter": "any_of",
        "options": [{"value": v, "label": LABEL} for v in ("wifi", "ac", "pool")],
    },
    {"key": "notes", "type": "text", "label": LABEL},
]


class World:
    group: Category
    rooms: Category
    cars: Category
    other: Category
    region: Location
    district: Location
    district2: Location


@pytest.fixture
async def world(db: AsyncSession) -> World:
    w = World()
    w.group = await make_category(db, mode=None, default_unit=None)
    w.rooms = await make_category(db, parent=w.group, attribute_schema=SCHEMA)
    w.cars = await make_category(db, parent=w.group, default_unit="day")
    w.other = await make_category(db, default_unit="day")
    w.region, w.district = await make_place(db, "Search region")
    from tests.factories import make_location

    w.district2 = await make_location(db, level="district", parent=w.region)
    return w


async def _listing(
    db: AsyncSession, w: World, category: Category | None = None, **kw: Any
) -> Listing:
    owner = kw.pop("owner", None) or await make_owner(db)
    return await make_listing(
        db,
        owner=owner,
        category=category or w.rooms,
        region=w.region,
        district=kw.pop("district", w.district),
        **kw,
    )


async def search(client: httpx.AsyncClient, w: World, **params: Any) -> dict[str, Any]:
    res = await client.get(URL, params={"region": w.region.id, **params})
    assert res.status_code == 200, res.text
    return res.json()


def ids(body: dict[str, Any]) -> set[str]:
    return {item["id"] for item in body["items"]}


async def test_category_subtree_and_location(
    client: httpx.AsyncClient, db: AsyncSession, world: World
) -> None:
    room = await _listing(db, world, title_en="Room")
    car = await _listing(db, world, world.cars, title_en="Car")
    other = await _listing(db, world, world.other)
    far = await _listing(db, world, district=world.district2)

    assert ids(await search(client, world, category=world.group.slug)) == {
        str(room.id),
        str(car.id),
        str(far.id),
    }
    assert ids(await search(client, world, category=world.cars.slug)) == {str(car.id)}
    assert str(other.id) in ids(await search(client, world))
    assert ids(await search(client, world, district=world.district2.id)) == {str(far.id)}
    res = await client.get(URL, params={"category": "no-such-category"})
    assert res.status_code == 404


async def test_only_active_listings_of_verified_owners(
    client: httpx.AsyncClient, db: AsyncSession, world: World
) -> None:
    visible = await _listing(db, world)
    await _listing(db, world, status="draft")
    await _listing(db, world, status="paused")
    await _listing(db, world, owner=await make_owner(db, verification="pending"))
    assert ids(await search(client, world)) == {str(visible.id)}


async def test_attribute_filters(client: httpx.AsyncClient, db: AsyncSession, world: World) -> None:
    a = await _listing(
        db,
        world,
        attributes={
            "bedrooms": 1,
            "furnished": True,
            "view": "sea",
            "kind": "flat",
            "amenities": ["wifi"],
        },
    )
    b = await _listing(
        db,
        world,
        attributes={
            "bedrooms": 3,
            "furnished": False,
            "view": "city",
            "kind": "villa",
            "amenities": ["ac", "pool"],
        },
    )
    c = await _listing(db, world, attributes={"bedrooms": 2, "kind": "hut"})
    cat = {"category": world.rooms.slug}

    async def found(**params: Any) -> set[str]:
        return ids(await search(client, world, **cat, **params))

    assert await found(**{"attr.furnished": "true"}) == {str(a.id)}
    assert await found(**{"attr.furnished": "false"}) == {str(b.id)}
    assert await found(**{"attr.view": "city"}) == {str(b.id)}
    assert await found(**{"attr.bedrooms.min": "2"}) == {str(b.id), str(c.id)}
    assert await found(**{"attr.bedrooms.min": "2", "attr.bedrooms.max": "2"}) == {str(c.id)}
    assert await found(**{"attr.kind": "flat,hut"}) == {str(a.id), str(c.id)}
    assert await found(**{"attr.amenities": "pool,wifi"}) == {str(a.id), str(b.id)}
    res = await client.get(
        URL,
        params=[
            ("region", world.region.id),
            ("category", world.rooms.slug),
            ("attr.kind", "villa"),
            ("attr.kind", "hut"),
        ],
    )
    assert ids(res.json()) == {str(b.id), str(c.id)}

    # Filters on a group category use its leaves' schemas.
    assert ids(await search(client, world, category=world.group.slug, **{"attr.view": "sea"})) == {
        str(a.id)
    }


@pytest.mark.parametrize(
    "params",
    [
        {"attr.colour": "red"},  # unknown key
        {"attr.notes": "x"},  # field without a filter
        {"attr.bedrooms": "2"},  # range field needs .min/.max
        {"attr.furnished.min": "1"},  # exact field has no range
        {"attr.bedrooms.min": "lots"},
        {"attr.furnished": "maybe"},
        {"attr.view": "mountain"},
        {"attr.kind": "flat,castle"},
    ],
)
async def test_invalid_attribute_filters(
    client: httpx.AsyncClient, world: World, params: dict[str, str]
) -> None:
    res = await client.get(URL, params={"category": world.rooms.slug, **params})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_attribute_filter_needs_a_category(client: httpx.AsyncClient) -> None:
    res = await client.get(URL, params={"attr.bedrooms.min": "2"})
    assert res.status_code == 422


async def test_period_excludes_unavailable_and_adds_totals(
    client: httpx.AsyncClient, db: AsyncSession, world: World
) -> None:
    free = await _listing(db, world, price=40_000)
    booked = await _listing(db, world, price=40_000)
    await make_block(db, booked, *day_range(D + timedelta(days=1), D + timedelta(days=2)))
    car = await _listing(db, world, world.cars, price=100_000)

    without = await search(client, world)
    assert ids(without) == {str(free.id), str(booked.id), str(car.id)}
    assert all(item["total_tzs"] is None for item in without["items"])

    period = {"start_date": D.isoformat(), "end_date": (D + timedelta(days=3)).isoformat()}
    body = await search(client, world, **period)
    assert ids(body) == {str(free.id), str(car.id)}
    totals = {item["id"]: item["total_tzs"] for item in body["items"]}
    assert totals[str(free.id)] == 3 * 40_000  # three nights
    assert totals[str(car.id)] == 4 * 100_000  # four days, last day inclusive

    # The check-out day is free for the next guest.
    after = {
        "start_date": (D + timedelta(days=2)).isoformat(),
        "end_date": (D + timedelta(days=4)).isoformat(),
    }
    assert str(booked.id) in ids(await search(client, world, **after))


async def test_stock_availability(
    client: httpx.AsyncClient, db: AsyncSession, world: World
) -> None:
    tents_cat = await make_category(db, mode="QUANTITY", default_unit="item_day")
    tents = await _listing(db, world, tents_cat, stock=10, price=5_000)
    await make_block(db, tents, *day_range(D, D + timedelta(days=1)), kind="stock", quantity=7)
    period = {"start_date": D.isoformat(), "end_date": D.isoformat()}

    body = await search(client, world, category=tents_cat.slug, quantity=3, **period)
    assert ids(body) == {str(tents.id)} and body["items"][0]["total_tzs"] == 15_000
    assert ids(await search(client, world, category=tents_cat.slug, quantity=4, **period)) == set()

    # Another listing's stock bookings do not count against this one.
    chairs = await _listing(db, world, tents_cat, stock=10, price=1_000)
    await make_block(db, chairs, *day_range(D, D + timedelta(days=1)), kind="stock", quantity=5)
    body = await search(client, world, category=tents_cat.slug, quantity=3, **period)
    assert ids(body) == {str(tents.id), str(chairs.id)}
    body = await search(client, world, category=tents_cat.slug, quantity=5, **period)
    assert ids(body) == {str(chairs.id)}


async def test_past_period_is_rejected(client: httpx.AsyncClient, world: World) -> None:
    res = await client.get(
        URL,
        params={"start_date": "2026-10-01", "end_date": "2026-10-03", "region": world.region.id},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_PERIOD"


async def test_sorting_and_pagination(
    client: httpx.AsyncClient, db: AsyncSession, world: World, frozen_clock: FrozenClock
) -> None:
    cheap = await _listing(db, world, price=10_000)
    frozen_clock.advance(minutes=1)
    mid = await _listing(db, world, price=20_000)
    frozen_clock.advance(minutes=1)
    dear = await _listing(db, world, price=30_000)

    def order(body: dict[str, Any]) -> list[str]:
        return [item["id"] for item in body["items"]]

    assert order(await search(client, world, sort="price_asc")) == [
        str(cheap.id),
        str(mid.id),
        str(dear.id),
    ]
    assert order(await search(client, world, sort="price_desc")) == [
        str(dear.id),
        str(mid.id),
        str(cheap.id),
    ]
    assert order(await search(client, world)) == [
        str(dear.id),
        str(mid.id),
        str(cheap.id),
    ]  # newest

    page2 = await search(client, world, sort="price_asc", page_size=2, page=2)
    assert page2["total"] == 3 and page2["page"] == 2 and page2["page_size"] == 2
    assert order(page2) == [str(dear.id)]
    res = await client.get(URL, params={"page_size": 51})
    assert res.status_code == 422


async def test_bbox_and_text(client: httpx.AsyncClient, db: AsyncSession, world: World) -> None:
    inside = await _listing(
        db, world, lat=-6.80, lng=39.28, title_sw="Chumba Msasani", title_en="Msasani room"
    )
    await _listing(db, world, lat=-3.37, lng=36.68, title_en="Arusha house")
    await _listing(db, world, title_en="No pin")

    assert ids(await search(client, world, bbox="39.0,-7.0,39.5,-6.5")) == {str(inside.id)}
    assert ids(await search(client, world, q="msasani")) == {str(inside.id)}
    res = await client.get(URL, params={"bbox": "not,a,box"})
    assert res.status_code == 422


async def test_card_shape(client: httpx.AsyncClient, db: AsyncSession, world: World) -> None:
    await _listing(
        db,
        world,
        price=45_000,
        title_sw="Chumba",
        title_en="Room",
        attributes={"bedrooms": 2},
        lat=-6.8,
        lng=39.2,
    )
    res = await client.get(
        URL, params={"region": world.region.id}, headers={"Accept-Language": "en"}
    )
    card = res.json()["items"][0]
    assert card["title"] == "Room"
    assert (
        card["category"]["slug"] == world.rooms.slug
        and card["category"]["name"] == world.rooms.name["en"]
    )
    assert card["location"] == {"region": world.region.name, "district": world.district.name}
    assert card["base_price"] == {"unit": "night", "amount_tzs": 45_000}
    assert card["cover_photo"]["url_320"].startswith("http")
    assert card["instant_book"] is True and card["rating_count"] == 0
    assert card["lat"] == -6.8 and card["lng"] == 39.2
    assert card["booking_mode"] == "DATE_RANGE"
    assert card["highlights"] == [{"key": "bedrooms", "label": "x", "value": "2"}]
    sw = (await client.get(URL, params={"region": world.region.id})).json()["items"][0]
    assert sw["title"] == "Chumba"
