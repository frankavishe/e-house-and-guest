"""`image.process` (T099, R12): turn an uploaded original into public WebP variants.

The original stays in the private bucket. Re-encoding drops every EXIF tag (including GPS),
after applying the EXIF orientation so the picture is upright.
"""

import io
import uuid
from typing import Any

from PIL import Image, ImageOps
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import get_storage
from app.jobs.registry import handler
from app.listings.models import ListingPhoto

WIDTHS = (320, 640, 1280)
WEBP_QUALITY = 80


def webp_variants(original: bytes) -> dict[int, bytes]:
    with Image.open(io.BytesIO(original)) as image:
        upright = ImageOps.exif_transpose(image).convert("RGB")
    out: dict[int, bytes] = {}
    for width in WIDTHS:
        variant = upright.copy()
        if variant.width > width:
            height = max(1, round(variant.height * width / variant.width))
            variant = variant.resize((width, height), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        variant.save(buffer, "WEBP", quality=WEBP_QUALITY)  # no `exif=`: metadata is dropped
        out[width] = buffer.getvalue()
    return out


@handler("image.process")
async def process_image(session: AsyncSession, payload: dict[str, Any]) -> None:
    photo = await session.get(ListingPhoto, uuid.UUID(payload["photo_id"]))
    if photo is None:
        return  # deleted before the job ran
    storage = get_storage()
    original = await storage.get(photo.storage_key, private=True)
    variants: dict[str, str] = {}
    for width, data in webp_variants(original).items():
        key = f"listings/{photo.listing_id}/{photo.id}/{width}.webp"
        await storage.put(key, data, "image/webp", private=False)
        variants[str(width)] = key
    photo.variants = variants
    await session.flush()
