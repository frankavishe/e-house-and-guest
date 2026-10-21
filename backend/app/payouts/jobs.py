"""Payout sweeps (R7, R9): the daily batch, the status poller and the per-payout send job.

Bookings become eligible 24 h after completion and the batch runs daily, so a payout starts
within 48 h of completion (SC-008)."""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.registry import handler, periodic
from app.payouts import service


@periodic("payouts.create", every=timedelta(days=1))
async def create_payouts(session: AsyncSession) -> int:
    return len(await service.create_payouts(session))


@periodic("payouts.poll", every=timedelta(minutes=5))
async def poll_payouts(session: AsyncSession) -> int:
    return await service.poll_processing(session)


@handler(service.DISBURSE_JOB)
async def disburse(session: AsyncSession, payload: dict[str, Any]) -> None:
    await service.disburse(session, uuid.UUID(payload["payout_id"]))
