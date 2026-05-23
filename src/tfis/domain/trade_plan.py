from __future__ import annotations

from dataclasses import dataclass

from .enums import OptionType


def _validate_optional_non_negative(name: str, value: int | float | None) -> None:
    if value is None:
        return
    if value < 0:
        raise ValueError(f"{name} must be non-negative when provided")


@dataclass(frozen=True, slots=True)
class TradePlan:
    strategy_code: str
    symbol: str
    option_type: OptionType | None
    start_strike: int | None
    end_strike: int | None
    ideal_premium: float | None
    minimum_premium: float | None
    entry_price: float
    stoploss_price: float
    target_price: float

    def __post_init__(self) -> None:
        if not self.strategy_code or not self.strategy_code.strip():
            raise ValueError("strategy_code must be a non-empty string")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")

        _validate_optional_non_negative("start_strike", self.start_strike)
        _validate_optional_non_negative("end_strike", self.end_strike)
        _validate_optional_non_negative("ideal_premium", self.ideal_premium)
        _validate_optional_non_negative("minimum_premium", self.minimum_premium)
        _validate_optional_non_negative("entry_price", self.entry_price)
        _validate_optional_non_negative("stoploss_price", self.stoploss_price)
        _validate_optional_non_negative("target_price", self.target_price)
