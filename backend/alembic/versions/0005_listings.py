"""Owners and listings: owner_profiles, payout_methods, listings, listing_photos,
listing_prices (T039).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


owner_kind = enum("owner_kind", "individual", "business")
verification_status = enum("verification_status", "draft", "pending", "verified", "rejected")
payout_kind = enum("payout_kind", "mobile_money", "bank")
payment_network = enum("payment_network", "mpesa", "mixx", "airtel", "halopesa", "azampesa")
listing_status = enum(
    "listing_status",
    "draft", "pending_review", "active", "paused", "rejected", "suspended", "deleted",
)
delivery_option = enum("delivery_option", "none", "optional", "required")
cancellation_policy = enum("cancellation_policy", "flexible", "moderate", "strict")
review_state = enum("review_state", "none", "pending", "rejected")
price_unit = enum("price_unit", "hour", "night", "day", "week", "month", "item_day")

ENUMS = (
    owner_kind, verification_status, payout_kind, payment_network, listing_status,
    delivery_option, cancellation_policy, review_state, price_unit,
)


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
    for e in ENUMS:
        e.create(bind, checkfirst=True)

    op.create_table(
        "owner_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", owner_kind, nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("nida_number_enc", sa.LargeBinary()),
        sa.Column("business_name", sa.Text()),
        sa.Column("brela_reg_no", sa.Text()),
        sa.Column("tin_enc", sa.LargeBinary()),
        sa.Column(
            "documents", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("verification_status", verification_status, nullable=False,
                  server_default="draft"),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verified_by", sa.Uuid()),
        sa.Column("rating_avg", sa.Numeric(3, 2)),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_owner_profiles"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_owner_profiles_user_id_users"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"],
                                name="fk_owner_profiles_verified_by_users"),
        sa.UniqueConstraint("user_id", name="uq_owner_profiles_user_id"),
        sa.CheckConstraint(
            "verification_status <> 'rejected' OR rejection_reason IS NOT NULL",
            name="rejection_reason",
        ),
    )

    op.create_table(
        "payout_methods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_profile_id", sa.Uuid(), nullable=False),
        sa.Column("kind", payout_kind, nullable=False),
        sa.Column("network", payment_network),
        sa.Column("msisdn", sa.Text()),
        sa.Column("bank_name", sa.Text()),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column("account_number_enc", sa.LargeBinary()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_payout_methods"),
        sa.ForeignKeyConstraint(["owner_profile_id"], ["owner_profiles.id"], ondelete="CASCADE",
                                name="fk_payout_methods_owner_profile_id_owner_profiles"),
        sa.CheckConstraint(
            "(kind = 'mobile_money' AND network IS NOT NULL AND msisdn IS NOT NULL)"
            " OR (kind = 'bank' AND bank_name IS NOT NULL AND account_number_enc IS NOT NULL)",
            name="destination",
        ),
    )
    op.create_index("ix_payout_methods_owner_profile_id", "payout_methods", ["owner_profile_id"])
    op.create_index("uq_payout_methods_one_default", "payout_methods", ["owner_profile_id"],
                    unique=True, postgresql_where=sa.text("is_default"))

    op.create_table(
        "listings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_profile_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("title_sw", sa.Text()),
        sa.Column("title_en", sa.Text()),
        sa.Column("description_sw", sa.Text()),
        sa.Column("description_en", sa.Text()),
        sa.Column(
            "attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("region_id", sa.Integer(), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column("ward_id", sa.Integer()),
        sa.Column("address_hint", sa.Text()),
        sa.Column("lat", sa.Numeric(9, 6)),
        sa.Column("lng", sa.Numeric(9, 6)),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deposit_tzs", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("delivery", delivery_option, nullable=False, server_default="none"),
        sa.Column("delivery_fee_tzs", sa.BigInteger()),
        sa.Column("delivery_area", postgresql.ARRAY(sa.Integer())),
        sa.Column("min_duration", sa.Integer()),
        sa.Column("max_duration", sa.Integer()),
        sa.Column("slot_config", postgresql.JSONB()),
        sa.Column("cancellation_policy", cancellation_policy, nullable=False,
                  server_default="moderate"),
        sa.Column("instant_book", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("base_price_tzs", sa.BigInteger()),
        sa.Column("status", listing_status, nullable=False, server_default="draft"),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("pending_changes", postgresql.JSONB()),
        sa.Column("review_state", review_state, nullable=False, server_default="none"),
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', coalesce(title_sw, '') || ' ' || coalesce(title_en, ''))",
                persisted=True,
            ),
        ),
        sa.Column("rating_avg", sa.Numeric(3, 2)),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_listings"),
        sa.ForeignKeyConstraint(["owner_profile_id"], ["owner_profiles.id"],
                                name="fk_listings_owner_profile_id_owner_profiles"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"],
                                name="fk_listings_category_id_categories"),
        sa.ForeignKeyConstraint(["region_id"], ["locations.id"],
                                name="fk_listings_region_id_locations"),
        sa.ForeignKeyConstraint(["district_id"], ["locations.id"],
                                name="fk_listings_district_id_locations"),
        sa.ForeignKeyConstraint(["ward_id"], ["locations.id"],
                                name="fk_listings_ward_id_locations"),
        sa.CheckConstraint("title_sw IS NOT NULL OR title_en IS NOT NULL", name="has_title"),
        sa.CheckConstraint(
            "char_length(coalesce(title_sw, '')) <= 120 AND char_length(coalesce(title_en, '')) <= 120",
            name="title_length",
        ),
        sa.CheckConstraint(
            "description_sw IS NOT NULL OR description_en IS NOT NULL", name="has_description"
        ),
        sa.CheckConstraint(
            "char_length(coalesce(description_sw, '')) <= 5000"
            " AND char_length(coalesce(description_en, '')) <= 5000",
            name="description_length",
        ),
        sa.CheckConstraint("stock >= 1", name="stock_positive"),
        sa.CheckConstraint("deposit_tzs >= 0", name="deposit_non_negative"),
        sa.CheckConstraint("delivery_fee_tzs IS NULL OR delivery_fee_tzs >= 0",
                           name="delivery_fee_non_negative"),
        sa.CheckConstraint("(lat IS NULL) = (lng IS NULL)", name="lat_lng_together"),
        sa.CheckConstraint(
            "min_duration IS NULL OR max_duration IS NULL OR min_duration <= max_duration",
            name="duration_range",
        ),
    )
    op.create_index("ix_listings_owner_profile_id", "listings", ["owner_profile_id"])
    op.create_index("ix_listings_active_category_district", "listings",
                    ["status", "category_id", "district_id"],
                    postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_listings_attributes", "listings", ["attributes"], postgresql_using="gin",
                    postgresql_ops={"attributes": "jsonb_path_ops"})
    op.create_index("ix_listings_base_price_tzs", "listings", ["base_price_tzs"])
    op.create_index("ix_listings_lat_lng", "listings", ["lat", "lng"])
    op.create_index("ix_listings_search_tsv", "listings", ["search_tsv"], postgresql_using="gin")

    op.create_table(
        "listing_photos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column(
            "variants", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alt_sw", sa.Text()),
        sa.Column("alt_en", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_listing_photos"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE",
                                name="fk_listing_photos_listing_id_listings"),
    )
    op.create_index("ix_listing_photos_listing_id", "listing_photos", ["listing_id"])

    op.create_table(
        "listing_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("unit", price_unit, nullable=False),
        sa.Column("amount_tzs", sa.BigInteger(), nullable=False),
        sa.Column("season_start", sa.Date()),
        sa.Column("season_end", sa.Date()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_listing_prices"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE",
                                name="fk_listing_prices_listing_id_listings"),
        sa.CheckConstraint("amount_tzs > 0", name="amount_positive"),
        sa.CheckConstraint(
            "(season_start IS NULL) = (season_end IS NULL)"
            " AND (season_start IS NULL OR season_start <= season_end)",
            name="season_range",
        ),
    )
    op.create_index("ix_listing_prices_listing_id", "listing_prices", ["listing_id"])
    # Exactly one non-seasonal (base) price per unit.
    op.create_index("uq_listing_prices_base_unit", "listing_prices", ["listing_id", "unit"],
                    unique=True, postgresql_where=sa.text("season_start IS NULL"))
    # Seasons of the same unit must not overlap.
    op.execute(
        "ALTER TABLE listing_prices ADD CONSTRAINT ex_listing_prices_season_overlap"
        " EXCLUDE USING gist (listing_id WITH =, unit WITH =,"
        " daterange(season_start, season_end, '[]') WITH &&)"
        " WHERE (season_start IS NOT NULL)"
    )


def downgrade() -> None:
    op.drop_table("listing_prices")
    op.drop_table("listing_photos")
    op.drop_table("listings")
    op.drop_table("payout_methods")
    op.drop_table("owner_profiles")
    bind = op.get_bind()
    for e in reversed(ENUMS):
        e.drop(bind, checkfirst=True)
