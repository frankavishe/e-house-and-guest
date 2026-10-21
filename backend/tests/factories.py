"""Test data helpers. Each returns persisted (flushed) rows inside the test transaction."""

import itertools
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.accounts.models import (
    Language,
    OwnerKind,
    OwnerProfile,
    User,
    UserStatus,
    VerificationStatus,
)
from app.availability.models import AvailabilityBlock, BlockKind, BlockSource
from app.catalog.models import BookingMode, Category, Location, LocationLevel, PriceUnit
from app.core import security
from app.listings.models import (
    CancellationPolicy,
    DeliveryOption,
    Listing,
    ListingPhoto,
    ListingPrice,
    ListingStatus,
)

_phones = itertools.count(1)
_location_ids = itertools.count(980_001)
_slugs = itertools.count(1)


def next_phone() -> str:
    return f"+25571{next(_phones):07d}"


async def make_user(
    db: AsyncSession,
    *,
    phone: str | None = None,
    name: str | None = "Test User",
    is_admin: bool = False,
    status: str = "active",
    language: str = "sw",
) -> User:
    user = User(
        phone=phone or next_phone(),
        name=name,
        is_admin=is_admin,
        status=UserStatus(status),
        language=Language(language),
    )
    db.add(user)
    await db.flush()
    return user


def sign_in(client: httpx.AsyncClient, user: User) -> None:
    """Attach an access-token cookie for `user` to the client (skips the OTP flow)."""
    client.cookies.set(
        security.ACCESS_COOKIE, security.encode_access_token(user.id, is_admin=user.is_admin)
    )


async def make_owner(
    db: AsyncSession,
    *,
    user: User | None = None,
    verification: str = "verified",
    display_name: str = "Test Owner",
) -> OwnerProfile:
    user = user or await make_user(db)
    profile = OwnerProfile(
        user_id=user.id,
        kind=OwnerKind.INDIVIDUAL,
        display_name=display_name,
        verification_status=VerificationStatus(verification),
    )
    db.add(profile)
    await db.flush()
    return profile


async def make_location(
    db: AsyncSession, *, level: str = "region", parent: Location | None = None, name: str = ""
) -> Location:
    loc_id = next(_location_ids)
    loc = Location(
        id=loc_id,
        parent_id=parent.id if parent else None,
        level=LocationLevel(level),
        name=name or f"Loc {loc_id}",
        slug=f"loc-{loc_id}",
    )
    db.add(loc)
    await db.flush()
    return loc


async def make_place(db: AsyncSession, name: str = "") -> tuple[Location, Location]:
    """A region and one district in it."""
    region = await make_location(db, name=name)
    district = await make_location(db, level="district", parent=region, name=f"{name} district")
    return region, district


async def make_category(
    db: AsyncSession,
    *,
    mode: str | None = "DATE_RANGE",
    parent: Category | None = None,
    slug: str | None = None,
    price_units: list[str] | None = None,
    default_unit: str | None = "night",
    attribute_schema: list[dict[str, Any]] | None = None,
    renter_fee_bps: int = 0,
    commission_bps: int = 1000,
) -> Category:
    slug = slug or f"t-cat-{next(_slugs)}"
    category = Category(
        parent_id=parent.id if parent else None,
        path=f"{parent.path}.{slug}" if parent else slug,
        slug=slug,
        name={"sw": f"{slug} sw", "en": f"{slug} en"},
        booking_mode=BookingMode(mode) if mode else None,
        price_units=price_units if price_units is not None else ([default_unit] if mode else []),
        default_unit=default_unit if mode else None,
        attribute_schema=attribute_schema or [],
        renter_fee_bps=renter_fee_bps,
        commission_bps=commission_bps,
    )
    db.add(category)
    await db.flush()
    return category


