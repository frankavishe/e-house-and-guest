"""Attribute schema meta-validation and listing value validation (T033, R3,
contracts/attribute-schema.md)."""

import copy
import uuid
from typing import Any

import pytest

from app.catalog.attributes import (
    SchemaError,
    ValuesError,
    parse_schema,
    validate_values,
)

L = {"sw": "Lebo", "en": "Label"}

GENERATORS: list[dict[str, Any]] = [
    {
        "key": "power_kva",
        "type": "decimal",
        "label": {"sw": "Nguvu (kVA)", "en": "Power (kVA)"},
        "required": True,
        "min": 0.5,
        "max": 2000,
        "filter": "range",
        "show_on_card": True,
        "order": 1,
    },
    {
        "key": "fuel_type",
        "type": "enum",
        "label": {"sw": "Aina ya mafuta", "en": "Fuel type"},
        "required": True,
        "filter": "any_of",
        "order": 2,
        "options": [
            {"value": "diesel", "label": {"sw": "Dizeli", "en": "Diesel"}},
            {"value": "petrol", "label": {"sw": "Petroli", "en": "Petrol"}},
        ],
    },
]

ALL_TYPES: list[dict[str, Any]] = [
    {
        "key": "bedrooms",
        "type": "integer",
        "label": L,
        "required": True,
        "min": 0,
        "max": 50,
        "filter": "range",
    },
    {"key": "area_m2", "type": "decimal", "label": L, "min": 1, "filter": "range"},
    {"key": "furnished", "type": "boolean", "label": L, "filter": "exact"},
    {
        "key": "vehicle_type",
        "type": "enum",
        "label": L,
        "filter": "any_of",
        "options": [{"value": "4x4", "label": L}, {"value": "suv", "label": L}],
    },
    {
        "key": "amenities",
        "type": "multi_enum",
        "label": L,
        "filter": "any_of",
        "options": [{"value": "wifi", "label": L}, {"value": "parking", "label": L}],
    },
    {"key": "notes", "type": "text", "label": L, "max_length": 20},
]


def field(**overrides: Any) -> dict[str, Any]:
    return {"key": "k1", "type": "integer", "label": L, **overrides}


# --- schema meta-validation ------------------------------------------------------------


def test_contract_example_is_valid() -> None:
    fields = parse_schema(GENERATORS)
    assert [f.key for f in fields] == ["power_kva", "fuel_type"]


def test_all_types_valid() -> None:
    assert len(parse_schema(ALL_TYPES)) == 6


@pytest.mark.parametrize(
    ("bad", "reason"),
    [
        ([field(key="Bad-Key")], "key"),
        ([field(key="a")], "key"),  # too short: ^[a-z][a-z0-9_]{1,39}$
        ([field(), field()], "duplicate"),
        ([field(type="date")], "type"),
        ([field(label={"sw": "Lebo"})], "label"),
        ([field(label={"sw": "Lebo", "en": ""})], "label"),
        ([field(help={"en": "only english"})], "help"),
        ([field(min=5, max=1)], "min"),
        ([field(type="text", min=1)], "min"),
        ([field(type="enum")], "options"),
        ([field(type="enum", options=[{"value": "a", "label": {"sw": "A"}}])], "label"),
        (
            [field(type="enum", options=[{"value": "a", "label": L}, {"value": "a", "label": L}])],
            "duplicate",
        ),
        ([field(type="integer", options=[{"value": "a", "label": L}])], "options"),
        ([field(type="text", max_length=600)], "max_length"),
        ([field(type="integer", max_length=10)], "max_length"),
        ([field(type="decimal", filter="exact")], "filter"),
        ([field(type="boolean", filter="range")], "filter"),
        (
            [field(type="multi_enum", filter="exact", options=[{"value": "a", "label": L}])],
            "filter",
        ),
        ([field(type="text", filter="exact")], "filter"),
        ([field(type="enum", filter="range", options=[{"value": "a", "label": L}])], "filter"),
        ([field(surprise=True)], "surprise"),
    ],
)
def test_invalid_schemas_rejected(bad: list[dict[str, Any]], reason: str) -> None:
    with pytest.raises(SchemaError) as exc:
        parse_schema(bad)
    assert reason in str(exc.value).lower()


