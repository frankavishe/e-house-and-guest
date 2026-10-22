"""Checks on browser uploads (R12, docs/security.md).

A presigned PUT cannot limit the object size, so every private upload is checked when it is
confirmed or attached: it must exist and fit the limit. An oversized object is deleted.
"""

from collections.abc import Iterable

from app.core.errors import AppError
from app.integrations import get_storage

MB = 1024 * 1024


def too_large(max_bytes: int) -> AppError:
    return AppError("FILE_TOO_LARGE", 422, {"max_mb": max_bytes // MB})


async def check_uploads(keys: Iterable[str], *, max_bytes: int, field: str) -> None:
    storage = get_storage()
    for key in keys:
        size = await storage.size(key, private=True)
        if size is None:
            raise AppError("VALIDATION_ERROR", 422, {field: "upload not found"})
        if size > max_bytes:
            await storage.delete(key, private=True)
            raise too_large(max_bytes)
