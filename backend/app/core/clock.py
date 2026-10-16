"""Injectable clock. All business code reads time from here so tests can freeze it.

Instants are stored in UTC; business rules (midnights, policy cut-offs) use EAT.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

EAT = ZoneInfo("Africa/Dar_es_Salaam")

_now_fn: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731


def now() -> datetime:
    """Current instant, timezone-aware UTC."""
    value = _now_fn()
    if value.tzinfo is None:  # freezegun returns naive UTC
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def now_eat() -> datetime:
    return now().astimezone(EAT)


def today_eat() -> date:
    return now_eat().date()


def to_eat_midnight(day: date) -> datetime:
    """Midnight at the start of `day` in EAT, as an aware UTC instant."""
    return datetime.combine(day, time.min, tzinfo=EAT).astimezone(UTC)


def to_eat(value: datetime) -> datetime:
    return value.astimezone(EAT)


def set_clock(fn: Callable[[], datetime]) -> None:
    """Replace the time source (tests)."""
    global _now_fn
    _now_fn = fn


def reset_clock() -> None:
    set_clock(lambda: datetime.now(UTC))
