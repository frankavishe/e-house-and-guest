"""Test data helpers. Each returns persisted (flushed) rows inside the test transaction."""

import itertools

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import Language, User, UserStatus
from app.core import security

_phones = itertools.count(1)


def next_phone() -> str:
    return f"+25571{next(_phones):07d}"


async def make_user(
    db: AsyncSession,
    *,
    phone: str | None = None,
    name: str | None = "Test User",
    is_admin: bool = False,
    status: str = "active",
    language: str = "sw",
) -> User:
    user = User(
        phone=phone or next_phone(),
        name=name,
        is_admin=is_admin,
        status=UserStatus(status),
        language=Language(language),
    )
    db.add(user)
    await db.flush()
    return user


def sign_in(client: httpx.AsyncClient, user: User) -> None:
    """Attach an access-token cookie for `user` to the client (skips the OTP flow)."""
    client.cookies.set(
        security.ACCESS_COOKIE, security.encode_access_token(user.id, is_admin=user.is_admin)
    )
