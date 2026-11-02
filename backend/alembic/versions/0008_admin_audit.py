"""Admin audit log, photo review/confirmation columns, owner block notes and draft listings
without a location yet (T098, T101, US3).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOT_DRAFT_CHECKS = {
    "has_title": "title_sw IS NOT NULL OR title_en IS NOT NULL",
    "has_description": "description_sw IS NOT NULL OR description_en IS NOT NULL",
    "has_location": "region_id IS NOT NULL AND district_id IS NOT NULL",
}


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("admin_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_admin_audit_log_target", "admin_audit_log", ["target_kind", "target_id"]
    )
    op.create_index("ix_admin_audit_log_admin", "admin_audit_log", ["admin_id", "created_at"])

    # A photo row exists from presign; it counts once the upload is confirmed. Photos added to
    # a live listing stay `pending` (hidden publicly) until an admin approves the change.
    op.add_column("listing_photos", sa.Column("confirmed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "listing_photos",
        sa.Column("pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE listing_photos SET confirmed_at = created_at")

    op.add_column("availability_blocks", sa.Column("note", sa.Text()))

    # Drafts start from a category alone; title, description and location are required
    # once the listing leaves `draft` (submit checks them first and answers with a 422).
    op.alter_column("listings", "region_id", nullable=True)
    op.alter_column("listings", "district_id", nullable=True)
    for name, condition in NOT_DRAFT_CHECKS.items():
        op.execute(f"ALTER TABLE listings DROP CONSTRAINT IF EXISTS ck_listings_{name}")
        op.execute(
            f"ALTER TABLE listings ADD CONSTRAINT ck_listings_{name}"
            f" CHECK (status = 'draft' OR ({condition}))"
        )


def downgrade() -> None:
    for name, condition in NOT_DRAFT_CHECKS.items():
        op.execute(f"ALTER TABLE listings DROP CONSTRAINT ck_listings_{name}")
        if name != "has_location":
            op.execute(f"ALTER TABLE listings ADD CONSTRAINT ck_listings_{name} CHECK ({condition})")
    op.alter_column("listings", "district_id", nullable=False)
    op.alter_column("listings", "region_id", nullable=False)
    op.drop_column("availability_blocks", "note")
    op.drop_column("listing_photos", "pending")
    op.drop_column("listing_photos", "confirmed_at")
    op.drop_index("ix_admin_audit_log_admin", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_target", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
