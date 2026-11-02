"""Job queue table (R9).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="8", nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("locked_by", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("done_at", sa.DateTime(timezone=True)),
        sa.Column("dead_at", sa.DateTime(timezone=True)),
        sa.Column("dedupe_key", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("dedupe_key", name="uq_jobs_dedupe_key"),
    )
    op.create_index(
        "ix_jobs_due",
        "jobs",
        ["run_at"],
        postgresql_where=sa.text("done_at IS NULL AND dead_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_due", table_name="jobs")
    op.drop_table("jobs")