async def make_listing(
    db: AsyncSession,
    *,
    owner: OwnerProfile,
    category: Category,
    region: Location,
    district: Location,
    price: int = 50_000,
    prices: list[dict[str, Any]] | None = None,
    status: str = "active",
    title_sw: str = "Tangazo",
    title_en: str = "Listing",
    attributes: dict[str, Any] | None = None,
    stock: int = 1,
    lat: float | None = None,
    lng: float | None = None,
    **fields: Any,
) -> Listing:
    """A listing with a base price in the category's default unit (plus `prices` rows)."""
    listing = Listing(
        owner_profile_id=owner.id,
        category_id=category.id,
        title_sw=title_sw,
        title_en=title_en,
        description_sw=f"{title_sw} maelezo",
        description_en=f"{title_en} description",
        attributes=attributes or {},
        region_id=region.id,
        district_id=district.id,
        stock=stock,
        lat=Decimal(str(lat)) if lat is not None else None,
        lng=Decimal(str(lng)) if lng is not None else None,
        base_price_tzs=price,
        status=ListingStatus(status),
        deposit_tzs=fields.pop("deposit_tzs", 0),
        delivery=DeliveryOption(fields.pop("delivery", "none")),
        cancellation_policy=CancellationPolicy(fields.pop("cancellation_policy", "moderate")),
        instant_book=fields.pop("instant_book", True),
        **fields,
    )
    db.add(listing)
    await db.flush()
    assert category.default_unit is not None
    rows = [{"unit": category.default_unit, "amount_tzs": price}, *(prices or [])]
    for row in rows:
        db.add(
            ListingPrice(
                listing_id=listing.id,
                unit=PriceUnit(row["unit"]),
                amount_tzs=row["amount_tzs"],
                season_start=row.get("season_start"),
                season_end=row.get("season_end"),
            )
        )
    db.add(
        ListingPhoto(
            listing_id=listing.id,
            storage_key=f"test/{listing.id}.jpg",
            position=0,
            confirmed_at=datetime.now(UTC),
        )
    )
    await db.flush()
    return listing


async def make_block(
    db: AsyncSession,
    listing: Listing,
    start: datetime,
    end: datetime,
    *,
    kind: str = "exclusive",
    quantity: int = 1,
    active: bool = True,
    source: str = "owner_block",
    booking_id: uuid.UUID | None = None,
) -> AvailabilityBlock:
    block = AvailabilityBlock(
        listing_id=listing.id,
        period=Range(start, end, bounds="[)"),
        quantity=quantity,
        kind=BlockKind(kind),
        source=BlockSource(source),
        booking_id=booking_id,
        active=active,
    )
    db.add(block)
    await db.flush()
    return block


def day_range(start: date, end: date) -> tuple[datetime, datetime]:
    """EAT midnights for [start, end)."""
    from app.core.clock import to_eat_midnight

    return to_eat_midnight(start), to_eat_midnight(end)


# --- bookings (US2) -----------------------------------------------------------------------

DEFAULT_UNITS = {
    "DATE_RANGE": "night",
    "TIME_SLOT": "hour",
    "LEASE": "month",
    "QUANTITY": "item_day",
}


class Bookable:
    """A public listing in a fresh category, its owner, and a separate renter."""

    listing: Listing
    category: Category
    owner: OwnerProfile
    owner_user: User
    renter: User


async def make_bookable(
    db: AsyncSession,
    mode: str = "DATE_RANGE",
    *,
    unit: str | None = None,
    price: int = 50_000,
    commission_bps: int = 1000,
    renter_fee_bps: int = 0,
    **listing_fields: Any,
) -> Bookable:
    b = Bookable()
    b.category = await make_category(
        db,
        mode=mode,
        default_unit=unit or DEFAULT_UNITS[mode],
        commission_bps=commission_bps,
        renter_fee_bps=renter_fee_bps,
    )
    region, district = await make_place(db)
    b.owner_user = await make_user(db, name="Owner Person")
    b.owner = await make_owner(db, user=b.owner_user)
    b.listing = await make_listing(
        db,
        owner=b.owner,
        category=b.category,
        region=region,
        district=district,
        price=price,
        **listing_fields,
    )
    b.renter = await make_user(db, name="Renter Person")
    return b


