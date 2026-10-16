"""Phone + OTP sign-in, refresh rotation and logout (T025, FR-001, R10)."""

import re

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OtpCode, RefreshToken, User
from app.core import security
from app.integrations import get_sms_provider
from app.integrations.sms.console import ConsoleSmsProvider
from tests.factories import make_user

PHONE = "+255712345678"


def last_code(phone: str = PHONE) -> str:
    sms = get_sms_provider()
    assert isinstance(sms, ConsoleSmsProvider)
    msg = sms.last_to(phone)
    assert msg is not None, "no SMS sent"
    match = re.search(r"\b(\d{6})\b", msg.text)
    assert match
    return match.group(1)


async def request_code(client: httpx.AsyncClient, phone: str = PHONE) -> httpx.Response:
    return await client.post("/api/v1/auth/otp/request", json={"phone": phone})


async def sign_in(client: httpx.AsyncClient, phone: str = PHONE) -> httpx.Response:
    assert (await request_code(client, phone)).status_code == 202
    return await client.post(
        "/api/v1/auth/otp/verify", json={"phone": phone, "code": last_code(phone)}
    )


# --- phone normalisation -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "0712345678",
        "0712 345 678",
        "712345678",
        "255712345678",
        "+255712345678",
        "+255 712-345-678",
    ],
)
def test_phone_normalisation(raw: str) -> None:
    assert security.normalize_phone(raw) == PHONE


@pytest.mark.parametrize("raw", ["0512345678", "071234567", "+254712345678", "abc", ""])
def test_invalid_phones_rejected(raw: str) -> None:
    with pytest.raises(security.InvalidPhone):
        security.normalize_phone(raw)


async def test_invalid_phone_returns_422(client: httpx.AsyncClient) -> None:
    res = await client.post("/api/v1/auth/otp/request", json={"phone": "12345"})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_PHONE"


# --- OTP request / verify ------------------------------------------------------------


