"""Claims, cancellation time, refund attempts and claim-award payout items (T119, US5).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


claim_kind = enum("claim_kind", "damage", "dispute")
claim_status = enum("claim_status", "open", "resolved")
claim_resolution = enum("claim_resolution", "owner_awarded", "renter_refunded", "split")
payout_item_kind = enum("payout_item_kind", "earnings", "claim_award")
ENUMS = (claim_kind, claim_status, claim_resolution, payout_item_kind)


def upgrade() -> None:
    bind = op.get_bind()
    for e in ENUMS:
        e.create(bind, checkfirst=True)

    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("opened_by", sa.Uuid(), nullable=False),
        sa.Column("kind", claim_kind, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("amount_claimed_tzs", sa.BigInteger()),
        sa.Column("status", claim_status, nullable=False),
        sa.Column("resolution", claim_resolution),
        sa.Column("amount_awarded_tzs", sa.BigInteger()),
        sa.Column("resolution_note", sa.Text()),
        sa.Column("resolved_by", sa.Uuid()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claims"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"],
                                name="fk_claims_booking_id_bookings"),
        sa.ForeignKeyConstraint(["opened_by"], ["users.id"], name="fk_claims_opened_by_users"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], name="fk_claims_resolved_by_users"),
        sa.CheckConstraint("amount_claimed_tzs IS NULL OR amount_claimed_tzs >= 0",
                           name="amount_claimed_non_negative"),
        sa.CheckConstraint("amount_awarded_tzs IS NULL OR amount_awarded_tzs >= 0",
                           name="amount_awarded_non_negative"),
        sa.CheckConstraint("status <> 'resolved' OR (resolution IS NOT NULL AND resolved_at IS "
                           "NOT NULL)", name="resolved_has_resolution"),
    )
    op.create_index("ix_claims_booking_id", "claims", ["booking_id"])
    op.create_index("ix_claims_status_created_at", "claims", ["status", "created_at"])
    op.create_index(
        "uq_claims_one_open",
        "claims",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.add_column("bookings", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column(
        "refunds", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
    )

    op.add_column(
        "payout_items",
        sa.Column("kind", payout_item_kind, nullable=False, server_default="earnings"),
    )
    op.drop_constraint("uq_payout_items_booking_id", "payout_items", type_="unique")
    op.create_unique_constraint(
        "uq_payout_items_booking_id_kind", "payout_items", ["booking_id", "kind"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_payout_items_booking_id_kind", "payout_items", type_="unique")
    op.execute("DELETE FROM payout_items WHERE kind <> 'earnings'")
    op.create_unique_constraint("uq_payout_items_booking_id", "payout_items", ["booking_id"])
    op.drop_column("payout_items", "kind")
    op.drop_column("refunds", "attempts")
    op.drop_column("bookings", "cancelled_at")
    op.drop_table("claims")
    bind = op.get_bind()
    for e in reversed(ENUMS):
        e.drop(bind, checkfirst=True)
