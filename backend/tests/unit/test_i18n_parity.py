"""SC-007: backend sw/en catalogs (errors, SMS, notifications) have identical keys and
placeholders (T046)."""

import re

from app.core.i18n import catalog


def _placeholders(text: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)", text))


def test_i18n_parity_keys() -> None:
    assert set(catalog("sw")) == set(catalog("en"))


def test_i18n_parity_placeholders() -> None:
    sw, en = catalog("sw"), catalog("en")
    for key in sw:
        assert _placeholders(sw[key]) == _placeholders(en[key]), key


def test_i18n_no_empty_strings() -> None:
    for loc in ("sw", "en"):
        for key, value in catalog(loc).items():
            assert value.strip(), f"{loc}:{key}"
