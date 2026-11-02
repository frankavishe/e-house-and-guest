"""Payment request shapes (contracts/rest-api.md "Payments")."""

import uuid
from typing import Literal

from pydantic import BaseModel, field_validator

from app.core.errors import AppError
from app.core.security import normalize_phone

NetworkT = Literal["mpesa", "mixx", "airtel", "halopesa", "azampesa"]


class PaymentCreate(BaseModel):
    """`msisdn` is the paying number; it may differ from the login phone."""

    network: NetworkT
    msisdn: str
    installment_id: uuid.UUID | None = None

    @field_validator("msisdn")
    @classmethod
    def _phone(cls, value: str) -> str:
        try:
            return normalize_phone(value)
        except AppError as exc:
            raise ValueError("expected a Tanzanian mobile number") from exc


class WebhookAck(BaseModel):
    ok: bool
