"""Admin category management (T132, US7-AS1, FR-006, FR-031, SC-006).

An admin adds a rental type with its fields; it is listable and filterable at once, with no
code or deploy. Schema edits bump `schema_version`; edits that would orphan stored values
(type change, removing an option in use) are refused.
"""

from datetime import date
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.models import AdminAuditLog
from app.bookings.models import Booking
from app.catalog.models import Category
from tests.factories import (
    book,
    day_range,
    make_admin,
    make_bookable,
    make_booking,
    make_category,
    make_listing,
    make_owner,
    make_place,
    make_user,
    sign_in,
)

pytestmark = pytest.mark.usefixtures("frozen_clock")  # now = 2026-11-02 09:00 EAT

URL = "/api/v1/admin/categories"

GENERATOR_SCHEMA: list[dict[str, Any]] = [
    {
        "key": "power_kva",
        "type": "decimal",
        "label": {"sw": "Nguvu (kVA)", "en": "Power (kVA)"},
        "unit": {"sw": "kVA", "en": "kVA"},
        "required": True,
        "min": 0.5,
        "max": 2000,
        "filter": "range",
        "show_on_card": True,
        "order": 1,
    },
    {
        "key": "fuel",
        "type": "enum",
        "label": {"sw": "Aina ya mafuta", "en": "Fuel type"},
        "options": [
            {"value": "diesel", "label": {"sw": "Dizeli", "en": "Diesel"}},
            {"value": "petrol", "label": {"sw": "Petroli", "en": "Petrol"}},
        ],
        "required": True,
        "filter": "exact",
        "order": 2,
    },
]


def _generators(parent_id: str | None = None, **overrides: Any) -> dict[str, Any]:
    return {
        "parent_id": parent_id,
        "slug": "generators",
        "name": {"sw": "Jenereta", "en": "Generators"},
        "booking_mode": "QUANTITY",
        "price_units": ["item_day"],
        "default_unit": "item_day",
        "attribute_schema": GENERATOR_SCHEMA,
        "commission_bps": 1200,
        "renter_fee_bps": 0,
        **overrides,
    }


async def _create(client: httpx.AsyncClient, body: dict[str, Any]) -> httpx.Response:
    return await client.post(URL, json=body)


async def test_admin_only(client: httpx.AsyncClient, db: AsyncSession) -> None:
    sign_in(client, await make_user(db))
    assert (await client.get(URL)).status_code == 403
    assert (await _create(client, _generators())).status_code == 403


async def test_new_type_is_listable_and_filterable_at_once(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    group = await make_category(db, mode=None, default_unit=None, slug="t-equipment")
    admin = await make_admin(db)
    sign_in(client, admin)
    r = await _create(client, _generators(str(group.id)))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["path"] == "t-equipment.generators"
    assert created["is_leaf"] is True
    assert created["schema_version"] == 1
    assert created["listing_count"] == 0
    assert [f["key"] for f in created["attribute_schema"]] == ["power_kva", "fuel"]

    listed = (await client.get(URL)).json()
    assert any(c["slug"] == "generators" for c in listed)
    audit = (
        await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "category.create"))
    ).scalar_one()
    assert str(audit.target_id) == created["id"]

    # Public catalogue: the new type appears with its fields.
    client.cookies.clear()
    detail = (await client.get("/api/v1/categories/generators")).json()
    assert [f["key"] for f in detail["attribute_schema"]] == ["power_kva", "fuel"]

    # An owner can start a listing in it; attribute values are checked against the schema.
    owner_user = await make_user(db, name="Generator Owner")
    await make_owner(db, user=owner_user)
    sign_in(client, owner_user)
    draft = await client.post("/api/v1/owner/listings", json={"category_id": created["id"]})
    assert draft.status_code == 201, draft.text
    bad = await client.patch(
        f"/api/v1/owner/listings/{draft.json()['id']}",
        json={"attributes": {"power_kva": 20, "fuel": "coal"}},
    )
    assert bad.status_code == 422
    good = await client.patch(
        f"/api/v1/owner/listings/{draft.json()['id']}",
        json={"attributes": {"power_kva": 20, "fuel": "diesel"}},
    )
    assert good.status_code == 200, good.text

    # Renters filter live listings by kVA and fuel.
    category = await db.get(Category, created["id"])
    assert category is not None
    owner = await make_owner(db)
    region, district = await make_place(db, "Gen region")
    small = await make_listing(
        db,
        owner=owner,
        category=category,
        region=region,
        district=district,
        attributes={"power_kva": 5, "fuel": "petrol"},
    )
    big = await make_listing(
        db,
        owner=owner,
        category=category,
        region=region,
        district=district,
        attributes={"power_kva": 60, "fuel": "diesel"},
    )
    client.cookies.clear()

    async def found(**params: str) -> set[str]:
        r = await client.get("/api/v1/listings/search", params={"category": "generators", **params})
        assert r.status_code == 200, r.text
        return {item["id"] for item in r.json()["items"]}

    assert await found() == {str(small.id), str(big.id)}
    assert await found(**{"attr.power_kva.min": "50"}) == {str(big.id)}
    assert await found(**{"attr.fuel": "petrol"}) == {str(small.id)}


