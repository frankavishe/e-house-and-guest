"""Payment and payout provider interfaces (contracts/providers.md, R6, R7).

Implementations: `mock.py` (dev/tests, US2) and `azampay.py` (US2/US4).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol
from uuid import UUID


class Network(StrEnum):
    MPESA = "mpesa"
    MIXX = "mixx"
    AIRTEL = "airtel"
    HALOPESA = "halopesa"
    AZAMPESA = "azampesa"


PaymentState = Literal["pending", "succeeded", "failed", "expired"]
PayoutState = Literal["pending", "processing", "paid", "failed"]


class ProviderUnavailable(Exception):
    """Transport error or provider outage; the caller retries or marks the payment failed."""


class InvalidCallback(Exception):
    """Callback failed authentication or could not be parsed (→ 401, logged without PII)."""


@dataclass(frozen=True)
class CheckoutStarted:
    provider_txn_id: str | None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PaymentStatus:
    state: PaymentState
    provider_txn_id: str | None = None
    failure_reason: str | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CallbackEvent:
    provider_event_id: str
    payment_id: UUID | None
    provider_txn_id: str | None
    claimed_state: PaymentState
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RefundResult:
    ok: bool
    provider_ref: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class PayoutDestination:
    kind: Literal["mobile_money", "bank"]
    account_name: str
    network: Network | None = None
    msisdn: str | None = None
    bank_name: str | None = None
    account_number: str | None = None


@dataclass(frozen=True)
class PayoutResult:
    state: PayoutState
    provider_ref: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class PayoutStatus:
    state: PayoutState
    failure_reason: str | None = None


class PaymentProvider(Protocol):
    name: str

    async def start_checkout(
        self, *, payment_id: UUID, amount_tzs: int, msisdn: str, network: Network
    ) -> CheckoutStarted:
        """Send the USSD push. Must not raise on user-side failure; raises
        ProviderUnavailable on transport errors."""
        ...

    async def get_status(self, *, payment_id: UUID, provider_txn_id: str | None) -> PaymentStatus:
        """Authoritative status query, used after every callback and by reconciliation."""
        ...

    def parse_callback(self, *, headers: Mapping[str, str], body: bytes) -> CallbackEvent:
        """Authenticate and parse a callback. Raises InvalidCallback."""
        ...

    async def refund(
        self, *, payment_id: UUID, amount_tzs: int, msisdn: str, network: Network
    ) -> RefundResult: ...


class PayoutProvider(Protocol):
    name: str

    async def disburse(
        self, *, payout_id: UUID, amount_tzs: int, destination: PayoutDestination
    ) -> PayoutResult: ...

    async def get_payout_status(self, *, payout_id: UUID, provider_ref: str) -> PayoutStatus: ...
