"""Booking endpoints (contracts/rest-api.md "Bookings")."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, status

from app.bookings import service
from app.bookings.models import BookingStatus
from app.bookings.schemas import (
    BookingCreate,
    BookingOut,
    BookingStatusT,
    BookingSummary,
    DeclineBody,
    Receipt,
)
from app.core import idempotency
from app.core.deps import CurrentUser, Owner, Session
from app.core.i18n import Locale, get_locale
from app.listings.schemas import Page

router = APIRouter(tags=["bookings"])

LocaleDep = Annotated[Locale, Depends(get_locale)]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Unknown booking"}}
TRANSITION: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND,
    403: {"description": "Not the owner of this listing"},
    409: {"description": "`INVALID_TRANSITION`"},
}


@router.post(
    "/bookings",
    response_model=BookingOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid period or duration"},
        404: {"description": "Unknown or non-public listing"},
        409: {"description": "`SLOT_TAKEN`, `INSUFFICIENT_STOCK` or `PRICE_UNAVAILABLE`"},
        422: {"description": "`OWN_LISTING`, delivery errors, `IDEMPOTENCY_KEY_REUSED`"},
    },
)
async def create_booking(
    request: Request,
    body: BookingCreate,
    user: CurrentUser,
    session: Session,
    locale: LocaleDep,
    idempotency_key: idempotency.IdempotencyHeader = None,
) -> Any:
    """Instant-book listings start in `awaiting_payment` (pay within 15 min); others in
    `requested` until the owner accepts (24 h). The dates are held either way."""

    async def action() -> BookingOut:
        booking = await service.create_booking(session, user, body)
        return await service.booking_out(session, booking, "renter", locale)

    return await idempotency.run(
        session,
        user_id=user.id,
        key=idempotency_key,
        method="POST",
        path=request.url.path,
        body=body,
        status=status.HTTP_201_CREATED,
        action=action,
    )


@router.get("/bookings", response_model=Page[BookingSummary])
async def list_bookings(
    user: CurrentUser,
    session: Session,
    locale: LocaleDep,
    role: Literal["renter", "owner"] = "renter",
    status_: Annotated[BookingStatusT | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[BookingSummary]:
    """The signed-in user's bookings as renter, or on their listings as owner; newest first."""
    return await service.list_bookings(
        session,
        user,
        role,
        BookingStatus(status_) if status_ else None,
        page,
        page_size,
        locale,
    )


@router.get("/bookings/{booking_id}", response_model=BookingOut, responses=NOT_FOUND)
async def get_booking(
    booking_id: uuid.UUID, user: CurrentUser, session: Session, locale: LocaleDep
) -> BookingOut:
    """For the renter, the listing owner or an admin. Phones are shown once confirmed."""
    booking, role = await service.get_for_party(session, user, booking_id)
    return await service.booking_out(session, booking, role, locale)


@router.post("/bookings/{booking_id}/accept", response_model=BookingOut, responses=TRANSITION)
async def accept_booking(
    booking_id: uuid.UUID, owner: Owner, user: CurrentUser, session: Session, locale: LocaleDep
) -> BookingOut:
    """`requested → awaiting_payment`; the renter has 24 h to pay."""
    booking = await service.accept(session, owner, user, booking_id)
    out = await service.booking_out(session, booking, "owner", locale)
    await session.commit()
    return out


@router.post("/bookings/{booking_id}/decline", response_model=BookingOut, responses=TRANSITION)
async def decline_booking(
    booking_id: uuid.UUID,
    owner: Owner,
    user: CurrentUser,
    session: Session,
    locale: LocaleDep,
    body: DeclineBody | None = None,
) -> BookingOut:
    """`requested → cancelled`; the held dates are released."""
    booking = await service.decline(
        session, owner, user, booking_id, body.reason if body else None
    )
    out = await service.booking_out(session, booking, "owner", locale)
    await session.commit()
    return out


@router.get(
    "/bookings/{booking_id}/receipt",
    response_model=Receipt,
    responses={**NOT_FOUND, 409: {"description": "`BOOKING_NOT_PAID`"}},
)
async def get_receipt(
    booking_id: uuid.UUID, user: CurrentUser, session: Session, locale: LocaleDep
) -> Receipt:
    return await service.receipt(session, user, booking_id, locale)
