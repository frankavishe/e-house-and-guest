"""`Idempotency-Key` support for unsafe POSTs (contracts/rest-api.md "Idempotency").

The stored response is written in the same transaction as the business change, so a replay
within 24 h returns exactly what the first request produced. The same key with a different
request → 422 `IDEMPOTENCY_KEY_REUSED`. A worker job purges keys older than 24 h.
"""

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, Text, delete, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import Base
from app.core.errors import AppError

TTL = timedelta(hours=24)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=clock.now, server_default=func.now(), nullable=False
    )


IdempotencyHeader = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=200,
        description="Replays within 24 h return the original response.",
    ),
]


def request_hash(method: str, path: str, body: BaseModel | None) -> str:
    raw = f"{method} {path}\n{body.model_dump_json() if body is not None else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _stored(
    session: AsyncSession, user_id: uuid.UUID, key: str, digest: str
) -> JSONResponse | None:
    row = await session.get(IdempotencyKey, (user_id, key), populate_existing=True)
    if row is None or row.created_at < clock.now() - TTL:
        return None
    if row.request_hash != digest:
        raise AppError("IDEMPOTENCY_KEY_REUSED", 422)
    return JSONResponse(row.response_body, row.response_status)


async def run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    key: str | None,
    method: str,
    path: str,
    body: BaseModel | None,
    status: int,
    action: Callable[[], Awaitable[Any]],
) -> Any:
    """Run `action` (which must not commit) once per key; commit its result with the key."""
    if key is None:
        result = await action()
        await session.commit()
        return result
    digest = request_hash(method, path, body)
    replay = await _stored(session, user_id, key, digest)
    if replay is not None:
        return replay
    # An expired row with the same key is replaced.
    await session.execute(
        delete(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
    )
    result = await action()
    session.add(
        IdempotencyKey(
            user_id=user_id,
            key=key,
            method=method,
            path=path,
            request_hash=digest,
            response_status=status,
            response_body=jsonable_encoder(result),
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        # A concurrent request with the same key won; return what it stored.
        await session.rollback()
        replay = await _stored(session, user_id, key, digest)
        if replay is None:
            raise
        return replay
    return result


async def purge(session: AsyncSession) -> int:
    result = await session.execute(
        delete(IdempotencyKey).where(IdempotencyKey.created_at < clock.now() - TTL)
    )
    return int(getattr(result, "rowcount", 0) or 0)
