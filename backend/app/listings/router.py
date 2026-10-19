"""Public listing endpoints: detail, availability and quotes (US1)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.availability.periods import IsoDate
from app.availability.schemas import Availability
from app.core.deps import Session
from app.core.i18n import Locale, get_locale
from app.listings import service
from app.listings.schemas import ListingDetail, QuoteRequest
from app.pricing.schemas import Quote

router = APIRouter(tags=["listings"])

LocaleDep = Annotated[Locale, Depends(get_locale)]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Unknown or non-public listing"}}


@router.get("/listings/{listing_id}", response_model=ListingDetail, responses=NOT_FOUND)
async def get_listing(listing_id: uuid.UUID, session: Session, locale: LocaleDep) -> ListingDetail:
    return await service.detail(session, listing_id, locale)


@router.get(
    "/listings/{listing_id}/availability",
    response_model=Availability,
    responses={**NOT_FOUND, 400: {"description": "Window longer than 366 days or reversed"}},
)
async def get_availability(
    listing_id: uuid.UUID,
    session: Session,
    from_: Annotated[IsoDate | None, Query(alias="from")] = None,
    to: IsoDate | None = None,
) -> Availability:
    """DATE_RANGE/LEASE: unavailable date ranges; TIME_SLOT: free slots per day;
    QUANTITY: units available per day. Defaults to the next 60 days."""
    return await service.listing_availability(session, listing_id, from_, to)


@router.post(
    "/listings/{listing_id}/quote",
    response_model=Quote,
    responses={
        **NOT_FOUND,
        400: {"description": "Invalid period or duration"},
        409: {"description": "`SLOT_TAKEN`, `INSUFFICIENT_STOCK` or `PRICE_UNAVAILABLE`"},
    },
)
async def quote_listing(listing_id: uuid.UUID, body: QuoteRequest, session: Session) -> Quote:
    return await service.quote_listing(session, listing_id, body)
