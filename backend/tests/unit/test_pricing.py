"""Pricing and period normalisation (T050, R2, R5). Pure functions: no database."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest

from app.availability.periods import PeriodParams, check_duration, normalize
from app.catalog.models import BookingMode, Category, PriceUnit
from app.core.clock import EAT, to_eat_midnight
from app.core.errors import AppError
from app.listings.models import DeliveryOption, Listing, ListingPrice
from app.pricing.schemas import Quote
from app.pricing.service import quote, round_half_up

pytestmark = pytest.mark.usefixtures("frozen_clock")  # today = 2026-11-02 EAT


def category(mode: str, default_unit: str, renter_fee_bps: int = 0) -> Category:
    return Category(
        id=uuid.uuid4(),
        slug="c",
        path="c",
        name={"sw": "c", "en": "c"},
        booking_mode=BookingMode(mode),
        price_units=[default_unit],
        default_unit=default_unit,
        renter_fee_bps=renter_fee_bps,
    )


def listing(**fields: Any) -> Listing:
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "deposit_tzs": 0,
        "delivery": DeliveryOption.NONE,
        "delivery_fee_tzs": None,
        "delivery_area": None,
        "district_id": 1,
        "stock": 1,
        "slot_config": None,
        "min_duration": None,
        "max_duration": None,
    }
    values.update(fields)
    return Listing(**values)


def price(
    unit: str, amount: int, start: date | None = None, end: date | None = None
) -> ListingPrice:
    return ListingPrice(unit=PriceUnit(unit), amount_tzs=amount, season_start=start, season_end=end)


def priced(
    cat: Category,
    prices: list[ListingPrice],
    lst: Listing | None = None,
    delivery: bool = False,
    delivery_district_id: int | None = None,
    require_district: bool = False,
    **period: Any,
) -> Quote:
    assert cat.booking_mode is not None and cat.default_unit is not None
    p = normalize(cat.booking_mode, cat.default_unit, PeriodParams(**period))
    return quote(
        lst or listing(),
        prices,
        cat,
        p,
        delivery=delivery,
        delivery_district_id=delivery_district_id,
        require_district=require_district,
    )


# --- periods (R2) --------------------------------------------------------------------------


def test_nights_period_is_half_open_in_eat() -> None:
    p = normalize(
        BookingMode.DATE_RANGE,
        "night",
        PeriodParams(start_date=date(2026, 11, 10), end_date=date(2026, 11, 13)),
    )
    assert p.start == to_eat_midnight(date(2026, 11, 10))
    assert p.end == to_eat_midnight(date(2026, 11, 13))  # check-out day stays free
    assert p.count == 3 and p.unit == "night"
    assert p.start.utcoffset() == UTC.utcoffset(None)


def test_days_period_includes_last_day() -> None:
    p = normalize(
        BookingMode.DATE_RANGE,
        "day",
        PeriodParams(start_date=date(2026, 11, 10), end_date=date(2026, 11, 12)),
    )
    assert p.end == to_eat_midnight(date(2026, 11, 13))
    assert p.count == 3


def test_lease_period_adds_calendar_months() -> None:
    p = normalize(BookingMode.LEASE, "month", PeriodParams(start_date=date(2027, 1, 31), months=1))
    assert p.end == to_eat_midnight(date(2027, 2, 28)) and p.count == 1


def test_time_slot_may_cross_midnight() -> None:
    start = datetime(2026, 11, 10, 20, 0, tzinfo=EAT)
    p = normalize(
        BookingMode.TIME_SLOT,
        "hour",
        PeriodParams(start=start, end=datetime(2026, 11, 11, 2, 0, tzinfo=EAT)),
    )
    assert p.count == 6 and p.start == start.astimezone(UTC)


D10, D11 = date(2026, 11, 10), date(2026, 11, 11)
NINE = datetime(2026, 11, 10, 9, tzinfo=EAT)


@pytest.mark.parametrize(
    ("mode", "unit", "params"),
    [
        (BookingMode.DATE_RANGE, "night", {"start_date": D10, "end_date": D10}),
        (BookingMode.DATE_RANGE, "day", {"start_date": D10, "end_date": date(2026, 11, 9)}),
        (BookingMode.DATE_RANGE, "night", {"start_date": date(2026, 11, 1), "end_date": D10}),
        (BookingMode.DATE_RANGE, "night", {"start_date": D10}),
        (BookingMode.LEASE, "month", {"start_date": D10}),
        (BookingMode.QUANTITY, "item_day", {"start_date": D10, "end_date": D11, "quantity": 0}),
        (BookingMode.TIME_SLOT, "hour", {"start": NINE, "end": NINE}),
        (BookingMode.TIME_SLOT, "hour", {"start": NINE, "end": NINE.replace(minute=20)}),
        (BookingMode.TIME_SLOT, "hour", {"start_date": D10, "end_date": D11}),
    ],
)
def test_invalid_periods(mode: BookingMode, unit: str, params: dict[str, Any]) -> None:
    with pytest.raises(AppError) as err:
        normalize(mode, unit, PeriodParams.model_construct(**params))
    assert err.value.code == "INVALID_PERIOD" and err.value.status == 400


def test_duration_limits() -> None:
    p = normalize(BookingMode.DATE_RANGE, "night", PeriodParams(start_date=D10, end_date=D11))
    with pytest.raises(AppError) as err:
        check_duration(p, listing(min_duration=2))
    assert err.value.code == "DURATION_OUT_OF_RANGE"
    with pytest.raises(AppError):
        check_duration(p, listing(max_duration=0))
    check_duration(p, listing(min_duration=1, max_duration=1))


# --- pricing (R5) --------------------------------------------------------------------------


def test_nights_are_counted() -> None:
    q = priced(
        category("DATE_RANGE", "night"),
        [price("night", 45_000)],
        start_date=D10,
        end_date=date(2026, 11, 13),
    )
    assert q.rental_tzs == 135_000
    assert [(ln.unit, ln.count, ln.unit_price_tzs) for ln in q.lines] == [("night", 3, 45_000)]
    assert q.total_tzs == 135_000


def test_days_count_both_ends() -> None:
    q = priced(
        category("DATE_RANGE", "day"),
        [price("day", 80_000)],
        start_date=D10,
        end_date=date(2026, 11, 12),
    )
    assert q.rental_tzs == 240_000


def test_hourly_slot() -> None:
    q = priced(
        category("TIME_SLOT", "hour"),
        [price("hour", 10_000)],
        start=NINE,
        end=NINE.replace(hour=12),
    )
    assert q.rental_tzs == 30_000 and q.lines[0].unit == "hour" and q.lines[0].count == 3


def test_day_rate_used_for_long_slot_when_cheaper() -> None:
    q = priced(
        category("TIME_SLOT", "day"),
        [price("day", 300_000), price("hour", 50_000)],
        start=NINE.replace(hour=8),
        end=NINE.replace(hour=18),
    )
    assert q.rental_tzs == 300_000
    short = priced(
        category("TIME_SLOT", "day"),
        [price("day", 300_000), price("hour", 50_000)],
        start=NINE,
        end=NINE.replace(hour=11),
    )
    assert short.rental_tzs == 100_000


def test_item_times_days() -> None:
    q = priced(
        category("QUANTITY", "item_day"),
        [price("item_day", 15_000)],
        start_date=D10,
        end_date=D11,
        quantity=4,
    )
    assert q.rental_tzs == 2 * 4 * 15_000
    assert q.lines[0].count == 8


def test_whole_week_rate_when_cheaper() -> None:
    cat = category("DATE_RANGE", "night")
    nine_nights = {"start_date": D10, "end_date": date(2026, 11, 19)}
    cheap = priced(cat, [price("night", 45_000), price("week", 280_000)], **nine_nights)
    assert cheap.rental_tzs == 280_000 + 2 * 45_000
    assert {ln.unit for ln in cheap.lines} == {"week", "night"}
    dear = priced(cat, [price("night", 45_000), price("week", 400_000)], **nine_nights)
    assert dear.rental_tzs == 9 * 45_000


def test_seasonal_rate_per_night_across_boundary() -> None:
    q = priced(
        category("DATE_RANGE", "night"),
        [price("night", 45_000), price("night", 60_000, date(2026, 12, 20), date(2026, 12, 31))],
        start_date=date(2026, 12, 18),
        end_date=date(2026, 12, 22),
    )
    assert q.rental_tzs == 2 * 45_000 + 2 * 60_000
    assert sorted((ln.label, ln.count, ln.unit_price_tzs) for ln in q.lines) == [
        ("base", 2, 45_000),
        ("season", 2, 60_000),
    ]


def test_lease_months_and_deposit() -> None:
    q = priced(
        category("LEASE", "month"),
        [price("month", 300_000)],
        lst=listing(deposit_tzs=300_000),
        start_date=date(2026, 12, 1),
        months=3,
    )
    assert q.rental_tzs == 900_000 and q.deposit_tzs == 300_000
    assert q.total_tzs == 1_200_000


def test_delivery_fee() -> None:
    cat = category("QUANTITY", "item_day")
    rates = [price("item_day", 1_000)]
    period = {"start_date": D10, "end_date": D10, "quantity": 1}
    optional = listing(delivery=DeliveryOption.OPTIONAL, delivery_fee_tzs=20_000, delivery_area=[7])
    assert priced(cat, rates, optional, **period).delivery_fee_tzs == 0
    q = priced(cat, rates, optional, delivery=True, delivery_district_id=7, **period)
    assert q.delivery_fee_tzs == 20_000 and q.total_tzs == 21_000
    with pytest.raises(AppError) as err:
        priced(cat, rates, optional, delivery=True, delivery_district_id=8, **period)
    assert err.value.code == "OUTSIDE_DELIVERY_AREA"
    # A quote may preview the fee without a district; a booking must name one in the area.
    assert priced(cat, rates, optional, delivery=True, **period).delivery_fee_tzs == 20_000
    with pytest.raises(AppError) as err:
        priced(cat, rates, optional, delivery=True, require_district=True, **period)
    assert err.value.code == "OUTSIDE_DELIVERY_AREA"
    assert err.value.details == {"reason": "district_required"}
    anywhere = listing(delivery=DeliveryOption.OPTIONAL, delivery_fee_tzs=20_000)
    q = priced(cat, rates, anywhere, delivery=True, require_district=True, **period)
    assert q.delivery_fee_tzs == 20_000

    required = listing(delivery=DeliveryOption.REQUIRED, delivery_fee_tzs=5_000)
    assert priced(cat, rates, required, **period).delivery_fee_tzs == 5_000
    with pytest.raises(AppError) as err:
        priced(cat, rates, listing(), delivery=True, **period)
    assert err.value.code == "DELIVERY_NOT_OFFERED"


def test_service_fee_rounds_half_up() -> None:
    assert round_half_up(30_010 * 500, 10_000) == 1_501  # 1500.5
    assert round_half_up(30_009 * 500, 10_000) == 1_500  # 1500.45
    q = priced(
        category("DATE_RANGE", "day", renter_fee_bps=500),
        [price("day", 30_010)],
        start_date=D10,
        end_date=D10,
    )
    assert q.service_fee_tzs == 1_501 and q.total_tzs == 31_511


def test_amounts_are_integers() -> None:
    q = priced(
        category("DATE_RANGE", "night", renter_fee_bps=333),
        [price("night", 33_333)],
        lst=listing(deposit_tzs=10_000),
        start_date=D10,
        end_date=date(2026, 11, 12),
    )
    amounts = [q.rental_tzs, q.delivery_fee_tzs, q.service_fee_tzs, q.deposit_tzs, q.total_tzs]
    assert all(type(a) is int for a in amounts)
    assert all(type(ln.amount_tzs) is int for ln in q.lines)
    assert q.total_tzs == q.rental_tzs + q.delivery_fee_tzs + q.service_fee_tzs + q.deposit_tzs


def test_missing_base_price() -> None:
    with pytest.raises(AppError) as err:
        priced(
            category("DATE_RANGE", "night"),
            [price("week", 1_000)],
            start_date=D10,
            end_date=D11,
        )
    assert err.value.code == "PRICE_UNAVAILABLE"
