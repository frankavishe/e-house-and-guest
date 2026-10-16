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


class PiiMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        record.msg = mask_pii(message)
        record.args = None
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(PiiMaskingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
