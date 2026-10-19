"""Request/response shapes for the catalogue, search and listing endpoints (T053)."""

from datetime import date, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import EAT
from app.listings.models import Listing
from app.main import app
from tests.factories import (
    day_range,
    make_block,
    make_category,
    make_listing,
    make_owner,
    make_place,
    make_user,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # today = 2026-11-02 EAT

D = date(2026, 11, 10)
CARD_KEYS = {
    "id",
    "title",
    "category",
    "location",
    "cover_photo",
    "base_price",
    "total_tzs",
    "rating_avg",
    "rating_count",
    "instant_book",
    "lat",
    "lng",
    "booking_mode",
    "highlights",
}
QUOTE_KEYS = {
    "lines",
    "rental_tzs",
    "delivery_fee_tzs",
    "service_fee_tzs",
    "deposit_tzs",
    "total_tzs",
}
SCHEMA = [
    {
        "key": "bedrooms",
        "type": "integer",
        "label": {"sw": "Vyumba", "en": "Bedrooms"},
        "filter": "range",
        "group": {"sw": "Ukubwa", "en": "Size"},
    },
    {
        "key": "view",
        "type": "enum",
        "label": {"sw": "Mandhari", "en": "View"},
        "options": [{"value": "sea", "label": {"sw": "Bahari", "en": "Sea"}}],
    },
]


def test_paths_are_documented() -> None:
    paths = app.openapi()["paths"]
    for path, method in [
        ("/api/v1/categories", "get"),
        ("/api/v1/categories/{slug}", "get"),
        ("/api/v1/locations", "get"),
        ("/api/v1/listings/search", "get"),
        ("/api/v1/listings/{listing_id}", "get"),
        ("/api/v1/listings/{listing_id}/availability", "get"),
        ("/api/v1/listings/{listing_id}/quote", "post"),
    ]:
        assert method in paths.get(path, {}), f"{method.upper()} {path} missing"
    params = {p["name"] for p in paths["/api/v1/listings/search"]["get"]["parameters"]}
    assert {
        "category",
        "region",
        "district",
        "ward",
        "start_date",
        "end_date",
        "start",
        "end",
    } <= params
    assert {
        "months",
        "quantity",
        "q",
        "price_min",
        "price_max",
        "bbox",
        "sort",
        "page",
        "page_size",
    } <= params


async def _room(db: AsyncSession, **kw: Any) -> Listing:
    category = await make_category(db, attribute_schema=SCHEMA, renter_fee_bps=500)
    region, district = await make_place(db, "Contract")
    user = await make_user(db, phone="+255713000001")
    owner = await make_owner(db, user=user, display_name="Mama Owner")
    return await make_listing(
        db,
        owner=owner,
        category=category,
        region=region,
        district=district,
        price=40_000,
        prices=[
            {
                "unit": "night",
                "amount_tzs": 50_000,
                "season_start": date(2026, 12, 20),
                "season_end": date(2026, 12, 31),
            }
        ],
        attributes={"bedrooms": 2, "view": "sea"},
        address_hint="Plot 12, Msasani",
        deposit_tzs=10_000,
        **kw,
    )


async def test_search_page_shape(client: httpx.AsyncClient, db: AsyncSession) -> None:
    room = await _room(db)
    res = await client.get("/api/v1/listings/search", params={"region": room.region_id})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body["page"] == 1 and body["page_size"] == 20 and body["total"] == 1
    assert set(body["items"][0]) == CARD_KEYS
    assert set(body["items"][0]["cover_photo"]) == {"url_320", "url_640", "alt"}


async def test_listing_detail_shape(client: httpx.AsyncClient, db: AsyncSession) -> None:
    room = await _room(db)
    res = await client.get(f"/api/v1/listings/{room.id}", headers={"Accept-Language": "en"})
    assert res.status_code == 200
    body = res.json()
    assert CARD_KEYS - {"total_tzs"} <= set(body)
    for key in (
        "description",
        "photos",
        "attributes",
        "prices",
        "deposit_tzs",
        "delivery",
        "delivery_fee_tzs",
        "cancellation_policy",
        "owner",
        "reviews",
        "default_unit",
        "min_duration",
        "max_duration",
        "stock",
    ):
        assert key in body, key
    assert body["title"] == "Listing" and body["description"] == "Listing description"
    assert body["owner"] == {
        "display_name": "Mama Owner",
        "rating_avg": None,
        "rating_count": 0,
        "verified": True,
    }
    assert body["attributes"] == [
        {
            "key": "bedrooms",
            "label": "Bedrooms",
            "value": 2,
            "display": "2",
            "unit": None,
            "group": "Size",
        },
        {
            "key": "view",
            "label": "View",
            "value": "sea",
            "display": "Sea",
            "unit": None,
            "group": None,
        },
    ]
    assert {(p["unit"], p["amount_tzs"], p["season_start"]) for p in body["prices"]} == {
        ("night", 40_000, None),
        ("night", 50_000, "2026-12-20"),
    }
    assert body["reviews"] == [] and body["deposit_tzs"] == 10_000
    # Contact details stay private until a booking is confirmed (FR-014).
    text = res.text
    assert "+255713000001" not in text and "Plot 12" not in text


async def test_listing_detail_hidden_unless_public(
    client: httpx.AsyncClient, db: AsyncSession, make_id: Any
) -> None:
    draft = await _room(db, status="draft")
    assert (await client.get(f"/api/v1/listings/{draft.id}")).status_code == 404
    assert (await client.get(f"/api/v1/listings/{make_id()}")).status_code == 404
    assert (await client.get("/api/v1/listings/not-a-uuid")).status_code == 422


async def test_availability_by_mode(client: httpx.AsyncClient, db: AsyncSession) -> None:
    room = await _room(db)
    await make_block(db, room, *day_range(D, D + timedelta(days=2)))
    res = await client.get(
        f"/api/v1/listings/{room.id}/availability",
        params={"from": D.isoformat(), "to": (D + timedelta(days=30)).isoformat()},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["booking_mode"] == "DATE_RANGE"
    assert body["unavailable"] == [{"start_date": "2026-11-10", "end_date": "2026-11-12"}]
    assert body["slots"] is None and body["stock"] is None

    region, district = await make_place(db)
    owner = await make_owner(db)
    tents = await make_listing(
        db,
        owner=owner,
        category=await make_category(db, mode="QUANTITY", default_unit="item_day"),
        region=region,
        district=district,
        stock=5,
    )
    stock = (
        await client.get(
            f"/api/v1/listings/{tents.id}/availability",
            params={"from": D.isoformat(), "to": (D + timedelta(days=1)).isoformat()},
        )
    ).json()
    assert stock["stock"] == [
        {"date": "2026-11-10", "available": 5},
        {"date": "2026-11-11", "available": 5},
    ]

    hall = await make_listing(
        db,
        owner=owner,
        category=await make_category(db, mode="TIME_SLOT", default_unit="hour"),
        region=region,
        district=district,
        slot_config={
            "open": "08:00",
            "close": "10:00",
            "slot_minutes": 60,
            "days": [1, 2, 3, 4, 5, 6, 7],
        },
    )
    slots = (
        await client.get(
            f"/api/v1/listings/{hall.id}/availability",
            params={"from": D.isoformat(), "to": D.isoformat()},
        )
    ).json()
    assert slots["slots"][0]["date"] == "2026-11-10"
    assert [
        datetime.fromisoformat(s["start"]).astimezone(EAT).hour for s in slots["slots"][0]["slots"]
    ] == [8, 9]

    too_long = await client.get(
        f"/api/v1/listings/{room.id}/availability",
        params={"from": D.isoformat(), "to": (D + timedelta(days=400)).isoformat()},
    )
    assert too_long.status_code == 400


async def test_quote(client: httpx.AsyncClient, db: AsyncSession) -> None:
    room = await _room(db)
    url = f"/api/v1/listings/{room.id}/quote"
    res = await client.post(url, json={"start_date": "2026-12-18", "end_date": "2026-12-22"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == QUOTE_KEYS
    assert set(body["lines"][0]) == {"label", "unit", "count", "unit_price_tzs", "amount_tzs"}
    assert body["rental_tzs"] == 2 * 40_000 + 2 * 50_000
    assert body["service_fee_tzs"] == 9_000 and body["deposit_tzs"] == 10_000
    assert body["total_tzs"] == 180_000 + 9_000 + 10_000

    await make_block(db, room, *day_range(D, D + timedelta(days=1)))
    taken = await client.post(url, json={"start_date": "2026-11-10", "end_date": "2026-11-12"})
    assert taken.status_code == 409 and taken.json()["error"]["code"] == "SLOT_TAKEN"

    bad = await client.post(url, json={"start_date": "2026-11-12", "end_date": "2026-11-12"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "INVALID_PERIOD"
    wrong_mode = await client.post(url, json={"start_date": "2026-11-12", "months": 2})
    assert wrong_mode.status_code == 400


async def test_quote_insufficient_stock(client: httpx.AsyncClient, db: AsyncSession) -> None:
    region, district = await make_place(db)
    tents = await make_listing(
        db,
        owner=await make_owner(db),
        category=await make_category(db, mode="QUANTITY", default_unit="item_day"),
        region=region,
        district=district,
        stock=10,
    )
    await make_block(db, tents, *day_range(D, D + timedelta(days=1)), kind="stock", quantity=7)
    res = await client.post(
        f"/api/v1/listings/{tents.id}/quote",
        json={"start_date": "2026-11-10", "end_date": "2026-11-10", "quantity": 5},
    )
    assert res.status_code == 409
    error = res.json()["error"]
    assert error["code"] == "INSUFFICIENT_STOCK" and error["details"] == {"available": 3}
