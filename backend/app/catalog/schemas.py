"""Public catalogue responses (contracts/rest-api.md "Catalogue")."""

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

BookingModeT = Literal["DATE_RANGE", "TIME_SLOT", "LEASE", "QUANTITY"]


class LocalizedText(BaseModel):
    sw: str
    en: str


class CategoryNode(BaseModel):
    id: uuid.UUID
    slug: str
    name: LocalizedText
    booking_mode: BookingModeT | None
    price_units: list[str]
    default_unit: str | None
    children: list["CategoryNode"] = Field(default_factory=list)


class CategoryDetail(BaseModel):
    id: uuid.UUID
    slug: str
    path: str
    parent_slug: str | None
    name: LocalizedText
    booking_mode: BookingModeT | None
    price_units: list[str]
    default_unit: str | None
    is_leaf: bool
    schema_version: int
    attribute_schema: list[dict[str, Any]]
    children: list["CategoryNode"] = Field(default_factory=list)


class LocationOut(BaseModel):
    id: int
    parent_id: int | None
    level: Literal["region", "district", "ward"]
    name: str
    slug: str
    lat: float | None
    lng: float | None
