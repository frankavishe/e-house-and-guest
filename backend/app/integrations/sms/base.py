"""SMS provider interface (contracts/providers.md, R11)."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SmsResult:
    ok: bool
    provider_ref: str | None = None
    failure_reason: str | None = None


class SmsProvider(Protocol):
    name: str

    async def send(self, *, to: str, text: str) -> SmsResult: ...
