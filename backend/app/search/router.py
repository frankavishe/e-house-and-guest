"""`GET /listings/search` (public). Registered before the listings router so the path is
not taken for a listing id."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import Session
from app.core.i18n import Locale, get_locale
from app.listings.schemas import ListingCard, Page
from app.search import service
from app.search.schemas import SearchParams

router = APIRouter(tags=["search"])

LocaleDep = Annotated[Locale, Depends(get_locale)]


@router.get(
    "/listings/search",
    response_model=Page[ListingCard],
    responses={
        400: {"description": "Invalid period (`INVALID_PERIOD`)"},
        404: {"description": "Unknown category"},
    },
)
async def search_listings(
    request: Request,
    params: Annotated[SearchParams, Query()],
    session: Session,
    locale: LocaleDep,
) -> Page[ListingCard]:
    """Public listings. Period fields (as `PeriodInput`) filter by availability and add
    `total_tzs`. Category attributes filter with `attr.<key>=value`, `attr.<key>=a,b`
    (any of) or `attr.<key>.min=` / `.max=` (ranges); unknown keys → 422."""
    return await service.search(session, params, request.query_params.multi_items(), locale)
