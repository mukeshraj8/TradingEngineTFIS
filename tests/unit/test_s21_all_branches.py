from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tfis.domain.enums import ExpiryType, MonthlyStatus, OptionType
from tfis.domain.market_levels import MarketLevels
from tfis.importers import load_strategy_rule, validate_folder_strategy_detailed
from tfis.rules import S21_LEG_RULES, validate_s21_strategy_rule_matches_matrix
from tfis.strategy import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_ROOT = ROOT / "config" / "strategies" / "options_sell" / "banknifty"

BRANCH_CASES = {
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL": {
        "unique_code": "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
        "option_type": OptionType.CALL,
        "statuses": (MonthlyStatus.BULL, MonthlyStatus.BULL_CF),
        "source_branch": "Bull/Bull CF Call",
        "expected": {
            "start_strike": 47200,
            "end_strike": 44900,
            "ideal_premium": 900.0,
            "minimum_premium": 675.0,
            "entry_price": 462.5,
            "target_price": 185.0,
            "stoploss_price": 740.0,
        },
    },
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT": {
        "unique_code": "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
        "option_type": OptionType.PUT,
        "statuses": (MonthlyStatus.BULL, MonthlyStatus.BULL_CF),
        "source_branch": "Bull/Bull CF Put",
        "expected": {
            "start_strike": 43900,
            "end_strike": 46300,
            "ideal_premium": 924.0,
            "minimum_premium": 693.0,
            "entry_price": 444.0,
            "target_price": 177.6,
            "stoploss_price": 710.4,
        },
    },
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL": {
        "unique_code": "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
        "option_type": OptionType.CALL,
        "statuses": (MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        "source_branch": "Bear/Bear CF Call",
        "expected": {
            "start_strike": 47000,
            "end_strike": 44700,
            "ideal_premium": 896.0,
            "minimum_premium": 672.0,
            "entry_price": 444.0,
            "target_price": 177.6,
            "stoploss_price": 710.4,
        },
    },
    "S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT": {
        "unique_code": "BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT",
        "option_type": OptionType.PUT,
        "statuses": (MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        "source_branch": "Bear/Bear CF Put",
        "expected": {
            "start_strike": 44200,
            "end_strike": 46600,
            "ideal_premium": 930.0,
            "minimum_premium": 697.5,
            "entry_price": 462.5,
            "target_price": 185.0,
            "stoploss_price": 740.0,
        },
    },
}


def _market_levels() -> MarketLevels:
    return MarketLevels(
        d2hh=46200.0,
        d2ll=44800.0,
        d3hh=46500.0,
        d3ll=45000.0,
        current_day_high=46100.0,
        current_day_low=45200.0,
    )


def _runtime_values() -> dict[str, object]:
    return {
        "OPT_LEVELS": {
            "OPT_PRV_2DHH": 760.0,
            "OPT_PRV_2DLL": 480.0,
            "OPT_PRV_3DHH": 780.0,
            "OPT_PRV_3DLL": 500.0,
        },
    }


@pytest.mark.parametrize("folder_name", sorted(BRANCH_CASES))
def test_all_s21_branch_folders_validate_and_load(folder_name: str) -> None:
    strategy_path = STRATEGY_ROOT / folder_name
    case = BRANCH_CASES[folder_name]

    ok, message, findings = validate_folder_strategy_detailed(strategy_path)
    assert ok, message
    assert [finding for finding in findings if finding.severity == "ERROR"] == []

    rule = load_strategy_rule(strategy_path)
    assert rule.strategy_code == "S21"
    assert rule.unique_code == case["unique_code"]
    assert rule.symbol == "BANKNIFTY"
    assert rule.expiry_policy.expiry_type == ExpiryType.MONTHLY
    assert rule.option_type == case["option_type"]
    assert rule.allowed_monthly_statuses == case["statuses"]
    assert rule.minimum_oi == 17500
    assert rule.parameters["minimum_lots"] == 500.0
    assert rule.parameters["lot_size"] == 35.0


@pytest.mark.parametrize("folder_name", sorted(BRANCH_CASES))
def test_all_s21_branch_folders_match_rule_matrix(folder_name: str) -> None:
    rule = load_strategy_rule(STRATEGY_ROOT / folder_name)

    assert validate_s21_strategy_rule_matches_matrix(rule) == ()

    matrix_rule = S21_LEG_RULES[rule.unique_code]
    assert rule.option_type == matrix_rule.option_type
    assert rule.allowed_monthly_statuses == matrix_rule.allowed_monthly_statuses


@pytest.mark.parametrize("folder_name", sorted(BRANCH_CASES))
def test_all_s21_branch_folders_evaluate_expected_sample_outputs(folder_name: str) -> None:
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
def test_all_s21_branch_crosschecks_reference_source_image(folder_name: str) -> None:
    strategy_path = STRATEGY_ROOT / folder_name
    case = BRANCH_CASES[folder_name]

    with (strategy_path / "excel_crosscheck.yaml").open("r", encoding="utf-8") as handle:
        crosscheck = yaml.safe_load(handle)

    assert crosscheck["strategy_code"] == "S21"
    assert crosscheck["source_sheet"] == "BNF Monthly OS Rules"
    assert crosscheck["source_branch"] == case["source_branch"]
    assert crosscheck["source_cells"]["minimum_oi"] == "image.step_6_500_lots_times_lot_size"
