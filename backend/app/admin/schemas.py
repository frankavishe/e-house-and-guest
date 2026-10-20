"""Admin moderation shapes (contracts/rest-api.md "Admin")."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


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
