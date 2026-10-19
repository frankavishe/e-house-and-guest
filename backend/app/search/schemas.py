"""`GET /listings/search` query parameters (contracts/rest-api.md). `attr.*` filters are read
from the raw query string because their keys come from category schemas (R3)."""

from typing import Annotated, Literal

from pydantic import Field, field_validator

from app.availability.periods import PeriodParams

INT32 = 2_147_483_647
MAX_PRICE = 10**12
NUMBER = r"-?\d{1,3}(\.\d{1,8})?"
BBOX_PATTERN = rf"^{NUMBER},{NUMBER},{NUMBER},{NUMBER}$"

SortT = Literal["newest", "price_asc", "price_desc", "rating"]


class SearchParams(PeriodParams):
    category: Annotated[str, Field(max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")] | None = None
    region: Annotated[int, Field(ge=1, le=INT32)] | None = None
    district: Annotated[int, Field(ge=1, le=INT32)] | None = None
    ward: Annotated[int, Field(ge=1, le=INT32)] | None = None
    q: Annotated[str, Field(max_length=100)] | None = None
    price_min: Annotated[int, Field(ge=0, le=MAX_PRICE)] | None = None
    price_max: Annotated[int, Field(ge=0, le=MAX_PRICE)] | None = None
    bbox: (
        Annotated[str, Field(pattern=BBOX_PATTERN, description="minLng,minLat,maxLng,maxLat")]
        | None
    ) = None
    sort: SortT = "newest"
    page: Annotated[int, Field(ge=1, le=10_000)] = 1
    page_size: Annotated[int, Field(ge=1, le=50)] = 20

    @field_validator("q")
    @classmethod
    def drop_nul(cls, value: str | None) -> str | None:
        """PostgreSQL text cannot hold NUL characters."""
        return value.replace(chr(0), "") if value is not None else None

    def period(self) -> PeriodParams:
        return PeriodParams(
            start_date=self.start_date,
            end_date=self.end_date,
            start=self.start,
            end=self.end,
            months=self.months,
            quantity=self.quantity,
        )
