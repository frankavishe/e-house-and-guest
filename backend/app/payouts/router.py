"""`/owner/earnings`, `/owner/payouts` and `/admin/payouts*` (contracts/rest-api.md
"Earnings & payouts", "Admin")."""

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from app.core.deps import AdminUser, Owner, Session
from app.core.errors import AppError
from app.core.i18n import Locale, get_locale
from app.listings.schemas import Page
from app.payouts import service
from app.payouts.models import PayoutStatus
from app.payouts.schemas import AdminPayoutOut, Earnings, MarkPaid, PayoutOut

router = APIRouter()

LocaleDep = Annotated[Locale, Depends(get_locale)]
PageNo = Annotated[int, Query(ge=1, le=10_000)]
PageSize = Annotated[int, Query(ge=1, le=50)]
TRANSITION: dict[int | str, dict[str, Any]] = {
    404: {"description": "Unknown payout"},
    409: {"description": "`INVALID_TRANSITION`"},
}


@router.get("/owner/earnings", response_model=Earnings, tags=["owner"])
async def owner_earnings(
    profile: Owner,
    session: Session,
    locale: LocaleDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> Earnings:
    """Gross, commission and net per booking and in total; `from`/`to` (inclusive) filter
    on the booking's start date in EAT (US4-AS1)."""
    if start and end and start > end:
        raise AppError("VALIDATION_ERROR", 422, {"from": "must not be after `to`"})
    return await service.earnings(session, profile, start, end, locale)


@router.get("/owner/payouts", response_model=Page[PayoutOut], tags=["owner"])
async def owner_payouts(
    profile: Owner, session: Session, page: PageNo = 1, page_size: PageSize = 20
) -> Page[PayoutOut]:
    """Newest first, with the bookings each payout covers."""
    return await service.owner_payouts(session, profile, page, page_size)


@router.get("/admin/payouts", response_model=Page[AdminPayoutOut], tags=["admin"])
async def admin_payouts(
    admin: AdminUser,
    session: Session,
    status: Literal["pending", "processing", "paid", "failed"] | None = None,
    page: PageNo = 1,
    page_size: PageSize = 20,
) -> Page[AdminPayoutOut]:
    """Oldest first. `pending` with the manual provider is the to-send queue (R7)."""
    return await service.admin_payouts(
        session, PayoutStatus(status) if status else None, page, page_size
    )


@router.post(
    "/admin/payouts/{payout_id}/mark-paid",
    response_model=AdminPayoutOut,
    responses=TRANSITION,
    tags=["admin"],
)
async def mark_payout_paid(
    payout_id: uuid.UUID, body: MarkPaid, admin: AdminUser, session: Session
) -> AdminPayoutOut:
    """Record a payout sent outside the platform with its transfer reference; the owner
    gets an SMS and the ledger records the payout."""
    payout = await service.mark_paid(session, admin, payout_id, body.provider_ref)
    out = await service.admin_payout_out(session, payout)
    await session.commit()
    return out


@router.post(
    "/admin/payouts/{payout_id}/retry",
    response_model=AdminPayoutOut,
    responses=TRANSITION,
    tags=["admin"],
)
async def retry_payout(payout_id: uuid.UUID, admin: AdminUser, session: Session) -> AdminPayoutOut:
    """`failed → pending`; the worker sends it again to the owner's current default method."""
    payout = await service.retry(session, admin, payout_id)
    out = await service.admin_payout_out(session, payout)
    await session.commit()
    return out
