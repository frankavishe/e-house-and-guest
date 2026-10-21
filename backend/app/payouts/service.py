"""Earnings views and the payout lifecycle (T113, US4, R7, SC-008).

Earnings come from the ledger: a booking's net is `-SUM(owner_payable:<owner>)` over its
non-payout entries, so refunds taken from the owner's share lower it automatically.

Payouts: the daily sweep batches each owner's eligible bookings (completed ≥ 24 h ago, not
disputed, not yet in a payout) into one `pending` payout and queues a `payouts.disburse`
job, so the provider is called outside the batch transaction and transport errors retry
with backoff. The provider answers `paid`, `processing` (polled until settled), `failed`
(admin can retry) or `pending` (manual provider: an admin sends the money and marks it
paid). Paying posts the `payout` ledger entry and texts the owner.

    pending ─disburse→ processing ─poll→ paid
       │                   └─────poll→ failed ─retry→ pending
       ├─disburse→ paid | failed
       └─mark-paid (admin, also from processing/failed) → paid
"""

import logging
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import Subquery, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, PayoutMethod, User
from app.accounts.owner_service import payout_method_out
from app.admin.moderation import audit
from app.bookings.models import Booking, BookingStatus, InstallmentStatus, LeaseInstallment
from app.bookings.schemas import PeriodOut
from app.catalog.models import BookingMode
from app.core import clock
from app.core.errors import AppError, not_found
from app.core.i18n import Locale, money
from app.core.security import decrypt
from app.integrations import get_payout_provider
from app.integrations.payments.base import (
    Network,
    PayoutDestination,
    PayoutState,
    ProviderUnavailable,
)
from app.jobs import service as jobs
from app.ledger import service as ledger
from app.ledger.models import EntryType, LedgerEntry
from app.listings.models import Listing
from app.listings.schemas import Page
from app.listings.service import localized
from app.notifications.service import notify
from app.payouts.models import Payout, PayoutItem, PayoutStatus
from app.payouts.schemas import (
    AdminPayoutOut,
    EarningItem,
    Earnings,
    EarningStatus,
    EarningsTotals,
    PayoutItemOut,
    PayoutOut,
    PayoutOwner,
)

log = logging.getLogger(__name__)

ELIGIBLE_AFTER = timedelta(hours=24)
DISBURSE_JOB = "payouts.disburse"
NO_PAYOUT_METHOD = "no_payout_method"
BATCH = 200


def _booking_net(owner_profile_id: uuid.UUID | None = None) -> Subquery:
    """Per-booking owner net from the ledger (excluding payouts), as a subquery."""
    where = [
        LedgerEntry.booking_id.is_not(None),
        LedgerEntry.entry_type != EntryType.PAYOUT,
    ]
    where.append(
        LedgerEntry.account == ledger.owner_account(owner_profile_id)
        if owner_profile_id
        else LedgerEntry.account.startswith("owner_payable:")
    )
    return (
        select(
            LedgerEntry.booking_id.label("booking_id"),
            (-func.sum(LedgerEntry.amount_tzs)).label("net"),
        )
        .where(*where)
        .group_by(LedgerEntry.booking_id)
        .subquery()
    )


def _available(booking: Booking) -> bool:
    return (
        booking.status == BookingStatus.COMPLETED
        and booking.completed_at is not None
        and booking.completed_at <= clock.now() - ELIGIBLE_AFTER
    )


# --- earnings (US4-AS1) -------------------------------------------------------------------


