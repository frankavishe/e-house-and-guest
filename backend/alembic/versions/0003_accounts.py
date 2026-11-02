"""Accounts: users, otp_codes, refresh_tokens; notifications (T028, T024).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

language = postgresql.ENUM("sw", "en", name="user_language", create_type=False)
user_status = postgresql.ENUM("active", "suspended", "deleted", name="user_status", create_type=False)
channel = postgresql.ENUM("sms", "in_app", name="notification_channel", create_type=False)
n_status = postgresql.ENUM("queued", "sent", "failed", name="notification_status", create_type=False)


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (language, user_status, channel, n_status):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("email", postgresql.CITEXT()),
        sa.Column("language", language, nullable=False, server_default="sw"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", user_status, nullable=False, server_default="active"),
        sa.Column("owner_cancellation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_avg", sa.Numeric(3, 2)),
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
        _created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("phone", name="uq_users_phone"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(r"phone ~ '^\+255[67][0-9]{8}$' OR status = 'deleted'", name="phone_e164"),
    )

    op.create_table(
        "otp_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False, server_default="login"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_otp_codes"),
    )
    op.create_index("ix_otp_codes_phone_created_at", "otp_codes", ["phone", "created_at"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("replaced_by", sa.Uuid()),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("locale", language, nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("status", n_status, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("provider_ref", sa.Text()),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_notifications_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_notifications_user_feed", "notifications", ["user_id", "channel", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("refresh_tokens")
    op.drop_table("otp_codes")
    op.drop_table("users")
    bind = op.get_bind()
    for enum in (n_status, channel, user_status, language):
        enum.drop(bind, checkfirst=True)
