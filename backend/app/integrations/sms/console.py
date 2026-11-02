"""Console SMS provider: prints in dev, keeps an in-memory outbox in tests (R11)."""

import itertools
from dataclasses import dataclass

from app.integrations.sms.base import SmsResult


@dataclass(frozen=True)
class SentSms:
    to: str
    text: str


class ConsoleSmsProvider:
    name = "console"

    def __init__(self, *, echo: bool = True) -> None:
        self.echo = echo
        self.outbox: list[SentSms] = []
        self._ids = itertools.count(1)

    async def send(self, *, to: str, text: str) -> SmsResult:
        self.outbox.append(SentSms(to=to, text=text))
        if self.echo:
            # Deliberately unmasked: dev sign-in needs to read the OTP from the logs.
            print(f"[sms → {to}] {text}", flush=True)
        return SmsResult(ok=True, provider_ref=f"console-{next(self._ids)}")

    def last_to(self, to: str) -> SentSms | None:
        return next((m for m in reversed(self.outbox) if m.to == to), None)
