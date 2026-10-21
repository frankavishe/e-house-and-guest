"""Booking shapes (contracts/rest-api.md "Bookings" and "Payments")."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.availability.periods import PeriodParams
from app.listings.schemas import ListingCard
from app.pricing.schemas import Quote

BookingStatusT = Literal[
    "requested",
    "awaiting_payment",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled",
    "disputed",
]
RoleT = Literal["renter", "owner", "admin"]


class BookingCreate(BaseModel):
    listing_id: uuid.UUID
    period: PeriodParams
    delivery: bool = False
    delivery_district_id: Annotated[int, Field(ge=1, le=2_147_483_647)] | None = None
    delivery_address: Annotated[str, Field(max_length=500)] | None = None
    message: Annotated[str, Field(max_length=1000)] | None = None


class DeclineBody(BaseModel):
    reason: Annotated[str, Field(max_length=500)] | None = None


class CancelBody(BaseModel):
    reason: Annotated[str, Field(max_length=500)] | None = None


class CancelPreviewOut(BaseModel):
    """What cancelling now would refund (FR-026). `deadline`: when the refund next drops."""

    policy: Literal["flexible", "moderate", "strict"]
    cancelled_by: Literal["renter", "owner", "admin"]
    percent: int
    paid_tzs: int
    rental_refund_tzs: int
    delivery_refund_tzs: int
    service_fee_refund_tzs: int
    deposit_refund_tzs: int
    refund_tzs: int
    deadline: datetime | None


ClaimKindT = Literal["damage", "dispute"]
ClaimResolutionT = Literal["owner_awarded", "renter_refunded", "split"]


class ClaimIn(BaseModel):
    """A damage claim (owner only, until 48 h after the end) or a dispute (either party).
    `evidence_keys` come from `POST /bookings/{id}/claims/evidence-upload`."""

    kind: ClaimKindT
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    amount_claimed_tzs: Annotated[int, Field(ge=0, le=1_000_000_000)] | None = None
    evidence_keys: Annotated[list[Annotated[str, Field(max_length=300)]], Field(max_length=10)] = []


class ClaimOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    kind: ClaimKindT
    opened_by: Literal["renter", "owner", "admin"]
    description: str
    amount_claimed_tzs: int | None
    evidence_keys: list[str]
    status: Literal["open", "resolved"]
    resolution: ClaimResolutionT | None
    amount_awarded_tzs: int | None
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class RefundOut(BaseModel):
    id: uuid.UUID
    amount_tzs: int
    reason: Literal["cancellation", "deposit_return", "owner_cancel", "admin", "late_payment"]
    status: Literal["pending", "sent", "failed"]
    provider_ref: str | None
    failure_reason: str | None
    created_at: datetime


class PeriodOut(BaseModel):
    start: datetime
    end: datetime


class Can(BaseModel):
    """What the viewer may do now; clients show actions from these flags only."""

    pay: bool
    cancel: bool
    accept: bool
    decline: bool
    review: bool
    claim: bool


class Counterpart(BaseModel):
    """The other party. `phone` only once the booking is confirmed (R18)."""

    name: str
    phone: str | None


class EventOut(BaseModel):
    from_status: BookingStatusT | None
    to_status: BookingStatusT
    actor_kind: Literal["user", "system", "provider"]
    created_at: datetime


class PaymentOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    installment_id: uuid.UUID | None
    status: Literal["pending", "succeeded", "failed", "expired"]
    network: Literal["mpesa", "mixx", "airtel", "halopesa", "azampesa"]
    msisdn: str
    amount_tzs: int
    failure_reason: str | None
    created_at: datetime
    confirmed_at: datetime | None


class InstallmentOut(BaseModel):
    id: uuid.UUID
    seq: int
    period: PeriodOut
    amount_tzs: int
    due_at: datetime
    status: Literal["pending", "paid", "overdue", "waived"]
    payable: bool


class BookingOut(BaseModel):
    id: uuid.UUID
    code: str
    status: BookingStatusT
    role: RoleT
    listing: ListingCard
    period: PeriodOut
    quantity: int
    quote: Quote
    amount_due_tzs: int
    payment_due_at: datetime | None
    request_expires_at: datetime | None
    cancellation_policy: Literal["flexible", "moderate", "strict"]
    delivery_requested: bool
    delivery_address: str | None
    lease_months: int | None
    can: Can
    counterpart: Counterpart
    events: list[EventOut]
    payments: list[PaymentOut]
    installments: list[InstallmentOut] | None
    refunds: list[RefundOut]
    claims: list[ClaimOut]
    cancelled_by: Literal["renter", "owner", "admin", "system"] | None
    cancel_reason: str | None
    created_at: datetime


class BookingSummary(BaseModel):
    id: uuid.UUID
    code: str
    status: BookingStatusT
    role: RoleT
    listing: ListingCard
    period: PeriodOut
    quantity: int
    total_tzs: int
    payment_due_at: datetime | None
    request_expires_at: datetime | None
    created_at: datetime


class ReceiptPayment(BaseModel):
    id: uuid.UUID
    network: str
    provider_txn_id: str | None
    amount_tzs: int
    confirmed_at: datetime | None


class Receipt(BaseModel):
    code: str
    status: BookingStatusT
    listing_title: str
    owner_name: str
    renter_name: str
    period: PeriodOut
    quantity: int
    quote: Quote
    total_tzs: int
    paid_tzs: int
    payments: list[ReceiptPayment]
    issued_at: datetime
