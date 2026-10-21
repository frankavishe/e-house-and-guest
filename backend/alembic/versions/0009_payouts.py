"""Payouts and payout items, and the ledger's payout foreign key (T111, US4, R7).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

payout_status = postgresql.ENUM(
    "pending", "processing", "paid", "failed", name="payout_status", create_type=False
)


def created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    payout_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "payouts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_profile_id", sa.Uuid(), nullable=False),
        sa.Column("amount_tzs", sa.BigInteger(), nullable=False),
        sa.Column("status", payout_status, nullable=False),
        sa.Column("payout_method_id", sa.Uuid()),
        sa.Column("payout_method", postgresql.JSONB()),
        sa.Column("provider", sa.Text()),
        sa.Column("provider_ref", sa.Text()),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("marked_paid_by", sa.Uuid()),
        created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payouts"),
        sa.ForeignKeyConstraint(["owner_profile_id"], ["owner_profiles.id"],
                                name="fk_payouts_owner_profile_id_owner_profiles"),
        sa.ForeignKeyConstraint(["payout_method_id"], ["payout_methods.id"], ondelete="SET NULL",
                                name="fk_payouts_payout_method_id_payout_methods"),
        sa.ForeignKeyConstraint(["marked_paid_by"], ["users.id"],
                                name="fk_payouts_marked_paid_by_users"),
        sa.CheckConstraint("amount_tzs > 0", name="amount_positive"),
        sa.CheckConstraint("status <> 'paid' OR paid_at IS NOT NULL", name="paid_has_paid_at"),
    )
    op.create_index(
        "ix_payouts_owner_profile_id_created_at", "payouts", ["owner_profile_id", "created_at"]
    )
    op.create_index("ix_payouts_status_updated_at", "payouts", ["status", "updated_at"])

    op.create_table(
        "payout_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payout_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("amount_tzs", sa.BigInteger(), nullable=False),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_payout_items"),
        sa.ForeignKeyConstraint(["payout_id"], ["payouts.id"], ondelete="CASCADE",
                                name="fk_payout_items_payout_id_payouts"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"],
                                name="fk_payout_items_booking_id_bookings"),
        # A booking is paid out once.
        sa.UniqueConstraint("booking_id", name="uq_payout_items_booking_id"),
        sa.CheckConstraint("amount_tzs > 0", name="amount_positive"),
    )
    op.create_index("ix_payout_items_payout_id", "payout_items", ["payout_id"])

    op.create_foreign_key(
        "fk_ledger_entries_payout_id_payouts", "ledger_entries", "payouts", ["payout_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_ledger_entries_payout_id_payouts", "ledger_entries", type_="foreignkey")
    op.drop_table("payout_items")
    op.drop_table("payouts")
    payout_status.drop(op.get_bind(), checkfirst=True)
