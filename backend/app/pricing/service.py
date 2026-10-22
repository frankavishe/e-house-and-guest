"""Pricing (R5): split a period into units, price each, add delivery, fee and deposit.

Pure functions over loaded rows, so callers (search, quotes, bookings) decide what to load.
All amounts are integer TZS; percentages are basis points rounded half-up.
"""

from collections.abc import Sequence
from datetime import date
from typing import Literal

from app.availability.periods import Period
from app.catalog.models import BookingMode, Category
from app.core.errors import AppError
from app.listings.models import DeliveryOption, Listing, ListingPrice
from app.pricing.schemas import Quote, QuoteLine, UnitT

Label = Literal["base", "season"]
BPS = 10_000


def round_half_up(numerator: int, denominator: int) -> int:
    """`numerator / denominator` rounded half-up, for non-negative integers."""
    return (2 * numerator + denominator) // (2 * denominator)


def price_unavailable(unit: str) -> AppError:
    return AppError("PRICE_UNAVAILABLE", 409, {"unit": unit})


class _Rates:
    def __init__(self, prices: Sequence[ListingPrice]) -> None:
        self.base: dict[str, int] = {}
        self.seasons: dict[str, list[tuple[date, date, int]]] = {}
        for p in prices:
            unit = str(p.unit)
            if p.season_start is None or p.season_end is None:
                self.base[unit] = p.amount_tzs
            else:
                self.seasons.setdefault(unit, []).append(
                    (p.season_start, p.season_end, p.amount_tzs)
                )

    def on(self, unit: str, day: date) -> tuple[int, Label]:
        for first, last, amount in self.seasons.get(unit, []):
            if first <= day <= last:
                return amount, "season"
        if unit not in self.base:
            raise price_unavailable(unit)
        return self.base[unit], "base"


class _Lines:
    """Accumulates line items, merging equal (label, unit, price) entries in order."""

    def __init__(self) -> None:
        self.counts: dict[tuple[Label, UnitT, int], int] = {}

    def add(self, label: Label, unit: UnitT, unit_price: int, count: int = 1) -> None:
        key = (label, unit, unit_price)
        self.counts[key] = self.counts.get(key, 0) + count

    def build(self) -> list[QuoteLine]:
        return [
            QuoteLine(label=label, unit=unit, count=n, unit_price_tzs=p, amount_tzs=n * p)
            for (label, unit, p), n in self.counts.items()
        ]


def _per_day(period: Period, rates: _Rates, lines: _Lines) -> None:
    """Nights, days or item-days; whole weeks use the weekly rate when it is cheaper."""
    unit: UnitT = (
        "item_day" if period.unit == "item_day" else ("night" if period.unit == "night" else "day")
    )
    day_rates = [rates.on(unit, d) for d in period.days]
    week = rates.base.get("week") if unit != "item_day" else None
    i = 0
    while i < len(day_rates):
        chunk = day_rates[i : i + 7]
        if week is not None and len(chunk) == 7 and week < sum(a for a, _ in chunk):
            lines.add("base", "week", week)
            i += 7
            continue
        amount, label = day_rates[i]
        lines.add(label, unit, amount, period.quantity)
        i += 1


def _time_slot(period: Period, rates: _Rates, lines: _Lines) -> None:
    """Hourly, or whole days at the day rate when that is cheaper."""
    hours = -(-period.minutes // 60)
    hour, day = rates.base.get("hour"), rates.base.get("day")
    if hour is None and day is None:
        raise price_unavailable(period.unit)
    options: list[list[tuple[UnitT, int, int]]] = []
    if hour is not None:
        options.append([("hour", hour, hours)])
    if day is not None:
        full, rest = divmod(hours, 24)
        option: list[tuple[UnitT, int, int]] = [("day", day, full)] if full else []
        if rest:
            option.append(
                ("hour", hour, rest) if hour is not None and rest * hour < day else ("day", day, 1)
            )
        options.append(option)
    best = min(options, key=lambda opt: sum(p * n for _, p, n in opt))
    for unit, unit_price, count in best:
        lines.add("base", unit, unit_price, count)


def _delivery_fee(
    listing: Listing, requested: bool, district_id: int | None, require_district: bool
) -> int:
    """A quote may omit the district (fee preview); a booking must name one inside the area."""
    if not requested and listing.delivery != DeliveryOption.REQUIRED:
        return 0
    if listing.delivery == DeliveryOption.NONE:
        raise AppError("DELIVERY_NOT_OFFERED", 422)
    if listing.delivery_area:
        if district_id is None:
            if require_district:
                raise AppError("OUTSIDE_DELIVERY_AREA", 422, {"reason": "district_required"})
        elif district_id not in listing.delivery_area:
            raise AppError("OUTSIDE_DELIVERY_AREA", 422)
    return listing.delivery_fee_tzs or 0


def quote(
    listing: Listing,
    prices: Sequence[ListingPrice],
    category: Category,
    period: Period,
    *,
    delivery: bool = False,
    delivery_district_id: int | None = None,
    require_district: bool = False,
) -> Quote:
    rates = _Rates(prices)
    lines = _Lines()
    match period.mode:
        case BookingMode.TIME_SLOT:
            _time_slot(period, rates, lines)
        case BookingMode.LEASE:
            if "month" not in rates.base:
                raise price_unavailable("month")
            lines.add("base", "month", rates.base["month"], period.count)
        case _:
            _per_day(period, rates, lines)
    built = lines.build()
    rental = sum(line.amount_tzs for line in built)
    delivery_fee = _delivery_fee(listing, delivery, delivery_district_id, require_district)
    service_fee = round_half_up(rental * category.renter_fee_bps, BPS)
    deposit = listing.deposit_tzs or 0
    return Quote(
        lines=built,
        rental_tzs=rental,
        delivery_fee_tzs=delivery_fee,
        service_fee_tzs=service_fee,
        deposit_tzs=deposit,
        total_tzs=rental + delivery_fee + service_fee + deposit,
    )
