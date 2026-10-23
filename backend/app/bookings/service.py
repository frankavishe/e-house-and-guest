"""Bookings (US2, US5): creation, owner decisions, cancellation and the views parties see.

Write functions flush but do not commit; the router commits (with the idempotency record
when there is one), so a booking, its hold, events and notifications land together.
"""

import secrets
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import Select, func, select, update
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User
from app.availability import service as availability
from app.availability.periods import add_months, check_duration
from app.bookings.models import (
    ActorKind,
    Booking,
    BookingEvent,
    BookingStatus,
    CancelledBy,
    InstallmentStatus,
    LeaseInstallment,
)
from app.bookings.policies import CancelRefund, Charged, cancellation_refund
from app.bookings.schemas import (
    BookingCreate,
    BookingOut,
    BookingSummary,
    Can,
    CancelPreviewOut,
    Counterpart,
    EventOut,
    InstallmentOut,
    PaymentOut,
    PeriodOut,
    Receipt,
    ReceiptPayment,
    RefundOut,
    RoleT,
)
from app.bookings.state import Event, invalid_transition, record, transition
from app.catalog.models import BookingMode, Category
from app.core import clock
from app.core.errors import AppError, forbidden, not_found
from app.core.i18n import Locale
from app.core.security import mask_tail
from app.ledger import service as ledger
from app.listings import service as listings
from app.listings.models import Listing
from app.listings.schemas import ListingCard, Page
from app.payments import refunds
from app.payments.models import Payment, PaymentStatus, Refund, RefundReason
from app.pricing.schemas import Quote
from app.pricing.service import BPS, round_half_up
from app.pricing.service import quote as price_quote

INSTANT_PAYMENT_WINDOW = timedelta(minutes=15)
REQUEST_WINDOW = timedelta(hours=24)
ACCEPTED_PAYMENT_WINDOW = timedelta(hours=24)
CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32
CODE_ATTEMPTS = 5
# Statuses in which the parties see each other's phone numbers (R18).
REVEALED = {
    BookingStatus.CONFIRMED,
    BookingStatus.IN_PROGRESS,
    BookingStatus.COMPLETED,
    BookingStatus.DISPUTED,
}
PAID = REVEALED
OPEN_LEASE = {BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS}
# Who may cancel from which status (US5). Owners decline requests instead; only admins stop
# a running booking. A disputed booking is settled through its claim.
CANCELLABLE: dict[CancelledBy, set[BookingStatus]] = {
    CancelledBy.RENTER: {
        BookingStatus.REQUESTED,
        BookingStatus.AWAITING_PAYMENT,
        BookingStatus.CONFIRMED,
    },
    CancelledBy.OWNER: {BookingStatus.AWAITING_PAYMENT, BookingStatus.CONFIRMED},
    CancelledBy.ADMIN: {
        BookingStatus.REQUESTED,
        BookingStatus.AWAITING_PAYMENT,
        BookingStatus.CONFIRMED,
        BookingStatus.IN_PROGRESS,
    },
}
REFUND_REASON = {
    CancelledBy.RENTER: RefundReason.CANCELLATION,
    CancelledBy.OWNER: RefundReason.OWNER_CANCEL,
    CancelledBy.ADMIN: RefundReason.ADMIN,
}


def new_code() -> str:
    return "EHG-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))


def split(total: int, parts: int) -> list[int]:
    """`total` in `parts` integer shares; the remainder goes on the first."""
    share, rest = divmod(total, parts)
    return [share + rest] + [share] * (parts - 1)


# --- creation -----------------------------------------------------------------------------


async def _insert(session: AsyncSession, booking: Booking) -> None:
    """Insert with a fresh code, retrying the rare clash on `code`."""
    for attempt in range(CODE_ATTEMPTS):
        booking.code = new_code()
        try:
            async with session.begin_nested():
                session.add(booking)
                await session.flush()
            return
        except IntegrityError:
            if attempt == CODE_ATTEMPTS - 1:
                raise


def _lease_installments(booking: Booking, months: int) -> list[LeaseInstallment]:
    rentals = split(booking.rental_tzs, months)
    fees = split(booking.service_fee_tzs, months)
    commissions = split(booking.commission_tzs, months)
    assert booking.period.lower is not None
    first_day = clock.to_eat(booking.period.lower).date()
    out = []
    for i in range(months):
        start = clock.to_eat_midnight(add_months(first_day, i))
        end = clock.to_eat_midnight(add_months(first_day, i + 1))
        out.append(
            LeaseInstallment(
                booking_id=booking.id,
                seq=i + 1,
                period=Range(start, end, bounds="[)"),
                rental_tzs=rentals[i],
                service_fee_tzs=fees[i],
                commission_tzs=commissions[i],
                amount_tzs=rentals[i] + fees[i],
                due_at=start,
                status=InstallmentStatus.PENDING,
            )
        )
    return out


async def create_booking(session: AsyncSession, renter: User, body: BookingCreate) -> Booking:
    """Validate, price, hold and record a booking in the caller's transaction."""
    listing, category = await listings.get_public_listing(session, body.listing_id)
    mode = category.booking_mode
    assert mode is not None
    if not body.period.fits(mode):
        raise AppError("INVALID_PERIOD", 400, {"reason": "wrong_mode", "booking_mode": mode.value})
    owner = await session.get(OwnerProfile, listing.owner_profile_id)
    assert owner is not None
    if owner.user_id == renter.id:
        raise AppError("OWN_LISTING", 422)
    period = listings.period_for(category, listing, body.period)
    check_duration(period, listing)
    prices = (await listings.prices_for(session, [listing.id]))[listing.id]
    quote = price_quote(
        listing,
        prices,
        category,
        period,
        delivery=body.delivery,
        delivery_district_id=body.delivery_district_id,
        require_district=True,
    )
    await availability.lock_listing(session, listing.id)
    now = clock.now()
    instant = listing.instant_book
    booking = Booking(
        listing_id=listing.id,
        renter_id=renter.id,
        owner_profile_id=owner.id,
        booking_mode=mode,
        period=period.range,
        quantity=period.quantity,
        status=BookingStatus.AWAITING_PAYMENT if instant else BookingStatus.REQUESTED,
        quote=quote.model_dump(mode="json"),
        rental_tzs=quote.rental_tzs,
        delivery_fee_tzs=quote.delivery_fee_tzs,
        service_fee_tzs=quote.service_fee_tzs,
        deposit_tzs=quote.deposit_tzs,
        total_tzs=quote.total_tzs,
        commission_bps=category.commission_bps,
        commission_tzs=round_half_up(quote.rental_tzs * category.commission_bps, BPS),
        cancellation_policy=listing.cancellation_policy,
        delivery_requested=quote.delivery_fee_tzs > 0 or body.delivery,
        delivery_address=body.delivery_address,
        payment_due_at=now + INSTANT_PAYMENT_WINDOW if instant else None,
        request_expires_at=None if instant else now + REQUEST_WINDOW,
        lease_months=period.count if mode == BookingMode.LEASE else None,
    )
    await _insert(session, booking)
    await availability.reserve(session, listing, mode, period, booking.id)
    if mode == BookingMode.LEASE:
        session.add_all(_lease_installments(booking, period.count))
    await record(
        session,
        booking,
        None,
        actor_kind=ActorKind.USER,
        actor_user_id=renter.id,
        note=body.message,
    )
    await session.flush()

    from app.bookings.notify import on_created

    await on_created(session, booking)
    return booking


# --- reads --------------------------------------------------------------------------------


async def installments_of(session: AsyncSession, booking_id: uuid.UUID) -> list[LeaseInstallment]:
    rows = await session.execute(
        select(LeaseInstallment)
        .where(LeaseInstallment.booking_id == booking_id)
        .order_by(LeaseInstallment.seq)
    )
    return list(rows.scalars())


async def payments_of(session: AsyncSession, booking_id: uuid.UUID) -> list[Payment]:
    rows = await session.execute(
        select(Payment).where(Payment.booking_id == booking_id).order_by(Payment.created_at)
    )
    return list(rows.scalars())


def first_payment_amount(booking: Booking, installments: Sequence[LeaseInstallment]) -> int:
    """What confirms the booking: the total, or for a lease month 1 + deposit + delivery."""
    if booking.booking_mode == BookingMode.LEASE and installments:
        return installments[0].amount_tzs + booking.deposit_tzs + booking.delivery_fee_tzs
    return booking.total_tzs


