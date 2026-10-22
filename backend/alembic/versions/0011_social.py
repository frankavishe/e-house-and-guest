"""Conversations, messages, reviews and abuse reports (T128, US6).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


review_subject = enum("review_subject", "listing", "renter")
report_target = enum("report_target", "listing", "user")
report_status = enum("report_status", "open", "actioned", "dismissed")
ENUMS = (review_subject, report_target, report_status)


def created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def updated_at() -> sa.Column:
    return sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    bind = op.get_bind()
    for e in ENUMS:
        e.create(bind, checkfirst=True)

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("listing_id", sa.Uuid(), nullable=False),
        sa.Column("renter_id", sa.Uuid(), nullable=False),
        sa.Column("owner_profile_id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid()),
        sa.Column("last_message_at", sa.DateTime(timezone=True)),
        created_at(),
        updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name="fk_conversations_listing_id_listings"
        ),
        sa.ForeignKeyConstraint(
            ["renter_id"], ["users.id"], name="fk_conversations_renter_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["owner_profile_id"],
            ["owner_profiles.id"],
            name="fk_conversations_owner_profile_id_owner_profiles",
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name="fk_conversations_booking_id_bookings"
        ),
        sa.UniqueConstraint("listing_id", "renter_id", name="uq_conversations_listing_id"),
    )
    op.create_index("ix_conversations_renter_id", "conversations", ["renter_id"])
    op.create_index("ix_conversations_owner_profile_id", "conversations", ["owner_profile_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_masked", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
            name="fk_messages_conversation_id_conversations",
        ),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], name="fk_messages_sender_id_users"),
        sa.UniqueConstraint("seq", name="uq_messages_seq"),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="body_length"),
    )
    op.create_index("ix_messages_conversation_id_seq", "messages", ["conversation_id", "seq"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("subject", review_subject, nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("body", sa.Text()),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_reviews"),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name="fk_reviews_booking_id_bookings"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_reviews_author_id_users"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        sa.CheckConstraint("char_length(body) <= 1000", name="body_length"),
    )
    op.create_index(
        "uq_reviews_booking_id_author_id", "reviews", ["booking_id", "author_id"], unique=True
    )

    op.create_table(
        "abuse_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reporter_id", sa.Uuid(), nullable=False),
        sa.Column("target_kind", report_target, nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", report_status, nullable=False),
        sa.Column("handled_by", sa.Uuid()),
        sa.Column("handled_at", sa.DateTime(timezone=True)),
        created_at(),
        updated_at(),
        sa.PrimaryKeyConstraint("id", name="pk_abuse_reports"),
        sa.ForeignKeyConstraint(
            ["reporter_id"], ["users.id"], name="fk_abuse_reports_reporter_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["handled_by"], ["users.id"], name="fk_abuse_reports_handled_by_users"
        ),
    )
    op.create_index("ix_abuse_reports_status_created_at", "abuse_reports", ["status", "created_at"])
    op.create_index("ix_abuse_reports_target", "abuse_reports", ["target_kind", "target_id"])
    op.create_index(
        "uq_abuse_reports_one_open",
        "abuse_reports",
        ["reporter_id", "target_kind", "target_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_table("abuse_reports")
    op.drop_table("reviews")
    op.drop_table("messages")
    op.drop_table("conversations")
    bind = op.get_bind()
    for e in reversed(ENUMS):
        e.drop(bind, checkfirst=True)
