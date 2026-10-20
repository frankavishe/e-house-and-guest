"""Auth and profile request/response models (contracts/rest-api.md "Auth & profile")."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.security import PHONE_INPUT_PATTERN

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


PhoneInput = Annotated[
    str,
    Field(
        max_length=32,
        pattern=PHONE_INPUT_PATTERN,
        description="Tanzanian mobile number: 0712345678, 712345678, 255712345678 or +255712345678",
        examples=["0712345678"],
    ),
]


class OtpRequestIn(BaseModel):
    phone: PhoneInput


class OtpRequestOut(BaseModel):
    expires_in: int


class OtpVerifyIn(BaseModel):
    phone: PhoneInput
    code: Annotated[str, Field(pattern=r"^[0-9]{6}$", examples=["123456"])]


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


# --- owner onboarding (US3) ---------------------------------------------------------------

OwnerKindT = Literal["individual", "business"]
VerificationT = Literal["draft", "pending", "verified", "rejected"]
NetworkT = Literal["mpesa", "mixx", "airtel", "halopesa", "azampesa"]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
IdNumber = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=40)]


class OwnerProfileCreate(BaseModel):
    """Individuals give their NIDA number; businesses their BRELA number and TIN."""

    kind: OwnerKindT
    display_name: ShortText
    nida_number: IdNumber | None = None
    business_name: ShortText | None = None
    brela_reg_no: IdNumber | None = None
    tin: IdNumber | None = None

    @model_validator(mode="after")
    def _identity(self) -> "OwnerProfileCreate":
        if self.kind == "individual" and not self.nida_number:
            raise ValueError("nida_number is required for individuals")
        if self.kind == "business" and not (self.business_name and self.brela_reg_no and self.tin):
            raise ValueError("business_name, brela_reg_no and tin are required for businesses")
        return self


class OwnerProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: ShortText | None = None
    nida_number: IdNumber | None = None
    business_name: ShortText | None = None
    brela_reg_no: IdNumber | None = None
    tin: IdNumber | None = None
    documents: (
        Annotated[list[Annotated[str, Field(max_length=300)]], Field(max_length=10)] | None
    ) = None


class OwnerProfileOut(BaseModel):
    """The owner's own view: identity numbers are masked (`****0123`), never returned."""

    id: uuid.UUID
    kind: OwnerKindT
    display_name: str
    business_name: str | None
    brela_reg_no: str | None
    nida_number_masked: str | None
    tin_masked: str | None
    documents: list[str]
    verification_status: VerificationT
    rejection_reason: str | None
    verified_at: datetime | None


class UploadIn(BaseModel):
    content_type: Annotated[str, Field(max_length=100)]


class UploadOut(BaseModel):
    """Presigned PUT: send the file to `upload_url` with `headers`."""

    upload_url: str
    storage_key: str
    headers: dict[str, str]


class PayoutMethodIn(BaseModel):
    kind: Literal["mobile_money", "bank"]
    network: NetworkT | None = None
    msisdn: PhoneInput | None = None
    bank_name: ShortText | None = None
    account_name: ShortText
    account_number: Annotated[str, StringConstraints(pattern=r"^[0-9A-Za-z-]{4,34}$")] | None = None
    is_default: bool = False

    @model_validator(mode="after")
    def _destination(self) -> "PayoutMethodIn":
        if self.kind == "mobile_money" and not (self.network and self.msisdn):
            raise ValueError("network and msisdn are required for mobile money")
        if self.kind == "bank" and not (self.bank_name and self.account_number):
            raise ValueError("bank_name and account_number are required for bank accounts")
        return self


class PayoutMethodOut(BaseModel):
    id: uuid.UUID
    kind: Literal["mobile_money", "bank"]
    network: NetworkT | None
    msisdn: str | None
    bank_name: str | None
    account_name: str
    account_number_masked: str | None
    is_default: bool
