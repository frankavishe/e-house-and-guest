"""Sign-in with phone + OTP, refresh-token rotation and profile updates (R10, FR-001)."""

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import (
    Language,
    OtpCode,
    OwnerProfile,
    RefreshToken,
    User,
    UserStatus,
)
from app.accounts.schemas import MePatch, OwnerProfileSummary, Role, UserOut
from app.core import clock, security
from app.core.config import get_settings
from app.core.db import uuid7
from app.core.errors import AppError, unauthenticated
from app.core.i18n import Locale, t
from app.integrations import get_sms_provider

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignedIn:
    user: User
    is_new: bool
    access_token: str
    refresh_token: str


# --- OTP ---------------------------------------------------------------------------------


async def request_otp(session: AsyncSession, raw_phone: str, locale: Locale) -> int:
    """Create and send a code. Returns its lifetime in seconds."""
    phone = security.normalize_phone(raw_phone)
    now = clock.now()
    window_start = now - security.OTP_RATE_WINDOW
    recent = (
        await session.execute(
            select(func.count(), func.min(OtpCode.created_at)).where(
                OtpCode.phone == phone, OtpCode.created_at > window_start
            )
        )
    ).one()
    count, oldest = int(recent[0]), recent[1]
    if count >= security.OTP_RATE_LIMIT and oldest is not None:
        retry_after = math.ceil((oldest + security.OTP_RATE_WINDOW - now).total_seconds())
        raise AppError("RATE_LIMITED", 429, {"retry_after": max(retry_after, 1)})

    code = security.generate_otp()
    session.add(
        OtpCode(
            phone=phone,
            code_hash=security.hash_otp(phone, code),
            expires_at=now + security.OTP_TTL,
            created_at=now,
        )
    )
    user_language = (
        await session.execute(select(User.language).where(User.phone == phone))
    ).scalar_one_or_none()
    await session.commit()

    # Sent directly (not via the job outbox) so the code is never stored in plain text.
    text = t("sms.otp", user_language or locale, code=code)
    result = await get_sms_provider().send(to=phone, text=text)
    if not result.ok:
        log.warning("OTP SMS to %s failed: %s", phone, result.failure_reason)
    return int(security.OTP_TTL.total_seconds())


async def verify_otp(session: AsyncSession, raw_phone: str, code: str, locale: Locale) -> SignedIn:
    phone = security.normalize_phone(raw_phone)
    now = clock.now()
    otp = (
        await session.execute(
            select(OtpCode)
            .where(OtpCode.phone == phone, OtpCode.consumed_at.is_(None))
            .order_by(OtpCode.created_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if otp is None or otp.expires_at <= now:
        raise AppError("OTP_INVALID", 400)
    if otp.attempts >= security.OTP_MAX_ATTEMPTS:
        raise AppError("OTP_TOO_MANY_ATTEMPTS", 400)
    if not security.verify_otp(phone, code.strip(), otp.code_hash):
        otp.attempts += 1
        await session.commit()
        raise AppError("OTP_INVALID", 400)
    otp.consumed_at = now

    user = (await session.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
    is_new = user is None
    if user is None:
        user = User(phone=phone, language=Language(locale))
        session.add(user)
        await session.flush()
    elif user.status == UserStatus.SUSPENDED:
        await session.commit()
        raise AppError("ACCOUNT_SUSPENDED", 403)

    _, refresh = await _issue_refresh(session, user.id, family_id=uuid7())
    await session.commit()
    return SignedIn(
        user=user,
        is_new=is_new,
        access_token=security.encode_access_token(user.id, is_admin=user.is_admin),
        refresh_token=refresh,
    )


# --- refresh tokens ----------------------------------------------------------------------


async def _issue_refresh(
    session: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID
) -> tuple[uuid.UUID, str]:
    """Store a new refresh token; returns its row id and the raw value for the cookie."""
    raw = security.new_refresh_token()
    ttl = timedelta(seconds=get_settings().jwt_refresh_ttl_seconds)
    token_id = uuid7()
    session.add(
        RefreshToken(
            id=token_id,
            user_id=user_id,
            token_hash=security.hash_token(raw),
            family_id=family_id,
            expires_at=clock.now() + ttl,
        )
    )
    await session.flush()
    return token_id, raw


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=clock.now())
    )


async def rotate_refresh(session: AsyncSession, raw: str | None) -> SignedIn:
    """Exchange a refresh token for new tokens. Reusing a rotated token revokes its family."""
    if not raw:
        raise unauthenticated()
    token = (
        await session.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == security.hash_token(raw))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if token is None:
        raise unauthenticated()
    now = clock.now()
    if token.revoked_at is not None:
        log.warning("refresh token reuse detected; revoking family %s", token.family_id)
        await _revoke_family(session, token.family_id)
        await session.commit()
        raise unauthenticated()
    if token.expires_at <= now:
        raise unauthenticated()
    user = await session.get(User, token.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        await _revoke_family(session, token.family_id)
        await session.commit()
        raise unauthenticated()

    new_id, new_raw = await _issue_refresh(session, user.id, token.family_id)
    token.revoked_at = now
    token.replaced_by = new_id
    await session.commit()
    return SignedIn(
        user=user,
        is_new=False,
        access_token=security.encode_access_token(user.id, is_admin=user.is_admin),
        refresh_token=new_raw,
    )


async def logout(session: AsyncSession, user: User, raw: str | None) -> None:
    if raw:
        token = (
            await session.execute(
                select(RefreshToken).where(
                    RefreshToken.token_hash == security.hash_token(raw),
                    RefreshToken.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if token is not None:
            await _revoke_family(session, token.family_id)
    await session.commit()


# --- profile -----------------------------------------------------------------------------


async def owner_profile_summary(session: AsyncSession, user: User) -> OwnerProfileSummary | None:
    profile = (
        await session.execute(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        return None
    return OwnerProfileSummary(
        id=profile.id,
        kind=profile.kind.value,
        display_name=profile.display_name,
        verification_status=profile.verification_status.value,
    )


async def user_out(session: AsyncSession, user: User) -> UserOut:
    profile = await owner_profile_summary(session, user)
    roles: list[Role] = ["renter"]
    if profile is not None:
        roles.append("owner")
    if user.is_admin:
        roles.append("admin")
    return UserOut(
        id=user.id,
        phone=user.phone,
        name=user.name,
        email=user.email,
        language=user.language.value,
        roles=roles,
        owner_profile=profile,
    )


async def update_me(session: AsyncSession, user: User, patch: MePatch) -> User:
    fields = patch.model_fields_set
    if "name" in fields and patch.name is not None:
        user.name = patch.name
    if "email" in fields:
        user.email = patch.email or None
    if "language" in fields and patch.language is not None:
        user.language = Language(patch.language)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise AppError("EMAIL_TAKEN", 409) from None
    await session.commit()
    return user
