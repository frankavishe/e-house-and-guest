"""Backend translations (R13): error messages, SMS and notification templates.

Catalogs live in `app/i18n/{sw,en}.json` as nested objects; keys are dotted paths
(`errors.SLOT_TAKEN`). Swahili is the default language (FR-004).
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Header

Locale = Literal["sw", "en"]
LOCALES: tuple[Locale, ...] = ("sw", "en")
DEFAULT_LOCALE: Locale = "sw"

_CATALOG_DIR = Path(__file__).resolve().parent.parent / "i18n"


def _flatten(prefix: str, node: Any, out: dict[str, str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _flatten(f"{prefix}.{key}" if prefix else key, value, out)
    else:
        out[prefix] = str(node)


@lru_cache
def catalog(locale: Locale) -> dict[str, str]:
    raw = json.loads((_CATALOG_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    flat: dict[str, str] = {}
    _flatten("", raw, flat)
    return flat


def t(key: str, locale: str = DEFAULT_LOCALE, **params: Any) -> str:
    """Translate `key`; falls back to the other language, then to the key itself."""
    loc = normalize_locale(locale)
    text = catalog(loc).get(key)
    if text is None:
        other: Locale = "en" if loc == "sw" else "sw"
        text = catalog(other).get(key, key)
    try:
        return text.format(**params) if params else text
    except (KeyError, IndexError):
        return text


def normalize_locale(value: str | None) -> Locale:
    """Pick `sw` or `en` from an Accept-Language value; default `sw`."""
    if not value:
        return DEFAULT_LOCALE
    for part in value.split(","):
        tag = part.split(";")[0].strip().lower()
        primary = tag.split("-")[0]
        if primary == "en":
            return "en"
        if primary == "sw":
            return "sw"
    return DEFAULT_LOCALE


def get_locale(accept_language: Annotated[str | None, Header()] = None) -> Locale:
    """FastAPI dependency: the request language."""
    return normalize_locale(accept_language)
