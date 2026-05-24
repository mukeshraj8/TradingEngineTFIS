from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "config" / "strategy_registry.yaml"
UNIVERSE_PATH = ROOT / "config" / "tradable_universe" / "liquid_stock_options.yaml"

ALLOWED_STATUSES = {
    "ACTIVE",
    "ACTIVE_CANDIDATE",
    "HISTORICAL_BACKTEST_ONLY",
    "PLACEHOLDER",
    "DISCONTINUED",
    "UNKNOWN_REQUIRES_REVIEW",
}


def test_strategy_registry_yaml_loads_and_uses_allowed_statuses() -> None:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    assert isinstance(data, dict)
    assert isinstance(data.get("strategies"), dict)
    assert data["strategies"]

    for strategy_name, entry in data["strategies"].items():
        assert isinstance(strategy_name, str)
        assert isinstance(entry, dict)
        assert entry["status"] in ALLOWED_STATUSES


def test_active_s23_branch_entries_exist() -> None:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    strategies = data["strategies"]
    assert strategies["S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"]["status"] == "ACTIVE_CANDIDATE"
    assert (
        strategies["S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT"]["status"]
        == "ACTIVE_CANDIDATE"
    )
    assert (
        strategies["S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"]["status"]
        == "ACTIVE_CANDIDATE"
    )
    assert (
        strategies["S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"]["status"]
        == "ACTIVE_CANDIDATE"
    )


def test_tradable_universe_yaml_loads_and_symbols_is_a_list() -> None:
    with UNIVERSE_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    assert data["universe_name"] == "liquid_stock_options"
    assert data["status"] == "USER_CONFIGURABLE"
    assert isinstance(data["symbols"], list)
