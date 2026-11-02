import logging
import sys
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.core import clock
from app.core.config import Settings
from app.core.db import uuid7
from app.core.i18n import normalize_locale, t
from app.core.logging import PiiMaskingFilter, mask_pii


def test_uuid7_is_version_7_and_time_ordered() -> None:
    a, b = uuid7(), uuid7()
    assert a.version == 7 and a.variant == "specified in RFC 4122"
    assert a.int >> 80 <= b.int >> 80


def test_eat_midnight_is_21_utc_previous_day() -> None:
    assert clock.to_eat_midnight(date(2026, 11, 2)) == datetime(2026, 11, 1, 21, 0, tzinfo=UTC)


def test_frozen_clock(frozen_clock) -> None:
    assert clock.now() == datetime(2026, 11, 2, 6, 0, tzinfo=UTC)
    frozen_clock.advance(minutes=15)
    assert clock.now_eat().hour == 9 and clock.now_eat().minute == 15
    assert clock.today_eat() == date(2026, 11, 2)


def test_locale_negotiation() -> None:
    assert normalize_locale(None) == "sw"
    assert normalize_locale("en-US,en;q=0.9") == "en"
    assert normalize_locale("fr-FR") == "sw"
    assert normalize_locale("sw-TZ") == "sw"


def test_translation_params_and_fallback() -> None:
    assert (
        t("errors.INSUFFICIENT_STOCK", "en", available=3) == "Not enough available. Available: 3."
    )
    assert t("missing.key", "en") == "missing.key"


def test_pii_masking() -> None:
    masked = mask_pii(
        "otp for +255712345678 and 0754 123 456 nida 19900101-12345-00001-23 tin 123-456-789"
    )
    assert "712345" not in masked and "+255*****678" in masked
    assert "+255*****456" in masked
    assert "[NIDA]" in masked and "[TIN]" in masked


def test_pii_filter_keeps_access_log_args_and_masks_tracebacks() -> None:
    # uvicorn.access: msg '%s - "%s %s HTTP/%s" %d' with a 5-tuple its formatter unpacks.
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/api/v1/admin/users?q=0712345678", "1.1", 200),
        None,
    )
    assert PiiMaskingFilter().filter(record)
    assert isinstance(record.args, tuple) and len(record.args) == 5
    assert "712345" not in record.getMessage() and "*****678" in record.getMessage()

    try:
        raise ValueError("no user +255754123456")
    except ValueError:
        failed = logging.LogRecord("app", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    PiiMaskingFilter().filter(failed)
    assert failed.exc_text and "754123" not in failed.exc_text and "+255*****456" in failed.exc_text


def test_settings_refuse_dev_values_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "JWT_SECRET",
        "OTP_HMAC_KEY",
        "FERNET_KEY",
        "PAYMENT_CALLBACK_SECRET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "COOKIE_SECURE",
        "SMS_PROVIDER",
        "PAYMENT_PROVIDER",
        "PAYOUT_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)
    Settings(env="dev")  # dev defaults are fine in dev
    with pytest.raises(ValidationError) as err:
        Settings(env="prod", _env_file=None)
    message = str(err.value)
    for problem in ("jwt_secret is the dev default", "cookie_secure", "sms_provider is console"):
        assert problem in message
    safe = {
        "jwt_secret": "j" * 40,
        "otp_hmac_key": "o" * 40,
        "fernet_key": "f" * 44,
        "payment_callback_secret": "c" * 40,
        "s3_access_key": "key",
        "s3_secret_key": "secret",
        "cookie_secure": True,
    }
    Settings(env="staging", _env_file=None, **safe)  # staging may use console SMS and mock pay
    with pytest.raises(ValidationError, match="payment_provider"):
        Settings(env="prod", _env_file=None, sms_provider="beem", **safe)
    Settings(
        env="prod",
        _env_file=None,
        sms_provider="beem",
        payment_provider="azampay",
        payout_provider="manual",
        **safe,
    )
