from __future__ import annotations

from tfis.domain.market_levels import MarketLevels
from tfis.domain.strategy_rule import StrategyRule
from tfis.domain.trade_plan import TradePlan
from tfis.formulas import FormulaEngine


class StrategyEvaluator:
    """Evaluates a single TFIS strategy rule into a concrete trade plan."""

    def __init__(self, formula_engine: FormulaEngine | None = None) -> None:
        self._formula_engine = formula_engine or FormulaEngine()

    def evaluate(
        self,
        rule: StrategyRule,
        *,
        market_levels: MarketLevels,
        runtime_values: dict[str, object] | None = None,
    ) -> TradePlan:
        inputs = dict(runtime_values or {})
        start_strike = self._formula_engine.evaluate(
            rule.start_strike_formula,
            market_levels=market_levels,
            runtime_values=inputs,
            parameters=rule.parameters,
        )
        end_strike = self._formula_engine.evaluate(
            rule.end_strike_formula,
            market_levels=market_levels,
            runtime_values=inputs,
            parameters=rule.parameters,
        )
        ideal_premium = self._formula_engine.evaluate(
            rule.ideal_premium_formula,
            market_levels=market_levels,
            runtime_values=inputs,
            parameters=rule.parameters,
        )
        minimum_premium = self._formula_engine.evaluate(
            rule.minimum_premium_formula,
            market_levels=market_levels,
            runtime_values=inputs,
            parameters=rule.parameters,
        )
        entry_price = self._formula_engine.evaluate(
            rule.entry_formula,
            market_levels=market_levels,
            runtime_values=inputs,
            parameters=rule.parameters,
        )
        inputs["ENTRY"] = entry_price
        target_price = self._formula_engine.evaluate(
            rule.target_formula,
            market_levels=market_levels,
            runtime_values=inputs,
            parameters=rule.parameters,
        )
        stoploss_price = self._formula_engine.evaluate(
            rule.stoploss_formula,
            market_levels=market_levels,
            runtime_values=inputs,
            parameters=rule.parameters,
        )

        return TradePlan(
            strategy_code=rule.strategy_code,
            symbol=rule.symbol,
            option_type=rule.option_type,
            start_strike=int(start_strike),
            end_strike=int(end_strike),
            ideal_premium=float(ideal_premium),
            minimum_premium=float(minimum_premium),
            entry_price=float(entry_price),
            stoploss_price=float(stoploss_price),
            target_price=float(target_price),
        )
