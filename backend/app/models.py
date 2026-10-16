"""Imports every model module so `Base.metadata` knows all tables (Alembic, tests)."""

from app.jobs import models as jobs  # noqa: F401
