"""Auth and profile request/response models (contracts/rest-api.md "Auth & profile")."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Role = Literal["renter", "owner", "admin"]

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class OwnerProfileSummary(BaseModel):
    id: uuid.UUID
    kind: Literal["individual", "business"]
    display_name: str
    verification_status: Literal["draft", "pending", "verified", "rejected"]


class UserOut(BaseModel):
    id: uuid.UUID
    phone: str
    name: str | None
    email: str | None
    language: Literal["sw", "en"]
    roles: list[Role]
    owner_profile: OwnerProfileSummary | None


class OtpRequestIn(BaseModel):
    phone: Annotated[str, Field(min_length=1, max_length=32, examples=["0712345678"])]


class OtpRequestOut(BaseModel):
    expires_in: int


class OtpVerifyIn(BaseModel):
    phone: Annotated[str, Field(min_length=1, max_length=32)]
    code: Annotated[str, Field(min_length=1, max_length=10, examples=["123456"])]


class OtpVerifyOut(BaseModel):
    user: UserOut
    is_new: bool


class MePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    email: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, max_length=254, pattern=EMAIL_PATTERN)
        ]
        | None
    ) = None
    language: Literal["sw", "en"] | None = None
