"""`/owner/listings*` and `/owner/calendar` (contracts/rest-api.md "Owner listing
management"). Every route is scoped to the signed-in owner's own listings."""

import uuid
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from app.core import clock
from app.core.deps import Owner, Session
from app.core.i18n import Locale, get_locale
from app.listings import blocks, manage, photos
from app.listings.owner_schemas import (
    BlockIn,
    BlockOut,
    Calendar,
    ListingCreate,
    ListingPatch,
    OwnerListingOut,
    OwnerPhoto,
    PhotoPatch,
    PhotoUploadIn,
    PhotoUploadOut,
    PriceRow,
)
from app.listings.schemas import Page

router = APIRouter(tags=["owner listings"])

LocaleDep = Annotated[Locale, Depends(get_locale)]
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "Not one of your listings"}}
TRANSITION: dict[int | str, dict[str, Any]] = {
    **NOT_FOUND,
    409: {"description": "`INVALID_TRANSITION`"},
}
DEFAULT_CALENDAR_DAYS = 60


@router.get("/owner/listings", response_model=Page[OwnerListingOut])
async def list_own_listings(
    profile: Owner,
    session: Session,
    locale: LocaleDep,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Page[OwnerListingOut]:
    """Own listings in any status except deleted, most recently edited first."""
    return await manage.owner_listings(session, profile, page, page_size, locale)


@router.post("/owner/listings", status_code=status.HTTP_201_CREATED, response_model=OwnerListingOut)
async def create_listing(
    body: ListingCreate, profile: Owner, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    """A draft in a leaf category; fill it in with PATCH, prices, photos, then submit."""
    listing, category = await manage.create(session, profile, body.category_id)
    out = await manage.listing_out(session, listing, category, locale)
    await session.commit()
    return out


@router.get("/owner/listings/{listing_id}", response_model=OwnerListingOut, responses=NOT_FOUND)
async def get_own_listing(
    listing_id: uuid.UUID, profile: Owner, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    listing, category = await manage.get_owned(session, profile, listing_id)
    return await manage.listing_out(session, listing, category, locale)


@router.patch(
    "/owner/listings/{listing_id}",
    response_model=OwnerListingOut,
    responses={**TRANSITION, 422: {"description": "`INVALID_ATTRIBUTES` with `details.fields`"}},
)
async def patch_listing(
    listing_id: uuid.UUID, body: ListingPatch, profile: Owner, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    listing, category = await manage.patch(session, profile, listing_id, body)
    out = await manage.listing_out(session, listing, category, locale)
    await session.commit()
    return out


@router.delete(
    "/owner/listings/{listing_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={**NOT_FOUND, 409: {"description": "`LISTING_HAS_BOOKINGS`"}},
)
async def delete_listing(listing_id: uuid.UUID, profile: Owner, session: Session) -> Response:
    await manage.soft_delete(session, profile, listing_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/owner/listings/{listing_id}/prices",
    response_model=OwnerListingOut,
    responses={
        **TRANSITION,
        422: {"description": "`PRICE_UNIT_NOT_ALLOWED` or `SEASON_OVERLAP`"},
    },
)
async def replace_prices(
    listing_id: uuid.UUID,
    body: list[PriceRow],
    profile: Owner,
    session: Session,
    locale: LocaleDep,
) -> OwnerListingOut:
    """Replace the whole price list; applies immediately, even on a live listing."""
    listing, category = await manage.replace_prices(session, profile, listing_id, body)
    out = await manage.listing_out(session, listing, category, locale)
    await session.commit()
    return out


@router.post(
    "/owner/listings/{listing_id}/submit",
    response_model=OwnerListingOut,
    responses={
        **TRANSITION,
        422: {"description": "`LISTING_INCOMPLETE` with `details.missing`"},
    },
)
async def submit_listing(
    listing_id: uuid.UUID, profile: Owner, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    """`draft | rejected → pending_review` (needs a photo and a base price)."""
    listing, category = await manage.submit(session, profile, listing_id)
    out = await manage.listing_out(session, listing, category, locale)
    await session.commit()
    return out


@router.post(
    "/owner/listings/{listing_id}/pause", response_model=OwnerListingOut, responses=TRANSITION
)
async def pause_listing(
    listing_id: uuid.UUID, profile: Owner, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    listing, category = await manage.set_paused(session, profile, listing_id, True)
    out = await manage.listing_out(session, listing, category, locale)
    await session.commit()
    return out


@router.post(
    "/owner/listings/{listing_id}/resume", response_model=OwnerListingOut, responses=TRANSITION
)
async def resume_listing(
    listing_id: uuid.UUID, profile: Owner, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    listing, category = await manage.set_paused(session, profile, listing_id, False)
    out = await manage.listing_out(session, listing, category, locale)
    await session.commit()
    return out


# --- photos -------------------------------------------------------------------------------


@router.post(
    "/owner/listings/{listing_id}/photos",
    status_code=status.HTTP_201_CREATED,
    response_model=PhotoUploadOut,
    responses=TRANSITION,
)
async def presign_photo(
    listing_id: uuid.UUID, body: PhotoUploadIn, profile: Owner, session: Session
) -> PhotoUploadOut:
    """Presigned PUT for a new photo; then PATCH it with `confirmed: true`."""
    out = await photos.presign(session, profile, listing_id, body.content_type)
    await session.commit()
    return out


@router.patch(
    "/owner/listings/{listing_id}/photos/{photo_id}",
    response_model=OwnerPhoto,
    responses={**NOT_FOUND, 422: {"description": "`PHOTO_NOT_UPLOADED`"}},
)
async def patch_photo(
    listing_id: uuid.UUID,
    photo_id: uuid.UUID,
    body: PhotoPatch,
    profile: Owner,
    session: Session,
) -> OwnerPhoto:
    """Confirm the upload (queues image processing), reorder, or set alt texts."""
    photo = await photos.update(session, profile, listing_id, photo_id, body)
    out = manage.photo_out(photo)
    await session.commit()
    return out


@router.delete(
    "/owner/listings/{listing_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=NOT_FOUND,
)
async def delete_photo(
    listing_id: uuid.UUID, photo_id: uuid.UUID, profile: Owner, session: Session
) -> Response:
    await photos.remove(session, profile, listing_id, photo_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- blocks & calendar --------------------------------------------------------------------


@router.get(
    "/owner/listings/{listing_id}/blocks", response_model=list[BlockOut], responses=NOT_FOUND
)
async def list_blocks(listing_id: uuid.UUID, profile: Owner, session: Session) -> list[BlockOut]:
    """Current and future owner blocks."""
    return [blocks.block_out(b) for b in await blocks.list_blocks(session, profile, listing_id)]


@router.post(
    "/owner/listings/{listing_id}/blocks",
    status_code=status.HTTP_201_CREATED,
    response_model=BlockOut,
    responses={**NOT_FOUND, 409: {"description": "`SLOT_TAKEN` or `INSUFFICIENT_STOCK`"}},
)
async def add_block(
    listing_id: uuid.UUID, body: BlockIn, profile: Owner, session: Session
) -> BlockOut:
    block = await blocks.add_block(session, profile, listing_id, body)
    out = blocks.block_out(block)
    await session.commit()
    return out


@router.delete(
    "/owner/listings/{listing_id}/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=NOT_FOUND,
)
async def delete_block(
    listing_id: uuid.UUID, block_id: uuid.UUID, profile: Owner, session: Session
) -> Response:
    await blocks.remove_block(session, profile, listing_id, block_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/owner/calendar", response_model=Calendar)
async def owner_calendar(
    profile: Owner,
    session: Session,
    locale: LocaleDep,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> Calendar:
    """Bookings and owner blocks across own listings for the EAT days `from..to`."""
    first = from_ or clock.today_eat()
    last = to or first + timedelta(days=DEFAULT_CALENDAR_DAYS - 1)
    return await blocks.calendar(session, profile, first, last, locale)
