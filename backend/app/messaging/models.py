"""Conversations between a renter and a listing's owner, and their messages (data-model.md
"Trust & communication", FR-028)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, Timestamps, UUIDPk

MESSAGE_MAX = 2000


class Conversation(UUIDPk, Timestamps, Base):
    """One thread per (listing, renter); the renter starts it. `booking_id` is the latest
    booking of that listing by that renter which reveals phone numbers (R18)."""

    __tablename__ = "conversations"

    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), nullable=False)
    renter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    owner_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("owner_profiles.id"), nullable=False, index=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bookings.id"))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("listing_id", "renter_id"),)


class Message(UUIDPk, CreatedAt, Base):
    """`seq` orders messages and is the polling cursor (`?after=`). `body_masked` records that
    phone numbers were hidden when it was sent."""

    __tablename__ = "messages"

    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True, nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_masked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_messages_conversation_id_seq", "conversation_id", "seq"),
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {MESSAGE_MAX}", name="body_length"),
    )