async def test_happy_path_creates_user_and_sets_cookies(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    res = await request_code(client, "0712345678")
    assert res.status_code == 202
    assert res.json() == {"expires_in": 300}

    res = await client.post(
        "/api/v1/auth/otp/verify", json={"phone": "0712345678", "code": last_code()}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_new"] is True
    assert body["user"]["phone"] == PHONE
    assert body["user"]["language"] == "sw"
    assert body["user"]["roles"] == ["renter"]
    assert security.ACCESS_COOKIE in res.cookies and security.REFRESH_COOKIE in res.cookies
    set_cookie = ",".join(res.headers.get_list("set-cookie")).lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie

    me = await client.get("/api/v1/me")
    assert me.status_code == 200 and me.json()["phone"] == PHONE

    # Second sign-in: same user, not new.
    client.cookies.clear()
    res = await sign_in(client)
    assert res.json()["is_new"] is False
    users = (await db.execute(select(User).where(User.phone == PHONE))).scalars().all()
    assert len(users) == 1


async def test_code_is_stored_hashed(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await request_code(client)
    row = (await db.execute(select(OtpCode).where(OtpCode.phone == PHONE))).scalar_one()
    assert last_code() not in row.code_hash


async def test_wrong_code_rejected(client: httpx.AsyncClient) -> None:
    await request_code(client)
    wrong = "000000" if last_code() != "000000" else "111111"
    res = await client.post("/api/v1/auth/otp/verify", json={"phone": PHONE, "code": wrong})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "OTP_INVALID"


async def test_five_wrong_attempts_burn_the_code(client: httpx.AsyncClient) -> None:
    await request_code(client)
    code = last_code()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        res = await client.post("/api/v1/auth/otp/verify", json={"phone": PHONE, "code": wrong})
        assert res.status_code == 400
    res = await client.post("/api/v1/auth/otp/verify", json={"phone": PHONE, "code": code})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "OTP_TOO_MANY_ATTEMPTS"


async def test_code_expires_after_5_minutes(client: httpx.AsyncClient, frozen_clock) -> None:
    await request_code(client)
    frozen_clock.advance(minutes=5, seconds=1)
    res = await client.post("/api/v1/auth/otp/verify", json={"phone": PHONE, "code": last_code()})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "OTP_INVALID"


async def test_code_cannot_be_reused(client: httpx.AsyncClient) -> None:
    await request_code(client)
    code = last_code()
    ok = await client.post("/api/v1/auth/otp/verify", json={"phone": PHONE, "code": code})
    assert ok.status_code == 200
    again = await client.post("/api/v1/auth/otp/verify", json={"phone": PHONE, "code": code})
    assert again.status_code == 400


async def test_rate_limit_3_per_15_minutes(client: httpx.AsyncClient, frozen_clock) -> None:
    for _ in range(3):
        assert (await request_code(client)).status_code == 202
        frozen_clock.advance(minutes=1)
    res = await request_code(client)
    assert res.status_code == 429
    assert res.json()["error"]["code"] == "RATE_LIMITED"
    assert int(res.headers["retry-after"]) > 0
    frozen_clock.advance(minutes=13)  # first request now older than 15 min
    assert (await request_code(client)).status_code == 202


async def test_suspended_user_cannot_sign_in(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await make_user(db, phone=PHONE, status="suspended")
    res = await sign_in(client)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "ACCOUNT_SUSPENDED"


# --- refresh / logout ----------------------------------------------------------------


async def test_refresh_rotates_tokens(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await sign_in(client)
    old_refresh = client.cookies.get(security.REFRESH_COOKIE)
    res = await client.post("/api/v1/auth/refresh")
    assert res.status_code == 204
    new_refresh = res.cookies.get(security.REFRESH_COOKIE)
    assert new_refresh and new_refresh != old_refresh
    assert security.ACCESS_COOKIE in res.cookies
    tokens = (await db.execute(select(RefreshToken))).scalars().all()
    assert len(tokens) == 2 and len({t.family_id for t in tokens}) == 1
    old = next(t for t in tokens if t.revoked_at is not None)
    assert old.replaced_by is not None


async def test_refresh_reuse_revokes_family(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await sign_in(client)
    stolen = client.cookies.get(security.REFRESH_COOKIE)
    assert stolen
    assert (await client.post("/api/v1/auth/refresh")).status_code == 204
    current = client.cookies.get(security.REFRESH_COOKIE)

    # Attacker replays the old token → whole family revoked.
    attacker = httpx.AsyncClient(transport=client._transport, base_url="http://test")
    attacker.cookies.set(security.REFRESH_COOKIE, stolen)
    assert (await attacker.post("/api/v1/auth/refresh")).status_code == 401
    await attacker.aclose()

    client.cookies.set(security.REFRESH_COOKIE, current or "")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    tokens = (await db.execute(select(RefreshToken))).scalars().all()
    assert all(t.revoked_at is not None for t in tokens)


async def test_refresh_without_cookie_is_401(client: httpx.AsyncClient) -> None:
    res = await client.post("/api/v1/auth/refresh")
    assert res.status_code == 401


async def test_logout_revokes_family_and_clears_cookies(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client)
    refresh = client.cookies.get(security.REFRESH_COOKIE)
    res = await client.post("/api/v1/auth/logout")
    assert res.status_code == 204
    tokens = (await db.execute(select(RefreshToken))).scalars().all()
    assert tokens and all(t.revoked_at is not None for t in tokens)
    assert (await client.get("/api/v1/me")).status_code == 401
    client.cookies.set(security.REFRESH_COOKIE, refresh or "")
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401


async def test_expired_access_token_is_401(client: httpx.AsyncClient, frozen_clock) -> None:
    await sign_in(client)
    frozen_clock.advance(minutes=16)
    res = await client.get("/api/v1/me")
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHENTICATED"


# --- /me -------------------------------------------------------------------------------


async def test_patch_me_updates_profile(client: httpx.AsyncClient) -> None:
    await sign_in(client)
    res = await client.patch(
        "/api/v1/me", json={"name": "Asha Mushi", "email": "Asha@Example.com", "language": "en"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Asha Mushi" and body["language"] == "en"
    assert body["email"] == "Asha@Example.com"


async def test_patch_me_rejects_bad_values(client: httpx.AsyncClient) -> None:
    await sign_in(client)
    for payload in ({"language": "fr"}, {"email": "not-an-email"}, {"name": ""}):
        res = await client.patch("/api/v1/me", json=payload)
        assert res.status_code == 422, payload


async def test_email_must_be_unique_case_insensitive(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    other = await make_user(db)
    other.email = "taken@example.com"
    await db.flush()
    await sign_in(client)
    res = await client.patch("/api/v1/me", json={"email": "TAKEN@example.com"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EMAIL_TAKEN"
