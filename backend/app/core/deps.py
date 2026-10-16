"""Authentication and authorization dependencies (FR-002, R10).

Access: 🌐 public (no dependency), 👤 `CurrentUser`, 🏠 `require_owner` /
`require_verified_owner`, 🛡 `require_admin`.
"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User, UserStatus, VerificationStatus
from app.core import security
from app.core.db import get_session
from app.core.errors import AppError, forbidden, unauthenticated

Session = Annotated[AsyncSession, Depends(get_session)]


def _token(request: Request) -> str | None:
    token = request.cookies.get(security.ACCESS_COOKIE)
    if token:
        return token
    auth = request.headers.get("authorization", "")
    scheme, _, value = auth.partition(" ")
    return value.strip() or None if scheme.lower() == "bearer" else None


async def optional_user(request: Request, session: Session) -> User | None:
    token = _token(request)
    if not token:
        return None
    user_id = security.decode_access_token(token)
    if user_id is None:
        return None
    user = await session.get(User, user_id)
    if user is None or user.status == UserStatus.DELETED:
        return None
    if user.status == UserStatus.SUSPENDED:
        raise AppError("ACCOUNT_SUSPENDED", 403)
    return user


async def current_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise unauthenticated()
    return user


CurrentUser = Annotated[User, Depends(current_user)]
OptionalUser = Annotated[User | None, Depends(optional_user)]


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise forbidden()
    return user


AdminUser = Annotated[User, Depends(require_admin)]


async def require_owner(user: CurrentUser, session: Session) -> OwnerProfile:
    """🏠 The signed-in user's owner profile, in any verification state."""
    profile = (
        await session.execute(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    ).scalar_one_or_none()
    if profile is None:
        raise forbidden()
    return profile


Owner = Annotated[OwnerProfile, Depends(require_owner)]


async def require_verified_owner(profile: Owner) -> OwnerProfile:
    """🏠 (verified) Required to submit listings for review."""
    if profile.verification_status != VerificationStatus.VERIFIED:
        raise AppError("OWNER_NOT_VERIFIED", 403)
    return profile


VerifiedOwner = Annotated[OwnerProfile, Depends(require_verified_owner)]
