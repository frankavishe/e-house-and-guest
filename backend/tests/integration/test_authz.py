"""Access levels: public, signed in, owner, admin; suspended users (T026, FR-002).

Probe routes are mounted on a separate app instance so the real OpenAPI stays clean.
"""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerKind, OwnerProfile, VerificationStatus
from app.core import security
from app.core.db import get_session
from app.core.deps import AdminUser, CurrentUser, OptionalUser, Owner, VerifiedOwner
from app.main import create_app
from tests.factories import make_user, sign_in

probe = APIRouter(prefix="/probe")


@probe.get("/public")
async def public(user: OptionalUser) -> dict[str, str | None]:
    return {"user": str(user.id) if user else None}


@probe.get("/signed-in")
async def signed_in(user: CurrentUser) -> dict[str, str]:
    return {"user": str(user.id)}


@probe.get("/admin")
async def admin(user: AdminUser) -> dict[str, str]:
    return {"user": str(user.id)}


@probe.get("/owner")
async def owner(profile: Owner) -> dict[str, str]:
    return {"owner": str(profile.id)}


@probe.get("/verified-owner")
async def verified_owner(profile: VerifiedOwner) -> dict[str, str]:
    return {"owner": str(profile.id)}


@pytest_asyncio.fixture(loop_scope="session")
async def probe_client(db: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.include_router(probe)

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = _session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_public_route_needs_no_auth(probe_client: httpx.AsyncClient) -> None:
    res = await probe_client.get("/probe/public")
    assert res.status_code == 200 and res.json() == {"user": None}


async def test_signed_in_route(probe_client: httpx.AsyncClient, db: AsyncSession) -> None:
    assert (await probe_client.get("/probe/signed-in")).status_code == 401
    user = await make_user(db)
    sign_in(probe_client, user)
    res = await probe_client.get("/probe/signed-in")
    assert res.status_code == 200 and res.json() == {"user": str(user.id)}


async def test_admin_route(probe_client: httpx.AsyncClient, db: AsyncSession) -> None:
    assert (await probe_client.get("/probe/admin")).status_code == 401
    sign_in(probe_client, await make_user(db))
    res = await probe_client.get("/probe/admin")
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"
    sign_in(probe_client, await make_user(db, is_admin=True))
    assert (await probe_client.get("/probe/admin")).status_code == 200


async def test_admin_flag_is_read_from_db_not_token(
    probe_client: httpx.AsyncClient, db: AsyncSession
) -> None:
    user = await make_user(db, is_admin=True)
    sign_in(probe_client, user)
    user.is_admin = False  # admin rights revoked after the token was issued
    await db.flush()
    assert (await probe_client.get("/probe/admin")).status_code == 403


async def test_suspended_user_rejected(probe_client: httpx.AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db, status="suspended")
    sign_in(probe_client, user)
    res = await probe_client.get("/probe/signed-in")
    assert res.status_code == 403 and res.json()["error"]["code"] == "ACCOUNT_SUSPENDED"


async def test_deleted_user_treated_as_signed_out(
    probe_client: httpx.AsyncClient, db: AsyncSession
) -> None:
    sign_in(probe_client, await make_user(db, status="deleted"))
    assert (await probe_client.get("/probe/signed-in")).status_code == 401


async def test_tampered_token_rejected(probe_client: httpx.AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db)
    token = security.encode_access_token(user.id)
    probe_client.cookies.set(security.ACCESS_COOKIE, token[:-2] + "xx")
    assert (await probe_client.get("/probe/signed-in")).status_code == 401


async def test_bearer_header_accepted(probe_client: httpx.AsyncClient, db: AsyncSession) -> None:
    user = await make_user(db)
    token = security.encode_access_token(user.id)
    res = await probe_client.get("/probe/signed-in", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


async def _owner(db: AsyncSession, status: VerificationStatus) -> tuple:
    user = await make_user(db)
    profile = OwnerProfile(
        user_id=user.id,
        kind=OwnerKind.INDIVIDUAL,
        display_name="Mama Neema",
        verification_status=status,
        rejection_reason="docs unclear" if status == VerificationStatus.REJECTED else None,
    )
    db.add(profile)
    await db.flush()
    return user, profile


async def test_owner_routes(probe_client: httpx.AsyncClient, db: AsyncSession) -> None:
    assert (await probe_client.get("/probe/owner")).status_code == 401
    sign_in(probe_client, await make_user(db))  # renter without an owner profile
    assert (await probe_client.get("/probe/owner")).status_code == 403
    assert (await probe_client.get("/probe/verified-owner")).status_code == 403

    user, profile = await _owner(db, VerificationStatus.PENDING)
    sign_in(probe_client, user)
    res = await probe_client.get("/probe/owner")
    assert res.status_code == 200 and res.json() == {"owner": str(profile.id)}
    res = await probe_client.get("/probe/verified-owner")
    assert res.status_code == 403 and res.json()["error"]["code"] == "OWNER_NOT_VERIFIED"

    user, _ = await _owner(db, VerificationStatus.VERIFIED)
    sign_in(probe_client, user)
    assert (await probe_client.get("/probe/verified-owner")).status_code == 200


async def test_me_reports_owner_role(client: httpx.AsyncClient, db: AsyncSession) -> None:
    user, profile = await _owner(db, VerificationStatus.VERIFIED)
    sign_in(client, user)
    body = (await client.get("/api/v1/me")).json()
    assert body["roles"] == ["renter", "owner"]
    assert body["owner_profile"] == {
        "id": str(profile.id),
        "kind": "individual",
        "display_name": "Mama Neema",
        "verification_status": "verified",
    }