async def earnings(
    session: AsyncSession,
    profile: OwnerProfile,
    start: date | None,
    end: date | None,
    locale: Locale,
) -> Earnings:
    """Bookings that earned money, by period start (EAT), newest first."""
    net = _booking_net(profile.id)
    lease_commission = (
        select(
            LeaseInstallment.booking_id.label("booking_id"),
            func.sum(LeaseInstallment.commission_tzs).label("commission"),
        )
        .where(LeaseInstallment.status == InstallmentStatus.PAID)
        .group_by(LeaseInstallment.booking_id)
        .subquery()
    )
    stmt = (
        select(
            Booking,
            Listing.title_sw,
            Listing.title_en,
            net.c.net,
            lease_commission.c.commission,
            Payout.id,
            Payout.status,
        )
        .join(net, net.c.booking_id == Booking.id)
        .join(Listing, Listing.id == Booking.listing_id)
        .outerjoin(lease_commission, lease_commission.c.booking_id == Booking.id)
        .outerjoin(PayoutItem, PayoutItem.booking_id == Booking.id)
        .outerjoin(Payout, Payout.id == PayoutItem.payout_id)
        .where(Booking.owner_profile_id == profile.id)
        .order_by(func.lower(Booking.period).desc(), Booking.id)
    )
    if start is not None:
        stmt = stmt.where(func.lower(Booking.period) >= clock.to_eat_midnight(start))
    if end is not None:
        stmt = stmt.where(
            func.lower(Booking.period) < clock.to_eat_midnight(end + timedelta(days=1))
        )

    items: list[EarningItem] = []
    for booking, title_sw, title_en, net_tzs, lease_comm, payout_id, payout_status in (
        await session.execute(stmt)
    ).all():
        commission = (
            int(lease_comm or 0)
            if booking.booking_mode == BookingMode.LEASE
            else booking.commission_tzs
        )
        status: EarningStatus
        if payout_status is not None:
            status = payout_status.value
        else:
            status = "available" if _available(booking) else "upcoming"
        items.append(
            EarningItem(
                booking_id=booking.id,
                booking_code=booking.code,
                listing_id=booking.listing_id,
                listing_title=localized({"sw": title_sw, "en": title_en}, locale),
                period=PeriodOut(start=booking.period.lower, end=booking.period.upper),
                completed_at=booking.completed_at,
                gross_tzs=int(net_tzs) + commission,
                commission_tzs=commission,
                net_tzs=int(net_tzs),
                status=status,
                payout_id=payout_id,
            )
        )
    net_total = sum(i.net_tzs for i in items)
    paid_out = sum(i.net_tzs for i in items if i.status == "paid")
    return Earnings(
        totals=EarningsTotals(
            gross_tzs=sum(i.gross_tzs for i in items),
            commission_tzs=sum(i.commission_tzs for i in items),
            net_tzs=net_total,
            paid_out_tzs=paid_out,
            pending_tzs=net_total - paid_out,
        ),
        items=items,
    )


# --- batching -----------------------------------------------------------------------------


async def _queue_disburse(session: AsyncSession, payout: Payout) -> None:
    await jobs.enqueue(
        session,
        DISBURSE_JOB,
        {"payout_id": str(payout.id)},
        dedupe_key=f"payout:{payout.id}:{payout.attempts + 1}",
    )


async def create_payouts(session: AsyncSession) -> list[Payout]:
    """The daily sweep: one new payout per owner with eligible bookings. Payouts that failed
    only for want of a payout method are queued again once the owner has added one."""
    net = _booking_net()
    rows = await session.execute(
        select(Booking.id, Booking.owner_profile_id, net.c.net)
        .join(net, net.c.booking_id == Booking.id)
        .where(
            Booking.status == BookingStatus.COMPLETED,
            Booking.completed_at <= clock.now() - ELIGIBLE_AFTER,
            net.c.net > 0,
            ~exists().where(PayoutItem.booking_id == Booking.id),
        )
        .order_by(Booking.owner_profile_id, Booking.completed_at, Booking.id)
        .limit(BATCH)
        .with_for_update(of=Booking, skip_locked=True)
    )
    by_owner: dict[uuid.UUID, list[tuple[uuid.UUID, int]]] = defaultdict(list)
    for booking_id, owner_id, amount in rows.all():
        by_owner[owner_id].append((booking_id, int(amount)))

    created: list[Payout] = []
    for owner_id, bookings in by_owner.items():
        payout = Payout(owner_profile_id=owner_id, amount_tzs=sum(a for _, a in bookings))
        session.add(payout)
        await session.flush()
        session.add_all(
            PayoutItem(payout_id=payout.id, booking_id=booking_id, amount_tzs=amount)
            for booking_id, amount in bookings
        )
        await _queue_disburse(session, payout)
        created.append(payout)

    waiting = await session.execute(
        select(Payout)
        .where(
            Payout.status == PayoutStatus.FAILED,
            Payout.failure_reason == NO_PAYOUT_METHOD,
            exists().where(
                PayoutMethod.owner_profile_id == Payout.owner_profile_id,
                PayoutMethod.is_default.is_(True),
            ),
        )
        .with_for_update(skip_locked=True)
    )
    for payout in waiting.scalars():
        payout.status, payout.failure_reason = PayoutStatus.PENDING, None
        await _queue_disburse(session, payout)
    await session.flush()
    return created


# --- sending and settling -----------------------------------------------------------------


async def _locked(session: AsyncSession, payout_id: uuid.UUID) -> Payout | None:
    return await session.get(Payout, payout_id, with_for_update=True, populate_existing=True)


