"""Admin moderation shapes (contracts/rest-api.md "Admin")."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.bookings.schemas import BookingStatusT, ClaimOut, ClaimResolutionT, PeriodOut


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
