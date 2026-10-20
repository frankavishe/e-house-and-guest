"""`/admin/owner-verifications*` and `/admin/listings*` (contracts/rest-api.md "Admin")."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.accounts.models import VerificationStatus
from app.admin import moderation
from app.admin.schemas import VerificationDecision, VerificationItem
from app.core.deps import AdminUser, Session
from app.core.i18n import Locale, get_locale
from app.listings.models import ListingStatus
from app.listings.owner_schemas import AdminListingItem, OwnerListingOut, Reason
from app.listings.schemas import Page

router = APIRouter(tags=["admin"])

LocaleDep = Annotated[Locale, Depends(get_locale)]
PageNo = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=50)]
TRANSITION: dict[int | str, dict[str, Any]] = {
    404: {"description": "Unknown profile or listing"},
    409: {"description": "`INVALID_TRANSITION`"},
}


@router.get("/admin/owner-verifications", response_model=Page[VerificationItem])
async def owner_verifications(
    admin: AdminUser,
    session: Session,
    status: Literal["draft", "pending", "verified", "rejected"] = "pending",
    page: PageNo = 1,
    page_size: PageSize = 20,
) -> Page[VerificationItem]:
    """Oldest first, with presigned document links (5 min)."""
    return await moderation.verification_queue(session, VerificationStatus(status), page, page_size)


async def _decide(
    session: Session, admin: AdminUser, profile_id: uuid.UUID, reason: str | None
) -> VerificationDecision:
    profile, _ = await moderation.decide_owner(session, admin, profile_id, reason)
    out = VerificationDecision(
        id=profile.id,
        verification_status=profile.verification_status.value,
        rejection_reason=profile.rejection_reason,
    )
    await session.commit()
    return out


@router.post(
    "/admin/owner-verifications/{profile_id}/approve",
    response_model=VerificationDecision,
    responses=TRANSITION,
)
async def approve_owner(
    profile_id: uuid.UUID, admin: AdminUser, session: Session
) -> VerificationDecision:
    """`pending → verified`; the owner's approved listings become searchable."""
    return await _decide(session, admin, profile_id, None)


@router.post(
    "/admin/owner-verifications/{profile_id}/reject",
    response_model=VerificationDecision,
    responses=TRANSITION,
)
async def reject_owner(
    profile_id: uuid.UUID, body: Reason, admin: AdminUser, session: Session
) -> VerificationDecision:
    """`pending → rejected` with a reason the owner sees (US7-AS2)."""
    return await _decide(session, admin, profile_id, body.reason)


@router.get("/admin/listings", response_model=Page[AdminListingItem])
async def admin_listings(
    admin: AdminUser,
    session: Session,
    locale: LocaleDep,
    status: Literal["draft", "pending_review", "active", "paused", "rejected", "suspended"]
    | None = None,
    page: PageNo = 1,
    page_size: PageSize = 20,
) -> Page[AdminListingItem]:
    """Without `status`: the review queue (new listings and pending changes), oldest first,
    each with a diff of the pending changes against the live values."""
    return await moderation.listing_queue(
        session, ListingStatus(status) if status else None, page, page_size, locale
    )


async def _review(
    session: Session,
    admin: AdminUser,
    listing_id: uuid.UUID,
    action: str,
    reason: str | None,
    locale: Locale,
) -> OwnerListingOut:
    out = await moderation.review_listing(session, admin, listing_id, action, reason, locale)
    await session.commit()
    return out


@router.post(
    "/admin/listings/{listing_id}/approve", response_model=OwnerListingOut, responses=TRANSITION
)
async def approve_listing(
    listing_id: uuid.UUID, admin: AdminUser, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    """A new listing goes live, or pending changes are applied."""
    return await _review(session, admin, listing_id, "approve", None, locale)


@router.post(
    "/admin/listings/{listing_id}/reject", response_model=OwnerListingOut, responses=TRANSITION
)
async def reject_listing(
    listing_id: uuid.UUID, body: Reason, admin: AdminUser, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    """A new listing is rejected, or pending changes are dropped (the listing stays live)."""
    return await _review(session, admin, listing_id, "reject", body.reason, locale)


@router.post(
    "/admin/listings/{listing_id}/suspend", response_model=OwnerListingOut, responses=TRANSITION
)
async def suspend_listing(
    listing_id: uuid.UUID, body: Reason, admin: AdminUser, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    """Hide a live listing; future confirmed bookings are kept for admin follow-up."""
    return await _review(session, admin, listing_id, "suspend", body.reason, locale)


@router.post(
    "/admin/listings/{listing_id}/unsuspend", response_model=OwnerListingOut, responses=TRANSITION
)
async def unsuspend_listing(
    listing_id: uuid.UUID, admin: AdminUser, session: Session, locale: LocaleDep
) -> OwnerListingOut:
    return await _review(session, admin, listing_id, "unsuspend", None, locale)
