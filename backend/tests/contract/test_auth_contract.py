"""Request/response shapes for /auth/*, /me and /health (T027, contracts/rest-api.md)."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from tests.factories import make_user, sign_in

ERROR_KEYS = {"code", "message", "details"}


def operation(path: str, method: str) -> dict:
    return app.openapi()["paths"][path][method]


def test_auth_paths_are_documented() -> None:
    paths = app.openapi()["paths"]
    for path, method in [
        ("/api/v1/auth/otp/request", "post"),
        ("/api/v1/auth/otp/verify", "post"),
        ("/api/v1/auth/refresh", "post"),
        ("/api/v1/auth/logout", "post"),
        ("/api/v1/me", "get"),
        ("/api/v1/me", "patch"),
        ("/api/v1/health", "get"),
    ]:
        assert method in paths.get(path, {}), f"{method.upper()} {path} missing"
    assert "202" in operation("/api/v1/auth/otp/request", "post")["responses"]
    assert "204" in operation("/api/v1/auth/refresh", "post")["responses"]
    assert "204" in operation("/api/v1/auth/logout", "post")["responses"]


async def test_me_response_shape(client: httpx.AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db, name="Juma")
    sign_in(client, user)
    body = (await client.get("/api/v1/me")).json()
    assert set(body) == {"id", "phone", "name", "email", "language", "roles", "owner_profile"}
    assert body["roles"] == ["renter"] and body["owner_profile"] is None


async def test_errors_use_common_envelope(client: httpx.AsyncClient) -> None:
    for res in (
        await client.get("/api/v1/me"),
        await client.post("/api/v1/auth/otp/request", json={}),
        await client.post("/api/v1/auth/otp/verify", json={"phone": "0712345678", "code": "x"}),
    ):
        assert res.status_code in (400, 401, 422)
        assert set(res.json()["error"]) == ERROR_KEYS


async def test_verify_response_shape(client: httpx.AsyncClient) -> None:
    from tests.integration.test_auth import sign_in as otp_sign_in

    body = (await otp_sign_in(client)).json()
    assert set(body) == {"user", "is_new"}
    assert set(body["user"]) == {
        "id",
        "phone",
        "name",
        "email",
        "language",
        "roles",
        "owner_profile",
    }
