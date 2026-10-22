"""Fixed-window rate limits kept in Postgres (T144): no extra infrastructure, shared by every
API process.

`hit()` increments the counter for `(key, window)` and commits at once, so the attempt counts
even when the request later fails (a refused booking still costs a try). Past the limit it
raises 429 `RATE_LIMITED` with `retry_after`, which the error handler turns into `Retry-After`.
A worker sweep drops windows older than a day.

Behind a reverse proxy the API must run with `--proxy-headers` so `request.client.host` is the
caller's address (docs/operations.md).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import DateTime, Integer, Text, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core import clock
from app.core.db import Base
from app.core.errors import AppError

RETENTION = timedelta(days=1)


class RateLimit(Base):
    __tablename__ = "rate_limits"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


@dataclass(frozen=True)
class Rule:
    name: str
    limit: int
    window: timedelta


# Generous enough for a real person; they stop scripted abuse. The per-phone OTP throttle in
# accounts.service (3 per 15 min) still applies on top of the per-IP rule.
OTP_PER_IP = Rule("otp:ip", 20, timedelta(hours=1))
BOOKINGS_PER_USER = Rule("booking:user", 10, timedelta(minutes=10))
MESSAGES_PER_USER = Rule("msg:user", 30, timedelta(minutes=1))


def _window_start(now: datetime, window: timedelta) -> datetime:
    seconds = int(window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, UTC)


async def hit(session: AsyncSession, rule: Rule, subject: str) -> None:
    """Count one attempt by `subject` under `rule`; 429 once the window's limit is passed."""
    now = clock.now()
    start = _window_start(now, rule.window)
    stmt = (
        insert(RateLimit)
        .values(key=f"{rule.name}:{subject}", window_start=start, count=1)
        .on_conflict_do_update(
            index_elements=[RateLimit.key, RateLimit.window_start],
            set_={"count": RateLimit.count + 1},
        )
        .returning(RateLimit.count)
    )
    count = (await session.execute(stmt)).scalar_one()
    await session.commit()
    if count > rule.limit:
        retry_after = max(1, int((start + rule.window - now).total_seconds()))
        raise AppError("RATE_LIMITED", 429, {"retry_after": retry_after})


async def hit_ip(session: AsyncSession, rule: Rule, request: Request) -> None:
    await hit(session, rule, request.client.host if request.client else "unknown")


async def hit_user(session: AsyncSession, rule: Rule, user_id: uuid.UUID) -> None:
    await hit(session, rule, str(user_id))


async def purge(session: AsyncSession) -> int:
    result = await session.execute(
        delete(RateLimit).where(RateLimit.window_start < clock.now() - RETENTION)
    )
    return int(getattr(result, "rowcount", 0) or 0)
