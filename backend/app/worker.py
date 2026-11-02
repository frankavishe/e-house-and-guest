"""Worker process (`python -m app.worker`), R9.

Loop: schedule due periodic sweeps → claim a batch of jobs → run each in its own
transaction → sleep briefly when idle. Every handler must be idempotent: a job can run
again after a crash or a lock timeout.
"""

import asyncio
import contextlib
import importlib
import logging
import os
import signal
import socket
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import clock
from app.core.db import dispose_engine, get_sessionmaker
from app.core.logging import configure_logging
from app.jobs import service as jobs
from app.jobs.registry import HANDLER_MODULES, HANDLERS, PERIODIC_PREFIX, PERIODICS

log = logging.getLogger("app.worker")

IDLE_SLEEP_S = 1.0
BATCH_SIZE = 10


def load_handlers() -> None:
    for module in HANDLER_MODULES:
        importlib.import_module(module)


async def schedule_periodics(session: AsyncSession) -> None:
    """Enqueue one job per periodic sweep per time bucket (dedupe makes this idempotent)."""
    now_s = int(clock.now().timestamp())
    for p in PERIODICS.values():
        every_s = max(int(p.every.total_seconds()), 1)
        bucket = now_s // every_s
        await jobs.enqueue(
            session,
            PERIODIC_PREFIX + p.name,
            {},
            dedupe_key=f"{PERIODIC_PREFIX}{p.name}:{bucket}",
            max_attempts=1,
        )


async def run_job(
    sessions: async_sessionmaker[AsyncSession], job_id: int, kind: str, payload: dict[str, Any]
) -> bool:
    fn = HANDLERS.get(kind)
    try:
        if fn is None:
            raise LookupError(f"no handler registered for job kind {kind!r}")
        async with sessions() as session, session.begin():
            await fn(session, payload)
            await jobs.complete(session, job_id)
        return True
    except Exception as exc:
        log.exception("job %s (%s) failed", job_id, kind)
        async with sessions() as session, session.begin():
            await jobs.fail(session, job_id, f"{type(exc).__name__}: {exc}")
        return False


async def run_once(
    sessions: async_sessionmaker[AsyncSession], worker_id: str, limit: int = BATCH_SIZE
) -> int:
    """One iteration; returns the number of jobs processed."""
    async with sessions() as session, session.begin():
        await schedule_periodics(session)
    async with sessions() as session, session.begin():
        claimed = [
            (j.id, j.kind, dict(j.payload))
            for j in await jobs.claim_batch(session, worker_id, limit)
        ]
    for job_id, kind, payload in claimed:
        await run_job(sessions, job_id, kind, payload)
    return len(claimed)


async def run_forever() -> None:
    load_handlers()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    sessions = get_sessionmaker()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: stop.set())
    log.info(
        "worker %s started (%d handlers, %d periodics)", worker_id, len(HANDLERS), len(PERIODICS)
    )
    try:
        while not stop.is_set():
            try:
                processed = await run_once(sessions, worker_id)
            except Exception:
                log.exception("worker iteration failed")
                processed = 0
            if processed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), IDLE_SLEEP_S)
    finally:
        await dispose_engine()
        log.info("worker %s stopped", worker_id)


def main() -> None:
    configure_logging()
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
