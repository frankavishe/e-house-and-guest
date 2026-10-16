"""Users, OTP codes and refresh tokens (data-model.md "Accounts & identity")."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAt, Timestamps, UUIDPk


class Language(StrEnum):
    SW = "sw"
    EN = "en"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


def pg_enum(enum: type[StrEnum], name: str) -> Enum:
    """Native Postgres enum storing the member values."""
    return Enum(enum, name=name, values_callable=lambda e: [m.value for m in e])


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    phone: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    language: Mapped[Language] = mapped_column(
        pg_enum(Language, "user_language"), nullable=False, default=Language.SW
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, "user_status"), nullable=False, default=UserStatus.ACTIVE
    )
    owner_cancellation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rating_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class OtpCode(UUIDPk, CreatedAt, Base):
    __tablename__ = "otp_codes"

    phone: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="login")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_otp_codes_phone_created_at", "phone", "created_at"),)


class RefreshToken(UUIDPk, CreatedAt, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column()


# --- owners (T039) -----------------------------------------------------------------------


class OwnerKind(StrEnum):
    INDIVIDUAL = "individual"
    BUSINESS = "business"


class VerificationStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class PayoutKind(StrEnum):
    MOBILE_MONEY = "mobile_money"
    BANK = "bank"


class PaymentNetwork(StrEnum):
    MPESA = "mpesa"
    MIXX = "mixx"
    AIRTEL = "airtel"
    HALOPESA = "halopesa"
    AZAMPESA = "azampesa"


class OwnerProfile(UUIDPk, Timestamps, Base):
    __tablename__ = "owner_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    kind: Mapped[OwnerKind] = mapped_column(pg_enum(OwnerKind, "owner_kind"), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    # NIDA, TIN and bank numbers are Fernet-encrypted (R18) and never returned in full.
    nida_number_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    business_name: Mapped[str | None] = mapped_column(Text)
    brela_reg_no: Mapped[str | None] = mapped_column(Text)
    tin_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    documents: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        pg_enum(VerificationStatus, "verification_status"),
        nullable=False,
        default=VerificationStatus.DRAFT,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    rating_avg: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class PayoutMethod(UUIDPk, Timestamps, Base):
    __tablename__ = "payout_methods"

    owner_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("owner_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[PayoutKind] = mapped_column(pg_enum(PayoutKind, "payout_kind"), nullable=False)
    network: Mapped[PaymentNetwork | None] = mapped_column(
        pg_enum(PaymentNetwork, "payment_network")
    )
    msisdn: Mapped[str | None] = mapped_column(Text)
    bank_name: Mapped[str | None] = mapped_column(Text)
    account_name: Mapped[str] = mapped_column(Text, nullable=False)
    account_number_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index(
            "uq_payout_methods_one_default",
            "owner_profile_id",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )
