"""Admin booking search (US5, FR-031): find a booking to cancel, refund or follow up."""

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.accounts.models import OwnerProfile, User, UserStatus
from app.admin.schemas import AdminBookingSummary, AdminParty
from app.bookings.models import Booking, BookingStatus, Claim, ClaimStatus
from app.bookings.schemas import PeriodOut
from app.core import clock
from app.core.i18n import Locale
from app.listings.models import Listing, ListingStatus
from app.listings.schemas import Page
from app.listings.service import localized


async def admin_bookings(
    session: AsyncSession,
    status: BookingStatus | None,
    q: str | None,
    page: int,
    page_size: int,
    locale: Locale,
    attention_only: bool = False,
) -> Page[AdminBookingSummary]:
    """Newest first. `q` matches the booking code or either party's phone; `attention_only`
    keeps future bookings whose listing or a party is suspended."""
    renter = aliased(User)
    owner_user = aliased(User)
    open_claim = exists().where(Claim.booking_id == Booking.id, Claim.status == ClaimStatus.OPEN)
    attention: ColumnElement[bool] = and_(
        Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS]),
        func.upper(Booking.period) > clock.now(),
        or_(
            Listing.status == ListingStatus.SUSPENDED,
            renter.status == UserStatus.SUSPENDED,
            owner_user.status == UserStatus.SUSPENDED,
        ),
    )
    query = (
        select(
            Booking,
            Listing.title_sw,
            Listing.title_en,
            renter,
            OwnerProfile.display_name,
            owner_user.phone,
            open_claim,
            attention,
        )
        .join(Listing, Listing.id == Booking.listing_id)
        .join(renter, renter.id == Booking.renter_id)
        .join(OwnerProfile, OwnerProfile.id == Booking.owner_profile_id)
        .join(owner_user, owner_user.id == OwnerProfile.user_id)
    )
    if status is not None:
        query = query.where(Booking.status == status)
    if attention_only:
        query = query.where(attention)
    if q:
        term = q.strip()
        query = query.where(
            or_(
                Booking.code.ilike(f"%{term}%"),
                renter.phone.contains(term),
                owner_user.phone.contains(term),
            )
        )
    total = (await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = await session.execute(
        query.order_by(Booking.created_at.desc(), Booking.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for booking, title_sw, title_en, r, owner_name, owner_phone, claimed, flagged in rows.all():
        assert booking.period.lower is not None and booking.period.upper is not None
        items.append(
            AdminBookingSummary(
                id=booking.id,
                code=booking.code,
                status=booking.status.value,
                listing_id=booking.listing_id,
                listing_title=localized({"sw": title_sw or "", "en": title_en or ""}, locale),
                period=PeriodOut(start=booking.period.lower, end=booking.period.upper),
                total_tzs=booking.total_tzs,
                renter=AdminParty(id=r.id, name=r.name or "", phone=r.phone),
                owner=AdminParty(id=booking.owner_profile_id, name=owner_name, phone=owner_phone),
                open_claim=bool(claimed),
                attention=bool(flagged),
                created_at=booking.created_at,
            )
        )
    return Page[AdminBookingSummary](items=items, page=page, page_size=page_size, total=total)
