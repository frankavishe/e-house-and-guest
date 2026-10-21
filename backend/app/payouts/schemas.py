"""Earnings and payout shapes (contracts/rest-api.md "Earnings & payouts", US4)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.accounts.schemas import PayoutMethodOut
from app.bookings.schemas import PeriodOut

EarningStatus = Literal["upcoming", "available", "pending", "processing", "paid", "failed"]
PayoutStatusName = Literal["pending", "processing", "paid", "failed"]


class EarningsTotals(BaseModel):
    gross_tzs: int
    commission_tzs: int
    net_tzs: int
    paid_out_tzs: int
    pending_tzs: int


class EarningItem(BaseModel):
    """One booking. `upcoming`: not yet payable (not completed, or completed < 24 h ago);
    `available`: waiting for the next payout run; otherwise its payout's status."""

    booking_id: uuid.UUID
    booking_code: str
    listing_id: uuid.UUID
    listing_title: str
    period: PeriodOut
    completed_at: datetime | None
    gross_tzs: int
    commission_tzs: int
    net_tzs: int
    status: EarningStatus
    payout_id: uuid.UUID | None


class Earnings(BaseModel):
    totals: EarningsTotals
    items: list[EarningItem]


class PayoutItemOut(BaseModel):
    booking_id: uuid.UUID
    booking_code: str
    amount_tzs: int


class PayoutOut(BaseModel):
    id: uuid.UUID
    amount_tzs: int
    status: PayoutStatusName
    provider: str | None
    provider_ref: str | None
    failure_reason: str | None
    # Masked snapshot of the payout method used at the last send attempt.
    destination: PayoutMethodOut | None
    paid_at: datetime | None
    created_at: datetime
    items: list[PayoutItemOut]


class PayoutOwner(BaseModel):
    id: uuid.UUID
    display_name: str
    phone: str


class AdminPayoutOut(PayoutOut):
    owner: PayoutOwner
    attempts: int


class MarkPaid(BaseModel):
    provider_ref: str = Field(min_length=1, max_length=100)

    @field_validator("provider_ref")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("provider_ref must not be blank")
        return value
