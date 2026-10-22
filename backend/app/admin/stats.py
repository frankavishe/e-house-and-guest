"""Admin reports (T137, FR-032): bookings, GBV, commission, refunds and payouts by month,
category or region, read from the ledger so they always agree with it (R8).

Each row covers money that moved in `[from, to]` (EAT dates, `to` inclusive):
- `gbv_tzs`: what renters paid for rentals, delivery and service fees (no deposits), i.e.
  the owner-payable and platform-revenue credits of payment transactions;
- `commission_tzs`: net platform revenue (commission and service fees, less what was handed
  back on cancellations or refunded from it);
- `refunds_tzs` / `payouts_tzs`: money sent to renters / owners. Payouts carry no booking,
  so they are attributed to bookings through `payout_items`;
- `bookings`: distinct bookings with a payment in the period.
"""

import csv
import io
from datetime import date, timedelta
from typing import Any

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Text,
    Uuid,
    and_,
    case,
    cast,
    distinct,
    func,
    literal,
    null,
    or_,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.schemas import StatsGroupT, StatsOut, StatsRow
from app.bookings.models import Booking
from app.catalog.models import Category, Location
from app.core.clock import to_eat_midnight
from app.core.i18n import Locale
from app.ledger.models import EntryType, LedgerEntry
from app.ledger.service import PLATFORM_REVENUE, PROVIDER_CASH
from app.listings.models import Listing
from app.listings.service import localized
from app.payouts.models import PayoutItem

NO_REGION = "none"
CSV_COLUMNS = [
    "key",
    "label",
    "bookings",
    "gbv_tzs",
    "commission_tzs",
    "refunds_tzs",
    "payouts_tzs",
]


def _facts(start: Any, end: Any) -> Any:
    """One row per ledger line (or payout item) in range, with its metric contributions."""
    le = LedgerEntry
    in_range = and_(le.created_at >= start, le.created_at < end)
    owner_credit = and_(
        le.amount_tzs < 0,
        le.entry_type == EntryType.PAYMENT,
        le.account.startswith("owner_payable:"),
    )
    gbv = or_(
        owner_credit,
        and_(
            le.amount_tzs < 0, le.entry_type == EntryType.COMMISSION, le.account == PLATFORM_REVENUE
        ),
    )
    zero = literal(0, BigInteger)
    lines = select(
        le.created_at.label("ts"),
        le.booking_id.label("booking_id"),
        case((gbv, -le.amount_tzs), else_=zero).label("gbv"),
        case((le.account == PLATFORM_REVENUE, -le.amount_tzs), else_=zero).label("commission"),
        case(
            (and_(le.account == PROVIDER_CASH, le.entry_type == EntryType.REFUND), -le.amount_tzs),
            else_=zero,
        ).label("refunds"),
        zero.label("payouts"),
        case((owner_credit, le.booking_id), else_=cast(null(), Uuid)).label("paid_booking"),
    ).where(le.booking_id.is_not(None), in_range)
    payouts = (
        select(
            le.created_at,
            PayoutItem.booking_id,
            zero,
            zero,
            zero,
            PayoutItem.amount_tzs,
            cast(null(), Uuid),
        )
        .join(PayoutItem, PayoutItem.payout_id == le.payout_id)
        .where(le.account == PROVIDER_CASH, le.entry_type == EntryType.PAYOUT, in_range)
    )
    return union_all(lines, payouts).subquery("facts")


def _group_key(group_by: StatsGroupT, facts: Any) -> ColumnElement[str]:
    match group_by:
        case "month":
            return func.to_char(func.timezone("Africa/Dar_es_Salaam", facts.c.ts), "YYYY-MM")
        case "category":
            return func.split_part(Category.path, ".", 1)
        case "region":
            return func.coalesce(cast(Listing.region_id, Text), NO_REGION)


async def _aggregate(
    session: AsyncSession, facts: Any, key: ColumnElement[str] | None
) -> list[tuple[str, list[int]]]:
    metrics = [
        func.count(distinct(facts.c.paid_booking)),
        func.coalesce(func.sum(facts.c.gbv), 0),
        func.coalesce(func.sum(facts.c.commission), 0),
        func.coalesce(func.sum(facts.c.refunds), 0),
        func.coalesce(func.sum(facts.c.payouts), 0),
    ]
    query = (
        select(key if key is not None else literal("total"), *metrics)
        .select_from(facts)
        .join(Booking, Booking.id == facts.c.booking_id)
        .join(Listing, Listing.id == Booking.listing_id)
        .join(Category, Category.id == Listing.category_id)
    )
    if key is not None:
        query = query.group_by(key).order_by(key)
    rows = await session.execute(query)
    return [(str(r[0]), [int(v) for v in r[1:]]) for r in rows.all()]


async def _labels(
    session: AsyncSession, group_by: StatsGroupT, keys: list[str], locale: Locale
) -> dict[str, str]:
    if group_by == "category":
        categories = await session.execute(
            select(Category.slug, Category.name).where(
                Category.parent_id.is_(None), Category.slug.in_(keys)
            )
        )
        return {slug: localized(name, locale) for slug, name in categories.all()}
    if group_by == "region":
        ids = [int(k) for k in keys if k != NO_REGION]
        regions = await session.execute(
            select(Location.id, Location.name).where(Location.id.in_(ids))
        )
        return {str(i): name for i, name in regions.all()}
    return {}


def _row(key: str, label: str, values: list[int]) -> StatsRow:
    bookings, gbv, commission, refunds, payouts = values
    return StatsRow(
        key=key,
        label=label,
        bookings=bookings,
        gbv_tzs=gbv,
        commission_tzs=commission,
        refunds_tzs=refunds,
        payouts_tzs=payouts,
    )


async def stats(
    session: AsyncSession, start: date, end: date, group_by: StatsGroupT, locale: Locale
) -> StatsOut:
    facts = _facts(to_eat_midnight(start), to_eat_midnight(end + timedelta(days=1)))
    grouped = await _aggregate(session, facts, _group_key(group_by, facts))
    totals = await _aggregate(session, facts, None)
    labels = await _labels(session, group_by, [k for k, _ in grouped], locale)
    rows = [_row(k, labels.get(k, k if group_by == "month" else "—"), v) for k, v in grouped]
    total = _row("total", "", totals[0][1])
    return StatsOut(**{"from": start}, to=end, group_by=group_by, rows=rows, totals=total)


def to_csv(out: StatsOut) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in [*out.rows, out.totals]:
        writer.writerow([getattr(row, c) for c in CSV_COLUMNS])
    return buf.getvalue()


def csv_filename(out: StatsOut) -> str:
    return f"stats-{out.group_by}-{out.from_.isoformat()}-{out.to.isoformat()}.csv"
