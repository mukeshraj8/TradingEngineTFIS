from __future__ import annotations

from dataclasses import dataclass

from tfis.domain.market_levels import MarketLevels
from tfis.domain.strategy_rule import StrategyRule
from tfis.domain.trade_plan import TradePlan
from tfis.execution.order_plan import OrderIntent
from tfis.execution.order_planner import OrderPlanner
from tfis.risk.risk_policy import RiskDecision, RiskPolicy

from .strategy_evaluator import StrategyEvaluator


@dataclass(frozen=True, slots=True)
class OfflinePipelineResult:
    trade_plan: TradePlan
    order_intent: OrderIntent
    risk_decision: RiskDecision


@dataclass(slots=True)
class OfflineStrategyPipeline:
    strategy_evaluator: StrategyEvaluator
    order_planner: OrderPlanner
    risk_policy: RiskPolicy

    def evaluate(
        self,
        rule: StrategyRule,
        *,
        market_levels: MarketLevels,
        runtime_values: dict[str, object] | None = None,
        lot_size: int,
        trades_taken_today: int,
    ) -> OfflinePipelineResult:
        trade_plan = self.strategy_evaluator.evaluate(
            rule,
            market_levels=market_levels,
            runtime_values=runtime_values,
        )
        order_intent = self.order_planner.build_order_intent(
            trade_plan,
            lot_size=lot_size,
        )
        risk_decision = self.risk_policy.evaluate_order(
            order_intent,
            trades_taken_today=trades_taken_today,
        )
        return OfflinePipelineResult(
            trade_plan=trade_plan,
            order_intent=order_intent,
            risk_decision=risk_decision,
        )
