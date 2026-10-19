"""Booking periods (R2): renter input per booking mode → a half-open UTC range + units.

`PeriodParams` is the flattened `PeriodInput` of contracts/rest-api.md, shared by search,
quotes and (US2) bookings. Which fields apply depends on the category's booking mode, and
whether a DATE_RANGE counts nights or days comes from its `default_unit` (Principle I).
"""

import calendar
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, BeforeValidator, Field
from sqlalchemy.dialects.postgresql import Range

from app.catalog.models import BookingMode
from app.core import clock
from app.core.errors import AppError

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def _iso(pattern: re.Pattern[str], kind: type, what: str) -> BeforeValidator:
    """Pydantic also reads numbers as Unix timestamps; the API accepts ISO 8601 only."""

    def check(value: object) -> object:
        if (isinstance(value, str) and pattern.match(value)) or isinstance(value, kind):
            return value
        raise ValueError(f"expected an ISO 8601 {what}")

    return BeforeValidator(check)


IsoDate = Annotated[date, _iso(ISO_DATE, date, "date (YYYY-MM-DD)")]
IsoDateTime = Annotated[AwareDatetime, _iso(ISO_DATETIME, datetime, "date-time with offset")]

MAX_MONTHS = 60
MAX_QUANTITY = 10_000
MAX_SPAN_DAYS = 366
DEFAULT_SLOT_MINUTES = 60


class PeriodParams(BaseModel):
    """DATE_RANGE `{start_date, end_date}`, TIME_SLOT `{start, end}`, LEASE `{start_date,
    months}`, QUANTITY `{start_date, end_date, quantity}`. Dates are EAT calendar days."""

    start_date: IsoDate | None = None
    end_date: IsoDate | None = None
    start: IsoDateTime | None = None
    end: IsoDateTime | None = None
    months: Annotated[int, Field(ge=1, le=MAX_MONTHS)] | None = None
    quantity: Annotated[int, Field(ge=1, le=MAX_QUANTITY)] | None = None

    def is_empty(self) -> bool:
        return all(getattr(self, name) is None for name in type(self).model_fields)

    def fits(self, mode: BookingMode) -> bool:
        """Whether the fields needed by `mode` are present (search skips modes that don't)."""
        match mode:
            case BookingMode.DATE_RANGE | BookingMode.QUANTITY:
                return self.start_date is not None and self.end_date is not None
            case BookingMode.LEASE:
                return self.start_date is not None and self.months is not None
            case BookingMode.TIME_SLOT:
                return self.start is not None and self.end is not None


@dataclass(frozen=True)
class Period:
    """A normalised period. `count` is in `unit`; `days` lists the EAT days priced per day
    (nights, days or item-days) and is empty for TIME_SLOT and LEASE."""

    mode: BookingMode
    start: datetime
    end: datetime
    unit: str
    count: int
    quantity: int = 1
    days: tuple[date, ...] = ()

    @property
    def range(self) -> Range[datetime]:
        return Range(self.start, self.end, bounds="[)")

    @property
    def minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


def invalid(reason: str) -> AppError:
    return AppError("INVALID_PERIOD", 400, {"reason": reason})


def add_months(day: date, months: int) -> date:
    """Calendar months; the day is clamped to the target month's length (Jan 31 + 1 → Feb 28)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def _days(first: date, last: date) -> tuple[date, ...]:
    return tuple(first + timedelta(days=i) for i in range((last - first).days + 1))


def _require(value: Any, field: str) -> Any:
    if value is None:
        raise invalid(f"{field}_required")
    return value


def normalize(
    mode: BookingMode,
    default_unit: str,
    params: PeriodParams,
    *,
    slot_minutes: int = DEFAULT_SLOT_MINUTES,
) -> Period:
    """Validate `params` for `mode` and build the period. Raises INVALID_PERIOD (400)."""
    today = clock.today_eat()
    if mode == BookingMode.TIME_SLOT:
        start = _require(params.start, "start").astimezone(UTC)
        end = _require(params.end, "end").astimezone(UTC)
        if end <= start:
            raise invalid("end_before_start")
        if start < clock.now():
            raise invalid("in_past")
        minutes = int((end - start).total_seconds() // 60)
        if (end - start).total_seconds() % 60 or minutes % slot_minutes:
            raise invalid("not_whole_slots")
        if minutes > MAX_SPAN_DAYS * 24 * 60:
            raise invalid("too_long")
        if default_unit == "hour":
            return Period(mode, start, end, "hour", -(-minutes // 60))
        return Period(mode, start, end, "day", -(-minutes // (24 * 60)))

    first: date = _require(params.start_date, "start_date")
    if first < today:
        raise invalid("in_past")

    if mode == BookingMode.LEASE:
        months: int = _require(params.months, "months")
        if not 1 <= months <= MAX_MONTHS:
            raise invalid("months")
        end_day = add_months(first, months)
        return Period(
            mode, clock.to_eat_midnight(first), clock.to_eat_midnight(end_day), "month", months
        )

    last: date = _require(params.end_date, "end_date")
    if mode == BookingMode.DATE_RANGE and default_unit == "night":
        # Check-in → check-out: the check-out day is free (R2).
        if last <= first:
            raise invalid("end_before_start")
        days = _days(first, last - timedelta(days=1))
    else:
        if last < first:
            raise invalid("end_before_start")
        days = _days(first, last)
    if len(days) > MAX_SPAN_DAYS:
        raise invalid("too_long")
    start, end = clock.to_eat_midnight(days[0]), clock.to_eat_midnight(days[-1] + timedelta(days=1))

    if mode == BookingMode.QUANTITY:
        quantity = params.quantity if params.quantity is not None else 1
        if not 1 <= quantity <= MAX_QUANTITY:
            raise invalid("quantity")
        return Period(mode, start, end, "item_day", len(days), quantity, days)
    unit = "night" if default_unit == "night" else "day"
    return Period(mode, start, end, unit, len(days), 1, days)


def check_duration(period: Period, listing: Any) -> None:
    """The listing's min/max duration, counted in the period's unit (R2)."""
    if (listing.min_duration is not None and period.count < listing.min_duration) or (
        listing.max_duration is not None and period.count > listing.max_duration
    ):
        raise AppError(
            "DURATION_OUT_OF_RANGE",
            400,
            {"min": listing.min_duration, "max": listing.max_duration, "unit": period.unit},
        )
