from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from math import isfinite

from .enums import MonthlyStatus, OptionType, Segment


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _require_non_negative_int(name: str, value: int) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _normalize_parameters(parameters: dict[str, float] | None) -> dict[str, float]:
    if parameters is None:
        return {}
    normalized: dict[str, float] = {}
    for key, value in parameters.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("parameter names must be non-empty strings")
        numeric_value = float(value)
        if not isfinite(numeric_value):
            raise ValueError(f"parameter {key!r} must be finite")
        normalized[key.strip()] = numeric_value
    return normalized


@dataclass(frozen=True, slots=True)
class StrategyRule:
    strategy_code: str
    unique_code: str
    symbol: str
    segment: Segment
    allowed_monthly_statuses: tuple[MonthlyStatus, ...]
    option_type: OptionType | None
    entry_time: time
    recalculation_time: time
    start_strike_formula: str
    end_strike_formula: str
    ideal_premium_formula: str
    minimum_premium_formula: str
    minimum_oi: int
    entry_formula: str
    target_formula: str
    stoploss_formula: str
    carry_forward_allowed: bool
    parameters: dict[str, float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy_code", _require_text("strategy_code", self.strategy_code))
        object.__setattr__(self, "unique_code", _require_text("unique_code", self.unique_code))
        object.__setattr__(self, "symbol", _require_text("symbol", self.symbol))

        if not self.allowed_monthly_statuses:
            raise ValueError("allowed_monthly_statuses must not be empty")
        if any(not isinstance(item, MonthlyStatus) for item in self.allowed_monthly_statuses):
            raise TypeError("allowed_monthly_statuses must contain MonthlyStatus values")
        object.__setattr__(self, "allowed_monthly_statuses", tuple(self.allowed_monthly_statuses))

        if not isinstance(self.entry_time, time):
            raise TypeError("entry_time must be a datetime.time instance")
        if not isinstance(self.recalculation_time, time):
            raise TypeError("recalculation_time must be a datetime.time instance")

        for name in (
            "start_strike_formula",
            "end_strike_formula",
            "ideal_premium_formula",
            "minimum_premium_formula",
            "entry_formula",
            "target_formula",
            "stoploss_formula",
        ):
            object.__setattr__(self, name, _require_text(name, getattr(self, name)))

        _require_non_negative_int("minimum_oi", self.minimum_oi)
        object.__setattr__(self, "parameters", _normalize_parameters(self.parameters))

        if self.segment in {Segment.OPTIONS_BUY, Segment.OPTIONS_SELL} and self.option_type is None:
            raise ValueError("option_type is required for option segments")
        if self.segment in {Segment.FUTURES, Segment.EQUITY} and self.option_type is not None:
            raise ValueError("option_type must be omitted for non-option segments")
