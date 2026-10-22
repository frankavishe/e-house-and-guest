"""Housekeeping sweeps for core tables: expired rate-limit windows (T144)."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.jobs.registry import periodic


@periodic("ratelimit.purge", every=timedelta(hours=1))
async def purge_rate_limits(session: AsyncSession) -> None:
    await ratelimit.purge(session)
