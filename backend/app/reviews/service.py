"""Reviews and abuse reports (T130, US6, FR-029, FR-030).

After a `completed` booking the renter rates the listing (counted for the listing and its
owner) and the owner rates the renter, once each. Averages are recomputed from the reviews
on every insert, so they never drift.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import OwnerProfile, User, UserStatus, VerificationStatus
from app.bookings import notify
from app.bookings.models import Booking, BookingStatus
from app.bookings.schemas import RoleT
from app.core.errors import AppError, not_found
from app.listings.models import Listing
from app.listings.schemas import OwnerRating, ReviewOut
from app.listings.service import get_public_listing
from app.reviews.models import AbuseReport, ReportStatus, ReportTarget, Review, ReviewSubject
from app.reviews.schemas import ReportIn, ReviewIn, UserProfile, UserReviewOut, UserReviews

RECENT = 5


def first_name(name: str | None) -> str:
    return (name or "").split(" ", 1)[0]


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


# --- writing ------------------------------------------------------------------------------


async def has_reviewed(session: AsyncSession, booking_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = await session.execute(
        select(Review.id).where(Review.booking_id == booking_id, Review.author_id == user_id)
    )
    return row.first() is not None


async def can_review(session: AsyncSession, booking: Booking, role: RoleT) -> bool:
    if role == "admin" or booking.status != BookingStatus.COMPLETED:
        return False
    author_id = (
        booking.renter_id if role == "renter" else await notify.owner_user_id(session, booking)
    )
    return not await has_reviewed(session, booking.id, author_id)


async def _aggregate(
    session: AsyncSession, *where: ColumnElement[bool]
) -> tuple[Decimal | None, int]:
    row = await session.execute(
        select(func.round(func.avg(Review.rating), 2), func.count())
        .select_from(Review)
        .join(Booking, Booking.id == Review.booking_id)
        .where(*where)
    )
    avg, count = row.one()
    return avg, count


async def _recompute(session: AsyncSession, booking: Booking, subject: ReviewSubject) -> None:
    if subject == ReviewSubject.RENTER:
        renter = await session.get(User, booking.renter_id)
        assert renter is not None
        renter.rating_avg, renter.rating_count = await _aggregate(
            session, Review.subject == subject, Booking.renter_id == booking.renter_id
        )
        return
    listing = await session.get(Listing, booking.listing_id)
    owner = await session.get(OwnerProfile, booking.owner_profile_id)
    assert listing is not None and owner is not None
    listing.rating_avg, listing.rating_count = await _aggregate(
        session, Review.subject == subject, Booking.listing_id == booking.listing_id
    )
    owner.rating_avg, owner.rating_count = await _aggregate(
        session, Review.subject == subject, Booking.owner_profile_id == booking.owner_profile_id
    )


async def create_review(
    session: AsyncSession, user: User, booking_id: uuid.UUID, body: ReviewIn
) -> Review:
    """403 unless the viewer is a party of a completed booking; 409 on a second review."""
    from app.bookings.service import get_for_party

    booking, role = await get_for_party(session, user, booking_id, lock=True)
    if role == "admin" or booking.status != BookingStatus.COMPLETED:
        raise AppError("REVIEW_NOT_ALLOWED", 403, {"status": booking.status.value})
    if await has_reviewed(session, booking.id, user.id):
        raise AppError("ALREADY_REVIEWED", 409)
    subject = ReviewSubject.LISTING if role == "renter" else ReviewSubject.RENTER
    review = Review(
        booking_id=booking.id,
        author_id=user.id,
        subject=subject,
        rating=body.rating,
        body=body.body or None,
    )
    session.add(review)  # the booking row lock serialises concurrent reviews
    await session.flush()
    await _recompute(session, booking, subject)
    if role == "renter":
        await notify.to_owner(session, booking, "review.received", rating=body.rating)
    else:
        await notify.to_renter(session, booking, "review.received", rating=body.rating)
    return review


# --- reading ------------------------------------------------------------------------------


async def review_outs(session: AsyncSession, reviews: Sequence[Review]) -> list[ReviewOut]:
    """Renters are shown by first name; owners by their display name."""
    authors = {
        u.id: u
        for u in (
            await session.execute(select(User).where(User.id.in_({r.author_id for r in reviews})))
        ).scalars()
    }
    owners = {
        o.user_id: o.display_name
        for o in (
            await session.execute(
                select(OwnerProfile).where(OwnerProfile.user_id.in_(set(authors)))
            )
        ).scalars()
    }
    return [
        ReviewOut(
            rating=r.rating,
            comment=r.body,
            author=(
                owners.get(r.author_id, "")
                if r.subject == ReviewSubject.RENTER
                else first_name(authors[r.author_id].name)
            ),
            created_at=r.created_at,
        )
        for r in reviews
    ]


def _listing_reviews(listing_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
    return (
        Review.subject == ReviewSubject.LISTING,
        Review.booking_id.in_(select(Booking.id).where(Booking.listing_id == listing_id)),
    )


async def recent_reviews(session: AsyncSession, listing_id: uuid.UUID) -> list[ReviewOut]:
    rows = await session.execute(
        select(Review)
        .where(*_listing_reviews(listing_id))
        .order_by(Review.created_at.desc(), Review.id.desc())
        .limit(RECENT)
    )
    return await review_outs(session, list(rows.scalars()))


async def listing_reviews(
    session: AsyncSession, listing_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[ReviewOut], int]:
    await get_public_listing(session, listing_id)
    where = _listing_reviews(listing_id)
    total = (
        await session.execute(select(func.count()).select_from(Review).where(*where))
    ).scalar_one()
    rows = await session.execute(
        select(Review)
        .where(*where)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return await review_outs(session, list(rows.scalars())), total


async def user_reviews(
    session: AsyncSession, user_id: uuid.UUID, page: int, page_size: int
) -> UserReviews:
    """Reviews about an active user, as a renter and (for owners) of their listings."""
    user = await session.get(User, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise not_found("user")
    owner = (
        await session.execute(select(OwnerProfile).where(OwnerProfile.user_id == user.id))
    ).scalar_one_or_none()
    about_user = [and_(Review.subject == ReviewSubject.RENTER, Booking.renter_id == user.id)]
    if owner is not None:
        about_user.append(
            and_(Review.subject == ReviewSubject.LISTING, Booking.owner_profile_id == owner.id)
        )
    where = or_(*about_user)
    total = (
        await session.execute(
            select(func.count())
            .select_from(Review)
            .join(Booking, Booking.id == Review.booking_id)
            .where(where)
        )
    ).scalar_one()
    rows = list(
        (
            await session.execute(
                select(Review)
                .join(Booking, Booking.id == Review.booking_id)
                .where(where)
                .order_by(Review.created_at.desc(), Review.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).scalars()
    )
    outs = await review_outs(session, rows)
    return UserReviews(
        items=[
            UserReviewOut(
                **out.model_dump(),
                about="renter" if r.subject == ReviewSubject.RENTER else "owner",
            )
            for r, out in zip(rows, outs, strict=True)
        ],
        page=page,
        page_size=page_size,
        total=total,
        profile=UserProfile(
            id=user.id,
            name=first_name(user.name),
            renter_rating_avg=_float(user.rating_avg),
            renter_rating_count=user.rating_count,
            owner=OwnerRating(
                display_name=owner.display_name,
                rating_avg=_float(owner.rating_avg),
                rating_count=owner.rating_count,
                verified=owner.verification_status == VerificationStatus.VERIFIED,
            )
            if owner is not None
            else None,
        ),
    )


# --- abuse reports (FR-030) ---------------------------------------------------------------


async def create_report(session: AsyncSession, user: User, body: ReportIn) -> AbuseReport:
    kind = ReportTarget(body.target_kind)
    if kind == ReportTarget.LISTING:
        if await session.get(Listing, body.target_id) is None:
            raise not_found("listing")
    else:
        if await session.get(User, body.target_id) is None:
            raise not_found("user")
        if body.target_id == user.id:
            raise AppError("VALIDATION_ERROR", 422, {"target_id": "cannot report yourself"})
    open_report = await session.execute(
        select(AbuseReport.id).where(
            AbuseReport.reporter_id == user.id,
            AbuseReport.target_kind == kind,
            AbuseReport.target_id == body.target_id,
            AbuseReport.status == ReportStatus.OPEN,
        )
    )
    if open_report.first() is not None:
        raise AppError("ALREADY_REPORTED", 409)
    report = AbuseReport(
        reporter_id=user.id, target_kind=kind, target_id=body.target_id, reason=body.reason
    )
    session.add(report)
    await session.flush()
    return report
