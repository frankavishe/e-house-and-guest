"""Notifications: one row per event per channel (data-model.md, FR-019)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.accounts.models import Language, pg_enum
from app.core.db import Base, CreatedAt, UUIDPk


class Channel(StrEnum):
    SMS = "sms"
    IN_APP = "in_app"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"


class Notification(UUIDPk, CreatedAt, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[Channel] = mapped_column(pg_enum(Channel, "notification_channel"))
    locale: Mapped[Language] = mapped_column(pg_enum(Language, "user_language"))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[NotificationStatus] = mapped_column(
        pg_enum(NotificationStatus, "notification_status"), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_ref: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_notifications_user_feed", "user_id", "channel", "created_at"),)
