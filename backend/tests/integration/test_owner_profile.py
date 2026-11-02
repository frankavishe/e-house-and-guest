"""Owner onboarding and verification (T094, FR-004, US7-AS2)."""

import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, PayoutMethod, User, VerificationStatus
from app.accounts.owner_service import DOCUMENT_MAX_BYTES
from app.admin.models import AdminAuditLog
from app.core.security import decrypt
from app.integrations import get_storage
from app.notifications.models import Notification
from tests.factories import make_admin, make_owner, make_user, sign_in

NIDA = "19900101123450000123"
TIN = "123456789"


async def _profile(db: AsyncSession, profile_id: str) -> OwnerProfile:
    row = (
        await db.execute(
            select(OwnerProfile)
            .where(OwnerProfile.id == uuid.UUID(profile_id))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return row


async def _individual(client: httpx.AsyncClient, db: AsyncSession) -> dict:
    sign_in(client, await make_user(db, name="Neema Owner"))
    r = await client.post(
        "/api/v1/owner-profile",
        json={"kind": "individual", "display_name": "Neema Rentals", "nida_number": NIDA},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_individual_requires_nida(client: httpx.AsyncClient, db: AsyncSession) -> None:
    sign_in(client, await make_user(db))
    r = await client.post(
        "/api/v1/owner-profile", json={"kind": "individual", "display_name": "No ID"}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_business_requires_brela_and_tin(client: httpx.AsyncClient, db: AsyncSession) -> None:
    sign_in(client, await make_user(db))
    base = {"kind": "business", "display_name": "Kampuni", "business_name": "Kampuni Ltd"}
    r = await client.post("/api/v1/owner-profile", json={**base, "tin": TIN})
    assert r.status_code == 422  # no BRELA number
    r = await client.post("/api/v1/owner-profile", json={**base, "brela_reg_no": "BRELA-1"})
    assert r.status_code == 422  # no TIN

    r = await client.post(
        "/api/v1/owner-profile", json={**base, "brela_reg_no": "BRELA-1", "tin": TIN}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "business" and body["business_name"] == "Kampuni Ltd"
    assert body["tin_masked"] == "****6789" and TIN not in r.text


async def test_numbers_are_encrypted_and_never_returned(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    body = await _individual(client, db)
    assert body["verification_status"] == "draft"
    assert body["nida_number_masked"] == "****0123"

    row = await _profile(db, body["id"])
    assert row.nida_number_enc is not None and NIDA.encode() not in row.nida_number_enc
    assert decrypt(row.nida_number_enc) == NIDA

    for path in ("/api/v1/owner-profile", "/api/v1/me"):
        r = await client.get(path)
        assert r.status_code == 200 and NIDA not in r.text
    me = (await client.get("/api/v1/me")).json()
    assert me["owner_profile"]["verification_status"] == "draft"
    assert "owner" in me["roles"]


async def test_one_profile_per_user(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _individual(client, db)
    r = await client.post(
        "/api/v1/owner-profile",
        json={"kind": "individual", "display_name": "Again", "nida_number": NIDA},
    )
    assert r.status_code == 409


async def test_documents_are_presigned_to_the_private_bucket(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    profile = await _individual(client, db)
    r = await client.post("/api/v1/owner-profile/documents", json={"content_type": "image/jpeg"})
    assert r.status_code == 200, r.text
    upload = r.json()
    assert "/private/" in upload["upload_url"]
    assert upload["storage_key"].startswith(f"owner-docs/{profile['id']}/")

    key = upload["storage_key"]
    r = await client.patch("/api/v1/owner-profile", json={"documents": [key]})
    assert r.status_code == 422  # not uploaded yet

    # An oversized upload is refused and deleted (a presigned PUT cannot limit the size).
    storage = get_storage()
    await storage.put(key, b"x" * (DOCUMENT_MAX_BYTES + 1), "image/jpeg", private=True)
    r = await client.patch("/api/v1/owner-profile", json={"documents": [key]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert await storage.size(key, private=True) is None

    await storage.put(key, b"jpeg", "image/jpeg", private=True)
    r = await client.patch("/api/v1/owner-profile", json={"documents": [key]})
    assert r.status_code == 200 and r.json()["documents"] == [key]

    r = await client.patch("/api/v1/owner-profile", json={"documents": ["owner-docs/other/x"]})
    assert r.status_code == 422


async def test_reject_and_resubmit_then_verify(client: httpx.AsyncClient, db: AsyncSession) -> None:
    profile = await _individual(client, db)
    owner_client_user = (await _profile(db, profile["id"])).user_id

    r = await client.patch("/api/v1/owner-profile", json={"display_name": "Neema Homes"})
    assert r.status_code == 200 and r.json()["display_name"] == "Neema Homes"

    r = await client.post("/api/v1/owner-profile/submit")
    assert r.status_code == 200 and r.json()["verification_status"] == "pending"
    again = await client.post("/api/v1/owner-profile/submit")
    assert again.status_code == 409 and again.json()["error"]["code"] == "INVALID_TRANSITION"
    locked = await client.patch("/api/v1/owner-profile", json={"display_name": "X"})
    assert locked.status_code == 409

    admin = await make_admin(db)
    sign_in(client, admin)
    queue = (await client.get("/api/v1/admin/owner-verifications?status=pending")).json()
    item = next(i for i in queue["items"] if i["id"] == profile["id"])
    assert item["nida_number"] == NIDA  # admins verify against the full number

    no_reason = await client.post(f"/api/v1/admin/owner-verifications/{profile['id']}/reject")
    assert no_reason.status_code == 422
    r = await client.post(
        f"/api/v1/admin/owner-verifications/{profile['id']}/reject",
        json={"reason": "ID photo unreadable"},
    )
    assert r.status_code == 200, r.text
    row = await _profile(db, profile["id"])
    assert row.verification_status == VerificationStatus.REJECTED
    assert row.rejection_reason == "ID photo unreadable"

    notes = (
        (
            await db.execute(
                select(Notification.event).where(Notification.user_id == owner_client_user)
            )
        )
        .scalars()
        .all()
    )
    assert "owner.rejected" in notes
    audit = (
        (await db.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == row.id)))
        .scalars()
        .all()
    )
    assert [a.action for a in audit] == ["owner.reject"]
    assert audit[0].admin_id == admin.id
    assert audit[0].before["verification_status"] == "pending"
    assert audit[0].after["verification_status"] == "rejected"

    # The owner sees the reason, fixes the profile and resubmits.
    sign_in(client, await db.get_one(User, owner_client_user))
    mine = (await client.get("/api/v1/owner-profile")).json()
    assert mine["verification_status"] == "rejected"
    assert mine["rejection_reason"] == "ID photo unreadable"
    assert (await client.patch("/api/v1/owner-profile", json={"display_name": "N"})).is_success
    r = await client.post("/api/v1/owner-profile/submit")
    assert r.json()["verification_status"] == "pending"

    sign_in(client, admin)
    r = await client.post(f"/api/v1/admin/owner-verifications/{profile['id']}/approve")
    assert r.status_code == 200, r.text
    row = await _profile(db, profile["id"])
    assert row.verification_status == VerificationStatus.VERIFIED
    assert row.verified_by == admin.id and row.verified_at is not None
    assert row.rejection_reason is None


async def test_admin_routes_need_admin(client: httpx.AsyncClient, db: AsyncSession) -> None:
    owner = await make_owner(db, verification="pending")
    assert (await client.get("/api/v1/admin/owner-verifications")).status_code == 401
    sign_in(client, await make_user(db))
    assert (await client.get("/api/v1/admin/owner-verifications")).status_code == 403
    r = await client.post(f"/api/v1/admin/owner-verifications/{owner.id}/approve")
    assert r.status_code == 403


async def test_payout_methods_keep_one_default(client: httpx.AsyncClient, db: AsyncSession) -> None:
    await _individual(client, db)
    r = await client.post(
        "/api/v1/owner-profile/payout-methods",
        json={
            "kind": "mobile_money",
            "network": "mpesa",
            "msisdn": "0712345678",
            "account_name": "Neema",
        },
    )
    assert r.status_code == 201, r.text
    first = r.json()
    assert first["is_default"] is True  # the first method becomes the default
    assert first["msisdn"] == "+255712345678"

    r = await client.post(
        "/api/v1/owner-profile/payout-methods",
        json={
            "kind": "bank",
            "bank_name": "CRDB",
            "account_name": "Neema Rentals",
            "account_number": "0150123456789",
            "is_default": True,
        },
    )
    assert r.status_code == 201, r.text
    second = r.json()
    assert second["account_number_masked"] == "****6789" and "0150123456789" not in r.text

    methods = (await client.get("/api/v1/owner-profile/payout-methods")).json()
    defaults = [m["id"] for m in methods if m["is_default"]]
    assert defaults == [second["id"]]

    r = await client.delete(f"/api/v1/owner-profile/payout-methods/{first['id']}")
    assert r.status_code == 204
    rows = (await db.execute(select(PayoutMethod.id))).scalars().all()
    assert uuid.UUID(first["id"]) not in rows

    bad = await client.post(
        "/api/v1/owner-profile/payout-methods",
        json={"kind": "mobile_money", "account_name": "No number"},
    )
    assert bad.status_code == 422


async def test_owner_routes_need_a_profile(client: httpx.AsyncClient, db: AsyncSession) -> None:
    assert (await client.get("/api/v1/owner-profile")).status_code == 401
    sign_in(client, await make_user(db))
    assert (await client.get("/api/v1/owner-profile")).status_code == 403
    assert (await client.post("/api/v1/owner-profile/submit")).status_code == 403
