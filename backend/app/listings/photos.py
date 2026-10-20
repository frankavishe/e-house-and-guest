"""Listing photo uploads (T099, R12): presign a PUT into the private uploads bucket,
confirm once uploaded (queues `image.process`), reorder, alt text, delete.

Originals stay private: they may carry EXIF GPS data. The image job publishes stripped WebP
variants. On a live listing a new photo is `pending` and a removal waits for review.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile
from app.core import clock
from app.core.db import uuid7
from app.core.errors import AppError, not_found
from app.integrations import get_storage
from app.jobs import service as jobs
from app.listings import manage
from app.listings.models import Listing, ListingPhoto
from app.listings.owner_schemas import PhotoPatch, PhotoUploadOut

PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
PHOTO_MAX_BYTES = 15 * 1024 * 1024
MAX_PHOTOS = 20


async def _photo(session: AsyncSession, listing: Listing, photo_id: uuid.UUID) -> ListingPhoto:
    photo = await session.get(ListingPhoto, photo_id)
    if photo is None or photo.listing_id != listing.id:
        raise not_found("photo")
    return photo


async def presign(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID, content_type: str
) -> PhotoUploadOut:
    listing, _ = await manage.get_owned(session, profile, listing_id, lock=True)
    if listing.status not in manage.EDITABLE_STATUSES:
        raise manage.invalid_transition(listing)
    ext = PHOTO_TYPES.get(content_type)
    if ext is None:
        raise AppError("VALIDATION_ERROR", 422, {"content_type": sorted(PHOTO_TYPES)})
    count, last = (
        await session.execute(
            select(func.count(), func.max(ListingPhoto.position)).where(
                ListingPhoto.listing_id == listing.id, ListingPhoto.confirmed_at.is_not(None)
            )
        )
    ).one()
    if count >= MAX_PHOTOS:
        raise AppError("VALIDATION_ERROR", 422, {"photos": f"at most {MAX_PHOTOS}"})
    photo_id = uuid7()
    key = f"uploads/listings/{listing.id}/{photo_id}.{ext}"
    session.add(
        ListingPhoto(
            id=photo_id,
            listing_id=listing.id,
            storage_key=key,
            position=(last + 1) if last is not None else 0,
        )
    )
    await session.flush()
    put = get_storage().presign_put(
        key=key, content_type=content_type, max_bytes=PHOTO_MAX_BYTES, private=True
    )
    return PhotoUploadOut(
        photo_id=photo_id, upload_url=put.url, storage_key=put.key, headers=put.headers
    )


async def update(
    session: AsyncSession,
    profile: OwnerProfile,
    listing_id: uuid.UUID,
    photo_id: uuid.UUID,
    body: PhotoPatch,
) -> ListingPhoto:
    listing, _ = await manage.get_owned(session, profile, listing_id, lock=True)
    photo = await _photo(session, listing, photo_id)
    if body.confirmed and photo.confirmed_at is None:
        size = await get_storage().size(photo.storage_key, private=True)
        if not size:
            raise AppError("PHOTO_NOT_UPLOADED", 422)
        photo.confirmed_at = clock.now()
        if listing.status in manage.LIVE:
            photo.pending = True
            manage.note_photo_added(listing, photo.id)
        await jobs.enqueue(
            session, "image.process", {"photo_id": str(photo.id)}, dedupe_key=f"image:{photo.id}"
        )
    if body.position is not None:
        photo.position = body.position
    if body.alt_sw is not None:
        photo.alt_sw = body.alt_sw or None
    if body.alt_en is not None:
        photo.alt_en = body.alt_en or None
    await session.flush()
    return photo


async def remove(
    session: AsyncSession, profile: OwnerProfile, listing_id: uuid.UUID, photo_id: uuid.UUID
) -> None:
    listing, _ = await manage.get_owned(session, profile, listing_id, lock=True)
    photo = await _photo(session, listing, photo_id)
    if listing.status in manage.LIVE and photo.confirmed_at and not photo.pending:
        manage.note_photo_removed(listing, photo.id)  # removed once the change is approved
    else:
        await session.delete(photo)
    await session.flush()