def installment_payable(booking: Booking, inst: LeaseInstallment) -> bool:
    """Later installments are payable once billed, while the lease runs."""
    return (
        booking.status in OPEN_LEASE
        and inst.seq > 1
        and inst.billed_at is not None
        and inst.status in (InstallmentStatus.PENDING, InstallmentStatus.OVERDUE)
    )


def amount_due(booking: Booking, installments: Sequence[LeaseInstallment]) -> int:
    if booking.status in (BookingStatus.REQUESTED, BookingStatus.AWAITING_PAYMENT):
        return first_payment_amount(booking, installments)
    payable = [i for i in installments if installment_payable(booking, i)]
    return payable[0].amount_tzs if payable else 0


def payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        booking_id=p.booking_id,
        installment_id=p.lease_installment_id,
        status=p.status.value,
        network=p.network.value,
        msisdn=mask_tail(p.msisdn),
        amount_tzs=p.amount_tzs,
        failure_reason=p.failure_reason,
        created_at=p.created_at,
        confirmed_at=p.confirmed_at,
    )


def _period(booking_period: Range[datetime]) -> PeriodOut:
    assert booking_period.lower is not None and booking_period.upper is not None
    return PeriodOut(start=booking_period.lower, end=booking_period.upper)


async def _role(session: AsyncSession, user: User, booking: Booking) -> RoleT | None:
    if booking.renter_id == user.id:
        return "renter"
    owner = await session.get(OwnerProfile, booking.owner_profile_id)
    if owner is not None and owner.user_id == user.id:
        return "owner"
    return "admin" if user.is_admin else None


async def get_for_party(
    session: AsyncSession, user: User, booking_id: uuid.UUID, *, lock: bool = False
) -> tuple[Booking, RoleT]:
    """The booking and the viewer's role; 404 for anyone who is not a party or an admin."""
    booking = await session.get(
        Booking, booking_id, with_for_update=True if lock else None, populate_existing=lock
    )
    if booking is None:
        raise not_found("booking")
    role = await _role(session, user, booking)
    if role is None:
        raise not_found("booking")
    return booking, role


async def _cards(
    session: AsyncSession, listing_ids: Sequence[uuid.UUID], locale: Locale
) -> dict[uuid.UUID, ListingCard]:
    if not listing_ids:
        return {}
    rows = await session.execute(
        select(Listing, Category)
        .join(Category, Category.id == Listing.category_id)
        .where(Listing.id.in_(set(listing_ids)))
    )
    pairs = [(listing, category) for listing, category in rows.all()]
    cards = await listings.cards(session, pairs, locale)
    return {card.id: card for card in cards}


async def _counterpart(session: AsyncSession, booking: Booking, role: RoleT) -> Counterpart:
    revealed = booking.status in REVEALED
    if role == "renter":
        owner = await session.get(OwnerProfile, booking.owner_profile_id)
        assert owner is not None
        owner_user = await session.get(User, owner.user_id)
        assert owner_user is not None
        return Counterpart(name=owner.display_name, phone=owner_user.phone if revealed else None)
    renter = await session.get(User, booking.renter_id)
    assert renter is not None
    return Counterpart(
        name=renter.name or "", phone=renter.phone if revealed or role == "admin" else None
    )