async def _owner_user_id(session: AsyncSession, payout: Payout) -> uuid.UUID:
    profile = await session.get(OwnerProfile, payout.owner_profile_id)
    assert profile is not None
    return profile.user_id


async def _paid(session: AsyncSession, payout: Payout, provider_ref: str | None) -> None:
    payout.status = PayoutStatus.PAID
    payout.provider_ref = provider_ref or payout.provider_ref
    payout.paid_at = clock.now()
    payout.failure_reason = None
    await session.flush()
    await ledger.post_payout(session, payout.owner_profile_id, payout.amount_tzs, payout.id)
    await notify(
        session,
        await _owner_user_id(session, payout),
        "payout.paid",
        {"amount": money(payout.amount_tzs), "ref": payout.provider_ref or "-"},
    )


async def _failed(session: AsyncSession, payout: Payout, reason: str | None) -> None:
    payout.status = PayoutStatus.FAILED
    payout.failure_reason = reason or "unknown"
    await session.flush()
    await notify(
        session,
        await _owner_user_id(session, payout),
        "payout.failed",
        {"amount": money(payout.amount_tzs)},
    )


async def _apply(
    session: AsyncSession,
    payout: Payout,
    state: PayoutState,
    provider_ref: str | None,
    reason: str | None,
) -> None:
    if state == "paid":
        await _paid(session, payout, provider_ref)
    elif state == "failed":
        await _failed(session, payout, reason)
    elif state == "processing":
        payout.status = PayoutStatus.PROCESSING
        payout.provider_ref = provider_ref or payout.provider_ref
    # "pending": the manual provider; an admin marks it paid.


def _destination(method: PayoutMethod) -> PayoutDestination:
    return PayoutDestination(
        kind=method.kind.value,
        account_name=method.account_name,
        network=Network(method.network.value) if method.network else None,
        msisdn=method.msisdn,
        bank_name=method.bank_name,
        account_number=decrypt(method.account_number_enc) if method.account_number_enc else None,
    )


async def disburse(session: AsyncSession, payout_id: uuid.UUID) -> Payout | None:
    """Send a pending payout to the owner's current default method. Idempotent: anything
    but `pending` is left alone. ProviderUnavailable propagates so the job retries."""
    payout = await _locked(session, payout_id)
    if payout is None or payout.status != PayoutStatus.PENDING:
        return payout
    payout.attempts += 1
    method = (
        await session.execute(
            select(PayoutMethod).where(
                PayoutMethod.owner_profile_id == payout.owner_profile_id,
                PayoutMethod.is_default.is_(True),
            )
        )
    ).scalar_one_or_none()
    if method is None:
        await _failed(session, payout, NO_PAYOUT_METHOD)
        return payout
    provider = get_payout_provider()
    payout.payout_method_id = method.id
    payout.payout_method = payout_method_out(method).model_dump(mode="json")
    payout.provider = provider.name
    result = await provider.disburse(
        payout_id=payout.id, amount_tzs=payout.amount_tzs, destination=_destination(method)
    )
    await _apply(session, payout, result.state, result.provider_ref, result.failure_reason)
    await session.flush()
    return payout