def test_schema_must_be_a_list() -> None:
    with pytest.raises(SchemaError):
        parse_schema({"key": "x"})  # type: ignore[arg-type]


# --- listing value validation ------------------------------------------------------------

CAT = uuid.uuid4()


def check(values: dict[str, Any], schema: list[dict[str, Any]] = ALL_TYPES) -> dict[str, Any]:
    return validate_values(CAT, 1, schema, values)


def errors(values: dict[str, Any], schema: list[dict[str, Any]] = ALL_TYPES) -> dict[str, str]:
    with pytest.raises(ValuesError) as exc:
        check(values, schema)
    return exc.value.fields


def test_valid_values_pass_and_optional_omitted() -> None:
    out = check({"bedrooms": 3, "furnished": True, "amenities": ["wifi"], "vehicle_type": "suv"})
    assert out == {"bedrooms": 3, "furnished": True, "amenities": ["wifi"], "vehicle_type": "suv"}


def test_decimal_accepts_int_and_float() -> None:
    assert check({"bedrooms": 1, "area_m2": 12})["area_m2"] == 12
    assert check({"bedrooms": 1, "area_m2": 12.5})["area_m2"] == 12.5
    out = validate_values(uuid.uuid4(), 1, GENERATORS, {"power_kva": 7.5, "fuel_type": "diesel"})
    assert out["power_kva"] == 7.5


def test_required_missing() -> None:
    assert "bedrooms" in errors({})


def test_unknown_key_rejected() -> None:
    assert "colour" in errors({"bedrooms": 1, "colour": "red"})


@pytest.mark.parametrize(
    ("values", "key"),
    [
        ({"bedrooms": 51}, "bedrooms"),  # > max
        ({"bedrooms": -1}, "bedrooms"),  # < min
        ({"bedrooms": 2.5}, "bedrooms"),  # not an int
        ({"bedrooms": "3"}, "bedrooms"),  # strings are not coerced
        ({"bedrooms": True}, "bedrooms"),  # bool is not an int
        ({"bedrooms": 1, "area_m2": 0.5}, "area_m2"),
        ({"bedrooms": 1, "area_m2": "big"}, "area_m2"),
        ({"bedrooms": 1, "furnished": "yes"}, "furnished"),
        ({"bedrooms": 1, "vehicle_type": "tank"}, "vehicle_type"),
        ({"bedrooms": 1, "amenities": ["wifi", "pool"]}, "amenities"),
        ({"bedrooms": 1, "amenities": "wifi"}, "amenities"),
        ({"bedrooms": 1, "amenities": ["wifi", "wifi"]}, "amenities"),
        ({"bedrooms": 1, "notes": "x" * 21}, "notes"),
        ({"bedrooms": 1, "notes": 5}, "notes"),
    ],
)
def test_invalid_values(values: dict[str, Any], key: str) -> None:
    assert key in errors(values)


def test_null_for_optional_field_is_dropped() -> None:
    assert check({"bedrooms": 1, "notes": None}) == {"bedrooms": 1}


def test_value_model_cache_follows_schema_version() -> None:
    schema = copy.deepcopy(GENERATORS)
    cat = uuid.uuid4()
    assert validate_values(cat, 1, schema, {"power_kva": 5, "fuel_type": "diesel"})
    schema[1]["options"].append({"value": "gas", "label": L})
    # Same version → cached model still rejects the new option…
    with pytest.raises(ValuesError):
        validate_values(cat, 1, schema, {"power_kva": 5, "fuel_type": "gas"})
    # …a bumped version picks up the edit.
    assert validate_values(cat, 2, schema, {"power_kva": 5, "fuel_type": "gas"})
