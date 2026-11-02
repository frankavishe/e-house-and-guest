"""`/owner-profile*` endpoints (contracts/rest-api.md "Owner onboarding & payouts setup")."""

import uuid
from typing import Any

from fastapi import APIRouter, Response, status

from app.accounts import owner_service as service
from app.accounts.schemas import (
    OwnerProfileCreate,
    OwnerProfileOut,
    OwnerProfilePatch,
    PayoutMethodIn,
    PayoutMethodOut,
    UploadIn,
    UploadOut,
)
from app.core.deps import CurrentUser, Owner, Session

router = APIRouter(tags=["owner"])

TRANSITION: dict[int | str, dict[str, Any]] = {
    409: {"description": "`INVALID_TRANSITION`: not editable in this state"}
}


@router.post(
    "/owner-profile",
    status_code=status.HTTP_201_CREATED,
    response_model=OwnerProfileOut,
    responses={409: {"description": "The user already has an owner profile"}},
)
async def create_owner_profile(
    body: OwnerProfileCreate, user: CurrentUser, session: Session
) -> OwnerProfileOut:
    out = service.profile_out(await service.create_profile(session, user, body))
    await session.commit()
    return out


@router.get("/owner-profile", response_model=OwnerProfileOut)
async def get_owner_profile(profile: Owner) -> OwnerProfileOut:
    return service.profile_out(profile)


@router.patch("/owner-profile", response_model=OwnerProfileOut, responses=TRANSITION)
async def patch_owner_profile(
    body: OwnerProfilePatch, profile: Owner, session: Session
) -> OwnerProfileOut:
    """Editable while `draft` or `rejected`."""
    out = service.profile_out(await service.patch_profile(session, profile, body))
    await session.commit()
    return out


@router.post("/owner-profile/documents", response_model=UploadOut)
async def presign_owner_document(body: UploadIn, profile: Owner) -> UploadOut:
    """Presigned PUT into the private bucket; attach the key with `PATCH {documents}`."""
    return service.presign_document(profile, body.content_type)


@router.post("/owner-profile/submit", response_model=OwnerProfileOut, responses=TRANSITION)
async def submit_owner_profile(profile: Owner, session: Session) -> OwnerProfileOut:
    """`draft | rejected → pending` (an admin then verifies or rejects)."""
    out = service.profile_out(await service.submit_profile(session, profile))
    await session.commit()
    return out


@router.get("/owner-profile/payout-methods", response_model=list[PayoutMethodOut])
async def list_payout_methods(profile: Owner, session: Session) -> list[PayoutMethodOut]:
    return [service.payout_method_out(m) for m in await service.payout_methods(session, profile)]


@router.post(
    "/owner-profile/payout-methods",
    status_code=status.HTTP_201_CREATED,
    response_model=PayoutMethodOut,
)
async def add_payout_method(
    body: PayoutMethodIn, profile: Owner, session: Session
) -> PayoutMethodOut:
    out = service.payout_method_out(await service.add_payout_method(session, profile, body))
    await session.commit()
    return out


@router.delete(
    "/owner-profile/payout-methods/{method_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_payout_method(method_id: uuid.UUID, profile: Owner, session: Session) -> Response:
    await service.delete_payout_method(session, profile, method_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
