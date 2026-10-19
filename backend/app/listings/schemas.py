"""Public listing shapes (contracts/rest-api.md "Search & listing detail").

Localized fields (`title`, `description`, labels) follow `Accept-Language`, falling back to
the other language. Owner phone and exact address are never part of these responses.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.availability.periods import PeriodParams
from app.catalog.schemas import BookingModeT
from app.pricing.schemas import UnitT


class Page[T](BaseModel):
    items: list[T]
    page: int
    page_size: int
    total: int


class CategoryRef(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class LocationRef(BaseModel):
    region: str
    district: str


class Photo(BaseModel):
    url_320: str
    url_640: str
    alt: str


class DetailPhoto(Photo):
    url_1280: str


class BasePrice(BaseModel):
    unit: UnitT
    amount_tzs: int


class Highlight(BaseModel):
    """A `show_on_card` attribute, already formatted for display."""

    key: str
    label: str
    value: str


class ListingSummary(BaseModel):
    id: uuid.UUID
    title: str
    category: CategoryRef
    location: LocationRef
    cover_photo: Photo | None
    base_price: BasePrice | None
    rating_avg: float | None
    rating_count: int
    instant_book: bool
    lat: float | None
    lng: float | None
    booking_mode: BookingModeT
    highlights: list[Highlight]


class ListingCard(ListingSummary):
    """`total_tzs` is the full price for the searched period, when one was given."""

    total_tzs: int | None


class AttributeOut(BaseModel):
    key: str
    label: str
    value: Any
    display: str
    unit: str | None
    group: str | None


class PriceOut(BaseModel):
    unit: UnitT
    amount_tzs: int
    season_start: date | None
    season_end: date | None


class OwnerOut(BaseModel):
    display_name: str
    rating_avg: float | None
    rating_count: int
    verified: bool


class ReviewOut(BaseModel):
    rating: int
    comment: str | None
    author: str
    created_at: datetime


class ListingDetail(ListingSummary):
    description: str
    photos: list[DetailPhoto]
    attributes: list[AttributeOut]
    prices: list[PriceOut]
    default_unit: UnitT
    deposit_tzs: int
    delivery: Literal["none", "optional", "required"]
    delivery_fee_tzs: int | None
    delivery_area: list[int] | None
    min_duration: int | None
    max_duration: int | None
    slot_config: dict[str, Any] | None
    stock: int
    cancellation_policy: Literal["flexible", "moderate", "strict"]
    owner: OwnerOut
    reviews: list[ReviewOut]


class QuoteRequest(PeriodParams):
    delivery: bool = False
    delivery_district_id: Annotated[int, Field(ge=1, le=2_147_483_647)] | None = None
