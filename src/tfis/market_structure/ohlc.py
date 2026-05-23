from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def _validate_non_negative(name: str, value: float | None) -> None:
    if value is None:
        return
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class OhlcBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime instance")

        for name in ("open", "high", "low", "close", "volume"):
            _validate_non_negative(name, getattr(self, name))

        if self.high < self.low:
            raise ValueError("high must be greater than or equal to low")
        if self.high < self.open or self.high < self.close:
            raise ValueError("high must be greater than or equal to open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("low must be less than or equal to open and close")
