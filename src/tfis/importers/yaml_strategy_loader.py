from __future__ import annotations

from datetime import time
from pathlib import Path

import yaml

from tfis.domain.enums import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment
from tfis.domain.strategy_rule import StrategyExpiryPolicy, StrategyRule


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


def _load_strategy_folder(path: Path) -> dict:
    strategy_path = path / "strategy.yaml"
    formulas_path = path / "formulas.yaml"
    parameters_path = path / "parameters.yaml"

    strategy_data = _load_yaml(strategy_path)
    formulas_data = _load_yaml(formulas_path)
    parameters_data = _load_yaml(parameters_path)
    if not isinstance(parameters_data, dict):
        raise ValueError(f"parameters.yaml must contain a mapping: {parameters_path}")

    merged = dict(strategy_data)
    merged.update(formulas_data)
    merged["parameters"] = {
        str(key): float(value) for key, value in parameters_data.items()
    }
    return merged


def _load_strategy_source(path: str | Path) -> dict:
    source_path = Path(path)
    if not source_path.exists():
        legacy_candidate = source_path.parent / "legacy" / source_path.name
        if legacy_candidate.exists():
            source_path = legacy_candidate

    if source_path.is_dir():
        return _load_strategy_folder(source_path)

    if source_path.name == "strategy.yaml":
        formulas_path = source_path.with_name("formulas.yaml")
        parameters_path = source_path.with_name("parameters.yaml")
        if formulas_path.exists() and parameters_path.exists():
            return _load_strategy_folder(source_path.parent)

    return _load_yaml(source_path)


def load_strategy_rule(path: str | Path) -> StrategyRule:
    data = _load_strategy_source(path)

    option_type_raw = data.get("option_type")
    option_type = OptionType(option_type_raw) if option_type_raw else None
    forced_close_time_raw = data.get("forced_close_time")
    forced_close_time = (
        _parse_time(forced_close_time_raw) if forced_close_time_raw else None
    )

    return StrategyRule(
        strategy_code=data["strategy_code"],
        unique_code=data["unique_code"],
        symbol=data["symbol"],
        segment=Segment(data["segment"]),
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType(data["expiry_type"]),
            rollover_policy=RolloverPolicy(data.get("rollover_policy", "T_MINUS_1")),
            forced_close_time=forced_close_time,
            no_carry_past_expiry=bool(data.get("no_carry_past_expiry", True)),
        ),
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
        parameters={str(key): float(value) for key, value in (data.get("parameters") or {}).items()},
    )
