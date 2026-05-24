from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.domain.market_levels import MarketLevels
from tfis.importers import load_strategy_rule, validate_folder_strategy_detailed
from tfis.strategy import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"

BRANCH_CASES = {
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D": {
        "option_type": OptionType.CALL,
        "statuses": (MonthlyStatus.BULL, MonthlyStatus.BULL_CF),
        "source_branch": "Bull/Bull CF Call",
        "source_cells": {
            "monthly_status": "D162",
            "option_type": "F162",
            "start_strike_formula": "G162",
            "end_strike_formula": "G163",
            "ideal_premium_formula": "H162",
            "minimum_premium_formula": "H163",
            "minimum_oi": "I162",
            "entry_formula": "M162",
            "target_formula": "O162",
            "stoploss_formula": "M163",
        },
        "expected": {
            "start_strike": 23100,
            "end_strike": 21999,
            "ideal_premium": 264.0,
            "minimum_premium": 198.0,
            "entry_price": 203.5,
            "target_price": 80.0,
            "stoploss_price": 320.0,
        },
    },
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT": {
        "option_type": OptionType.PUT,
        "statuses": (MonthlyStatus.BULL, MonthlyStatus.BULL_CF),
        "source_branch": "Bull/Bull CF Put",
        "source_cells": {
            "monthly_status": "D162",
            "option_type": "F165",
            "start_strike_formula": "G165",
            "end_strike_formula": "G166",
            "ideal_premium_formula": "H165",
            "minimum_premium_formula": "H166",
            "minimum_oi": "I165",
            "entry_formula": "M165",
            "target_formula": "O165",
            "stoploss_formula": "M166",
        },
        "expected": {
            "start_strike": 21375,
            "end_strike": 22501,
            "ideal_premium": 270.0,
            "minimum_premium": 202.5,
            "entry_price": 194.25,
            "target_price": 80.0,
            "stoploss_price": 320.0,
        },
    },
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL": {
        "option_type": OptionType.CALL,
        "statuses": (MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        "source_branch": "Bear/Bear CF Call",
        "source_cells": {
            "monthly_status": "D168",
            "option_type": "F168",
            "start_strike_formula": "G168",
            "end_strike_formula": "G169",
            "ideal_premium_formula": "H168",
            "minimum_premium_formula": "H169",
            "minimum_oi": "I168",
            "entry_formula": "M168",
            "target_formula": "O168",
            "stoploss_formula": "M169",
        },
        "expected": {
            "start_strike": 22995,
            "end_strike": 21899,
            "ideal_premium": 262.8,
            "minimum_premium": 197.1,
            "entry_price": 194.25,
            "target_price": 80.0,
            "stoploss_price": 320.0,
        },
    },
    "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT": {
        "option_type": OptionType.PUT,
        "statuses": (MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        "source_branch": "Bear/Bear CF Put",
        "source_cells": {
            "monthly_status": "D168",
            "option_type": "F171",
            "start_strike_formula": "G171",
            "end_strike_formula": "G172",
            "ideal_premium_formula": "H171",
            "minimum_premium_formula": "H172",
            "minimum_oi": "I171",
            "entry_formula": "M171",
            "target_formula": "O171",
            "stoploss_formula": "M172",
        },
        "expected": {
            "start_strike": 21470,
            "end_strike": 22601,
            "ideal_premium": 271.2,
            "minimum_premium": 203.4,
            "entry_price": 203.5,
            "target_price": 80.0,
            "stoploss_price": 320.0,
        },
    },
}


def _market_levels() -> MarketLevels:
    return MarketLevels(
        d2hh=22500.0,
        d2ll=21900.0,
        d3hh=22600.0,
        d3ll=22000.0,
        current_day_high=22400.0,
        current_day_low=22100.0,
    )


def _runtime_values() -> dict[str, object]:
    return {
        "ENTRY": 200.0,
        "OPT_LEVELS": {
            "OPT_PRV_2DLL": 210.0,
            "OPT_PRV_3DLL": 220.0,
            "OPT_PRV_2DHH": 300.0,
            "OPT_PRV_3DHH": 330.0,
        },
    }


@pytest.mark.parametrize("folder_name", sorted(BRANCH_CASES))
def test_all_s23_branch_folders_validate_and_load(folder_name: str) -> None:
    strategy_path = STRATEGY_ROOT / folder_name
    case = BRANCH_CASES[folder_name]

    ok, message, findings = validate_folder_strategy_detailed(strategy_path)
    assert ok, message
    assert [finding for finding in findings if finding.severity == "ERROR"] == []

    rule = load_strategy_rule(strategy_path)
    assert rule.strategy_code == "S23"
    assert rule.option_type == case["option_type"]
    assert rule.allowed_monthly_statuses == case["statuses"]


@pytest.mark.parametrize("folder_name", sorted(BRANCH_CASES))
def test_all_s23_branch_folders_evaluate_expected_sample_outputs(folder_name: str) -> None:
    strategy_path = STRATEGY_ROOT / folder_name
    expected = BRANCH_CASES[folder_name]["expected"]
    plan = StrategyEvaluator().evaluate(
        load_strategy_rule(strategy_path),
        market_levels=_market_levels(),
        runtime_values=_runtime_values(),
    )

    assert plan.start_strike == expected["start_strike"]
    assert plan.end_strike == expected["end_strike"]
    assert plan.ideal_premium == pytest.approx(expected["ideal_premium"])
    assert plan.minimum_premium == pytest.approx(expected["minimum_premium"])
    assert plan.entry_price == pytest.approx(expected["entry_price"])
    assert plan.target_price == pytest.approx(expected["target_price"])
    assert plan.stoploss_price == pytest.approx(expected["stoploss_price"])


@pytest.mark.parametrize("folder_name", sorted(BRANCH_CASES))
def test_all_s23_branch_crosschecks_contain_expected_source_cells(folder_name: str) -> None:
    strategy_path = STRATEGY_ROOT / folder_name
    case = BRANCH_CASES[folder_name]
    crosscheck_path = strategy_path / "excel_crosscheck.yaml"

    with crosscheck_path.open("r", encoding="utf-8") as handle:
        crosscheck = yaml.safe_load(handle)

    assert crosscheck["strategy_code"] == "S23"
    assert crosscheck["source_sheet"] == "AB6 OS"
    assert crosscheck["source_branch"] == case["source_branch"]
    assert crosscheck["source_cells"] == case["source_cells"]