async def poll_processing(session: AsyncSession) -> int:
    """Ask the provider about payouts in `processing`; returns how many settled."""
    rows = await session.execute(
        select(Payout)
        .where(Payout.status == PayoutStatus.PROCESSING)
        .order_by(Payout.updated_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    )
    provider = get_payout_provider()
    settled = 0
    for payout in rows.scalars():
        try:
            status = await provider.get_payout_status(
                payout_id=payout.id, provider_ref=payout.provider_ref or str(payout.id)
            )
        except ProviderUnavailable:
            log.warning("payout status check failed for %s", payout.id)
            continue
        if status.state in ("paid", "failed"):
            await _apply(session, payout, status.state, None, status.failure_reason)
            settled += 1
    await session.flush()
    return settled


# --- admin (R7 manual fallback) -----------------------------------------------------------


def _invalid(payout: Payout) -> AppError:
    return AppError("INVALID_TRANSITION", 409, {"status": payout.status.value})


async def _admin_payout(session: AsyncSession, payout_id: uuid.UUID) -> Payout:
    payout = await _locked(session, payout_id)
    if payout is None:
        raise not_found("payout")
    return payout


async def mark_paid(
    session: AsyncSession, admin: User, payout_id: uuid.UUID, provider_ref: str
) -> Payout:
    """An admin sent the money outside the platform and records the transfer reference."""
    payout = await _admin_payout(session, payout_id)
    if payout.status == PayoutStatus.PAID:
        raise _invalid(payout)
    before = {"status": payout.status.value, "provider_ref": payout.provider_ref}
    payout.provider = "manual"
    payout.marked_paid_by = admin.id
    await _paid(session, payout, provider_ref)
    await audit(
        session,
        admin,
        "payout.mark_paid",
        "payout",
        payout.id,
        before,
        {"status": payout.status.value, "provider_ref": provider_ref},
    )
    return payout


async def retry(session: AsyncSession, admin: User, payout_id: uuid.UUID) -> Payout:
    """A failed payout goes back to `pending` and is sent again."""
    payout = await _admin_payout(session, payout_id)
    if payout.status != PayoutStatus.FAILED:
        raise _invalid(payout)
    before = {"status": payout.status.value, "failure_reason": payout.failure_reason}
    payout.status, payout.failure_reason = PayoutStatus.PENDING, None
    await _queue_disburse(session, payout)
    await session.flush()
    await audit(session, admin, "payout.retry", "payout", payout.id, before, {"status": "pending"})
    return payout


# --- listings -----------------------------------------------------------------------------


async def _items(
    session: AsyncSession, payout_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[PayoutItemOut]]:
    out: dict[uuid.UUID, list[PayoutItemOut]] = defaultdict(list)
    if not payout_ids:
        return out
    rows = await session.execute(
        select(PayoutItem, Booking.code)
        .join(Booking, Booking.id == PayoutItem.booking_id)
        .where(PayoutItem.payout_id.in_(payout_ids))
        .order_by(PayoutItem.created_at, PayoutItem.id)
    )
    for item, code in rows.all():
        out[item.payout_id].append(
            PayoutItemOut(booking_id=item.booking_id, booking_code=code, amount_tzs=item.amount_tzs)
        )
    return out


def payout_out(payout: Payout, items: list[PayoutItemOut]) -> PayoutOut:
    return PayoutOut(
        id=payout.id,
        amount_tzs=payout.amount_tzs,
        status=payout.status.value,
        provider=payout.provider,
        provider_ref=payout.provider_ref,
        failure_reason=payout.failure_reason,
        destination=payout.payout_method,
        paid_at=payout.paid_at,
        created_at=payout.created_at,
        items=items,
    )


async def owner_payouts(
    session: AsyncSession, profile: OwnerProfile, page: int, page_size: int
) -> Page[PayoutOut]:
    where = Payout.owner_profile_id == profile.id
    total = (
        await session.execute(select(func.count()).select_from(Payout).where(where))
    ).scalar_one()
    payouts = list(
        (
            await session.execute(
                select(Payout)
                .where(where)
                .order_by(Payout.created_at.desc(), Payout.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    items = await _items(session, [p.id for p in payouts])
    return Page[PayoutOut](
        items=[payout_out(p, items[p.id]) for p in payouts],
        page=page,
        page_size=page_size,
        total=total,
    )


async def admin_payout_out(session: AsyncSession, payout: Payout) -> AdminPayoutOut:
    [out] = await _admin_outs(session, [payout])
    return out


async def _admin_outs(session: AsyncSession, payouts: list[Payout]) -> list[AdminPayoutOut]:
    items = await _items(session, [p.id for p in payouts])
    owners = {
        profile.id: PayoutOwner(id=profile.id, display_name=profile.display_name, phone=phone)
        for profile, phone in (
            await session.execute(
                select(OwnerProfile, User.phone)
                .join(User, User.id == OwnerProfile.user_id)
                .where(OwnerProfile.id.in_({p.owner_profile_id for p in payouts}))
            )
        ).all()
    }
    return [
        AdminPayoutOut(
            **payout_out(p, items[p.id]).model_dump(),
            owner=owners[p.owner_profile_id],
            attempts=p.attempts,
        )
        for p in payouts
    ]


async def admin_payouts(
    session: AsyncSession, status: PayoutStatus | None, page: int, page_size: int
) -> Page[AdminPayoutOut]:
    """Oldest first, so the longest-waiting payouts are handled first."""
    where = [Payout.status == status] if status else []
    total = (
        await session.execute(select(func.count()).select_from(Payout).where(*where))
    ).scalar_one()
    payouts = list(
        (
            await session.execute(
                select(Payout)
                .where(*where)
                .order_by(Payout.created_at, Payout.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    return Page[AdminPayoutOut](
        items=await _admin_outs(session, payouts) if payouts else [],
        page=page,
        page_size=page_size,
        total=total,
    )
