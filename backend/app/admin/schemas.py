"""Admin moderation shapes (contracts/rest-api.md "Admin")."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.bookings.schemas import BookingStatusT, ClaimOut, ClaimResolutionT, PeriodOut
from app.catalog.attributes import Localized
from app.catalog.schemas import BookingModeT, LocalizedText

PriceUnitT = Literal["hour", "night", "day", "week", "month", "item_day"]
Bps = Annotated[int, Field(ge=0, le=10_000)]


class VerificationUser(BaseModel):
    id: uuid.UUID
    name: str | None
    phone: str


class DocumentLink(BaseModel):
    """`url` is a presigned GET valid for 5 minutes."""

    key: str
    url: str


class VerificationItem(BaseModel):
    """Admins see the full identity numbers to check them against NIDA/BRELA/TRA."""

    id: uuid.UUID
    user: VerificationUser
    kind: Literal["individual", "business"]
    display_name: str
    business_name: str | None
    brela_reg_no: str | None
    nida_number: str | None
    tin: str | None
    documents: list[DocumentLink]
    verification_status: Literal["draft", "pending", "verified", "rejected"]
    rejection_reason: str | None
    updated_at: datetime


class VerificationDecision(BaseModel):
    id: uuid.UUID
    verification_status: Literal["draft", "pending", "verified", "rejected"]
    rejection_reason: str | None


class AdminParty(BaseModel):
    id: uuid.UUID
    name: str
    phone: str


class AdminBookingSummary(BaseModel):
    id: uuid.UUID
    code: str
    status: BookingStatusT
    listing_id: uuid.UUID
    listing_title: str
    period: PeriodOut
    total_tzs: int
    renter: AdminParty
    owner: AdminParty
    open_claim: bool
    attention: bool
    """A future booking whose listing or one of whose parties is suspended (follow up)."""
    created_at: datetime


class AdminRefundIn(BaseModel):
    """A discretionary refund, taken from the owner's share or from platform revenue."""

    amount_tzs: Annotated[int, Field(ge=1, le=1_000_000_000)]
    source: Literal["owner", "platform"] = "platform"
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class MarkRefundSentIn(BaseModel):
    provider_ref: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]


class ResolveClaimIn(BaseModel):
    """`amount_awarded_tzs` is the part of the deposit the owner receives: the whole deposit
    when omitted for `owner_awarded`, 0 for `renter_refunded`, strictly between for `split`."""

    resolution: ClaimResolutionT
    amount_awarded_tzs: Annotated[int, Field(ge=0, le=1_000_000_000)] | None = None
    note: Annotated[str, Field(max_length=1000)] | None = None


class AdminClaimOut(ClaimOut):
    booking_code: str
    booking_status: BookingStatusT
    deposit_tzs: int
    renter: AdminParty
    owner: AdminParty
    evidence: list[DocumentLink]


# --- categories (US7-AS1) -----------------------------------------------------------------


class AdminCategoryIn(BaseModel):
    """A group (no `booking_mode`, no fields) or a leaf that holds listings. `slug`,
    `parent_id` and `booking_mode` are fixed once created."""

    parent_id: uuid.UUID | None = None
    slug: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{1,59}$")]
    name: Localized
    booking_mode: BookingModeT | None = None
    price_units: list[PriceUnitT] = Field(default_factory=list, max_length=6)
    default_unit: PriceUnitT | None = None
    attribute_schema: list[dict[str, Any]] = Field(default_factory=list, max_length=60)
    commission_bps: Bps = 1000
    renter_fee_bps: Bps = 0
    is_active: bool = True
    sort_order: Annotated[int, Field(ge=0, le=10_000)] = 0


class AdminCategoryPatch(BaseModel):
    """Only the fields sent change. A changed `attribute_schema` bumps `schema_version`;
    commission and fee changes apply to bookings made afterwards."""

    name: Localized | None = None
    price_units: list[PriceUnitT] | None = Field(default=None, max_length=6)
    default_unit: PriceUnitT | None = None
    attribute_schema: list[dict[str, Any]] | None = Field(default=None, max_length=60)
    commission_bps: Bps | None = None
    renter_fee_bps: Bps | None = None
    is_active: bool | None = None
    sort_order: Annotated[int, Field(ge=0, le=10_000)] | None = None


class AdminCategoryOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    path: str
    slug: str
    name: LocalizedText
    booking_mode: BookingModeT | None
    price_units: list[str]
    default_unit: str | None
    attribute_schema: list[dict[str, Any]]
    schema_version: int
    commission_bps: int
    renter_fee_bps: int
    is_active: bool
    sort_order: int
    is_leaf: bool
    listing_count: int
    updated_at: datetime


# --- users and abuse reports (FR-030) -----------------------------------------------------


class AdminOwnerBrief(BaseModel):
    id: uuid.UUID
    display_name: str
    verification_status: Literal["draft", "pending", "verified", "rejected"]


class AdminUserOut(BaseModel):
    id: uuid.UUID
    name: str | None
    phone: str
    email: str | None
    status: Literal["active", "suspended", "deleted"]
    is_admin: bool
    owner: AdminOwnerBrief | None
    created_at: datetime


class AdminReportOut(BaseModel):
    id: uuid.UUID
    target_kind: Literal["listing", "user"]
    target_id: uuid.UUID
    target_label: str
    """The listing title or the user's name (phone when unnamed)."""
    target_status: str
    """The target's current status, e.g. `active` or `suspended`."""
    reason: str
    status: Literal["open", "actioned", "dismissed"]
    reporter: AdminParty
    open_reports_on_target: int
    handled_at: datetime | None
    created_at: datetime


class ReportActionIn(BaseModel):
    """`actioned` closes every open report on the target; `suspend_target` also suspends the
    listing or user (the `note`, else the report's reason, is the suspension reason)."""

    decision: Literal["actioned", "dismissed"]
    suspend_target: bool = False
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


# --- stats (FR-032) -----------------------------------------------------------------------

StatsGroupT = Literal["month", "category", "region"]


class StatsRow(BaseModel):
    """Money moved in the period. `gbv_tzs` is rental + delivery + service fee paid (no
    deposits); `commission_tzs` is net platform revenue (commission and service fees, less
    what was handed back or refunded from it); `refunds_tzs` and `payouts_tzs` are money sent."""

    key: str
    label: str
    bookings: int
    gbv_tzs: int
    commission_tzs: int
    refunds_tzs: int
    payouts_tzs: int


class StatsOut(BaseModel):
    from_: date = Field(alias="from")
    to: date
    group_by: StatsGroupT
    rows: list[StatsRow]
    totals: StatsRow

    model_config = {"populate_by_name": True}
