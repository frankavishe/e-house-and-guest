from datetime import UTC, date, datetime

from app.core import clock
from app.core.db import uuid7
from app.core.i18n import normalize_locale, t
from app.core.logging import mask_pii


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
