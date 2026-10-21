"""Shared fixtures (R15).

- The test database (TEST_DATABASE_URL) is reset and migrated once per session.
- `db` is a session inside an outer transaction that is rolled back after each test;
  service-level `commit()` calls only release savepoints.
- `client` is an httpx client bound to the app with `get_session` overridden to `db`.
- `committed_sessions` gives real, independent sessions for concurrency tests; every table
  is truncated afterwards.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["ENV"] = "test"
os.environ.setdefault("STORAGE_PROVIDER", "local")
os.environ.setdefault("SMS_PROVIDER", "console")
os.environ.setdefault("PAYMENT_PROVIDER", "mock")

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import clock
from app.core.config import get_settings
from app.core.db import Base, get_session

get_settings.cache_clear()

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _alembic_upgrade(url: str) -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["url"] = url
    cfg.attributes["skip_logging"] = True
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = get_settings().test_database_url
    eng = create_async_engine(url, pool_size=25, max_overflow=10)
    async with eng.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    # env.py calls asyncio.run(), so migrate from a worker thread.
    await asyncio.to_thread(_alembic_upgrade, url)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def client(db: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = _session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(loop_scope="session")
async def committed_sessions(
    engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Independent sessions whose commits are real (concurrency tests). Cleans up after."""
    yield async_sessionmaker(engine, expire_on_commit=False)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    if tables:
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


class FrozenClock:
    """Controls `app.core.clock.now()`; starts at 2026-11-02 09:00 EAT (06:00 UTC)."""

    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def set(self, value: datetime) -> None:
        self.current = value if value.tzinfo else value.replace(tzinfo=UTC)

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


@pytest.fixture
def frozen_clock() -> Iterator[FrozenClock]:
    fc = FrozenClock(datetime(2026, 11, 2, 6, 0, tzinfo=UTC))
    clock.set_clock(fc)
    yield fc
    clock.reset_clock()


@pytest.fixture
def make_id() -> Callable[[], str]:
    import uuid

    return lambda: str(uuid.uuid4())


@pytest.fixture(autouse=True)
def mock_payments() -> Iterator[object]:
    """A fresh mock payment provider per test; callbacks are queued, never sent on their own
    (tests deliver them with `factories.deliver_callbacks`)."""
    from app.integrations import override_payments
    from app.integrations.payments.mock import MockPaymentProvider

    provider = MockPaymentProvider(secret=get_settings().payment_callback_secret)
    override_payments(provider)
    yield provider
    override_payments(None)


@pytest.fixture(autouse=True)
def mock_payouts() -> Iterator[object]:
    """A fresh mock payout provider per test (outcome by the destination number)."""
    from app.integrations import override_payouts
    from app.integrations.payments.mock import MockPayoutProvider

    provider = MockPayoutProvider()
    override_payouts(provider)
    yield provider
    override_payouts(None)
