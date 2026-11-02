"""Logging setup with a PII-masking filter (constitution Security, R18).

Phone numbers, NIDA numbers and TINs are masked in every log record, including arguments.
"""

import logging
import re

# +255712345678 / 255712345678 / 0712345678 (optionally spaced) → keep the last 3 digits.
_PHONE = re.compile(r"(?:\+?255|0)\s?[67]\d{2}\s?\d{3}\s?(\d{3})\b")
# NIDA: 20 digits, often written 8-5-5-2 with dashes.
_NIDA = re.compile(r"\b\d{8}-?\d{5}-?\d{5}-?\d{2}\b")
# TIN: 9 digits, often written 3-3-3.
_TIN = re.compile(r"\b\d{3}-?\d{3}-?\d{3}\b")


def mask_pii(text: str) -> str:
    text = _NIDA.sub("[NIDA]", text)
    text = _PHONE.sub(lambda m: f"+255*****{m.group(1)}", text)
    return _TIN.sub("[TIN]", text)


def _mask_arg(arg: object) -> object:
    return mask_pii(arg) if isinstance(arg, str) else arg


class PiiMaskingFilter(logging.Filter):
    """Masks the message, each string argument and the traceback. Arguments stay a tuple:
    uvicorn's access formatter unpacks them (client, method, path, version, status)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_pii(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_mask_arg(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _mask_arg(v) for k, v in record.args.items()}
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = mask_pii(record.exc_text)
        return True


# Uvicorn installs its own handlers (propagate=False) before importing the app; the access
# log carries query strings such as the admin user search (`?q=0712…`).
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(PiiMaskingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in _UVICORN_LOGGERS:
        for existing in logging.getLogger(name).handlers:
            if not any(isinstance(f, PiiMaskingFilter) for f in existing.filters):
                existing.addFilter(PiiMaskingFilter())