async def booking_out(
    session: AsyncSession, booking: Booking, role: RoleT, locale: Locale
) -> BookingOut:
    from app.reviews import service as reviews

    installments = await installments_of(session, booking.id)
    payments = await payments_of(session, booking.id)
    pending = any(p.status == PaymentStatus.PENDING for p in payments)
    events = (
        (
            await session.execute(
                select(BookingEvent)
                .where(BookingEvent.booking_id == booking.id)
                .order_by(BookingEvent.created_at, BookingEvent.id)
            )
        )
        .scalars()
        .all()
    )
    card = (await _cards(session, [booking.listing_id], locale))[booking.listing_id]
    now = clock.now()
    awaiting = booking.status == BookingStatus.AWAITING_PAYMENT and (
        booking.payment_due_at is None or booking.payment_due_at > now
    )
    lease_due = any(installment_payable(booking, i) for i in installments)
    is_owner = role == "owner"
    from app.bookings import claims as claim_service

    claims = await claim_service.claims_of(session, booking.id)
    claim_kinds = claim_service.claim_kinds(booking, role, claims)
    return BookingOut(
        id=booking.id,
        code=booking.code,
        status=booking.status.value,
        role=role,
        listing=card,
        period=_period(booking.period),
        quantity=booking.quantity,
        quote=Quote.model_validate(booking.quote),
        amount_due_tzs=amount_due(booking, installments),
        payment_due_at=booking.payment_due_at,
        request_expires_at=booking.request_expires_at,
        cancellation_policy=booking.cancellation_policy.value,
        delivery_requested=booking.delivery_requested,
        delivery_address=booking.delivery_address,
        lease_months=booking.lease_months,
        can=Can(
            pay=role == "renter" and not pending and (awaiting or lease_due),
            cancel=booking.status in CANCELLABLE[canceller(role)],
            accept=is_owner and booking.status == BookingStatus.REQUESTED,
            decline=is_owner and booking.status == BookingStatus.REQUESTED,
            review=await reviews.can_review(session, booking, role),
            claim=bool(claim_kinds),
        ),
        counterpart=await _counterpart(session, booking, role),
        events=[
            EventOut(
                from_status=e.from_status.value if e.from_status else None,
                to_status=e.to_status.value,
                actor_kind=e.actor_kind.value,
                created_at=e.created_at,
            )
            for e in events
        ],
        payments=[payment_out(p) for p in payments],
        installments=[
            InstallmentOut(
                id=i.id,
                seq=i.seq,
                period=_period(i.period),
                amount_tzs=i.amount_tzs,
                due_at=i.due_at,
                status=i.status.value,
                payable=installment_payable(booking, i),
            )
            for i in installments
        ]
        if booking.booking_mode == BookingMode.LEASE
        else None,
        refunds=[refund_out(r) for r in await refunds.refunds_of(session, booking.id)],
        claims=[await claim_service.claim_out(session, booking, c) for c in claims],
        cancelled_by=booking.cancelled_by.value if booking.cancelled_by else None,
        cancel_reason=booking.cancel_reason,
        request_message=next((e.note for e in events if e.from_status is None), None),
        created_at=booking.created_at,
    )


def refund_out(r: Refund) -> RefundOut:
    return RefundOut(
        id=r.id,
        amount_tzs=r.amount_tzs,
        reason=r.reason.value,
        status=r.status.value,
        provider_ref=r.provider_ref,
        failure_reason=r.failure_reason,
        created_at=r.created_at,
    )


