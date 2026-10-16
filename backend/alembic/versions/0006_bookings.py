"""Bookings and availability blocks with the no-overlap exclusion constraint (T040, R1).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

booking_status = postgresql.ENUM(
    "requested", "awaiting_payment", "confirmed", "in_progress", "completed", "cancelled",
    "disputed", name="booking_status", create_type=False,
)
cancelled_by = postgresql.ENUM(
    "renter", "owner", "admin", "system", name="cancelled_by", create_type=False
)
block_kind = postgresql.ENUM("exclusive", "stock", name="block_kind", create_type=False)
block_source = postgresql.ENUM("booking", "owner_block", name="block_source", create_type=False)
# Created in 0004/0005.
booking_mode = postgresql.ENUM(name="booking_mode", create_type=False)
cancellation_policy = postgresql.ENUM(name="cancellation_policy", create_type=False)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for e in (booking_status, cancelled_by, block_kind, block_source):
        e.create(bind, checkfirst=True)

    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("renter_id", sa.Uuid(), nullable=False),
        sa.Column("owner_profile_id", sa.Uuid(), nullable=False),
        sa.Column("booking_mode", booking_mode, nullable=False),
        sa.Column("period", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", booking_status, nullable=False),
        sa.Column("quote", postgresql.JSONB(), nullable=False),
        sa.Column("rental_tzs", sa.BigInteger(), nullable=False),
        sa.Column("delivery_fee_tzs", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("service_fee_tzs", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("deposit_tzs", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_tzs", sa.BigInteger(), nullable=False),
        sa.Column("commission_bps", sa.Integer(), nullable=False),
        sa.Column("commission_tzs", sa.BigInteger(), nullable=False),
        sa.Column("cancellation_policy", cancellation_policy, nullable=False),
        sa.Column("delivery_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("delivery_address", sa.Text()),
        sa.Column("payment_due_at", sa.DateTime(timezone=True)),
        sa.Column("request_expires_at", sa.DateTime(timezone=True)),
        sa.Column("lease_months", sa.Integer()),
        sa.Column("cancelled_by", cancelled_by),
        sa.Column("cancel_reason", sa.Text()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_bookings"),
        sa.UniqueConstraint("code", name="uq_bookings_code"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"],
                                name="fk_bookings_listing_id_listings"),
        sa.ForeignKeyConstraint(["renter_id"], ["users.id"], name="fk_bookings_renter_id_users"),
        sa.ForeignKeyConstraint(["owner_profile_id"], ["owner_profiles.id"],
                                name="fk_bookings_owner_profile_id_owner_profiles"),
        sa.CheckConstraint("NOT isempty(period)", name="period_not_empty"),
        sa.CheckConstraint("quantity >= 1", name="quantity_positive"),
        sa.CheckConstraint(
            "total_tzs = rental_tzs + delivery_fee_tzs + service_fee_tzs + deposit_tzs",
            name="total_sum",
        ),
        sa.CheckConstraint(
            "rental_tzs >= 0 AND delivery_fee_tzs >= 0 AND service_fee_tzs >= 0"
            " AND deposit_tzs >= 0 AND commission_tzs >= 0",
            name="amounts_non_negative",
        ),
        sa.CheckConstraint(
            "(booking_mode = 'LEASE') = (lease_months IS NOT NULL)", name="lease_months"
        ),
    )
    op.create_index("ix_bookings_listing_id", "bookings", ["listing_id"])
    op.create_index("ix_bookings_status_payment_due_at", "bookings", ["status", "payment_due_at"])
    op.create_index(
        "ix_bookings_status_request_expires_at", "bookings", ["status", "request_expires_at"]
    )
    op.create_index("ix_bookings_renter_id_created_at", "bookings", ["renter_id", "created_at"])
    op.create_index(
        "ix_bookings_owner_profile_id_status", "bookings", ["owner_profile_id", "status"]
    )

    op.create_table(
        "availability_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("period", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("kind", block_kind, nullable=False),
        sa.Column("source", block_source, nullable=False),
        sa.Column("booking_id", sa.Uuid()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_availability_blocks"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE",
                                name="fk_availability_blocks_listing_id_listings"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"],
                                name="fk_availability_blocks_booking_id_bookings"),
        sa.CheckConstraint("NOT isempty(period)", name="period_not_empty"),
        sa.CheckConstraint("quantity >= 1", name="quantity_positive"),
        sa.CheckConstraint("kind = 'stock' OR quantity = 1", name="exclusive_quantity_one"),
        sa.CheckConstraint(
            "(source = 'booking') = (booking_id IS NOT NULL)", name="booking_source"
        ),
    )
    op.create_index("ix_availability_blocks_booking_id", "availability_blocks", ["booking_id"])
    op.create_index(
        "ix_availability_blocks_listing_period",
        "availability_blocks",
        ["listing_id", "period"],
        postgresql_using="gist",
        postgresql_where=sa.text("active"),
    )
    # R1: overlapping active exclusive blocks on one listing are impossible.
    op.execute(
        "ALTER TABLE availability_blocks ADD CONSTRAINT ex_availability_blocks_no_overlap"
        " EXCLUDE USING gist (listing_id WITH =, period WITH &&)"
        " WHERE (kind = 'exclusive' AND active)"
    )


def downgrade() -> None:
    op.drop_table("availability_blocks")
    op.drop_table("bookings")
    bind = op.get_bind()
    for e in (block_source, block_kind, cancelled_by, booking_status):
        e.drop(bind, checkfirst=True)