def period_json(mode: str, start: date, *, days: int = 3, quantity: int = 1) -> dict[str, Any]:
    """A `PeriodInput` for `mode` starting on `start` (TIME_SLOT: 10:00-12:00 EAT)."""
    from datetime import time, timedelta

    from app.core.clock import EAT

    match mode:
        case "TIME_SLOT":
            begin = datetime.combine(start, time(10), tzinfo=EAT)
            return {"start": begin.isoformat(), "end": (begin + timedelta(hours=2)).isoformat()}
        case "LEASE":
            return {"start_date": start.isoformat(), "months": days}
        case "QUANTITY":
            end = start + timedelta(days=days - 1)
            return {
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "quantity": quantity,
            }
        case _:
            end = start + timedelta(days=days)
            return {"start_date": start.isoformat(), "end_date": end.isoformat()}


async def book(
    client: httpx.AsyncClient,
    b: Bookable,
    start: date,
    *,
    days: int = 3,
    quantity: int = 1,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> httpx.Response:
    """POST /bookings as the renter."""
    sign_in(client, b.renter)
    assert b.category.booking_mode is not None
    body = {
        "listing_id": str(b.listing.id),
        "period": period_json(b.category.booking_mode.value, start, days=days, quantity=quantity),
        **extra,
    }
    return await client.post("/api/v1/bookings", json=body, headers=headers)


def webhook_url(provider: str = "mock") -> str:
    from app.core.config import get_settings

    return f"/api/v1/webhooks/payments/{provider}/{get_settings().payment_callback_secret}"


async def pay(
    client: httpx.AsyncClient,
    b: Bookable,
    booking_id: str,
    *,
    msisdn: str = "+255700000001",
    network: str = "mpesa",
    **extra: Any,
) -> httpx.Response:
    """POST /bookings/{id}/payments as the renter."""
    sign_in(client, b.renter)
    return await client.post(
        f"/api/v1/bookings/{booking_id}/payments",
        json={"network": network, "msisdn": msisdn, **extra},
    )


async def deliver_callbacks(client: httpx.AsyncClient) -> list[httpx.Response]:
    """Send every callback the mock provider has queued to the webhook, in order."""
    from app.integrations import get_payment_provider
    from app.integrations.payments.mock import MockPaymentProvider

    provider = get_payment_provider()
    assert isinstance(provider, MockPaymentProvider)
    return [
        await client.post(webhook_url(), content=cb.body, headers=cb.headers)
        for cb in provider.take_callbacks()
    ]


async def make_booking(
    db: AsyncSession,
    b: Bookable,
    start: datetime,
    end: datetime,
    *,
    status: str = "awaiting_payment",
    quantity: int = 1,
    total: int = 100_000,
    deposit: int = 0,
    delivery: int = 0,
    service_fee: int = 0,
    policy: str = "moderate",
) -> Any:
    """A booking row with its active block, bypassing the booking service. `total` is the
    rental; deposit, delivery and service fee are added to the booking total."""
    from app.bookings.models import Booking, BookingStatus

    assert b.category.booking_mode is not None
    booking = Booking(
        code=f"T-{uuid.uuid4().hex[:8].upper()}",
        listing_id=b.listing.id,
        renter_id=b.renter.id,
        owner_profile_id=b.owner.id,
        booking_mode=b.category.booking_mode,
        period=Range(start, end, bounds="[)"),
        quantity=quantity,
        status=BookingStatus(status),
        quote={
            "lines": [],
            "rental_tzs": total,
            "delivery_fee_tzs": delivery,
            "service_fee_tzs": service_fee,
            "deposit_tzs": deposit,
            "total_tzs": total + deposit + delivery + service_fee,
        },
        rental_tzs=total,
        delivery_fee_tzs=delivery,
        service_fee_tzs=service_fee,
        deposit_tzs=deposit,
        total_tzs=total + deposit + delivery + service_fee,
        commission_bps=1000,
        commission_tzs=total // 10,
        cancellation_policy=CancellationPolicy(policy),
        lease_months=1 if b.category.booking_mode == BookingMode.LEASE else None,
    )
    db.add(booking)
    await db.flush()
    kind = "stock" if b.category.booking_mode == BookingMode.QUANTITY else "exclusive"
    await make_block(
        db,
        b.listing,
        start,
        end,
        kind=kind,
        quantity=quantity,
        source="booking",
        booking_id=booking.id,
    )
    return booking


# --- owners & moderation (US3) ------------------------------------------------------------

WAREHOUSE_SCHEMA: list[dict[str, Any]] = [
    {
        "key": "floor_area",
        "type": "decimal",
        "label": {"sw": "Eneo la sakafu", "en": "Floor area"},
        "required": True,
        "min": 1,
        "max": 100_000,
        "filter": "range",
        "order": 1,
    },
    {
        "key": "loading_bay",
        "type": "boolean",
        "label": {"sw": "Sehemu ya kupakia", "en": "Loading bay"},
        "required": False,
        "filter": "exact",
        "order": 2,
    },
]


async def make_admin(db: AsyncSession) -> User:
    return await make_user(db, name="Admin Person", is_admin=True)


# --- earnings & payouts (US4) -------------------------------------------------------------


async def make_payout_method(
    db: AsyncSession,
    owner: OwnerProfile,
    *,
    msisdn: str = "+255700000001",
    network: str = "mpesa",
    is_default: bool = True,
) -> Any:
    """A default mobile money payout method (the mock payout outcome follows `msisdn`)."""
    from app.accounts.models import PaymentNetwork, PayoutKind, PayoutMethod

    method = PayoutMethod(
        owner_profile_id=owner.id,
        kind=PayoutKind.MOBILE_MONEY,
        network=PaymentNetwork(network),
        msisdn=msisdn,
        account_name=owner.display_name,
        is_default=is_default,
    )
    db.add(method)
    await db.flush()
    return method


async def make_completed_booking(
    db: AsyncSession,
    b: Bookable,
    start: datetime,
    end: datetime,
    *,
    completed_at: datetime,
    total: int = 200_000,
) -> Any:
    """A completed booking whose payment is in the ledger (rental `total`, 10% commission)."""
    from app.ledger import service as ledger

    booking = await make_booking(db, b, start, end, status="completed", total=total)
    booking.completed_at = completed_at
    await ledger.post_booking_payment(db, booking, payment_id=None)
    await db.flush()
    return booking


async def make_paid_booking(
    db: AsyncSession,
    b: Bookable,
    start: datetime,
    end: datetime,
    *,
    status: str = "confirmed",
    completed_at: datetime | None = None,
    msisdn: str = "+255700000001",
    **fields: Any,
) -> Any:
    """A booking paid in full by mobile money: a succeeded payment and its ledger rows."""
    from app.accounts.models import PaymentNetwork
    from app.core import clock
    from app.ledger import service as ledger
    from app.payments.models import Payment, PaymentStatus

    booking = await make_booking(db, b, start, end, status=status, **fields)
    booking.completed_at = completed_at
    payment = Payment(
        booking_id=booking.id,
        provider="mock",
        network=PaymentNetwork.MPESA,
        msisdn=msisdn,
        amount_tzs=booking.total_tzs,
        status=PaymentStatus.SUCCEEDED,
        provider_txn_id=f"MOCKS-{uuid.uuid4().hex[:12].upper()}",
        confirmed_at=clock.now(),
    )
    db.add(payment)
    await db.flush()
    await ledger.post_booking_payment(db, booking, payment.id)
    await db.flush()
    return booking


def jpeg_with_exif(size: tuple[int, int] = (1600, 1200)) -> bytes:
    """A JPEG carrying EXIF GPS data, to check the image job strips it."""
    import io

    from PIL import Image

    image = Image.new("RGB", size, (200, 120, 40))
    exif = Image.Exif()
    exif[0x010F] = "TestCam"  # Make
    exif[0x8825] = {1: "S", 2: (6.0, 48.0, 0.0), 3: "E", 4: (39.0, 17.0, 0.0)}  # GPS IFD
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    return out.getvalue()