async def test_create_validation(client: httpx.AsyncClient, db: AsyncSession) -> None:
    leaf = await make_category(db)
    sign_in(client, await make_admin(db))

    bad_schema = [
        *GENERATOR_SCHEMA,
        GENERATOR_SCHEMA[0],
        {**GENERATOR_SCHEMA[1], "key": "fuel2", "filter": "range"},
    ]
    r = await _create(client, _generators(attribute_schema=bad_schema))
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "INVALID_SCHEMA"
    assert len(body["details"]["problems"]) == 2  # disallowed filter + duplicate key

    r = await _create(client, _generators(default_unit="day"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_CATEGORY"

    r = await _create(client, _generators(str(leaf.id)))  # a leaf cannot have children
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_CATEGORY"

    r = await _create(
        client, _generators(booking_mode=None, price_units=[], default_unit=None, slug="t-grp")
    )
    assert r.status_code == 422  # a group carries no fields
    assert r.json()["error"]["code"] == "INVALID_CATEGORY"

    r = await _create(client, _generators(slug=leaf.slug))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "SLUG_TAKEN"

    r = await _create(client, _generators(slug="Not A Slug"))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_schema_edits_bump_version_and_refuse_breaking_changes(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    sign_in(client, await make_admin(db))
    created = (await _create(client, _generators())).json()
    url = f"{URL}/{created['id']}"
    category = await db.get(Category, created["id"])
    assert category is not None
    owner = await make_owner(db)
    region, district = await make_place(db)
    await make_listing(
        db,
        owner=owner,
        category=category,
        region=region,
        district=district,
        attributes={"power_kva": 20, "fuel": "diesel"},
    )

    # Labels, new fields and new options are always allowed; each edit bumps the version.
    schema = [dict(f) for f in GENERATOR_SCHEMA]
    schema[1] = {
        **schema[1],
        "label": {"sw": "Mafuta", "en": "Fuel"},
        "options": [
            *schema[1]["options"],
            {"value": "gas", "label": {"sw": "Gesi", "en": "Gas"}},
        ],
    }
    schema.append(
        {
            "key": "silent",
            "type": "boolean",
            "label": {"sw": "Kimya", "en": "Silent"},
            "order": 3,
        }
    )
    r = await client.patch(url, json={"attribute_schema": schema})
    assert r.status_code == 200, r.text
    assert r.json()["schema_version"] == 2
    assert r.json()["listing_count"] == 1

    # Unused options can be removed; options in use cannot.
    unused_removed = [schema[0], {**schema[1], "options": schema[1]["options"][:2]}, schema[2]]
    r = await client.patch(url, json={"attribute_schema": unused_removed})
    assert r.status_code == 200, r.text
    assert r.json()["schema_version"] == 3
    in_use_removed = [schema[0], {**schema[1], "options": schema[1]["options"][1:2]}, schema[2]]
    r = await client.patch(url, json={"attribute_schema": in_use_removed})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "SCHEMA_FIELD_IN_USE"
    assert r.json()["error"]["details"]["field"] == "fuel"

    # Changing the type of a field that listings use is refused.
    retyped = [{**schema[0], "type": "integer", "min": 1, "max": 2000}, *unused_removed[1:]]
    r = await client.patch(url, json={"attribute_schema": retyped})
    assert r.status_code == 409
    assert r.json()["error"]["details"]["field"] == "power_kva"

    # Removing a field hides it; stored values stay.
    r = await client.patch(url, json={"attribute_schema": unused_removed[1:]})
    assert r.status_code == 200, r.text
    assert r.json()["schema_version"] == 4
    assert [f["key"] for f in r.json()["attribute_schema"]] == ["fuel", "silent"]

    # Editing non-schema fields leaves the version alone.
    r = await client.patch(url, json={"name": {"sw": "Jenereta!", "en": "Generators!"}})
    assert r.status_code == 200
    assert r.json()["schema_version"] == 4

    # A unit used by listing prices cannot be dropped.
    r = await client.patch(url, json={"price_units": ["day"], "default_unit": "day"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PRICE_UNIT_IN_USE"

    actions = (
        (
            await db.execute(
                select(AdminAuditLog.action).where(AdminAuditLog.target_id == category.id)
            )
        )
        .scalars()
        .all()
    )
    assert actions.count("category.update") == 4


async def test_commission_change_applies_to_new_bookings_only(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    b = await make_bookable(db, commission_bps=1000)
    existing = await make_booking(
        db, b, *day_range(date(2026, 11, 20), date(2026, 11, 22)), status="confirmed"
    )
    sign_in(client, await make_admin(db))
    r = await client.patch(
        f"{URL}/{b.category.id}", json={"commission_bps": 1500, "renter_fee_bps": 300}
    )
    assert r.status_code == 200, r.text
    assert r.json()["commission_bps"] == 1500

    await db.refresh(existing)
    assert existing.commission_bps == 1000
    created = await book(client, b, date(2026, 11, 10))
    assert created.status_code == 201, created.text
    new = await db.get(Booking, created.json()["id"])
    assert new is not None
    assert new.commission_bps == 1500
    assert new.service_fee_tzs > 0


async def test_inactive_category_is_hidden(client: httpx.AsyncClient, db: AsyncSession) -> None:
    sign_in(client, await make_admin(db))
    created = (await _create(client, _generators())).json()
    r = await client.patch(f"{URL}/{created['id']}", json={"is_active": False})
    assert r.status_code == 200
    client.cookies.clear()
    assert (await client.get("/api/v1/categories/generators")).status_code == 404
