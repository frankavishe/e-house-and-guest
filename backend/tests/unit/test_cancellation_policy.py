"""Cancellation policy calculator (T116, FR-026): tiers, EAT boundaries and fee handling."""

from datetime import UTC, datetime, timedelta

import pytest

from app.bookings.models import CancelledBy
from app.bookings.policies import Charged, cancellation_refund, policy_percent
from app.core.clock import EAT
from app.listings.models import CancellationPolicy

P = CancellationPolicy
# Check-in at 14:00 EAT on 20 Nov 2026 (11:00 UTC).
START = datetime(2026, 11, 20, 14, 0, tzinfo=EAT)
CHARGED = Charged(
    rental_tzs=200_000,
    delivery_fee_tzs=15_000,
    service_fee_tzs=10_000,
    deposit_tzs=50_000,
    commission_tzs=20_000,
)
SECOND = timedelta(seconds=1)


@pytest.mark.parametrize(
    ("policy", "now", "percent"),
    [
        (P.FLEXIBLE, START - timedelta(days=10), 100),
        (P.FLEXIBLE, START - timedelta(hours=24), 100),  # on the edge: still full
        (P.FLEXIBLE, START - timedelta(hours=24) + SECOND, 0),
        (P.FLEXIBLE, START - timedelta(hours=1), 0),
        (P.MODERATE, START - timedelta(days=5), 100),
        (P.MODERATE, START - timedelta(days=5) + SECOND, 50),
        (P.MODERATE, START - timedelta(hours=2), 50),
        (P.STRICT, START - timedelta(days=30), 50),
        (P.STRICT, START - timedelta(days=7), 50),
        (P.STRICT, START - timedelta(days=7) + SECOND, 0),
    ],
    ids=str,
)
def test_tiers(policy: CancellationPolicy, now: datetime, percent: int) -> None:
    assert policy_percent(policy, START, now)[0] == percent


def test_boundaries_are_instants_in_eat() -> None:
    """24 h before 14:00 EAT is 14:00 EAT the day before, i.e. 11:00 UTC, not 14:00 UTC."""
    assert policy_percent(P.FLEXIBLE, START, datetime(2026, 11, 19, 11, 0, tzinfo=UTC))[0] == 100
    assert policy_percent(P.FLEXIBLE, START, datetime(2026, 11, 19, 11, 1, tzinfo=UTC))[0] == 0


def test_deadline_is_the_tier_edge() -> None:
    _, deadline = policy_percent(P.MODERATE, START, START - timedelta(days=9))
    assert deadline == START - timedelta(days=5)
    assert policy_percent(P.MODERATE, START, START - timedelta(days=1))[1] is None


def test_renter_full_refund_returns_everything() -> None:
    r = cancellation_refund(
        P.FLEXIBLE, START, CHARGED, by=CancelledBy.RENTER, now=START - timedelta(days=3)
    )
    assert r.percent == 100
    assert (r.rental_tzs, r.delivery_fee_tzs, r.service_fee_tzs, r.deposit_tzs) == (
        200_000,
        15_000,
        10_000,
        50_000,
    )
    assert r.total_tzs == r.paid_tzs == 275_000
    assert r.commission_tzs == 20_000
    assert (r.from_owner_tzs, r.from_platform_tzs) == (195_000, 30_000)


def test_partial_refund_keeps_service_fee_returns_deposit_and_delivery() -> None:
    r = cancellation_refund(
        P.MODERATE, START, CHARGED, by=CancelledBy.RENTER, now=START - timedelta(days=2)
    )
    assert r.percent == 50
    assert r.rental_tzs == 100_000
    assert r.service_fee_tzs == 0
    assert r.deposit_tzs == 50_000
    assert r.delivery_fee_tzs == 15_000
    assert r.total_tzs == 165_000
    # Half the commission goes back; the owner keeps 90% of the forfeited half.
    assert r.commission_tzs == 10_000
    assert r.from_owner_tzs == 100_000 - 10_000 + 15_000


def test_no_refund_tier_still_returns_deposit() -> None:
    r = cancellation_refund(
        P.STRICT, START, CHARGED, by=CancelledBy.RENTER, now=START - timedelta(days=1)
    )
    assert r.percent == 0
    assert (r.rental_tzs, r.service_fee_tzs, r.commission_tzs) == (0, 0, 0)
    assert r.total_tzs == 50_000 + 15_000


@pytest.mark.parametrize("by", [CancelledBy.OWNER, CancelledBy.ADMIN])
def test_owner_and_admin_cancellations_refund_in_full(by: CancelledBy) -> None:
    r = cancellation_refund(P.STRICT, START, CHARGED, by=by, now=START - timedelta(hours=1))
    assert r.percent == 100
    assert r.total_tzs == CHARGED.total_tzs
    assert r.deadline is None


def test_unpaid_booking_refunds_nothing() -> None:
    r = cancellation_refund(
        P.FLEXIBLE, START, Charged(), by=CancelledBy.RENTER, now=START - timedelta(days=3)
    )
    assert r.total_tzs == 0 and r.paid_tzs == 0


def test_odd_amounts_round_half_up() -> None:
    charged = Charged(rental_tzs=100_001, commission_tzs=10_001)
    r = cancellation_refund(
        P.MODERATE, START, charged, by=CancelledBy.RENTER, now=START - timedelta(days=1)
    )
    assert (r.rental_tzs, r.commission_tzs) == (50_001, 5_001)
