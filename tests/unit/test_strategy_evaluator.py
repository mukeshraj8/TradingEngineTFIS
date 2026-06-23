from __future__ import annotations

from pathlib import Path

import pytest

from tfis.domain.enums import MonthlyStatus, OptionType, Segment
from tfis.domain.market_levels import MarketLevels
from tfis.importers import load_strategy_rule
from tfis.strategy import StrategyEvaluator


def test_load_s23_rule_from_yaml() -> None:
    rule = load_strategy_rule(
        Path("config/strategies/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml")
    )

    assert rule.strategy_code == "S23"
    assert rule.unique_code == "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert rule.segment is Segment.OPTIONS_SELL
    assert rule.option_type is OptionType.CALL
    assert rule.allowed_monthly_statuses == (
        MonthlyStatus.BULL,
        MonthlyStatus.BULL_CF,
    )


def test_strategy_evaluator_builds_expected_trade_plan() -> None:
    rule = load_strategy_rule(
        Path("config/strategies/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml")
    )
    market_levels = MarketLevels(
        d3ll=22000.0,
        d2hh=22500.0,
        current_day_high=22400.0,
        current_day_low=22100.0,
    )
    runtime_values = {"ENTRY": 200.0}

    plan = StrategyEvaluator().evaluate(
        rule,
        market_levels=market_levels,
        runtime_values=runtime_values,
    )

    assert plan.strategy_code == "S23"
    assert plan.symbol == "NIFTY"
    assert plan.option_type is OptionType.CALL
    assert plan.start_strike == 23100
    assert plan.end_strike == 21999
    assert plan.ideal_premium == pytest.approx(22264.0)
    assert plan.minimum_premium == pytest.approx(22198.0)
    assert plan.entry_price == pytest.approx(20350.0)
    assert plan.target_price == pytest.approx(8140.0)
    assert plan.stoploss_price == pytest.approx(24075.0)
