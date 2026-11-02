"""Job queue: enqueue, claim, retry/backoff, dedupe, skip-locked (T023, R9)."""

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.jobs import service as jobs
from app.jobs.models import Job
from app.jobs.registry import HANDLERS, PERIODICS, handler, periodic
from app.worker import run_once


async def test_enqueue_and_claim_due_jobs_only(db: AsyncSession, frozen_clock) -> None:
    due = await jobs.enqueue(db, "t.due", {"n": 1})
    await jobs.enqueue(db, "t.later", run_at=frozen_clock.current + timedelta(minutes=5))

    claimed = await jobs.claim_batch(db, "w1")

    assert [j.id for j in claimed] == [due]
    assert claimed[0].attempts == 1 and claimed[0].locked_by == "w1"
    assert claimed[0].payload == {"n": 1}
    # Already locked → not claimed again.
    assert await jobs.claim_batch(db, "w2") == []


async def test_dedupe_key_prevents_duplicates(db: AsyncSession, frozen_clock) -> None:
    first = await jobs.enqueue(db, "t.x", dedupe_key="same")
    second = await jobs.enqueue(db, "t.x", dedupe_key="same")
    assert first is not None and second is None
    rows = (await db.execute(select(Job).where(Job.dedupe_key == "same"))).scalars().all()
    assert len(rows) == 1


async def test_failure_retries_with_exponential_backoff(db: AsyncSession, frozen_clock) -> None:
    job_id = await jobs.enqueue(db, "t.flaky", max_attempts=3)
    assert job_id is not None

    await jobs.claim_batch(db, "w")
    await jobs.fail(db, job_id, "boom")
    job = await db.get(Job, job_id, populate_existing=True)
    assert job is not None
    assert job.run_at == frozen_clock.current + timedelta(seconds=30)
    assert job.locked_at is None and job.last_error == "boom"

    frozen_clock.advance(seconds=30)
    await jobs.claim_batch(db, "w")
    await jobs.fail(db, job_id, "boom")
    job = await db.get(Job, job_id, populate_existing=True)
    assert job is not None and job.run_at == frozen_clock.current + timedelta(seconds=60)

    frozen_clock.advance(seconds=60)
    await jobs.claim_batch(db, "w")
    await jobs.fail(db, job_id, "boom")
    job = await db.get(Job, job_id, populate_existing=True)
    assert job is not None and job.dead_at is not None and job.attempts == 3
    frozen_clock.advance(hours=2)
    assert await jobs.claim_batch(db, "w") == []


def test_backoff_is_capped() -> None:
    assert jobs.backoff(1) == timedelta(seconds=30)
    assert jobs.backoff(4) == timedelta(seconds=240)
    assert jobs.backoff(20) == timedelta(hours=1)


async def test_completed_job_is_not_claimed(db: AsyncSession, frozen_clock) -> None:
    job_id = await jobs.enqueue(db, "t.once")
    assert job_id is not None
    await jobs.claim_batch(db, "w")
    await jobs.complete(db, job_id)
    frozen_clock.advance(hours=1)
    assert await jobs.claim_batch(db, "w") == []


async def test_stale_lock_is_reclaimed(db: AsyncSession, frozen_clock) -> None:
    job_id = await jobs.enqueue(db, "t.crashed")
    await jobs.claim_batch(db, "dead-worker")
    frozen_clock.advance(minutes=6)
    claimed = await jobs.claim_batch(db, "w2")
    assert [j.id for j in claimed] == [job_id] and claimed[0].attempts == 2


async def test_two_workers_never_claim_the_same_job(
    committed_sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with committed_sessions() as s, s.begin():
        for i in range(6):
            await jobs.enqueue(s, "t.parallel", {"i": i})

    async with committed_sessions() as a, committed_sessions() as b:
        await a.begin()
        await b.begin()
        first = await jobs.claim_batch(a, "A", limit=4)  # rows stay locked until commit
        second = await jobs.claim_batch(b, "B", limit=4)
        await a.commit()
        await b.commit()

    ids_a, ids_b = {j.id for j in first}, {j.id for j in second}
    assert len(ids_a) == 4 and len(ids_b) == 2 and not ids_a & ids_b


async def test_worker_runs_handlers_and_records_failures(
    committed_sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.worker.PERIODICS", {})  # only count the jobs enqueued here
    seen: list[dict[str, Any]] = []

    @handler("t.ok")
    async def ok(session: AsyncSession, payload: dict[str, Any]) -> None:
        seen.append(payload)

    @handler("t.bad")
    async def bad(session: AsyncSession, payload: dict[str, Any]) -> None:
        raise RuntimeError("nope")

    try:
        async with committed_sessions() as s, s.begin():
            ok_id = await jobs.enqueue(s, "t.ok", {"a": 1})
            bad_id = await jobs.enqueue(s, "t.bad")
            unknown_id = await jobs.enqueue(s, "t.unknown")

        assert await run_once(committed_sessions, "w") == 3

        async with committed_sessions() as s:
            ok_job = await s.get(Job, ok_id)
            bad_job = await s.get(Job, bad_id)
            unknown_job = await s.get(Job, unknown_id)
        assert seen == [{"a": 1}]
        assert ok_job is not None and ok_job.done_at is not None
        assert bad_job is not None and bad_job.done_at is None
        assert bad_job.last_error == "RuntimeError: nope"
        assert unknown_job is not None and "no handler" in (unknown_job.last_error or "")
    finally:
        HANDLERS.pop("t.ok", None)
        HANDLERS.pop("t.bad", None)


async def test_periodic_sweep_runs_once_per_bucket(
    committed_sessions: async_sessionmaker[AsyncSession], frozen_clock
) -> None:
    calls: list[int] = []

    @periodic("t.sweep", every=timedelta(minutes=1))
    async def sweep(session: AsyncSession) -> None:
        calls.append(1)

    try:
        await run_once(committed_sessions, "w1")
        await run_once(committed_sessions, "w2")  # same minute → deduped
        assert len(calls) == 1
        frozen_clock.advance(minutes=1)
        await run_once(committed_sessions, "w1")
        assert len(calls) == 2
    finally:
        PERIODICS.pop("t.sweep", None)
        HANDLERS.pop("periodic:t.sweep", None)
