"""Damage claims and disputes (T122, US5, FR-027, FR-031).

An owner may claim damage while a booking runs or until 48 h after it ends; either party may
open a dispute in the same window. An open claim puts the booking in `disputed`, which
stops the deposit refund and the payout until an admin resolves it:

- `owner_awarded`: the owner gets `amount_awarded_tzs` of the deposit (all of it if omitted)
- `split`: the owner gets part of the deposit and the renter the rest
- `renter_refunded`: the whole deposit goes back to the renter

The rest of the deposit is refunded to the renter, and the booking returns to `completed`
(a running booking ends there). The owner's award goes into their next payout, as a
separate `claim_award` item if the earnings were already paid out. A rental refund beyond
the deposit is a separate admin refund (`POST /admin/bookings/{id}/refund`).
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User
from app.accounts.schemas import UploadOut
from app.admin.moderation import DOCUMENT_URL_TTL_S, audit
from app.admin.schemas import AdminClaimOut, AdminParty, DocumentLink
from app.bookings import notify
from app.bookings.models import (
    ActorKind,
    Booking,
    BookingStatus,
    Claim,
    ClaimKind,
    ClaimResolution,
    ClaimStatus,
)
from app.bookings.schemas import ClaimIn, ClaimOut, RoleT
from app.bookings.state import Event, transition
from app.core import clock
from app.core.db import uuid7
from app.core.errors import AppError, not_found
from app.core.i18n import money
from app.integrations import get_storage
from app.integrations.uploads import check_uploads
from app.ledger import service as ledger
from app.listings.schemas import Page
from app.payments import refunds
from app.payments.models import RefundReason

CLAIM_WINDOW = timedelta(hours=48)
EVIDENCE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}
EVIDENCE_MAX_BYTES = 10 * 1024 * 1024


def evidence_prefix(booking: Booking) -> str:
    return f"claims/{booking.id}/"


async def claims_of(session: AsyncSession, booking_id: uuid.UUID) -> list[Claim]:
    rows = await session.execute(
        select(Claim).where(Claim.booking_id == booking_id).order_by(Claim.created_at)
    )
    return list(rows.scalars())


def window_open(booking: Booking) -> bool:
    """A running booking, or a completed one until 48 h after its end."""
    if booking.status == BookingStatus.IN_PROGRESS:
        return True
    end = booking.period.upper
    return (
        booking.status == BookingStatus.COMPLETED
        and end is not None
        and clock.now() < end + CLAIM_WINDOW
    )


def claim_kinds(booking: Booking, role: RoleT, claims: list[Claim]) -> set[ClaimKind]:
    """The claim kinds the viewer may open now."""
    if role == "admin" or any(c.status == ClaimStatus.OPEN for c in claims):
        return set()
    if not window_open(booking):
        return set()
    return {ClaimKind.DAMAGE, ClaimKind.DISPUTE} if role == "owner" else {ClaimKind.DISPUTE}


async def _opener_role(session: AsyncSession, booking: Booking, claim: Claim) -> RoleT:
    if claim.opened_by == booking.renter_id:
        return "renter"
    owner = await session.get(OwnerProfile, booking.owner_profile_id)
    return "owner" if owner is not None and owner.user_id == claim.opened_by else "admin"


async def claim_out(session: AsyncSession, booking: Booking, claim: Claim) -> ClaimOut:
    return ClaimOut(
        id=claim.id,
        booking_id=claim.booking_id,
        kind=claim.kind.value,
        opened_by=await _opener_role(session, booking, claim),
        description=claim.description,
        amount_claimed_tzs=claim.amount_claimed_tzs,
        evidence_keys=list(claim.evidence),
        status=claim.status.value,
        resolution=claim.resolution.value if claim.resolution else None,
        amount_awarded_tzs=claim.amount_awarded_tzs,
        resolution_note=claim.resolution_note,
        created_at=claim.created_at,
        resolved_at=claim.resolved_at,
    )


async def has_open_claim(session: AsyncSession, booking_id: uuid.UUID) -> bool:
    count = await session.execute(
        select(func.count())
        .select_from(Claim)
        .where(Claim.booking_id == booking_id, Claim.status == ClaimStatus.OPEN)
    )
    return count.scalar_one() > 0


# --- parties ------------------------------------------------------------------------------


async def presign_evidence(
    session: AsyncSession, user: User, booking_id: uuid.UUID, content_type: str
) -> UploadOut:
    from app.bookings.service import get_for_party

    booking, role = await get_for_party(session, user, booking_id)
    if role == "admin":
        raise not_found("booking")
    ext = EVIDENCE_TYPES.get(content_type)
    if ext is None:
        raise AppError("VALIDATION_ERROR", 422, {"content_type": sorted(EVIDENCE_TYPES)})
    put = get_storage().presign_put(
        key=f"{evidence_prefix(booking)}{uuid7()}.{ext}",
        content_type=content_type,
        max_bytes=EVIDENCE_MAX_BYTES,
        private=True,
    )
    return UploadOut(upload_url=put.url, storage_key=put.key, headers=put.headers)


async def open_claim(
    session: AsyncSession, user: User, booking_id: uuid.UUID, body: ClaimIn
) -> tuple[Booking, Claim]:
    from app.bookings.service import get_for_party

    booking, role = await get_for_party(session, user, booking_id, lock=True)
    if role == "admin":
        raise not_found("booking")
    kind = ClaimKind(body.kind)
    if kind == ClaimKind.DAMAGE and role != "owner":
        raise AppError("FORBIDDEN", 403)
    if await has_open_claim(session, booking.id):
        raise AppError("CLAIM_OPEN", 409)
    if not window_open(booking):
        raise AppError("CLAIM_WINDOW_CLOSED", 409, {"status": booking.status.value})
    prefix = evidence_prefix(booking)
    if any(not key.startswith(prefix) for key in body.evidence_keys):
        raise AppError("VALIDATION_ERROR", 422, {"evidence_keys": "unknown upload"})
    await check_uploads(body.evidence_keys, max_bytes=EVIDENCE_MAX_BYTES, field="evidence_keys")
    claim = Claim(
        booking_id=booking.id,
        opened_by=user.id,
        kind=kind,
        description=body.description,
        evidence=list(body.evidence_keys),
        amount_claimed_tzs=body.amount_claimed_tzs,
        status=ClaimStatus.OPEN,
    )
    session.add(claim)
    await session.flush()
    await transition(
        session,
        booking,
        Event.DISPUTE,
        actor_kind=ActorKind.USER,
        actor_user_id=user.id,
        note=f"claim {claim.id}",
    )
    extra = {"kind": kind.value}
    if role == "owner":
        await notify.to_renter(session, booking, "claim.opened", **extra)
    else:
        await notify.to_owner(session, booking, "claim.opened", **extra)
    await notify.to_admins(session, booking, "claim.opened_admin", **extra)
    return booking, claim


# --- admin --------------------------------------------------------------------------------


async def _parties(session: AsyncSession, booking: Booking) -> tuple[AdminParty, AdminParty]:
    renter = await session.get(User, booking.renter_id)
    owner = await session.get(OwnerProfile, booking.owner_profile_id)
    assert renter is not None and owner is not None
    owner_user = await session.get(User, owner.user_id)
    assert owner_user is not None
    return (
        AdminParty(id=renter.id, name=renter.name or "", phone=renter.phone),
        AdminParty(id=owner.id, name=owner.display_name, phone=owner_user.phone),
    )


async def admin_claim_out(session: AsyncSession, claim: Claim) -> AdminClaimOut:
    booking = await session.get(Booking, claim.booking_id)
    assert booking is not None
    renter, owner = await _parties(session, booking)
    storage = get_storage()
    return AdminClaimOut(
        **(await claim_out(session, booking, claim)).model_dump(),
        booking_code=booking.code,
        booking_status=booking.status.value,
        deposit_tzs=booking.deposit_tzs,
        renter=renter,
        owner=owner,
        evidence=[
            DocumentLink(key=key, url=storage.presign_get(key=key, ttl_s=DOCUMENT_URL_TTL_S))
            for key in claim.evidence
        ],
    )


async def admin_claims(
    session: AsyncSession, status: ClaimStatus | None, page: int, page_size: int
) -> Page[AdminClaimOut]:
    """Oldest first, so the longest-waiting claims are handled first."""
    where = [Claim.status == status] if status else []
    total = (
        await session.execute(select(func.count()).select_from(Claim).where(*where))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Claim)
            .where(*where)
            .order_by(Claim.created_at, Claim.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars()
    return Page[AdminClaimOut](
        items=[await admin_claim_out(session, c) for c in rows],
        page=page,
        page_size=page_size,
        total=total,
    )


def _award(resolution: ClaimResolution, requested: int | None, held: int) -> int:
    match resolution:
        case ClaimResolution.RENTER_REFUNDED:
            award = requested or 0
            ok = award == 0
        case ClaimResolution.OWNER_AWARDED:
            award = held if requested is None else requested
            ok = 0 < award <= held
        case ClaimResolution.SPLIT:
            award = requested or 0
            ok = 0 < award < held
    if not ok:
        raise AppError(
            "INVALID_AWARD", 422, {"resolution": resolution.value, "deposit_held_tzs": held}
        )
    return award


def _state(claim: Claim) -> dict[str, Any]:
    return {
        "status": claim.status.value,
        "resolution": claim.resolution.value if claim.resolution else None,
        "amount_awarded_tzs": claim.amount_awarded_tzs,
    }


async def resolve(
    session: AsyncSession,
    admin: User,
    claim_id: uuid.UUID,
    resolution: ClaimResolution,
    amount_awarded_tzs: int | None,
    note: str | None,
) -> Claim:
    claim = await session.get(Claim, claim_id, with_for_update=True, populate_existing=True)
    if claim is None:
        raise not_found("claim")
    if claim.status != ClaimStatus.OPEN:
        raise AppError("INVALID_TRANSITION", 409, {"status": claim.status.value})
    booking = await session.get(
        Booking, claim.booking_id, with_for_update=True, populate_existing=True
    )
    assert booking is not None
    held = -(await ledger.booking_balance(session, booking.id, ledger.DEPOSIT_HELD))
    award = _award(resolution, amount_awarded_tzs, held)
    before = _state(claim)

    claim.status = ClaimStatus.RESOLVED
    claim.resolution = resolution
    claim.amount_awarded_tzs = award
    claim.resolution_note = note
    claim.resolved_by = admin.id
    claim.resolved_at = clock.now()
    if award:
        await ledger.post_deposit_award(session, booking, award)
    await refunds.issue(
        session,
        booking,
        reason=RefundReason.DEPOSIT_RETURN,
        created_by=admin.id,
        from_deposit_tzs=held - award,
    )
    if booking.status == BookingStatus.DISPUTED:
        booking.completed_at = booking.completed_at or clock.now()
        await transition(
            session,
            booking,
            Event.RESOLVE_COMPLETE,
            actor_kind=ActorKind.USER,
            actor_user_id=admin.id,
            note=f"claim {claim.id}: {resolution.value}",
        )
    await session.flush()
    await audit(session, admin, "claim.resolve", "claim", claim.id, before, _state(claim))
    extra = {"resolution": resolution.value, "award": money(award)}
    await notify.to_renter(session, booking, "claim.resolved", **extra)
    await notify.to_owner(session, booking, "claim.resolved", **extra)
    return claim
