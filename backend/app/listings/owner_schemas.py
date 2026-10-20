"""Owner listing management and moderation shapes (contracts/rest-api.md "Owner listing
management", "Admin")."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalog.schemas import BookingModeT

ListingStatusT = Literal[
    "draft", "pending_review", "active", "paused", "rejected", "suspended", "deleted"
]
ReviewStateT = Literal["none", "pending", "rejected"]
UnitT = Literal["hour", "night", "day", "week", "month", "item_day"]
LocationId = Annotated[int, Field(ge=1, le=2_147_483_647)]
Money = Annotated[int, Field(ge=0, le=10**12)]
Count = Annotated[int, Field(ge=1, le=10_000)]


class OwnerCategory(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    booking_mode: BookingModeT
    price_units: list[str]
    default_unit: str


class OwnerPhoto(BaseModel):
    """`pending` photos were added to a live listing and wait for review."""

    id: uuid.UUID
    url_320: str
    url_640: str
    url_1280: str
    position: int
    alt_sw: str | None
    alt_en: str | None
    pending: bool


class PriceRow(BaseModel):
    unit: UnitT
    amount_tzs: Annotated[int, Field(gt=0, le=10**12)]
    season_start: date | None = None
    season_end: date | None = None

    @model_validator(mode="after")
    def _season(self) -> "PriceRow":
        if (self.season_start is None) != (self.season_end is None):
            raise ValueError("season_start and season_end go together")
        if self.season_start and self.season_end and self.season_end < self.season_start:
            raise ValueError("season_end is before season_start")
        return self


class OwnerListingOut(BaseModel):
    """The owner's editable view: raw bilingual fields, live values and pending changes."""

    id: uuid.UUID
    status: ListingStatusT
    review_state: ReviewStateT
    rejection_reason: str | None
    pending_changes: dict[str, Any] | None
    category: OwnerCategory
    title_sw: str | None
    title_en: str | None
    description_sw: str | None
    description_en: str | None
    attributes: dict[str, Any]
    region_id: int | None
    district_id: int | None
    ward_id: int | None
    address_hint: str | None
    lat: float | None
    lng: float | None
    stock: int
    deposit_tzs: int
    delivery: Literal["none", "optional", "required"]
    delivery_fee_tzs: int | None
    delivery_area: list[int] | None
    min_duration: int | None
    max_duration: int | None
    slot_config: dict[str, Any] | None
    cancellation_policy: Literal["flexible", "moderate", "strict"]
    instant_book: bool
    prices: list[PriceRow]
    photos: list[OwnerPhoto]
    base_price_tzs: int | None
    missing: list[str] = Field(description="What still blocks submitting for review")
    created_at: datetime
    updated_at: datetime


class ListingCreate(BaseModel):
    category_id: uuid.UUID


class ListingPatch(BaseModel):
    """Any subset of the listing's fields. On a live listing, material fields (texts,
    attributes, location) wait in `pending_changes` for review; the rest apply at once."""

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    title_sw: Annotated[str, Field(max_length=120)] | None = None
    title_en: Annotated[str, Field(max_length=120)] | None = None
    description_sw: Annotated[str, Field(max_length=5000)] | None = None
    description_en: Annotated[str, Field(max_length=5000)] | None = None
    attributes: dict[str, Any] | None = None
    region_id: LocationId | None = None
    district_id: LocationId | None = None
    ward_id: LocationId | None = None
    address_hint: Annotated[str, Field(max_length=300)] | None = None
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lng: Annotated[float, Field(ge=-180, le=180)] | None = None
    stock: Count | None = None
    deposit_tzs: Money | None = None
    delivery: Literal["none", "optional", "required"] | None = None
    delivery_fee_tzs: Money | None = None
    delivery_area: Annotated[list[LocationId], Field(max_length=200)] | None = None
    min_duration: Count | None = None
    max_duration: Count | None = None
    slot_config: dict[str, Any] | None = None
    cancellation_policy: Literal["flexible", "moderate", "strict"] | None = None
    instant_book: bool | None = None


class PhotoUploadIn(BaseModel):
    content_type: Annotated[str, Field(max_length=100)]


class PhotoUploadOut(BaseModel):
    photo_id: uuid.UUID
    upload_url: str
    storage_key: str
    headers: dict[str, str]


class PhotoPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool | None = None
    position: Annotated[int, Field(ge=0, le=100)] | None = None
    alt_sw: Annotated[str, Field(max_length=200)] | None = None
    alt_en: Annotated[str, Field(max_length=200)] | None = None


class BlockIn(BaseModel):
    """Inclusive EAT days `start_date..end_date`, or `start`/`end` times for time slots."""

    start_date: date | None = None
    end_date: date | None = None
    start: datetime | None = None
    end: datetime | None = None
    quantity: Count = 1
    note: Annotated[str, Field(max_length=200)] | None = None


class SpanOut(BaseModel):
    start: datetime
    end: datetime


class BlockOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    period: SpanOut
    quantity: int
    note: str | None


class CalendarListing(BaseModel):
    id: uuid.UUID
    title: str


class CalendarBooking(BaseModel):
    id: uuid.UUID
    code: str
    listing_id: uuid.UUID
    status: str
    period: SpanOut
    quantity: int
    renter_name: str


class Calendar(BaseModel):
    listings: list[CalendarListing]
    bookings: list[CalendarBooking]
    blocks: list[BlockOut]


class Reason(BaseModel):
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class OwnerBrief(BaseModel):
    id: uuid.UUID
    display_name: str
    verification_status: Literal["draft", "pending", "verified", "rejected"]


class AdminListingItem(BaseModel):
    """A listing in the review queue; `diff` shows pending changes vs the live values."""

    listing: OwnerListingOut
    owner: OwnerBrief
    diff: dict[str, dict[str, Any]] | None
