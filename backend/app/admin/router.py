"""`/admin/owner-verifications*`, `/admin/listings*`, `/admin/bookings*`, `/admin/refunds*`
and `/admin/claims*` (contracts/rest-api.md "Admin")."""

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.accounts.models import VerificationStatus
from app.admin import bookings as admin_bookings
from app.admin import moderation
from app.admin.schemas import (
    AdminBookingSummary,
    AdminClaimOut,
    AdminRefundIn,
    MarkRefundSentIn,
    ResolveClaimIn,
    VerificationDecision,
    VerificationItem,
)
from app.bookings import claims
from app.bookings import service as bookings
from app.bookings.models import BookingStatus, ClaimResolution, ClaimStatus
from app.bookings.schemas import BookingOut, BookingStatusT, CancelBody, RefundOut
from app.core.deps import AdminUser, Session
from app.core.i18n import Locale, get_locale
from app.listings.models import ListingStatus
from app.listings.owner_schemas import AdminListingItem, OwnerListingOut, Reason
from app.listings.schemas import Page
from app.payments import refunds

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


# --- bookings, refunds and claims (US5) ---------------------------------------------------

BOOKING: dict[int | str, dict[str, Any]] = {404: {"description": "Unknown booking"}}
REFUND: dict[int | str, dict[str, Any]] = {
    404: {"description": "Unknown refund"},
    409: {"description": "`INVALID_TRANSITION`"},
}


@router.get("/admin/bookings", response_model=Page[AdminBookingSummary])
async def list_admin_bookings(
    admin: AdminUser,
    session: Session,
    locale: LocaleDep,
    status: BookingStatusT | None = None,
    q: Annotated[str | None, Query(max_length=50)] = None,
    page: PageNo = 1,
    page_size: PageSize = 20,
) -> Page[AdminBookingSummary]:
    """Newest first; `q` matches the booking code or a party's phone number."""
    return await admin_bookings.admin_bookings(
        session, BookingStatus(status) if status else None, q, page, page_size, locale
    )


@router.get("/admin/bookings/{booking_id}", response_model=BookingOut, responses=BOOKING)
async def get_admin_booking(
    booking_id: uuid.UUID, admin: AdminUser, session: Session, locale: LocaleDep
) -> BookingOut:
    booking, _ = await bookings.get_for_party(session, admin, booking_id)
    return await bookings.booking_out(session, booking, "admin", locale)


@router.post(
    "/admin/bookings/{booking_id}/cancel",
    response_model=BookingOut,
    responses={**BOOKING, 409: {"description": "`INVALID_TRANSITION`"}},
)
async def cancel_admin_booking(
    booking_id: uuid.UUID,
    admin: AdminUser,
    session: Session,
    locale: LocaleDep,
    body: CancelBody | None = None,
) -> BookingOut:
    """Cancel (also a running booking) with a full refund of what was paid."""
    booking = await bookings.cancel(
        session, admin, booking_id, body.reason if body else None, as_admin=True
    )
    out = await bookings.booking_out(session, booking, "admin", locale)
    await session.commit()
    return out


@router.post(
    "/admin/bookings/{booking_id}/refund",
    response_model=RefundOut,
    responses={
        **BOOKING,
        409: {"description": "`REFUND_EXCEEDS_BALANCE` or `BOOKING_NOT_PAID`"},
    },
)
async def refund_admin_booking(
    booking_id: uuid.UUID, body: AdminRefundIn, admin: AdminUser, session: Session
) -> RefundOut:
    """A discretionary refund to the renter, from the owner's share or platform revenue."""
    refund = await refunds.admin_refund(
        session, admin, booking_id, body.amount_tzs, body.source, body.reason
    )
    out = bookings.refund_out(refund)
    await session.commit()
    return out


@router.post("/admin/refunds/{refund_id}/retry", response_model=RefundOut, responses=REFUND)
async def retry_refund(refund_id: uuid.UUID, admin: AdminUser, session: Session) -> RefundOut:
    """A failed refund goes back to `pending` and is sent again."""
    refund = await refunds.retry(session, admin, refund_id)
    out = bookings.refund_out(refund)
    await session.commit()
    return out


@router.post("/admin/refunds/{refund_id}/mark-sent", response_model=RefundOut, responses=REFUND)
async def mark_refund_sent(
    refund_id: uuid.UUID, body: MarkRefundSentIn, admin: AdminUser, session: Session
) -> RefundOut:
    """The money was returned outside the platform; record the transfer reference."""
    refund = await refunds.mark_sent(session, admin, refund_id, body.provider_ref)
    out = bookings.refund_out(refund)
    await session.commit()
    return out


@router.get("/admin/claims", response_model=Page[AdminClaimOut])
async def list_claims(
    admin: AdminUser,
    session: Session,
    status: Literal["open", "resolved"] | None = "open",
    page: PageNo = 1,
    page_size: PageSize = 20,
) -> Page[AdminClaimOut]:
    """Oldest first, with presigned evidence links (5 min)."""
    return await claims.admin_claims(
        session, ClaimStatus(status) if status else None, page, page_size
    )


@router.post(
    "/admin/claims/{claim_id}/resolve",
    response_model=AdminClaimOut,
    responses={
        404: {"description": "Unknown claim"},
        409: {"description": "`INVALID_TRANSITION`: already resolved"},
        422: {"description": "`INVALID_AWARD`"},
    },
)
async def resolve_claim(
    claim_id: uuid.UUID, body: ResolveClaimIn, admin: AdminUser, session: Session
) -> AdminClaimOut:
    """Decide the deposit: the award goes to the owner, the rest back to the renter."""
    claim = await claims.resolve(
        session,
        admin,
        claim_id,
        ClaimResolution(body.resolution),
        body.amount_awarded_tzs,
        body.note,
    )
    out = await claims.admin_claim_out(session, claim)
    await session.commit()
    return out
