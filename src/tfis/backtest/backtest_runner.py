from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tfis.backtest.models import BacktestInput, BacktestTradeResult, BacktestValidation
from tfis.execution.order_planner import OrderPlanner
from tfis.importers import load_strategy_rule, validate_folder_strategy_detailed
from tfis.market_structure.structure_calculator import MarketStructureCalculator
from tfis.risk.risk_policy import RiskPolicy
from tfis.strategy.strategy_evaluator import StrategyEvaluator


@dataclass(slots=True)
class BacktestRunner:
    structure_calculator: MarketStructureCalculator
    strategy_evaluator: StrategyEvaluator
    order_planner: OrderPlanner
    risk_policy: RiskPolicy

    def run(self, backtest_input: BacktestInput) -> BacktestTradeResult:
        strategy_path = Path(backtest_input.strategy_path)
        if strategy_path.is_file():
            raise ValueError(
                "BacktestRunner accepts folder-based strategy paths only, not YAML files"
            )

        ok, message, findings = validate_folder_strategy_detailed(strategy_path)
        if not ok:
            raise ValueError(f"Strategy folder validation failed: {message}")

        rule = load_strategy_rule(strategy_path)
        market_levels = self.structure_calculator.build_market_levels(
            backtest_input.daily_bars,
            intraday_bars=backtest_input.intraday_bars,
        )
        trade_plan = self.strategy_evaluator.evaluate(
            rule,
            market_levels=market_levels,
            runtime_values=backtest_input.runtime_values,
        )
        order_intent = self.order_planner.build_order_intent(
            trade_plan,
            lot_size=backtest_input.lot_size,
        )
        risk_decision = self.risk_policy.evaluate_order(
            order_intent,
            trades_taken_today=backtest_input.trades_taken_today,
        )
        return BacktestTradeResult(
            strategy_code=rule.strategy_code,
            trade_plan=trade_plan,
            order_intent=order_intent,
            risk_decision=risk_decision,
            validation=BacktestValidation(
                strategy_config_ok=True,
                formula_safety_findings=findings,
            ),
            accepted=risk_decision.approved,
            reason=risk_decision.reason,
        )
