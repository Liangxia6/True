"""Injectable UTC clock."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return utc_now()


class FrozenClock:
    def __init__(self, when: datetime) -> None:
        self._when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._when

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._when = self._when + timedelta(seconds=seconds)
