from __future__ import annotations

from pathlib import Path

import pytest

from tfis.domain.market_levels import MarketLevels
from tfis.importers import load_strategy_rule
from tfis.strategy import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
LEGACY_S23 = ROOT / "config" / "strategies" / "legacy" / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml"
FOLDER_S23 = (
    ROOT
    / "config"
    / "strategies"
    / "options_sell"
    / "nifty"
    / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
)


def _market_levels() -> MarketLevels:
    return MarketLevels(
        d3ll=22000.0,
        d2hh=22500.0,
        current_day_high=22400.0,
        current_day_low=22100.0,
    )


def test_strategy_folder_loads_s23_with_parameters() -> None:
    rule = load_strategy_rule(FOLDER_S23)

    assert rule.strategy_code == "S23"
    assert rule.unique_code == "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert rule.parameters == {
        "strike_buffer_pct": 5.0,
        "ideal_premium_pct": 1.20,
        "minimum_premium_pct": 0.90,
        "entry_discount_pct": 7.5,
        "target_pct": 60.0,
        "sl_entry_pct": 60.0,
        "sl_reference_pct": 7.0,
    }
    assert rule.start_strike_formula == "ROUND_DOWN(PRV_3DLL + PARAM(strike_buffer_pct)%)"
    assert rule.ideal_premium_formula == "PRV_3DLL * PARAM(ideal_premium_pct)%"
    assert rule.entry_formula == "OPT_PRV_3DLL - PARAM(entry_discount_pct)%"
    assert (
        rule.stoploss_formula
        == "MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)"
    )


def test_legacy_single_file_yaml_still_loads() -> None:
    rule = load_strategy_rule(LEGACY_S23)

    assert rule.strategy_code == "S23"
    assert rule.parameters == {}


def test_strategy_evaluator_folder_s23_uses_excel_premium_semantics() -> None:
    rule = load_strategy_rule(FOLDER_S23)

    plan = StrategyEvaluator().evaluate(
        rule,
        market_levels=_market_levels(),
        runtime_values={
            "ENTRY": 200.0,
            "OPT_LEVELS": {
                "OPT_PRV_3DLL": 220.0,
                "OPT_PRV_2DHH": 300.0,
            },
        },
    )

    assert plan.start_strike == 23100
    assert plan.end_strike == 21999
    assert plan.ideal_premium == pytest.approx(264.0)
    assert plan.minimum_premium == pytest.approx(198.0)
    assert plan.entry_price == pytest.approx(203.5)
    assert plan.target_price == pytest.approx(80.0)
    assert plan.stoploss_price == pytest.approx(320.0)


def test_strategy_evaluator_legacy_s23_keeps_compatibility_premium_behavior() -> None:
    rule = load_strategy_rule(LEGACY_S23)

    plan = StrategyEvaluator().evaluate(
        rule,
        market_levels=_market_levels(),
        runtime_values={"ENTRY": 200.0},
    )

    assert plan.ideal_premium == pytest.approx(22264.0)
    assert plan.minimum_premium == pytest.approx(22198.0)


def test_folder_and_legacy_s23_premium_behavior_is_explicitly_different() -> None:
    folder_rule = load_strategy_rule(FOLDER_S23)
    legacy_rule = load_strategy_rule(LEGACY_S23)
    evaluator = StrategyEvaluator()

    folder_plan = evaluator.evaluate(
        folder_rule,
        market_levels=_market_levels(),
        runtime_values={
            "ENTRY": 200.0,
            "OPT_LEVELS": {
                "OPT_PRV_3DLL": 220.0,
                "OPT_PRV_2DHH": 300.0,
            },
        },
    )
    legacy_plan = evaluator.evaluate(
        legacy_rule,
        market_levels=_market_levels(),
        runtime_values={"ENTRY": 200.0},
    )

    assert folder_plan.ideal_premium == pytest.approx(264.0)
    assert legacy_plan.ideal_premium == pytest.approx(22264.0)
    assert folder_plan.minimum_premium == pytest.approx(198.0)
    assert legacy_plan.minimum_premium == pytest.approx(22198.0)
    assert folder_plan.entry_price == pytest.approx(203.5)
    assert legacy_plan.entry_price == pytest.approx(20350.0)


def test_no_root_level_strategy_yaml_remains_outside_legacy() -> None:
    strategy_root = ROOT / "config" / "strategies"
    root_yaml_files = sorted(path.name for path in strategy_root.glob("*.yaml"))

    assert root_yaml_files == []
