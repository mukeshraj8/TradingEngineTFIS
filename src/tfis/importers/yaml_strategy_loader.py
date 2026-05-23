from __future__ import annotations

from datetime import time
from pathlib import Path

import yaml

from tfis.domain.enums import MonthlyStatus, OptionType, Segment
from tfis.domain.strategy_rule import StrategyRule


def _load_yaml(path: str | Path) -> dict:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Strategy YAML must contain a mapping: {file_path}")
    return data


def _parse_time(value: str) -> time:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Time values must be non-empty strings")
    return time.fromisoformat(value.strip())


def load_strategy_rule(path: str | Path) -> StrategyRule:
    data = _load_yaml(path)

    option_type_raw = data.get("option_type")
    option_type = OptionType(option_type_raw) if option_type_raw else None

    return StrategyRule(
        strategy_code=data["strategy_code"],
        unique_code=data["unique_code"],
        symbol=data["symbol"],
        segment=Segment(data["segment"]),
        allowed_monthly_statuses=tuple(
            MonthlyStatus(item) for item in data["allowed_monthly_statuses"]
        ),
        option_type=option_type,
        entry_time=_parse_time(data["entry_time"]),
        recalculation_time=_parse_time(data["recalculation_time"]),
        start_strike_formula=data["start_strike_formula"],
        end_strike_formula=data["end_strike_formula"],
        ideal_premium_formula=data["ideal_premium_formula"],
        minimum_premium_formula=data["minimum_premium_formula"],
        minimum_oi=int(data["minimum_oi"]),
        entry_formula=data["entry_formula"],
        target_formula=data["target_formula"],
        stoploss_formula=data["stoploss_formula"],
        carry_forward_allowed=bool(data["carry_forward_allowed"]),
    )
