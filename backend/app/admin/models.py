"""Admin audit log (data-model.md "admin_audit_log"): one row per admin mutation."""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, UUIDPk


class AdminAuditLog(UUIDPk, CreatedAt, Base):
    __tablename__ = "admin_audit_log"

    admin_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (
        Index("ix_admin_audit_log_target", "target_kind", "target_id"),
        Index("ix_admin_audit_log_admin", "admin_id", "created_at"),
    )
