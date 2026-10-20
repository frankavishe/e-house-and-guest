"""Minimal admin moderation (T101, US7-AS2): owner verification and listing review.

Every mutation writes an `admin_audit_log` row (before/after) and notifies the owner.
"""

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User, VerificationStatus
from app.admin.models import AdminAuditLog
from app.admin.schemas import DocumentLink, VerificationItem, VerificationUser
from app.catalog.models import Category
from app.core import clock
from app.core.errors import AppError, not_found
from app.core.i18n import Locale
from app.core.security import decrypt
from app.integrations import get_storage
from app.listings import manage
from app.listings.models import Listing, ListingStatus, ReviewState
from app.listings.owner_schemas import AdminListingItem, OwnerBrief, OwnerListingOut
from app.listings.schemas import Page
from app.notifications.service import notify

DOCUMENT_URL_TTL_S = 300


async def audit(
    session: AsyncSession,
    admin: User,
    action: str,
    target_kind: str,
    target_id: uuid.UUID,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    session.add(
        AdminAuditLog(
            admin_id=admin.id,
            action=action,
            target_kind=target_kind,
            target_id=target_id,
            before=before,
            after=after,
        )
    )
    await session.flush()


# --- owner verification -------------------------------------------------------------------


def _profile_state(profile: OwnerProfile) -> dict[str, Any]:
    return {
        "verification_status": profile.verification_status.value,
        "rejection_reason": profile.rejection_reason,
    }


def verification_item(profile: OwnerProfile, user: User) -> VerificationItem:
    storage = get_storage()
    return VerificationItem(
        id=profile.id,
        user=VerificationUser(id=user.id, name=user.name, phone=user.phone),
        kind=profile.kind.value,
        display_name=profile.display_name,
        business_name=profile.business_name,
        brela_reg_no=profile.brela_reg_no,
        nida_number=decrypt(profile.nida_number_enc) if profile.nida_number_enc else None,
        tin=decrypt(profile.tin_enc) if profile.tin_enc else None,
        documents=[
            DocumentLink(key=key, url=storage.presign_get(key=key, ttl_s=DOCUMENT_URL_TTL_S))
            for key in profile.documents
        ],
        verification_status=profile.verification_status.value,
        rejection_reason=profile.rejection_reason,
        updated_at=profile.updated_at,
    )


async def verification_queue(
    session: AsyncSession, status: VerificationStatus, page: int, page_size: int
) -> Page[VerificationItem]:
    where = OwnerProfile.verification_status == status
    total = (
        await session.execute(select(func.count()).select_from(OwnerProfile).where(where))
    ).scalar_one()
    rows = await session.execute(
        select(OwnerProfile, User)
        .join(User, User.id == OwnerProfile.user_id)
        .where(where)
        .order_by(OwnerProfile.updated_at, OwnerProfile.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [verification_item(profile, user) for profile, user in rows.all()]
    return Page[VerificationItem](items=items, page=page, page_size=page_size, total=total)


async def _pending_profile(session: AsyncSession, profile_id: uuid.UUID) -> OwnerProfile:
    profile = await session.get(OwnerProfile, profile_id, with_for_update=True)
    if profile is None:
        raise not_found("owner_profile")
    if profile.verification_status != VerificationStatus.PENDING:
        raise AppError("INVALID_TRANSITION", 409, {"status": profile.verification_status.value})
    return profile


async def decide_owner(
    session: AsyncSession, admin: User, profile_id: uuid.UUID, reason: str | None
) -> tuple[OwnerProfile, User]:
    """Approve (no reason) or reject (with reason) a pending owner verification."""
    profile = await _pending_profile(session, profile_id)
    before = _profile_state(profile)
    if reason is None:
        profile.verification_status = VerificationStatus.VERIFIED
        profile.verified_at = clock.now()
        profile.verified_by = admin.id
        profile.rejection_reason = None
        action, event = "owner.approve", "owner.verified"
    else:
        profile.verification_status = VerificationStatus.REJECTED
        profile.rejection_reason = reason
        action, event = "owner.reject", "owner.rejected"
    await audit(
        session, admin, action, "owner_profile", profile.id, before, _profile_state(profile)
    )
    await notify(session, profile.user_id, event, {"reason": reason or ""})
    user = await session.get(User, profile.user_id)
    assert user is not None
    return profile, user


# --- listing review -----------------------------------------------------------------------


def _listing_state(listing: Listing) -> dict[str, Any]:
    return {
        "status": listing.status.value,
        "review_state": listing.review_state.value,
        "rejection_reason": listing.rejection_reason,
        "pending_changes": listing.pending_changes,
    }


async def listing_queue(
    session: AsyncSession,
    status: ListingStatus | None,
    page: int,
    page_size: int,
    locale: Locale,
) -> Page[AdminListingItem]:
    """By default the review queue: new listings and live listings with pending changes."""
    where = (
        Listing.status == status
        if status is not None
        else or_(
            Listing.status == ListingStatus.PENDING_REVIEW,
            Listing.review_state == ReviewState.PENDING,
        )
    )
    total = (
        await session.execute(select(func.count()).select_from(Listing).where(where))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Listing, Category, OwnerProfile)
            .join(Category, Category.id == Listing.category_id)
            .join(OwnerProfile, OwnerProfile.id == Listing.owner_profile_id)
            .where(where)
            .order_by(Listing.updated_at, Listing.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    outs = await manage.listings_out(session, [(r[0], r[1]) for r in rows], locale)
    items = [
        AdminListingItem(
            listing=out,
            owner=OwnerBrief(
                id=owner.id,
                display_name=owner.display_name,
                verification_status=owner.verification_status.value,
            ),
            diff=manage.review_diff(listing),
        )
        for out, (listing, _, owner) in zip(outs, rows, strict=True)
    ]
    return Page[AdminListingItem](items=items, page=page, page_size=page_size, total=total)


async def _notify_owner(
    session: AsyncSession, listing: Listing, event: str, reason: str | None = None
) -> None:
    owner = await session.get(OwnerProfile, listing.owner_profile_id)
    assert owner is not None
    user = await session.get(User, owner.user_id)
    assert user is not None
    payload = {"listing_id": str(listing.id), "title": listing.title(user.language)}
    await notify(session, user.id, event, {**payload, "reason": reason or ""})


async def review_listing(
    session: AsyncSession,
    admin: User,
    listing_id: uuid.UUID,
    action: str,
    reason: str | None,
    locale: Locale,
) -> OwnerListingOut:
    """`approve` / `reject` a new listing or pending changes; `suspend` / `unsuspend`."""
    listing, category = await manage.get_any(session, listing_id)
    before = _listing_state(listing)
    match action:
        case "approve" if listing.status == ListingStatus.PENDING_REVIEW:
            listing.status = ListingStatus.ACTIVE
            listing.rejection_reason = None
            event = "listing.approved"
        case "approve" if listing.review_state == ReviewState.PENDING:
            await manage.apply_pending(session, listing)
            event = "listing.changes_approved"
        case "reject" if listing.status == ListingStatus.PENDING_REVIEW:
            listing.status = ListingStatus.REJECTED
            listing.rejection_reason = reason
            event = "listing.rejected"
        case "reject" if listing.review_state == ReviewState.PENDING:
            assert reason is not None
            await manage.reject_pending(session, listing, reason)
            event = "listing.changes_rejected"
        case "suspend" if listing.status in manage.LIVE:
            listing.status = ListingStatus.SUSPENDED
            listing.rejection_reason = reason
            event = "listing.suspended"
        case "unsuspend" if listing.status == ListingStatus.SUSPENDED:
            listing.status = ListingStatus.ACTIVE
            listing.rejection_reason = None
            event = "listing.unsuspended"
        case _:
            raise AppError("INVALID_TRANSITION", 409, {"status": listing.status.value})
    listing.updated_at = clock.now()
    await session.flush()
    await audit(
        session, admin, f"listing.{action}", "listing", listing.id, before, _listing_state(listing)
    )
    await _notify_owner(session, listing, event, reason)
    return await manage.listing_out(session, listing, category, locale)
