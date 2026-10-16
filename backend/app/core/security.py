"""Security helpers (R10, R18): phones, OTPs, JWTs, refresh tokens, encryption, cookies."""

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet
from fastapi import Response

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"
# The refresh cookie is only sent to the auth endpoints.
REFRESH_COOKIE_PATH = "/api/v1/auth"
JWT_ALGORITHM = "HS256"

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5
OTP_RATE_LIMIT = 3
OTP_RATE_WINDOW = timedelta(minutes=15)


# --- phones ------------------------------------------------------------------------------

_PHONE_NOISE = re.compile(r"[\s\-().]")
_LOCAL = re.compile(r"^[67]\d{8}$")


class InvalidPhone(AppError):
    def __init__(self) -> None:
        super().__init__("INVALID_PHONE", 422)


def normalize_phone(raw: str) -> str:
    """Tanzanian mobile number → E.164 `+255[67]XXXXXXXX`. Raises InvalidPhone."""
    digits = _PHONE_NOISE.sub("", raw or "")
    if digits.startswith("+255"):
        local = digits[4:]
    elif digits.startswith("255") and len(digits) == 12:
        local = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        local = digits[1:]
    else:
        local = digits
    if not _LOCAL.match(local):
        raise InvalidPhone()
    return f"+255{local}"


# --- OTP ---------------------------------------------------------------------------------


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(phone: str, code: str) -> str:
    key = get_settings().otp_hmac_key.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def verify_otp(phone: str, code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(phone, code), code_hash)


# --- JWT access tokens -------------------------------------------------------------------


def encode_access_token(user_id: uuid.UUID, *, is_admin: bool = False) -> str:
    settings = get_settings()
    now = clock.now()
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "adm": is_admin,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_access_ttl_seconds)).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    """User id from a valid, unexpired access token; None otherwise."""
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False, "require": ["sub", "exp", "typ"]},
        )
    except jwt.PyJWTError:
        return None
    # Expiry is checked against the injectable clock (tests freeze time).
    if claims.get("typ") != "access" or int(claims["exp"]) <= int(clock.now().timestamp()):
        return None
    try:
        return uuid.UUID(str(claims["sub"]))
    except ValueError:
        return None


# --- refresh tokens ----------------------------------------------------------------------


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- encryption at rest (NIDA, TIN, bank account numbers) ---------------------------------


def _fernet() -> Fernet:
    return Fernet(get_settings().fernet_key.encode())


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(value: bytes) -> str:
    return _fernet().decrypt(value).decode()


def mask_tail(value: str, keep: int = 4) -> str:
    """`19900101123450000123` → `****0123` for display."""
    return "****" + value[-keep:] if len(value) > keep else "****"


# --- cookies -----------------------------------------------------------------------------


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    settings = get_settings()
    common: dict[str, Any] = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
    }
    response.set_cookie(
        ACCESS_COOKIE, access, max_age=settings.jwt_access_ttl_seconds, path="/", **common
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=settings.jwt_refresh_ttl_seconds,
        path=REFRESH_COOKIE_PATH,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    for name, path in ((ACCESS_COOKIE, "/"), (REFRESH_COOKIE, REFRESH_COOKIE_PATH)):
        response.delete_cookie(
            name, path=path, secure=settings.cookie_secure, httponly=True, samesite="lax"
        )
