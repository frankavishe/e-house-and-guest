import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.listings.schemas import OwnerRating, Page, ReviewOut
from app.reviews.models import REASON_MAX, REVIEW_MAX


class ReviewIn(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5)]
    body: Annotated[str, StringConstraints(strip_whitespace=True, max_length=REVIEW_MAX)] | None = (
        None
    )


class UserReviewOut(ReviewOut):
    """`about`: whether the review rates the user as a renter or as an owner (their listing)."""

    about: Literal["renter", "owner"]


class UserProfile(BaseModel):
    """A public profile: first name, renter rating and, for owners, the owner rating."""

    id: uuid.UUID
    name: str
    renter_rating_avg: float | None
    renter_rating_count: int
    owner: OwnerRating | None


class UserReviews(Page[UserReviewOut]):
    profile: UserProfile


class ReportIn(BaseModel):
    target_kind: Literal["listing", "user"]
    target_id: uuid.UUID
    reason: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX)
    ]


class ReportOut(BaseModel):
    id: uuid.UUID
    target_kind: Literal["listing", "user"]
    target_id: uuid.UUID
    reason: str
    status: Literal["open", "actioned", "dismissed"]
    created_at: datetime
