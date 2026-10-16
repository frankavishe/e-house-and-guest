"""Catalogue: locations and categories (T034).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

location_level = postgresql.ENUM(
    "region", "district", "ward", name="location_level", create_type=False
)
booking_mode = postgresql.ENUM(
    "DATE_RANGE", "TIME_SLOT", "LEASE", "QUANTITY", name="booking_mode", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    location_level.create(bind, checkfirst=True)
    booking_mode.create(bind, checkfirst=True)

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer()),
        sa.Column("level", location_level, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.PrimaryKeyConstraint("id", name="pk_locations"),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["locations.id"], name="fk_locations_parent_id_locations"
        ),
        sa.UniqueConstraint(
            "parent_id", "slug", name="uq_locations_parent_slug", postgresql_nulls_not_distinct=True
        ),
    )
    op.create_index("ix_locations_parent_id", "locations", ["parent_id"])

    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid()),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", postgresql.JSONB(), nullable=False),
        sa.Column("booking_mode", booking_mode),
        sa.Column(
            "price_units",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("default_unit", sa.Text()),
        sa.Column(
            "attribute_schema",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("commission_bps", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("renter_fee_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_categories"),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["categories.id"], name="fk_categories_parent_id_categories"
        ),
        sa.UniqueConstraint("slug", name="uq_categories_slug"),
        sa.CheckConstraint(
            "commission_bps BETWEEN 0 AND 10000 AND renter_fee_bps BETWEEN 0 AND 10000",
            name="bps_range",
        ),
        sa.CheckConstraint(
            "booking_mode IS NULL OR (cardinality(price_units) > 0 AND default_unit IS NOT NULL"
            " AND default_unit = ANY(price_units))",
            name="leaf_units",
        ),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_index(
        "ix_categories_path", "categories", ["path"], postgresql_ops={"path": "text_pattern_ops"}
    )


def downgrade() -> None:
    op.drop_table("categories")
    op.drop_table("locations")
    bind = op.get_bind()
    booking_mode.drop(bind, checkfirst=True)
    location_level.drop(bind, checkfirst=True)
