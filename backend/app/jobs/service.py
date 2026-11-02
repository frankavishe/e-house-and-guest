"""Enqueue, claim and finish jobs (R9).

`enqueue` joins the caller's transaction (outbox pattern): the job exists only if the
business change commits. Workers claim with `FOR UPDATE SKIP LOCKED`, so several workers
never take the same job. Failed jobs retry with exponential backoff until `max_attempts`.
"""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.jobs.models import Job

BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 3600
# A job locked longer than this is assumed abandoned (worker crashed) and can be reclaimed.
LOCK_TIMEOUT = timedelta(minutes=5)


def backoff(attempts: int) -> timedelta:
    """Delay before the next try after `attempts` failed tries: 30 s, 60 s, 120 s … ≤ 1 h."""
    return timedelta(seconds=min(BACKOFF_BASE_S * 2 ** max(attempts - 1, 0), BACKOFF_MAX_S))


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    run_at: datetime | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 8,
) -> int | None:
    """Add a job. Returns its id, or None if `dedupe_key` already exists."""
    stmt = (
        insert(Job)
        .values(
            kind=kind,
            payload=payload or {},
            run_at=run_at or clock.now(),
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
        )
        .on_conflict_do_nothing(index_elements=[Job.dedupe_key])
        .returning(Job.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def claim_batch(session: AsyncSession, worker_id: str, limit: int = 10) -> list[Job]:
    """Lock up to `limit` due jobs for this worker and count the attempt. Caller commits."""
    now = clock.now()
    due = (
        select(Job.id)
        .where(
            Job.done_at.is_(None),
            Job.dead_at.is_(None),
            Job.run_at <= now,
            (Job.locked_at.is_(None)) | (Job.locked_at < now - LOCK_TIMEOUT),
        )
        .order_by(Job.run_at, Job.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    stmt = (
        update(Job)
        .where(Job.id.in_(due.scalar_subquery()))
        .values(locked_at=now, locked_by=worker_id, attempts=Job.attempts + 1)
        .returning(Job)
        .execution_options(synchronize_session=False)
    )
    jobs = list((await session.execute(stmt)).scalars().all())
    return sorted(jobs, key=lambda j: (j.run_at, j.id))


async def complete(session: AsyncSession, job_id: int) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(done_at=clock.now(), locked_at=None, locked_by=None, last_error=None)
    )


async def fail(session: AsyncSession, job_id: int, error: str) -> None:
    """Schedule a retry with backoff, or mark the job dead after `max_attempts`."""
    job = await session.get(Job, job_id, populate_existing=True)
    if job is None:
        return
    now = clock.now()
    job.locked_at = None
    job.locked_by = None
    job.last_error = error[:4000]
    if job.attempts >= job.max_attempts:
        job.dead_at = now
    else:
        job.run_at = now + backoff(job.attempts)
    await session.flush()
