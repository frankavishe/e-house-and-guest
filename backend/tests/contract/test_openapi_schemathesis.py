"""Whole-schema property test (T049, R15): every public endpoint in /api/v1/openapi.json is
called with generated data and must answer within its documented contract (status codes,
response schemas, content types, no 5xx). New endpoints are picked up automatically.

Runs against a migrated and seeded test database; webhooks and dev-only routes are excluded.
"""

import asyncio
import threading
from collections.abc import Iterator

import pytest
import schemathesis
from alembic import command
from alembic.config import Config
from hypothesis import HealthCheck, settings
from schemathesis.config import SchemathesisConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.db import Base
from app.main import app
from app.seed import seed_categories, seed_demo, seed_locations
from tests.conftest import BACKEND_DIR

# 400 is a business-rule rejection of well-formed input (e.g. a wrong OTP), not a schema
# mismatch; 422 still counts as rejecting valid data.
CONFIG = SchemathesisConfig.from_str(
    """
[checks.positive_data_acceptance]
expected-statuses = ["2XX", "400", "401", "403", "404", "409", "429"]
"""
)

schema = schemathesis.openapi.from_asgi("/api/v1/openapi.json", app, config=CONFIG).exclude(
    path_regex=r"^/api/v1/(webhooks|dev)/"
)


def _in_thread(fn) -> None:  # type: ignore[no-untyped-def]
    """Run a blocking/async setup step outside pytest-asyncio's event loop."""
    errors: list[BaseException] = []

    def target() -> None:
        try:
            fn()
        except BaseException as exc:
            errors.append(exc)

    t = threading.Thread(target=target)
    t.start()
    t.join()
    if errors:
        raise errors[0]


async def _seed(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await seed_locations(session)
        await seed_categories(session)
        await seed_demo(session)
        await session.commit()
    await engine.dispose()


async def _truncate(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture(scope="module", autouse=True)
def seeded_database() -> Iterator[None]:
    url = get_settings().test_database_url

    def migrate() -> None:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.attributes["url"] = url
        cfg.attributes["skip_logging"] = True
        command.upgrade(cfg, "head")

    _in_thread(migrate)
    _in_thread(lambda: asyncio.run(_seed(url)))
    yield
    _in_thread(lambda: asyncio.run(_truncate(url)))


@schema.parametrize()
@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_api_conforms_to_openapi(case: schemathesis.Case) -> None:
    case.call_and_validate()
