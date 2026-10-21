"""Local provider implementations (T017, T018)."""

import json
import uuid
from urllib.parse import urlparse

import httpx
import pytest

from app.core.config import Settings
from app.integrations.payments.azampay import AzamPayProvider
from app.integrations.payments.base import Network, PayoutDestination
from app.integrations.payments.mock import MockPayoutProvider
from app.integrations.sms.console import ConsoleSmsProvider
from app.integrations.storage.local import LocalStorage
from app.integrations.storage.s3 import S3Storage


async def test_console_sms_keeps_outbox() -> None:
    sms = ConsoleSmsProvider(echo=False)
    result = await sms.send(to="+255712345678", text="hello")
    assert result.ok and result.provider_ref
    last = sms.last_to("+255712345678")
    assert last is not None and last.text == "hello"


async def test_local_storage_roundtrip() -> None:
    storage = LocalStorage()
    await storage.put("a/b.jpg", b"img", "image/jpeg", private=True)
    assert await storage.get("a/b.jpg", private=True) == b"img"
    assert await storage.size("a/b.jpg", private=True) == 3
    assert await storage.size("a/b.jpg") is None
    assert storage.public_url(key="x.webp").endswith("/public/x.webp")


def test_s3_presigned_urls_use_browser_endpoint() -> None:
    settings = Settings(
        s3_endpoint_url="http://minio:9000",
        s3_presign_endpoint_url="http://localhost:9010",
        s3_public_base_url="http://localhost:9010/public",
    )
    storage = S3Storage(settings)
    put = storage.presign_put(
        key="docs/id.jpg", content_type="image/jpeg", max_bytes=10, private=True
    )
    parsed = urlparse(put.url)
    assert parsed.netloc == "localhost:9010" and parsed.path == "/private/docs/id.jpg"
    assert put.headers == {"Content-Type": "image/jpeg"}
    get = storage.presign_get(key="docs/id.jpg", ttl_s=60)
    assert "X-Amz-Expires=60" in get
    assert storage.public_url(key="p/1.webp") == "http://localhost:9010/public/p/1.webp"


# --- payout providers (T112) --------------------------------------------------------------


def test_payout_provider_falls_back_to_manual_until_disburse_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.integrations import get_payout_provider, override_payouts

    for enabled, expected in ((False, "manual"), (True, "azampay")):
        settings = Settings(payout_provider="azampay", azampay_disburse_enabled=enabled)
        monkeypatch.setattr("app.integrations.get_settings", lambda s=settings: s)
        override_payouts(None)
        assert get_payout_provider().name == expected
    override_payouts(None)


async def test_mock_payout_outcomes_follow_the_number() -> None:
    provider = MockPayoutProvider()
    payout_id = uuid.uuid4()

    def mobile(msisdn: str) -> PayoutDestination:
        return PayoutDestination(
            kind="mobile_money", account_name="A", network=Network.MPESA, msisdn=msisdn
        )

    paid = await provider.disburse(
        payout_id=payout_id, amount_tzs=1, destination=mobile("+255700000001")
    )
    assert paid.state == "paid" and paid.provider_ref
    failed = await provider.disburse(
        payout_id=payout_id, amount_tzs=1, destination=mobile("+255700000002")
    )
    assert (failed.state, failed.failure_reason) == ("failed", "invalid_account")
    later = await provider.disburse(
        payout_id=payout_id, amount_tzs=1, destination=mobile("+255700000003")
    )
    assert later.state == "processing"
    assert (await provider.get_payout_status(payout_id=payout_id, provider_ref="x")).state == "paid"


async def test_azampay_disburse_request_and_status() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/GenerateToken"):
            return httpx.Response(200, json={"data": {"accessToken": "tok"}})
        if request.url.path.endswith("/azampay/disburse"):
            return httpx.Response(200, json={"success": True, "data": "PG-123", "message": "ok"})
        return httpx.Response(200, json={"data": {"transactionStatus": "success"}})

    settings = Settings(azampay_disburse_source_account="SRC-1")
    provider = AzamPayProvider(
        settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )
    payout_id = uuid.uuid4()
    result = await provider.disburse(
        payout_id=payout_id,
        amount_tzs=180_000,
        destination=PayoutDestination(
            kind="mobile_money", account_name="Neema", network=Network.MIXX, msisdn="+255650000001"
        ),
    )
    assert (result.state, result.provider_ref) == ("processing", "PG-123")
    body = json.loads(seen[1].content)
    assert seen[1].headers["authorization"] == "Bearer tok"
    assert body["destination"] == {
        "countryCode": "TZ",
        "fullName": "Neema",
        "bankName": "Tigo",
        "accountNumber": "255650000001",
        "currency": "TZS",
    }
    assert body["transferDetails"]["amount"] == 180_000
    assert body["externalReferenceId"] == str(payout_id)
    assert body["source"]["accountNumber"] == "SRC-1"

    status = await provider.get_payout_status(payout_id=payout_id, provider_ref="PG-123")
    assert status.state == "paid"
    assert seen[2].url.params["pgReferenceId"] == "PG-123"

    bad = await provider.disburse(
        payout_id=payout_id,
        amount_tzs=1,
        destination=PayoutDestination(kind="bank", account_name="Neema"),
    )
    assert (bad.state, bad.failure_reason) == ("failed", "invalid_destination")
