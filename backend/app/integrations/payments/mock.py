"""Mock payment provider for dev and tests (contracts/providers.md "MockProvider behaviour").

The outcome is chosen by the paying number's last four digits:

- `…0001` succeeds (callback after ~2 s), and so does any number without a rule;
- `…0002` fails with `insufficient_funds`;
- `…0003` never calls back and stays pending (reconciliation and expiry);
- `…0004` calls back twice with the same event (idempotency).

The outcome is encoded in `provider_txn_id`, so `get_status` gives the same answer in the API
and the worker process. `force()` overrides a status (the dev endpoint and tests use it).
Callbacks are signed with HMAC-SHA256 over the body. With `callback_url` set (dev), they are
POSTed there in the background; otherwise they queue in `take_callbacks()` (tests).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

from app.integrations.payments.base import (
    CallbackEvent,
    CheckoutStarted,
    InvalidCallback,
    Network,
    PaymentState,
    PaymentStatus,
    RefundResult,
)

log = logging.getLogger(__name__)

SIGNATURE_HEADER = "x-mock-signature"
CALLBACK_DELAY_S = 2.0

# outcome code → (state, failure reason, callbacks sent)
_OUTCOMES: dict[str, tuple[PaymentState, str | None, int]] = {
    "S": ("succeeded", None, 1),
    "F": ("failed", "insufficient_funds", 1),
    "P": ("pending", None, 0),
    "D": ("succeeded", None, 2),
}
_RULES = {"0001": "S", "0002": "F", "0003": "P", "0004": "D"}


@dataclass(frozen=True)
class MockCallback:
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


def outcome_for(msisdn: str) -> str:
    return _RULES.get(msisdn[-4:], "S")


class MockPaymentProvider:
    name = "mock"

    def __init__(self, *, secret: str, callback_url: str | None = None) -> None:
        self._secret = secret.encode()
        self._callback_url = callback_url
        self._queued: list[MockCallback] = []
        self._forced: dict[uuid.UUID, PaymentStatus] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # --- PaymentProvider -----------------------------------------------------------------

    async def start_checkout(
        self, *, payment_id: uuid.UUID, amount_tzs: int, msisdn: str, network: Network
    ) -> CheckoutStarted:
        code = outcome_for(msisdn)
        txn = f"MOCK{code}-{secrets.token_hex(6).upper()}"
        state, _, callbacks = _OUTCOMES[code]
        if callbacks:
            event_id = f"evt-{txn}"
            cb = self._callback(payment_id, txn, state, event_id)
            for _ in range(callbacks):
                self._send(cb)
        return CheckoutStarted(provider_txn_id=txn, raw={"amount": amount_tzs, "network": network})

    async def get_status(
        self, *, payment_id: uuid.UUID, provider_txn_id: str | None
    ) -> PaymentStatus:
        if payment_id in self._forced:
            return self._forced[payment_id]
        if not provider_txn_id or not provider_txn_id.startswith("MOCK"):
            return PaymentStatus(state="pending", provider_txn_id=provider_txn_id)
        state, reason, _ = _OUTCOMES.get(provider_txn_id[4], _OUTCOMES["P"])
        return PaymentStatus(state=state, provider_txn_id=provider_txn_id, failure_reason=reason)

    def parse_callback(self, *, headers: Mapping[str, str], body: bytes) -> CallbackEvent:
        given = {k.lower(): v for k, v in headers.items()}.get(SIGNATURE_HEADER, "")
        if not hmac.compare_digest(given, self._sign(body)):
            raise InvalidCallback("bad signature")
        try:
            data = json.loads(body)
            return CallbackEvent(
                provider_event_id=str(data["event_id"]),
                payment_id=uuid.UUID(data["payment_id"]),
                provider_txn_id=data.get("provider_txn_id"),
                claimed_state=data["status"],
                raw=data,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidCallback("malformed body") from exc

    async def refund(
        self, *, payment_id: uuid.UUID, amount_tzs: int, msisdn: str, network: Network
    ) -> RefundResult:
        return RefundResult(ok=True, provider_ref=f"MOCKREF-{secrets.token_hex(6).upper()}")

    # --- test and dev helpers ------------------------------------------------------------

    def force(self, payment_id: uuid.UUID, state: PaymentState, reason: str | None = None) -> None:
        self._forced[payment_id] = PaymentStatus(state=state, failure_reason=reason)

    def take_callbacks(self) -> list[MockCallback]:
        queued, self._queued = self._queued, []
        return queued

    def _sign(self, body: bytes) -> str:
        return hmac.new(self._secret, body, hashlib.sha256).hexdigest()

    def _callback(
        self, payment_id: uuid.UUID, txn: str, state: PaymentState, event_id: str
    ) -> MockCallback:
        body = json.dumps(
            {
                "event_id": event_id,
                "payment_id": str(payment_id),
                "provider_txn_id": txn,
                "status": state,
            }
        ).encode()
        return MockCallback(
            body=body,
            headers={"content-type": "application/json", SIGNATURE_HEADER: self._sign(body)},
        )

    def _send(self, cb: MockCallback) -> None:
        if self._callback_url is None:
            self._queued.append(cb)
            return
        task = asyncio.get_running_loop().create_task(self._post_later(cb))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _post_later(self, cb: MockCallback) -> None:
        assert self._callback_url is not None
        await asyncio.sleep(CALLBACK_DELAY_S)
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(self._callback_url, content=cb.body, headers=cb.headers)
        except httpx.HTTPError:
            log.warning("mock callback delivery failed", exc_info=True)
