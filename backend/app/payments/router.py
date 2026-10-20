"""Payment endpoints (contracts/rest-api.md "Payments") and the provider webhook."""

import hmac
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request, status

from app.bookings.schemas import PaymentOut
from app.bookings.service import payment_out
from app.core import idempotency
from app.core.config import get_settings
from app.core.deps import CurrentUser, Session
from app.core.errors import AppError, not_found
from app.integrations import get_payment_provider
from app.integrations.payments.base import InvalidCallback
from app.payments import service
from app.payments.schemas import PaymentCreate, WebhookAck

log = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])
webhook_router = APIRouter(tags=["webhooks"], include_in_schema=False)


@router.post(
    "/bookings/{booking_id}/payments",
    response_model=PaymentOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        403: {"description": "Only the renter pays"},
        404: {"description": "Unknown booking or installment"},
        409: {
            "description": "`INVALID_TRANSITION` (not awaiting payment), `PAYMENT_PENDING` or "
            "`INSTALLMENT_NOT_DUE`"
        },
    },
)
async def start_payment(
    request: Request,
    booking_id: uuid.UUID,
    body: PaymentCreate,
    user: CurrentUser,
    session: Session,
    idempotency_key: idempotency.IdempotencyHeader = None,
) -> Any:
    """Sends a USSD push to `msisdn`. Poll `GET /payments/{id}` (every 3 s) for the result."""

    async def action() -> PaymentOut:
        return payment_out(await service.start_payment(session, user, booking_id, body))

    return await idempotency.run(
        session,
        user_id=user.id,
        key=idempotency_key,
        method="POST",
        path=request.url.path,
        body=body,
        status=status.HTTP_202_ACCEPTED,
        action=action,
    )


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentOut,
    responses={404: {"description": "Unknown payment"}},
)
async def get_payment(payment_id: uuid.UUID, user: CurrentUser, session: Session) -> PaymentOut:
    """A payment pending for more than 60 s is re-checked with the provider first."""
    return payment_out(await service.get_payment(session, user, payment_id))


@webhook_router.post("/webhooks/payments/{provider_name}/{secret}", response_model=WebhookAck)
async def payment_webhook(
    provider_name: str, secret: str, request: Request, session: Session
) -> WebhookAck:
    """Provider callback (R6): wrong secret → 404, failed authentication → 401, else 200
    once stored. Processing re-queries the provider before changing anything."""
    expected = get_settings().payment_callback_secret
    provider = get_payment_provider()
    if not hmac.compare_digest(secret, expected) or provider_name != provider.name:
        raise not_found()
    try:
        await service.handle_callback(session, provider, request.headers, await request.body())
    except InvalidCallback as exc:
        log.warning("rejected %s payment callback: %s", provider_name, exc)
        raise AppError("UNAUTHENTICATED", 401) from exc
    await session.commit()
    return WebhookAck(ok=True)
