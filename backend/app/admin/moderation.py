"""Admin moderation (T101, T136, US7): owner verification, listing review, user suspension
and abuse reports.

Every mutation writes an `admin_audit_log` row (before/after) and notifies the affected user.
"""

import uuid
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, RefreshToken, User, UserStatus, VerificationStatus
from app.admin.models import AdminAuditLog
from app.admin.schemas import (
    AdminOwnerBrief,
    AdminParty,
    AdminReportOut,
    AdminUserOut,
    DocumentLink,
    VerificationItem,
    VerificationUser,
)
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
from app.reviews.models import AbuseReport, ReportStatus, ReportTarget

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


# --- users (FR-030) -----------------------------------------------------------------------


async def _user_out(session: AsyncSession, user: User) -> AdminUserOut:
    owner = (
        await session.execute(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    ).scalar_one_or_none()
    return AdminUserOut(
        id=user.id,
        name=user.name,
        phone=user.phone,
        email=user.email,
        status=user.status.value,
        is_admin=user.is_admin,
        owner=AdminOwnerBrief(
            id=owner.id,
            display_name=owner.display_name,
            verification_status=owner.verification_status.value,
        )
        if owner
        else None,
        created_at=user.created_at,
    )


async def users(
    session: AsyncSession, q: str | None, status: UserStatus | None, page: int, page_size: int
) -> Page[AdminUserOut]:
    """Newest first. `q` matches the phone, name or email."""
    query = select(User)
    if status is not None:
        query = query.where(User.status == status)
    if q:
        term = q.strip()
        query = query.where(
            or_(
                User.phone.contains(term),
                User.name.ilike(f"%{term}%"),
                User.email.ilike(f"%{term}%"),
            )
        )
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await session.execute(
        query.order_by(User.created_at.desc(), User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [await _user_out(session, u) for u in rows.scalars().all()]
    return Page[AdminUserOut](items=items, page=page, page_size=page_size, total=total)


async def set_user_status(
    session: AsyncSession, admin: User, user_id: uuid.UUID, suspend: bool, reason: str | None
) -> AdminUserOut:
    """Suspend (signing the user out everywhere) or unsuspend; admins cannot be suspended.
    Bookings are kept: future ones show as needing attention in `/admin/bookings`, and an
    owner's listings leave search while the account is suspended."""
    user = await session.get(User, user_id, with_for_update=True)
    if user is None or user.status == UserStatus.DELETED:
        raise not_found("user")
    want, current = (
        (UserStatus.SUSPENDED, UserStatus.ACTIVE)
        if suspend
        else (UserStatus.ACTIVE, UserStatus.SUSPENDED)
    )
    if user.is_admin or user.status != current:
        raise AppError("INVALID_TRANSITION", 409, {"status": user.status.value})
    user.status = want
    if suspend:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=clock.now())
        )
    await session.flush()
    await audit(
        session,
        admin,
        "user.suspend" if suspend else "user.unsuspend",
        "user",
        user.id,
        {"status": current.value},
        {"status": want.value, "reason": reason},
    )
    event = "account.suspended" if suspend else "account.unsuspended"
    await notify(session, user.id, event, {"reason": reason or ""})
    return await _user_out(session, user)


# --- abuse reports (FR-030) ---------------------------------------------------------------


async def _report_outs(session: AsyncSession, reports: list[AbuseReport]) -> list[AdminReportOut]:
    listing_ids = [r.target_id for r in reports if r.target_kind == ReportTarget.LISTING]
    user_ids = [r.target_id for r in reports if r.target_kind == ReportTarget.USER]
    listings = {
        x.id: x
        for x in (await session.execute(select(Listing).where(Listing.id.in_(listing_ids))))
        .scalars()
        .all()
    }
    people_ids = [*user_ids, *(r.reporter_id for r in reports)]
    people = {
        u.id: u
        for u in (await session.execute(select(User).where(User.id.in_(people_ids))))
        .scalars()
        .all()
    }
    open_counts: dict[tuple[ReportTarget, uuid.UUID], int] = {}
    if reports:
        rows = await session.execute(
            select(AbuseReport.target_kind, AbuseReport.target_id, func.count())
            .where(
                AbuseReport.status == ReportStatus.OPEN,
                AbuseReport.target_id.in_([r.target_id for r in reports]),
            )
            .group_by(AbuseReport.target_kind, AbuseReport.target_id)
        )
        open_counts = {(kind, tid): int(n) for kind, tid, n in rows.all()}
    outs = []
    for r in reports:
        if r.target_kind == ReportTarget.LISTING:
            listing = listings.get(r.target_id)
            label = listing.title_sw if listing else ""
            target_status = listing.status.value if listing else "deleted"
        else:
            target = people.get(r.target_id)
            label = (target.name or target.phone) if target else ""
            target_status = target.status.value if target else "deleted"
        reporter = people[r.reporter_id]
        outs.append(
            AdminReportOut(
                id=r.id,
                target_kind=r.target_kind.value,
                target_id=r.target_id,
                target_label=label,
                target_status=target_status,
                reason=r.reason,
                status=r.status.value,
                reporter=AdminParty(id=reporter.id, name=reporter.name or "", phone=reporter.phone),
                open_reports_on_target=open_counts.get((r.target_kind, r.target_id), 0),
                handled_at=r.handled_at,
                created_at=r.created_at,
            )
        )
    return outs


async def report_queue(
    session: AsyncSession, status: ReportStatus | None, page: int, page_size: int
) -> Page[AdminReportOut]:
    """Open reports oldest first; handled ones newest first."""
    query = select(AbuseReport)
    if status is not None:
        query = query.where(AbuseReport.status == status)
    order = (
        (AbuseReport.created_at, AbuseReport.id)
        if status == ReportStatus.OPEN
        else (AbuseReport.created_at.desc(), AbuseReport.id.desc())
    )
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await session.execute(
        query.order_by(*order).offset((page - 1) * page_size).limit(page_size)
    )
    items = await _report_outs(session, list(rows.scalars().all()))
    return Page[AdminReportOut](items=items, page=page, page_size=page_size, total=total)


async def action_report(
    session: AsyncSession,
    admin: User,
    report_id: uuid.UUID,
    decision: str,
    suspend_target: bool,
    note: str | None,
    locale: Locale,
) -> AdminReportOut:
    """Dismiss one open report, or action it: every open report on the same target closes,
    and with `suspend_target` the listing or user is suspended (unless it already is)."""
    report = await session.get(AbuseReport, report_id, with_for_update=True)
    if report is None:
        raise not_found("report")
    if report.status != ReportStatus.OPEN:
        raise AppError("INVALID_TRANSITION", 409, {"status": report.status.value})
    status = ReportStatus(decision)
    closing = [report]
    if status == ReportStatus.ACTIONED:
        same_target = await session.execute(
            select(AbuseReport).where(
                AbuseReport.target_kind == report.target_kind,
                AbuseReport.target_id == report.target_id,
                AbuseReport.status == ReportStatus.OPEN,
            )
        )
        closing = list(same_target.scalars().all())
    now = clock.now()
    for r in closing:
        r.status = status
        r.handled_by = admin.id
        r.handled_at = now
    await session.flush()
    if status == ReportStatus.ACTIONED and suspend_target:
        reason = note or report.reason
        if report.target_kind == ReportTarget.LISTING:
            listing = await session.get(Listing, report.target_id)
            if listing is not None and listing.status in manage.LIVE:
                await review_listing(session, admin, listing.id, "suspend", reason, locale)
        else:
            target = await session.get(User, report.target_id)
            if target is not None and target.status == UserStatus.ACTIVE and not target.is_admin:
                await set_user_status(session, admin, target.id, True, reason)
    await audit(
        session,
        admin,
        f"report.{status.value}",
        "abuse_report",
        report.id,
        {"status": ReportStatus.OPEN.value},
        {
            "status": status.value,
            "closed": [str(r.id) for r in closing],
            "suspend_target": suspend_target,
            "note": note,
        },
    )
    return (await _report_outs(session, [report]))[0]
