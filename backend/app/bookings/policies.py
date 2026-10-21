"""Cancellation policies (FR-026, T120): how much of a paid booking goes back to the renter.

Tiers count back from the booking start; an instant exactly on a tier's edge is still inside
it. The policy percentage applies to the rental only:

- flexible: 100% until 24 h before the start, then 0%
- moderate: 100% until 5 days before, then 50%
- strict: 50% until 7 days before, then 0%

The deposit is always returned, and so is the delivery fee (nothing was delivered yet). The
renter's service fee is returned only on a full refund. Owner and admin cancellations refund
everything that was paid. The commission is returned in proportion to the rental refund, so
the owner keeps the net of what the renter forfeits.

This module is pure: callers pass the clock and what was actually charged.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.bookings.models import CancelledBy
from app.listings.models import CancellationPolicy
from app.pricing.service import round_half_up

P = CancellationPolicy


@dataclass(frozen=True)
class Tier:
    """`percent` applies while `now <= start - before`."""

    before: timedelta
    percent: int


TIERS: dict[CancellationPolicy, tuple[Tier, ...]] = {
    P.FLEXIBLE: (Tier(timedelta(hours=24), 100),),
    P.MODERATE: (Tier(timedelta(days=5), 100),),
    P.STRICT: (Tier(timedelta(days=7), 50),),
}
# The percentage once every tier has passed.
LATE_PERCENT: dict[CancellationPolicy, int] = {P.FLEXIBLE: 0, P.MODERATE: 50, P.STRICT: 0}


@dataclass(frozen=True)
class Charged:
    """What the renter paid for the booking (for a lease: month 1, deposit and delivery)."""

    rental_tzs: int = 0
    delivery_fee_tzs: int = 0
    service_fee_tzs: int = 0
    deposit_tzs: int = 0
    commission_tzs: int = 0

    @property
    def total_tzs(self) -> int:
        return self.rental_tzs + self.delivery_fee_tzs + self.service_fee_tzs + self.deposit_tzs


@dataclass(frozen=True)
class CancelRefund:
    policy: CancellationPolicy
    percent: int
    paid_tzs: int
    rental_tzs: int
    delivery_fee_tzs: int
    service_fee_tzs: int
    deposit_tzs: int
    # Commission handed back by the platform with the rental refund (ledger only).
    commission_tzs: int
    # When the current tier ends (the refund drops after it); None once no tier is left.
    deadline: datetime | None

    @property
    def total_tzs(self) -> int:
        return self.rental_tzs + self.delivery_fee_tzs + self.service_fee_tzs + self.deposit_tzs

    @property
    def from_owner_tzs(self) -> int:
        """Taken back from the owner's payable."""
        return self.rental_tzs - self.commission_tzs + self.delivery_fee_tzs

    @property
    def from_platform_tzs(self) -> int:
        return self.commission_tzs + self.service_fee_tzs


def policy_percent(
    policy: CancellationPolicy, start: datetime, now: datetime
) -> tuple[int, datetime | None]:
    """The rental refund percentage at `now` and when it next changes."""
    for tier in TIERS[policy]:
        edge = start - tier.before
        if now <= edge:
            return tier.percent, edge
    return LATE_PERCENT[policy], None


def cancellation_refund(
    policy: CancellationPolicy,
    start: datetime,
    charged: Charged,
    *,
    by: CancelledBy,
    now: datetime,
) -> CancelRefund:
    if by in (CancelledBy.OWNER, CancelledBy.ADMIN):
        percent, deadline = 100, None
    else:
        percent, deadline = policy_percent(policy, start, now)
    full = percent == 100
    return CancelRefund(
        policy=policy,
        percent=percent,
        paid_tzs=charged.total_tzs,
        rental_tzs=round_half_up(charged.rental_tzs * percent, 100),
        delivery_fee_tzs=charged.delivery_fee_tzs,
        service_fee_tzs=charged.service_fee_tzs if full else 0,
        deposit_tzs=charged.deposit_tzs,
        commission_tzs=round_half_up(charged.commission_tzs * percent, 100),
        deadline=deadline,
    )
