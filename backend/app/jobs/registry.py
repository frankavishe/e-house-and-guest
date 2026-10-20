"""Handler and periodic-sweep registries (R9).

Modules register with decorators at import time; `app.worker` imports `HANDLER_MODULES`.

    @handler("sms.send")
    async def send_sms(session, payload): ...

    @periodic("bookings.expire_holds", every=timedelta(minutes=1))
    async def expire_holds(session): ...

A periodic sweep is run as an ordinary job whose dedupe key contains the time bucket, so
with several workers each bucket runs once.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]
Sweep = Callable[[AsyncSession], Awaitable[object]]  # a sweep may return a count

PERIODIC_PREFIX = "periodic:"

# Modules whose import registers handlers and sweeps. Stories append to this list.
HANDLER_MODULES: list[str] = [
    "app.notifications.handlers",
    "app.bookings.jobs",
    "app.bookings.leases",
    "app.payments.jobs",
    "app.listings.jobs",
]


@dataclass(frozen=True)
class Periodic:
    name: str
    every: timedelta
    fn: Sweep


HANDLERS: dict[str, Handler] = {}
PERIODICS: dict[str, Periodic] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        if kind in HANDLERS and HANDLERS[kind] is not fn:
            raise ValueError(f"duplicate job handler for {kind!r}")
        HANDLERS[kind] = fn
        return fn

    return register


def periodic(name: str, *, every: timedelta) -> Callable[[Sweep], Sweep]:
    def register(fn: Sweep) -> Sweep:
        PERIODICS[name] = Periodic(name=name, every=every, fn=fn)

        async def run(session: AsyncSession, _payload: dict[str, Any]) -> None:
            await fn(session)

        HANDLERS[PERIODIC_PREFIX + name] = run
        return fn

    return register
