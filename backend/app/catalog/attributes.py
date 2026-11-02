"""Category attribute schemas (R3, contracts/attribute-schema.md).

`parse_schema` validates the schema an admin saves. `validate_values` checks a listing's
`attributes` against it with a Pydantic model built from the schema and cached per
`(category_id, schema_version)`, so a new rental type never needs code (Principle I).
"""

import re
import uuid
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
    create_model,
    field_validator,
    model_validator,
)

FieldType = Literal["integer", "decimal", "boolean", "enum", "multi_enum", "text"]
FilterType = Literal["none", "exact", "range", "any_of"]

KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
TEXT_MAX_LENGTH = 500

ALLOWED_FILTERS: dict[str, set[str]] = {
    "integer": {"none", "exact", "range"},
    "decimal": {"none", "range"},
    "boolean": {"none", "exact"},
    "enum": {"none", "exact", "any_of"},
    "multi_enum": {"none", "any_of"},
    "text": {"none"},
}
NUMERIC = {"integer", "decimal"}
CHOICE = {"enum", "multi_enum"}


class SchemaError(ValueError):
    """The attribute schema itself is invalid (admin save → 422)."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


class ValuesError(ValueError):
    """Listing attribute values do not match the schema. `fields` maps key → message."""

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__(", ".join(f"{k}: {v}" for k, v in fields.items()))
        self.fields = fields


class Localized(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sw: Annotated[str, Field(min_length=1, max_length=200)]
    en: Annotated[str, Field(min_length=1, max_length=200)]

    @field_validator("sw", "en")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("label must not be blank")
        return value


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.\-+]+$")]
    label: Localized


class FieldDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    type: FieldType
    label: Localized
    help: Localized | None = None
    unit: Localized | None = None
    required: bool = False
    min: float | None = None
    max: float | None = None
    options: list[Option] | None = None
    max_length: int | None = None
    filter: FilterType = "none"
    show_on_card: bool = False
    group: Localized | None = None
    order: int = 0

    @field_validator("key")
    @classmethod
    def key_format(cls, value: str) -> str:
        if not KEY_PATTERN.match(value):
            raise ValueError("key must match ^[a-z][a-z0-9_]{1,39}$")
        return value

    @model_validator(mode="after")
    def type_rules(self) -> "FieldDef":
        if self.type not in NUMERIC and (self.min is not None or self.max is not None):
            raise ValueError("min/max are allowed only for integer and decimal")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min must be ≤ max")
        if self.type in CHOICE:
            if not self.options:
                raise ValueError("options are required for enum and multi_enum")
            values = [o.value for o in self.options]
            if len(values) != len(set(values)):
                raise ValueError("duplicate option value")
        elif self.options is not None:
            raise ValueError("options are allowed only for enum and multi_enum")
        if self.max_length is not None:
            if self.type != "text":
                raise ValueError("max_length is allowed only for text")
            if not 1 <= self.max_length <= TEXT_MAX_LENGTH:
                raise ValueError(f"max_length must be between 1 and {TEXT_MAX_LENGTH}")
        if self.filter not in ALLOWED_FILTERS[self.type]:
            raise ValueError(f"filter {self.filter!r} is not allowed for type {self.type!r}")
        return self

    @property
    def option_values(self) -> list[str]:
        return [o.value for o in self.options or []]


def _describe(err: ValidationError, index: int | None = None) -> list[str]:
    out = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"])
        prefix = f"field[{index}]" if index is not None else "schema"
        out.append(f"{prefix}{'.' + loc if loc else ''}: {e['msg']}")
    return out


def parse_schema(raw: Sequence[dict[str, Any]]) -> list[FieldDef]:
    """Validate an attribute schema. Raises SchemaError listing every problem."""
    if not isinstance(raw, list):
        raise SchemaError(["schema must be a list of field definitions"])
    fields: list[FieldDef] = []
    problems: list[str] = []
    for i, item in enumerate(raw):
        try:
            fields.append(FieldDef.model_validate(item))
        except ValidationError as err:
            problems.extend(_describe(err, i))
    seen: set[str] = set()
    for f in fields:
        if f.key in seen:
            problems.append(f"duplicate key {f.key!r}")
        seen.add(f.key)
    if problems:
        raise SchemaError(problems)
    return sorted(fields, key=lambda f: f.order)


# --- values ------------------------------------------------------------------------------


def _unique(values: list[str]) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError("values must be unique")
    return values


def _annotation(f: FieldDef) -> Any:
    bounds: dict[str, Any] = {}
    if f.min is not None:
        bounds["ge"] = f.min
    if f.max is not None:
        bounds["le"] = f.max
    match f.type:
        case "integer":
            return Annotated[StrictInt, Field(**bounds)]
        case "decimal":
            return Annotated[StrictInt | StrictFloat, Field(**bounds)]
        case "boolean":
            return StrictBool
        case "enum":
            return Literal[tuple(f.option_values)]
        case "multi_enum":
            return Annotated[
                list[Literal[tuple(f.option_values)]],  # type: ignore[misc]
                Field(min_length=1),
            ]
        case "text":
            return Annotated[StrictStr, Field(max_length=f.max_length or TEXT_MAX_LENGTH)]
    raise AssertionError(f.type)


class _ValuesBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


# Built models keyed by (category_id, schema_version). Every schema edit bumps the
# version (T135), so a cached model is never stale.
_MODELS: dict[tuple[uuid.UUID, int], type[BaseModel]] = {}
_MODEL_CACHE_MAX = 1024


def _build_model(name: str, schema: Sequence[dict[str, Any]]) -> type[BaseModel]:
    definitions: dict[str, Any] = {}
    validators: dict[str, Any] = {}
    for f in parse_schema(schema):
        ann = _annotation(f)
        definitions[f.key] = (ann, ...) if f.required else (ann | None, None)
        if f.type == "multi_enum":
            validators[f"unique_{f.key}"] = field_validator(f.key)(
                classmethod(lambda cls, v: _unique(v) if v is not None else v)
            )
    return create_model(name, __base__=_ValuesBase, __validators__=validators, **definitions)


def value_model(
    category_id: uuid.UUID, schema_version: int, schema: Sequence[dict[str, Any]]
) -> type[BaseModel]:
    key = (category_id, schema_version)
    model = _MODELS.get(key)
    if model is None:
        if len(_MODELS) >= _MODEL_CACHE_MAX:
            _MODELS.clear()
        model = _build_model(f"Attributes_{category_id.hex}_{schema_version}", schema)
        _MODELS[key] = model
    return model


def validate_values(
    category_id: uuid.UUID,
    schema_version: int,
    schema: Sequence[dict[str, Any]],
    values: dict[str, Any],
) -> dict[str, Any]:
    """Validated attributes with None/omitted optional fields dropped. Raises ValuesError."""
    model = value_model(category_id, schema_version, schema)
    try:
        parsed = model.model_validate(values)
    except ValidationError as err:
        fields: dict[str, str] = {}
        for e in err.errors():
            key = str(e["loc"][0]) if e["loc"] else "_"
            fields.setdefault(key, "unknown field" if e["type"] == "extra_forbidden" else e["msg"])
        raise ValuesError(fields) from None
    return parsed.model_dump(exclude_none=True)
