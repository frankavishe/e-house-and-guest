"""Dev-only mock payment controls (contracts/providers.md). Mounted only when `ENV` is `dev`
or `test`, and never part of the public OpenAPI client."""

import uuid
from typing import Literal

from fastapi import APIRouter

from app.bookings.schemas import PaymentOut
from app.bookings.service import payment_out
from app.core.deps import Session
from app.core.errors import AppError, not_found
from app.integrations import get_payment_provider
from app.integrations.payments.base import PaymentStatus
from app.integrations.payments.mock import MockPaymentProvider
from app.payments import service
from app.payments.models import Payment

router = APIRouter(tags=["dev"], include_in_schema=False)


@router.post("/dev/mock-payments/{payment_id}/{outcome}", response_model=PaymentOut)
async def settle_mock_payment(
    payment_id: uuid.UUID, outcome: Literal["succeed", "fail"], session: Session
) -> PaymentOut:
    """Settle a pending mock payment now, as if the provider had called back."""
    provider = get_payment_provider()
    if not isinstance(provider, MockPaymentProvider):
        raise AppError("CONFLICT", 409, message="The mock payment provider is not active.")
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise not_found("payment")
    state: Literal["succeeded", "failed"] = "succeeded" if outcome == "succeed" else "failed"
    reason = None if state == "succeeded" else "declined"
    provider.force(payment.id, state, reason)
    await service.apply_status(
        session, provider, payment.id, PaymentStatus(state=state, failure_reason=reason)
    )
    await session.commit()
    await session.refresh(payment)
    return payment_out(payment)
