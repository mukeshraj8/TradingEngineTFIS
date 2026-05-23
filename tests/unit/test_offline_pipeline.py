from __future__ import annotations

from pathlib import Path

import pytest

from tfis.domain.enums import OptionType
from tfis.domain.market_levels import MarketLevels
from tfis.execution import OrderPlanner
from tfis.importers import load_strategy_rule
from tfis.risk import RiskPolicy
from tfis.strategy import OfflineStrategyPipeline, StrategyEvaluator


def _build_pipeline(*, max_trades_per_day: int = 3) -> OfflineStrategyPipeline:
    return OfflineStrategyPipeline(
        strategy_evaluator=StrategyEvaluator(),
        order_planner=OrderPlanner(),
        risk_policy=RiskPolicy(
            max_lots_per_trade=100,
            max_trades_per_day=max_trades_per_day,
            allow_short_options=True,
            paper_only=True,
        ),
    )


def test_offline_pipeline_loads_s23_and_approves_valid_order() -> None:
    rule = load_strategy_rule(
        Path("config/strategies/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml")
    )
    market_levels = MarketLevels(
        d3ll=22000.0,
        d2hh=22500.0,
        current_day_high=22400.0,
        current_day_low=22100.0,
    )

    result = _build_pipeline().evaluate(
        rule,
        market_levels=market_levels,
        runtime_values={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert result.trade_plan.strategy_code == "S23"
    assert result.trade_plan.option_type is OptionType.CALL
    assert result.trade_plan.start_strike == 23100
    assert result.order_intent.side.value == "SELL"
    assert result.order_intent.quantity == 50
    assert result.risk_decision.approved is True
    assert result.risk_decision.reason == "Approved"


def test_offline_pipeline_rejects_when_max_trades_exceeded() -> None:
    rule = load_strategy_rule(
        Path("config/strategies/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml")
    )
    market_levels = MarketLevels(
        d3ll=22000.0,
        d2hh=22500.0,
        current_day_high=22400.0,
        current_day_low=22100.0,
    )

    result = _build_pipeline(max_trades_per_day=1).evaluate(
        rule,
        market_levels=market_levels,
        runtime_values={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert result.trade_plan.entry_price == pytest.approx(20350.0)
    assert result.order_intent.reference_price == pytest.approx(20350.0)
    assert result.risk_decision.approved is False
    assert "max_trades_per_day" in result.risk_decision.reason
