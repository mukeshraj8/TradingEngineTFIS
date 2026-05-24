from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[3] / "config" / "strategy_registry.yaml"
ALLOWED_BACKTEST_STATUSES = {
    "ACTIVE",
    "ACTIVE_CANDIDATE",
    "HISTORICAL_BACKTEST_ONLY",
}
DISALLOWED_BACKTEST_STATUSES = {
    "PLACEHOLDER",
    "DISCONTINUED",
    "UNKNOWN_REQUIRES_REVIEW",
}


def load_strategy_registry(path: Path | None = None) -> dict:
    registry_path = path or DEFAULT_REGISTRY_PATH
    with registry_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Strategy registry must contain a mapping: {registry_path}")
    strategies = data.get("strategies")
    if not isinstance(strategies, dict):
        raise ValueError(f"Strategy registry missing strategies mapping: {registry_path}")
    return data


def get_strategy_status(
    unique_code_or_folder_name: str,
    path: Path | None = None,
) -> str | None:
    registry = load_strategy_registry(path)
    strategies = registry["strategies"]
    entry = strategies.get(str(unique_code_or_folder_name))
    if not isinstance(entry, dict):
        return None
    status = entry.get("status")
    return str(status) if status is not None else None


def assert_backtest_allowed(
    strategy_identifier: str,
    path: Path | None = None,
) -> str | None:
    status = get_strategy_status(strategy_identifier, path)
    if status is None:
        return None
    if status in ALLOWED_BACKTEST_STATUSES:
        return status
    if status in DISALLOWED_BACKTEST_STATUSES:
        raise ValueError(
            f"Strategy {strategy_identifier} is not allowed for backtest because registry status is {status}"
        )
    raise ValueError(
        f"Strategy {strategy_identifier} has unrecognized registry status {status}"
    )