async def list_bookings(
    session: AsyncSession,
    user: User,
    role: RoleT,
    status: BookingStatus | None,
    page: int,
    page_size: int,
    locale: Locale,
) -> Page[BookingSummary]:
    query: Select[Booking] = select(Booking)
    if role == "owner":
        query = query.join(OwnerProfile, OwnerProfile.id == Booking.owner_profile_id).where(
            OwnerProfile.user_id == user.id
        )
    else:
        query = query.where(Booking.renter_id == user.id)
    if status is not None:
        query = query.where(Booking.status == status)
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                query.order_by(Booking.created_at.desc(), Booking.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    cards = await _cards(session, [b.listing_id for b in rows], locale)
    ids = [b.id for b in rows]
    events = await session.execute(
        select(BookingEvent.booking_id, BookingEvent.note).where(
            BookingEvent.booking_id.in_(ids), BookingEvent.from_status.is_(None)
        )
    )
    messages = {booking_id: note for booking_id, note in events.all()}
    if role == "owner":
        names_query = select(Booking.id, User.name).join(User, User.id == Booking.renter_id)
    else:
        names_query = select(Booking.id, OwnerProfile.display_name).join(
            OwnerProfile, OwnerProfile.id == Booking.owner_profile_id
        )
    names = {
        booking_id: name
        for booking_id, name in (await session.execute(names_query.where(Booking.id.in_(ids))))
    }
    return Page[BookingSummary](
        items=[
            BookingSummary(
                id=b.id,
                code=b.code,
                status=b.status.value,
                role=role,
                listing=cards[b.listing_id],
                period=_period(b.period),
                quantity=b.quantity,
                total_tzs=b.total_tzs,
                payment_due_at=b.payment_due_at,
                request_expires_at=b.request_expires_at,
                counterpart_name=names.get(b.id) or "",
                request_message=messages.get(b.id),
                created_at=b.created_at,
            )
            for b in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


# --- owner decisions ----------------------------------------------------------------------


async def _owned(session: AsyncSession, owner: OwnerProfile, booking_id: uuid.UUID) -> Booking:
    booking = await session.get(Booking, booking_id, with_for_update=True, populate_existing=True)
    if booking is None:
        raise not_found("booking")
    if booking.owner_profile_id != owner.id:
        raise forbidden()
    return booking


async def accept(
    session: AsyncSession, owner: OwnerProfile, user: User, booking_id: uuid.UUID
) -> Booking:
    """`requested → awaiting_payment`; the renter then has 24 h to pay (FR-017)."""
    booking = await _owned(session, owner, booking_id)
    booking.payment_due_at = clock.now() + ACCEPTED_PAYMENT_WINDOW
    await transition(
        session, booking, Event.ACCEPT, actor_kind=ActorKind.USER, actor_user_id=user.id
    )
    return booking


async def decline(
    session: AsyncSession,
    owner: OwnerProfile,
    user: User,
    booking_id: uuid.UUID,
    reason: str | None,
) -> Booking:
    booking = await _owned(session, owner, booking_id)
    await transition(
        session,
        booking,
        Event.DECLINE,
        actor_kind=ActorKind.USER,
        actor_user_id=user.id,
        cancelled_by=CancelledBy.OWNER,
        note=reason,
    )
    booking.cancel_reason = reason
    await availability.release(session, booking.id)
    return booking


# --- cancellation (US5, FR-026) ----------------------------------------------------------


def canceller(role: RoleT) -> CancelledBy:
    return {"renter": CancelledBy.RENTER, "owner": CancelledBy.OWNER}.get(role, CancelledBy.ADMIN)


async def charged(session: AsyncSession, booking: Booking) -> Charged:
    """What the renter has paid for this booking (nothing before it is confirmed)."""
    if booking.status not in PAID:
        return Charged()
    if booking.booking_mode != BookingMode.LEASE:
        return Charged(
            rental_tzs=booking.rental_tzs,
            delivery_fee_tzs=booking.delivery_fee_tzs,
            service_fee_tzs=booking.service_fee_tzs,
            deposit_tzs=booking.deposit_tzs,
            commission_tzs=booking.commission_tzs,
        )
    paid = [
        i for i in await installments_of(session, booking.id) if i.status == InstallmentStatus.PAID
    ]
    if not paid:
        return Charged()
    return Charged(
        rental_tzs=sum(i.rental_tzs for i in paid),
        delivery_fee_tzs=booking.delivery_fee_tzs,
        service_fee_tzs=sum(i.service_fee_tzs for i in paid),
        deposit_tzs=booking.deposit_tzs,
        commission_tzs=sum(i.commission_tzs for i in paid),
    )


async def _refund_for(session: AsyncSession, booking: Booking, by: CancelledBy) -> CancelRefund:
    if booking.status not in CANCELLABLE[by]:
        raise invalid_transition(booking.status, Event.CANCEL)
    assert booking.period.lower is not None
    return cancellation_refund(
        booking.cancellation_policy,
        booking.period.lower,
        await charged(session, booking),
        by=by,
        now=clock.now(),
    )


def preview_out(refund: CancelRefund, by: CancelledBy) -> CancelPreviewOut:
    return CancelPreviewOut(
        policy=refund.policy.value,
        cancelled_by=by.value,
        percent=refund.percent,
        paid_tzs=refund.paid_tzs,
        rental_refund_tzs=refund.rental_tzs,
        delivery_refund_tzs=refund.delivery_fee_tzs,
        service_fee_refund_tzs=refund.service_fee_tzs,
        deposit_refund_tzs=refund.deposit_tzs,
        refund_tzs=refund.total_tzs,
        deadline=refund.deadline,
    )


async def cancel_preview(
    session: AsyncSession, user: User, booking_id: uuid.UUID
) -> CancelPreviewOut:
    booking, role = await get_for_party(session, user, booking_id)
    by = canceller(role)
    return preview_out(await _refund_for(session, booking, by), by)


async def _issue_refund(
    session: AsyncSession, booking: Booking, refund: CancelRefund, by: CancelledBy, user: User
) -> Refund | None:
    """Queue the policy refund, each part capped at what its account still holds for the
    booking (an earlier admin refund may have taken some already)."""

    async def left(account: str) -> int:
        return max(-(await ledger.booking_balance(session, booking.id, account)), 0)

    platform = await left(ledger.PLATFORM_REVENUE)
    commission = min(refund.commission_tzs, platform)
    return await refunds.issue(
        session,
        booking,
        reason=REFUND_REASON[by],
        created_by=user.id,
        from_owner_tzs=min(
            refund.from_owner_tzs, await left(ledger.owner_account(booking.owner_profile_id))
        ),
        from_commission_tzs=commission,
        from_service_fee_tzs=min(refund.service_fee_tzs, platform - commission),
        from_deposit_tzs=min(refund.deposit_tzs, await left(ledger.DEPOSIT_HELD)),
    )


async def cancel(
    session: AsyncSession,
    user: User,
    booking_id: uuid.UUID,
    reason: str | None,
    *,
    as_admin: bool = False,
) -> Booking:
    """Cancel under the booking's policy: release the dates, waive unbilled lease months and
    queue the refund. An owner's cancellation refunds in full and counts against them."""
    booking, role = await get_for_party(session, user, booking_id, lock=True)
    by = CancelledBy.ADMIN if as_admin else canceller(role)
    refund = await _refund_for(session, booking, by)
    before = booking.status
    await transition(
        session,
        booking,
        Event.CANCEL,
        actor_kind=ActorKind.USER,
        actor_user_id=user.id,
        cancelled_by=by,
        note=reason,
    )
    booking.cancel_reason = reason
    booking.payment_due_at = None
    await availability.release(session, booking.id)
    if by == CancelledBy.OWNER:
        owner = await session.get(OwnerProfile, booking.owner_profile_id)
        assert owner is not None
        await session.execute(
            update(User)
            .where(User.id == owner.user_id)
            .values(owner_cancellation_count=User.owner_cancellation_count + 1)
        )
    for inst in await installments_of(session, booking.id):
        if inst.status in (InstallmentStatus.PENDING, InstallmentStatus.OVERDUE):
            inst.status = InstallmentStatus.WAIVED
    issued = await _issue_refund(session, booking, refund, by, user)
    if as_admin:
        from app.admin.moderation import audit

        await audit(
            session,
            user,
            "booking.cancel",
            "booking",
            booking.id,
            {"status": before.value},
            {
                "status": booking.status.value,
                "reason": reason,
                "refund_tzs": issued.amount_tzs if issued else 0,
            },
        )
    await session.flush()
    return booking


# --- receipt ------------------------------------------------------------------------------


async def receipt(
    session: AsyncSession, user: User, booking_id: uuid.UUID, locale: Locale
) -> Receipt:
    booking, _ = await get_for_party(session, user, booking_id)
    if booking.status not in PAID:
        raise AppError("BOOKING_NOT_PAID", 409)
    paid = [
        p for p in await payments_of(session, booking.id) if p.status == PaymentStatus.SUCCEEDED
    ]
    listing = await session.get(Listing, booking.listing_id)
    owner = await session.get(OwnerProfile, booking.owner_profile_id)
    renter = await session.get(User, booking.renter_id)
    assert listing is not None and owner is not None and renter is not None
    return Receipt(
        code=booking.code,
        status=booking.status.value,
        listing_title=listing.title(locale),
        owner_name=owner.display_name,
        renter_name=renter.name or "",
        period=_period(booking.period),
        quantity=booking.quantity,
        quote=Quote.model_validate(booking.quote),
        total_tzs=booking.total_tzs,
        paid_tzs=sum(p.amount_tzs for p in paid),
        payments=[
            ReceiptPayment(
                id=p.id,
                network=p.network.value,
                provider_txn_id=p.provider_txn_id,
                amount_tzs=p.amount_tzs,
                confirmed_at=p.confirmed_at,
            )
            for p in paid
        ],
        issued_at=min((p.confirmed_at for p in paid if p.confirmed_at), default=clock.now()),
    )
