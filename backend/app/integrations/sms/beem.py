"""Beem Africa SMS (R11): `POST {base}/v1/send` with HTTP Basic auth (API key : secret key).

The sender ID must be registered with Beem (and TCRA) before go-live; an unregistered sender
is rejected. Delivery reports are not consumed: an accepted request counts as sent.

`send` never raises. A failure returns `ok=False` so the caller decides: notification jobs
retry with backoff, OTP requests log and let the user ask again.

TODO(verify R11): the payload and response codes follow Beem's public API reference
(code 100 = submitted). Confirm them against a live account before `SMS_PROVIDER=beem`
(docs/operations.md go-live checklist).
"""

from typing import Any

import httpx

from app.core.config import Settings
from app.integrations.sms.base import SmsResult

TIMEOUT_S = 15.0
SUBMITTED = 100


class BeemSmsProvider:
    name = "beem"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._url = f"{settings.beem_base_url.rstrip('/')}/v1/send"
        self._auth = httpx.BasicAuth(settings.beem_api_key, settings.beem_secret_key)
        self._sender = settings.beem_sender_id
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)

    async def send(self, *, to: str, text: str) -> SmsResult:
        body = {
            "source_addr": self._sender,
            "encoding": 0,
            "schedule_time": "",
            "message": text,
            "recipients": [{"recipient_id": 1, "dest_addr": to.removeprefix("+")}],
        }
        try:
            response = await self._client.post(self._url, json=body, auth=self._auth)
        except httpx.HTTPError as exc:
            return SmsResult(ok=False, failure_reason=f"beem unreachable: {type(exc).__name__}")
        try:
            data: dict[str, Any] = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            return SmsResult(ok=False, failure_reason=f"beem {response.status_code}")
        if data.get("successful") is True and data.get("code") == SUBMITTED:
            return SmsResult(ok=True, provider_ref=str(data.get("request_id") or "") or None)
        return SmsResult(
            ok=False, failure_reason=f"beem code {data.get('code')}: {data.get('message')}"
        )
