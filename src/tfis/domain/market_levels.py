from __future__ import annotations

from dataclasses import dataclass


def _validate_price_field(name: str, value: float | None) -> None:
    if value is None:
        return
    if value < 0:
        raise ValueError(f"{name} must be non-negative when provided")


@dataclass(frozen=True, slots=True)
class MarketLevels:
    previous_month_high: float | None = None
    previous_month_low: float | None = None
    previous_week_high: float | None = None
    previous_week_low: float | None = None
    d2hh: float | None = None
    d2ll: float | None = None
    d3hh: float | None = None
    d3ll: float | None = None
    d4hh: float | None = None
    d4ll: float | None = None
    current_day_high: float | None = None
    current_day_low: float | None = None

    def __post_init__(self) -> None:
        for name in (
            "previous_month_high",
            "previous_month_low",
            "previous_week_high",
            "previous_week_low",
            "d2hh",
            "d2ll",
            "d3hh",
            "d3ll",
            "d4hh",
            "d4ll",
            "current_day_high",
            "current_day_low",
        ):
            _validate_price_field(name, getattr(self, name))

        self._validate_order("previous_month_high", "previous_month_low")
        self._validate_order("previous_week_high", "previous_week_low")
        self._validate_order("current_day_high", "current_day_low")

    def _validate_order(self, high_name: str, low_name: str) -> None:
        high = getattr(self, high_name)
        low = getattr(self, low_name)
        if high is not None and low is not None and high < low:
            raise ValueError(f"{high_name} must be greater than or equal to {low_name}")
