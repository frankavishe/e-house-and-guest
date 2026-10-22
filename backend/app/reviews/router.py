"""Review and abuse report endpoints (contracts/rest-api.md "Messaging & reviews")."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, Session
from app.listings.schemas import Page, ReviewOut
from app.reviews import service
from app.reviews.schemas import ReportIn, ReportOut, ReviewIn, UserReviews

router = APIRouter(tags=["reviews"])

PageParam = Annotated[int, Query(ge=1, le=10_000)]
PageSizeParam = Annotated[int, Query(ge=1, le=50)]


@router.post(
    "/bookings/{booking_id}/reviews",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        403: {"description": "`REVIEW_NOT_ALLOWED`: the booking is not completed"},
        404: {"description": "Unknown booking"},
        409: {"description": "`ALREADY_REVIEWED`"},
    },
)
async def create_review(
    booking_id: uuid.UUID, body: ReviewIn, user: CurrentUser, session: Session
) -> ReviewOut:
    """The renter rates the listing, the owner rates the renter; once each per booking."""
    review = await service.create_review(session, user, booking_id, body)
    (out,) = await service.review_outs(session, [review])
    await session.commit()
    return out


@router.get(
    "/listings/{listing_id}/reviews",
    response_model=Page[ReviewOut],
    responses={404: {"description": "Unknown or non-public listing"}},
)
async def listing_reviews(
    listing_id: uuid.UUID, session: Session, page: PageParam = 1, page_size: PageSizeParam = 10
) -> Page[ReviewOut]:
    items, total = await service.listing_reviews(session, listing_id, page, page_size)
    return Page(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/users/{user_id}/reviews",
    response_model=UserReviews,
    responses={404: {"description": "Unknown or suspended user"}},
)
async def user_reviews(
    user_id: uuid.UUID, session: Session, page: PageParam = 1, page_size: PageSizeParam = 10
) -> UserReviews:
    """A user's public profile and the reviews about them."""
    return await service.user_reviews(session, user_id, page, page_size)


@router.post(
    "/reports",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Unknown listing or user"},
        409: {"description": "`ALREADY_REPORTED`"},
    },
)
async def create_report(body: ReportIn, user: CurrentUser, session: Session) -> ReportOut:
    """Report a listing or user to the admins (FR-030)."""
    report = await service.create_report(session, user, body)
    out = ReportOut(
        id=report.id,
        target_kind=report.target_kind.value,
        target_id=report.target_id,
        reason=report.reason,
        status=report.status.value,
        created_at=report.created_at,
    )
    await session.commit()
    return out
