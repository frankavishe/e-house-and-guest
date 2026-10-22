"""BeemSmsProvider against a stubbed Beem HTTP endpoint (T142, R11)."""

import base64
import json
from collections.abc import Callable, Iterator

import httpx
import pytest

from app import integrations
from app.core.config import Settings, get_settings
from app.integrations.sms.beem import BeemSmsProvider

SETTINGS = Settings(
    beem_api_key="key",
    beem_secret_key="secret",
    beem_sender_id="EHOUSE",
    beem_base_url="https://beem.test/",
)

Handler = Callable[[httpx.Request], httpx.Response]


def provider(handle: Handler) -> BeemSmsProvider:
    return BeemSmsProvider(
        SETTINGS, client=httpx.AsyncClient(transport=httpx.MockTransport(handle))
    )


def accepted(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "successful": True,
            "request_id": 58402,
            "code": 100,
            "message": "Message Submitted Successfully",
            "valid": 1,
            "invalid": 0,
            "duplicates": 0,
        },
    )


async def test_send_request_shape_and_success() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return accepted(request)

    result = await provider(handle).send(to="+255700000001", text="Nambari yako: 123456")
    assert result.ok and result.provider_ref == "58402"

    (request,) = seen
    assert request.method == "POST" and str(request.url) == "https://beem.test/v1/send"
    assert request.headers["authorization"] == "Basic " + base64.b64encode(b"key:secret").decode()
    assert json.loads(request.content) == {
        "source_addr": "EHOUSE",
        "encoding": 0,
        "schedule_time": "",
        "message": "Nambari yako: 123456",
        "recipients": [{"recipient_id": 1, "dest_addr": "255700000001"}],
    }


async def test_beem_rejection_is_a_failed_result() -> None:
    def handle(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"successful": False, "code": 111, "message": "Invalid Sender Id"}
        )

    result = await provider(handle).send(to="+255700000001", text="x")
    assert not result.ok
    assert result.failure_reason == "beem code 111: Invalid Sender Id"


@pytest.mark.parametrize("status", [401, 500, 503])
async def test_http_errors_are_failed_results(status: int) -> None:
    result = await provider(lambda _r: httpx.Response(status, text="oops")).send(
        to="+255700000001", text="x"
    )
    assert not result.ok and result.failure_reason == f"beem {status}"


async def test_transport_error_never_raises() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    result = await provider(handle).send(to="+255700000001", text="x")
    assert not result.ok and result.failure_reason == "beem unreachable: ConnectTimeout"


@pytest.fixture
def beem_selected(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("SMS_PROVIDER", "beem")
    get_settings.cache_clear()
    integrations.override_sms(None)
    yield
    monkeypatch.undo()
    get_settings.cache_clear()
    integrations.override_sms(None)


@pytest.mark.usefixtures("beem_selected")
def test_selected_by_settings() -> None:
    assert isinstance(integrations.get_sms_provider(), BeemSmsProvider)
