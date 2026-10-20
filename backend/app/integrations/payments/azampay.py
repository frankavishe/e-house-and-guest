"""AzamPay MNO checkout (R6): USSD push to M-Pesa, Mixx by Yas (Tigo), Airtel, HaloPesa and
AzamPesa wallets.

Flow: a bearer token from the authenticator (`/AppRegistration/GenerateToken`), then
`POST /azampay/mno/checkout` with our payment id as `externalId`. The result arrives by
callback at `/api/v1/webhooks/payments/azampay/{secret}`; the service re-queries the status
before trusting it.

TODO(verify R6): the callback authentication, the status-query endpoint and the refund
capability could not be confirmed from public docs. Check them against the sandbox at
developerdocs.azampay.co.tz before enabling `PAYMENT_PROVIDER=azampay`.
"""

import hmac
import json
import time
import uuid
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.payments.base import (
    CallbackEvent,
    CheckoutStarted,
    InvalidCallback,
    Network,
    PaymentState,
    PaymentStatus,
    ProviderUnavailable,
    RefundResult,
)

BASE_URLS = {
    "sandbox": ("https://authenticator-sandbox.azampay.co.tz", "https://sandbox.azampay.co.tz"),
    "live": ("https://authenticator.azampay.co.tz", "https://checkout.azampay.co.tz"),
}
PROVIDERS = {
    Network.MPESA: "Mpesa",
    Network.MIXX: "Tigo",
    Network.AIRTEL: "Airtel",
    Network.HALOPESA: "Halopesa",
    Network.AZAMPESA: "Azampesa",
}
TIMEOUT_S = 15.0
TOKEN_MARGIN_S = 60
CALLBACK_PASSWORD_HEADER = "x-callback-password"  # TODO(verify R6)


def _state(value: Any) -> PaymentState:
    text = str(value or "").lower()
    if text in ("success", "successful", "succeeded", "completed"):
        return "succeeded"
    if text in ("failure", "failed", "cancelled", "rejected"):
        return "failed"
    return "pending"


class AzamPayProvider:
    name = "azampay"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._auth_url, self._base_url = BASE_URLS[settings.azampay_env]
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)
        self._token: str | None = None
        self._token_expires = 0.0

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(str(exc)) from exc
        if response.status_code >= 500:
            raise ProviderUnavailable(f"azampay {response.status_code}")
        try:
            data: dict[str, Any] = response.json()
        except ValueError as exc:
            raise ProviderUnavailable("azampay returned non-JSON") from exc
        return data

    async def _headers(self) -> dict[str, str]:
        if self._token is None or time.monotonic() >= self._token_expires:
            data = await self._request(
                "POST",
                f"{self._auth_url}/AppRegistration/GenerateToken",
                json={
                    "appName": self._settings.azampay_app_name,
                    "clientId": self._settings.azampay_client_id,
                    "clientSecret": self._settings.azampay_client_secret,
                },
            )
            token = (data.get("data") or {}).get("accessToken")
            if not token:
                raise ProviderUnavailable("azampay token request failed")
            self._token = str(token)
            # Tokens last about an hour; refresh a little early.
            self._token_expires = time.monotonic() + 3600 - TOKEN_MARGIN_S
        return {
            "Authorization": f"Bearer {self._token}",
            "X-API-Key": self._settings.azampay_api_key,
        }

    async def start_checkout(
        self, *, payment_id: uuid.UUID, amount_tzs: int, msisdn: str, network: Network
    ) -> CheckoutStarted:
        data = await self._request(
            "POST",
            f"{self._base_url}/azampay/mno/checkout",
            headers=await self._headers(),
            json={
                "accountNumber": msisdn.lstrip("+"),
                "amount": str(amount_tzs),
                "currency": "TZS",
                "externalId": str(payment_id),
                "provider": PROVIDERS[network],
            },
        )
        # A refused push (e.g. unknown number) is not a transport error: the payment stays
        # pending until the status check or reconciliation marks it failed.
        return CheckoutStarted(provider_txn_id=data.get("transactionId") or None, raw=data)

    async def get_status(
        self, *, payment_id: uuid.UUID, provider_txn_id: str | None
    ) -> PaymentStatus:
        # TODO(verify R6): endpoint and response shape of the transaction status query.
        data = await self._request(
            "GET",
            f"{self._base_url}/api/v1/Partner/GetTransactionStatus",
            headers=await self._headers(),
            params={"reference": provider_txn_id or str(payment_id), "bankName": ""},
        )
        payload = data.get("data") or data
        return PaymentStatus(
            state=_state(payload.get("transactionStatus") or payload.get("status")),
            provider_txn_id=provider_txn_id,
            failure_reason=payload.get("message"),
            raw=data,
        )

    def parse_callback(self, *, headers: Mapping[str, str], body: bytes) -> CallbackEvent:
        # TODO(verify R6): how AzamPay authenticates callbacks. Until confirmed we require
        # the password configured in the portal in a header.
        password = self._settings.azampay_callback_password
        given = {k.lower(): v for k, v in headers.items()}.get(CALLBACK_PASSWORD_HEADER, "")
        if not password or not hmac.compare_digest(given, password):
            raise InvalidCallback("bad callback password")
        try:
            data = json.loads(body)
            reference = str(data["reference"])
            external = data.get("utilityref") or data.get("externalreference")
            return CallbackEvent(
                provider_event_id=f"{reference}:{data.get('transactionstatus', '')}",
                payment_id=uuid.UUID(external) if external else None,
                provider_txn_id=reference,
                claimed_state=_state(data.get("transactionstatus")),
                raw=data,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidCallback("malformed body") from exc

    async def refund(
        self, *, payment_id: uuid.UUID, amount_tzs: int, msisdn: str, network: Network
    ) -> RefundResult:
        # TODO(verify R6/R7): refunds go out as disbursements once confirmed (US4).
        return RefundResult(ok=False, failure_reason="manual_refund_required")
