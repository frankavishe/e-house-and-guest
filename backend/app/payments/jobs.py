"""Payment sweeps (R6, R9): reconcile pending payments whose callback never arrived, and
purge idempotency keys older than 24 h."""

from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import idempotency
from app.jobs.registry import periodic
from app.payments.service import reconcile_pending


@periodic("payments.reconcile", every=timedelta(minutes=1))
async def reconcile(session: AsyncSession) -> None:
    await reconcile_pending(session)


@periodic("idempotency.purge", every=timedelta(hours=1))
async def purge_idempotency_keys(session: AsyncSession) -> None:
    await idempotency.purge(session)
