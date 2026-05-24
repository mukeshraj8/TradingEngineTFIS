from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfis.importers import assert_backtest_allowed, get_strategy_status


ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "docs"
REGISTRY_PATH = ROOT / "config" / "strategy_registry.yaml"


def test_reference_material_docs_exist() -> None:
    assert (DOCS_ROOT / "reference_materials" / "README.md").is_file()
    assert (DOCS_ROOT / "strategy" / "rollover_rules_design.md").is_file()
    assert (DOCS_ROOT / "strategy" / "monthly_option_buying_design.md").is_file()


def test_reference_registry_entries_exist() -> None:
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    strategies = data["strategies"]
    assert strategies["ROLLOVER_RULES"]["status"] == "PLACEHOLDER"
    assert strategies["MONTHLY_OPTION_BUYING"]["status"] == "UNKNOWN_REQUIRES_REVIEW"
    assert strategies["STOCK_OPTION_BUYING_MONTHLY"]["status"] == "UNKNOWN_REQUIRES_REVIEW"
    assert strategies["BANKNIFTY_BACKTESTING_TEMPLATE"]["status"] == "HISTORICAL_BACKTEST_ONLY"


def test_reference_only_statuses_are_not_backtest_allowed() -> None:
    with pytest.raises(ValueError, match="PLACEHOLDER"):
        assert_backtest_allowed("ROLLOVER_RULES")

    with pytest.raises(ValueError, match="UNKNOWN_REQUIRES_REVIEW"):
        assert_backtest_allowed("MONTHLY_OPTION_BUYING")

    with pytest.raises(ValueError, match="UNKNOWN_REQUIRES_REVIEW"):
        assert_backtest_allowed("STOCK_OPTION_BUYING_MONTHLY")


def test_historical_reference_status_can_still_be_backtested() -> None:
    assert get_strategy_status("BANKNIFTY_BACKTESTING_TEMPLATE") == "HISTORICAL_BACKTEST_ONLY"
    assert (
        assert_backtest_allowed("BANKNIFTY_BACKTESTING_TEMPLATE")
        == "HISTORICAL_BACKTEST_ONLY"
    )
