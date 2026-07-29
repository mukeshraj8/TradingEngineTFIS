from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Any

from tfis.decision import (
    ContractSelectionPolicyInput,
    ContractSelectionPolicyResult,
    EntryPolicyInput,
    EntryPolicyResult,
    GapPolicyInput,
    GapPolicyResult,
    MSLPolicyInput,
    MSLPolicyResult,
    MissedEntryPolicyInput,
    MissedEntryPolicyResult,
    PolicyStatus,
    ProductPolicyInput,
    ProductPolicyResult,
    TargetPolicyInput,
    TargetPolicyResult,
    TargetPolicyTarget,
)
from tfis.domain import (
    Segment,
    StrategyRule,
    TFISContractIdentity,
    TFISDirection,
    TFISExecutionSide,
    TFISFormulaTrace,
    TFISProductType,
    product_type_from_segment,
)
from tfis.domain.market_levels import MarketLevels
from tfis.paper.contract_selection import (
    S23PaperContractSelectionRequest,
    S23PaperContractSelector,
)
from tfis.paper.models import OptionChainSnapshotEvent
from tfis.strategy import StrategyEvaluator


class LegacyOptionSellingProductPolicyAdapter:
    """Current S21/S23 option-selling product resolution."""

    policy_name = "legacy.option_selling.product"

    def __init__(self, strategy_rule: StrategyRule) -> None:
        self._strategy_rule = strategy_rule

    def evaluate(self, policy_input: ProductPolicyInput) -> ProductPolicyResult:
        runtime_input = policy_input.runtime_input
        if runtime_input.monthly_status not in self._strategy_rule.allowed_monthly_statuses:
            return ProductPolicyResult(
                policy_name=self.policy_name,
                evaluated_at=runtime_input.evaluated_at,
                status=PolicyStatus.BLOCKED,
                applicable=True,
                reason="Runtime Monthly Status is not allowed for this strategy branch.",
                requirement_id="MON-019",
                inputs={
                    "runtime_monthly_status": runtime_input.monthly_status,
                    "allowed_monthly_statuses": self._strategy_rule.allowed_monthly_statuses,
                },
                evidence={"strategy_unique_code": self._strategy_rule.unique_code},
            )
        return ProductPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.PASSED,
            applicable=True,
            reason="Legacy option-selling branch explicitly resolves to SHORT/SELL.",
            requirement_id="AB16-PRODUCT",
            inputs={
                "strategy_code": self._strategy_rule.strategy_code,
                "unique_code": self._strategy_rule.unique_code,
                "segment": self._strategy_rule.segment,
            },
            evidence={"adapter": type(self).__name__},
            product_type=product_type_from_segment(self._strategy_rule.segment),
            direction=TFISDirection.SHORT,
            execution_side=TFISExecutionSide.SELL,
            branch=self._strategy_rule.unique_code,
        )


class S21ProductPolicyAdapter(LegacyOptionSellingProductPolicyAdapter):
    policy_name = "legacy.s21.option_selling.product"


class S23ProductPolicyAdapter(LegacyOptionSellingProductPolicyAdapter):
    policy_name = "legacy.s23.option_selling.product"


class LegacyOptionSellingEntryPolicyAdapter:
    """Wraps the current StrategyEvaluator formula path."""

    policy_name = "legacy.option_selling.entry"

    def __init__(
        self,
        strategy_rule: StrategyRule,
        *,
        evaluator: StrategyEvaluator | None = None,
    ) -> None:
        self._strategy_rule = strategy_rule
        self._evaluator = evaluator or StrategyEvaluator()

    def evaluate(self, policy_input: EntryPolicyInput) -> EntryPolicyResult:
        runtime_input = policy_input.runtime_input
        market_levels = _market_levels_from_runtime_input(runtime_input.market_structure_references)
        runtime_values = _plain_value(runtime_input.runtime_values)
        plan = self._evaluator.evaluate(
            self._strategy_rule,
            market_levels=market_levels,
            runtime_values=runtime_values,
        )
        evidence = {
            "adapter": type(self).__name__,
            "trade_plan": asdict(plan),
            "formulas": {
                "start_strike": self._strategy_rule.start_strike_formula,
                "end_strike": self._strategy_rule.end_strike_formula,
                "ideal_premium": self._strategy_rule.ideal_premium_formula,
                "minimum_premium": self._strategy_rule.minimum_premium_formula,
                "entry": self._strategy_rule.entry_formula,
                "target": self._strategy_rule.target_formula,
                "stoploss": self._strategy_rule.stoploss_formula,
            },
            "parameters": dict(self._strategy_rule.parameters or {}),
        }
        return EntryPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.PASSED,
            applicable=True,
            reason="Legacy strategy formulas evaluated through StrategyEvaluator.",
            requirement_id="AB16-ENTRY",
            formula=self._strategy_rule.entry_formula,
            calculated_value=plan.entry_price,
            inputs={
                "market_structure_references": runtime_input.market_structure_references,
                "runtime_values": runtime_values,
            },
            intermediate_values={
                "start_strike": plan.start_strike,
                "end_strike": plan.end_strike,
                "ideal_premium": plan.ideal_premium,
                "minimum_premium": plan.minimum_premium,
                "target_price": plan.target_price,
                "stoploss_price": plan.stoploss_price,
            },
            quality_status="VALID",
            evidence=evidence,
            entry_value=plan.entry_price,
            formula_trace=TFISFormulaTrace(
                name=f"{self._strategy_rule.strategy_code}.entry",
                formula=self._strategy_rule.entry_formula,
                result=plan.entry_price,
                inputs={
                    "market_structure_references": runtime_input.market_structure_references,
                    "runtime_values": runtime_values,
                },
                evidence=evidence,
            ),
        )


class S21EntryPolicyAdapter(LegacyOptionSellingEntryPolicyAdapter):
    policy_name = "legacy.s21.option_selling.entry"


class S23EntryPolicyAdapter(LegacyOptionSellingEntryPolicyAdapter):
    policy_name = "legacy.s23.option_selling.entry"


class LegacyUnsupportedGapPolicyAdapter:
    policy_name = "legacy.option_selling.gap.not_configured"

    def evaluate(self, policy_input: GapPolicyInput) -> GapPolicyResult:
        runtime_input = policy_input.runtime_input
        return GapPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.NOT_APPLICABLE,
            applicable=False,
            reason="No separate legacy gap policy is represented in this offline parity fixture.",
            requirement_id="PHASE2B-GAP-COMPAT",
            branch="LEGACY_NOT_CONFIGURED",
            evidence={"adapter": type(self).__name__},
        )


class LegacyUnsupportedMissedEntryPolicyAdapter:
    policy_name = "legacy.option_selling.missed_entry.not_configured"

    def evaluate(self, policy_input: MissedEntryPolicyInput) -> MissedEntryPolicyResult:
        runtime_input = policy_input.runtime_input
        return MissedEntryPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.NOT_APPLICABLE,
            applicable=False,
            reason="No separate legacy missed-entry policy is represented in this offline parity fixture.",
            requirement_id="PHASE2B-MISSED-COMPAT",
            missed=False,
            branch="LEGACY_NOT_CONFIGURED",
            evidence={"adapter": type(self).__name__},
        )


class S23GapPolicyAdapter(LegacyUnsupportedGapPolicyAdapter):
    policy_name = "legacy.s23.gap.not_configured"

    def evaluate(self, policy_input: GapPolicyInput) -> GapPolicyResult:
        runtime_input = policy_input.runtime_input
        timing = _plain_value(runtime_input.gap_context.get("orpt_rc_timing") or {})
        if not timing:
            return super().evaluate(policy_input)
        status = str(timing.get("status") or "UNKNOWN")
        failed = status.startswith("MISSING_")
        return GapPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.UNAVAILABLE if failed else PolicyStatus.PASSED,
            applicable=True,
            reason=str(timing.get("reason") or "Legacy S23 ORPT/RC timing evidence supplied."),
            requirement_id="S23-ORPT-RC",
            branch=status,
            inputs={"orpt_rc_timing": timing},
            quality_status=status,
            evidence={"adapter": type(self).__name__, "orpt_rc_timing": timing},
        )


class S23MissedEntryPolicyAdapter(LegacyUnsupportedMissedEntryPolicyAdapter):
    policy_name = "legacy.s23.missed_entry.not_configured"

    def evaluate(self, policy_input: MissedEntryPolicyInput) -> MissedEntryPolicyResult:
        runtime_input = policy_input.runtime_input
        timing = _plain_value(runtime_input.gap_context.get("orpt_rc_timing") or {})
        if not timing:
            return super().evaluate(policy_input)
        status = str(timing.get("status") or "UNKNOWN")
        failed = status.startswith("MISSING_")
        missed = status == "ENTRY_MISSED_RECALCULATED"
        return MissedEntryPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.UNAVAILABLE if failed else PolicyStatus.PASSED,
            applicable=True,
            reason=str(timing.get("reason") or "Legacy S23 missed-entry evidence supplied."),
            requirement_id="S23-ORPT-RC",
            missed=missed,
            branch=status,
            inputs={"orpt_rc_timing": timing},
            quality_status=status,
            evidence={"adapter": type(self).__name__, "orpt_rc_timing": timing},
        )


class LegacyOptionSellingContractSelectionPolicyAdapter:
    """Wraps the current option-chain selector for deterministic offline parity."""

    policy_name = "legacy.option_selling.contract_selection"

    def __init__(
        self,
        strategy_rule: StrategyRule,
        *,
        selector: S23PaperContractSelector | None = None,
    ) -> None:
        self._strategy_rule = strategy_rule
        self._selector = selector or S23PaperContractSelector()

    def evaluate(
        self,
        policy_input: ContractSelectionPolicyInput,
    ) -> ContractSelectionPolicyResult:
        runtime_input = policy_input.runtime_input
        option_chain = runtime_input.product_specific.get("option_chain_snapshot")
        if not isinstance(option_chain, OptionChainSnapshotEvent):
            return ContractSelectionPolicyResult(
                policy_name=self.policy_name,
                evaluated_at=runtime_input.evaluated_at,
                status=PolicyStatus.UNAVAILABLE,
                applicable=True,
                reason="Offline parity contract selection requires option_chain_snapshot.",
                requirement_id="AB16-CONTRACT",
                evidence={"adapter": type(self).__name__},
            )
        expiry_date = _date_value(runtime_input.product_specific.get("expiry_date"))
        if expiry_date is None:
            return ContractSelectionPolicyResult(
                policy_name=self.policy_name,
                evaluated_at=runtime_input.evaluated_at,
                status=PolicyStatus.UNAVAILABLE,
                applicable=True,
                reason="Offline parity contract selection requires expiry_date.",
                requirement_id="AB16-CONTRACT",
                evidence={"adapter": type(self).__name__},
            )
        trade_plan = dict(policy_input.entry_result.evidence.get("trade_plan") or {})
        request = S23PaperContractSelectionRequest(
            underlying_symbol=self._strategy_rule.symbol,
            expiry_date=expiry_date,
            option_type=self._strategy_rule.option_type,
            start_strike=float(trade_plan["start_strike"]),
            end_strike=float(trade_plan["end_strike"]),
            ideal_premium=float(trade_plan["ideal_premium"]),
            minimum_premium=float(trade_plan["minimum_premium"]),
            minimum_oi=float(self._strategy_rule.minimum_oi),
            fallback_expiry_dates=tuple(
                item
                for item in (
                    _date_value(value)
                    for value in runtime_input.product_specific.get(
                        "fallback_expiry_dates",
                        (),
                    )
                )
                if item is not None
            ),
        )
        result = self._selector.select(request, option_chain)
        evidence = {
            "adapter": type(self).__name__,
            "request": {
                "underlying_symbol": request.underlying_symbol,
                "expiry_date": request.expiry_date,
                "option_type": request.option_type,
                "start_strike": request.start_strike,
                "end_strike": request.end_strike,
                "ideal_premium": request.ideal_premium,
                "minimum_premium": request.minimum_premium,
                "minimum_oi": request.minimum_oi,
                "fallback_expiry_dates": request.fallback_expiry_dates,
            },
            "legacy_result": {
                "selected": result.selected,
                "failure_code": result.failure_code,
                "selection_reason": result.selection_reason,
                "attempted_expiries": result.attempted_expiries,
                "rejected_candidate_counts": result.rejected_candidate_counts,
            },
        }
        if not result.selected:
            return ContractSelectionPolicyResult(
                policy_name=self.policy_name,
                evaluated_at=runtime_input.evaluated_at,
                status=PolicyStatus.UNAVAILABLE,
                applicable=True,
                reason=result.selection_reason,
                requirement_id="AB16-CONTRACT",
                candidate_count=result.ranked_candidate_count,
                quality_status=result.failure_code.value if result.failure_code else None,
                evidence=evidence,
            )
        selected = TFISContractIdentity(
            symbol=result.selected_contract_symbol,
            segment=Segment.OPTIONS_SELL,
            product_type=TFISProductType.OPTION_SELLING,
            expiry=result.expiry_date,
            strike=result.strike,
            option_type=result.option_type.value if result.option_type else None,
            metadata={
                "ltp": result.premium_used,
                "oi": result.oi_used,
                "selection_reason": result.selection_reason,
            },
        )
        return ContractSelectionPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.PASSED,
            applicable=True,
            reason=result.selection_reason,
            requirement_id="AB16-CONTRACT",
            selected_contract=selected,
            candidate_count=result.ranked_candidate_count,
            evidence=evidence,
        )


class S21ContractSelectionPolicyAdapter(LegacyOptionSellingContractSelectionPolicyAdapter):
    policy_name = "legacy.s21.option_selling.contract_selection"


class S23ContractSelectionPolicyAdapter(LegacyOptionSellingContractSelectionPolicyAdapter):
    policy_name = "legacy.s23.option_selling.contract_selection"


class LegacyOptionSellingTargetPolicyAdapter:
    policy_name = "legacy.option_selling.target"

    def __init__(self, strategy_rule: StrategyRule) -> None:
        self._strategy_rule = strategy_rule

    def evaluate(self, policy_input: TargetPolicyInput) -> TargetPolicyResult:
        runtime_input = policy_input.runtime_input
        trade_plan = dict(policy_input.entry_result.evidence.get("trade_plan") or {})
        target_price = _float_or_none(trade_plan.get("target_price"))
        if target_price is None:
            return TargetPolicyResult(
                policy_name=self.policy_name,
                evaluated_at=runtime_input.evaluated_at,
                status=PolicyStatus.NOT_APPLICABLE,
                applicable=False,
                reason="Legacy branch has no target price in the evaluated trade plan.",
                requirement_id="AB16-TARGET",
                targets=(),
                evidence={"adapter": type(self).__name__, "trade_plan": trade_plan},
            )
        target = TargetPolicyTarget(
            order=1,
            target_price=target_price,
            quantity=runtime_input.quantity,
            formula=self._strategy_rule.target_formula,
            evidence={"source": "StrategyEvaluator.trade_plan.target_price"},
        )
        return TargetPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.PASSED,
            applicable=True,
            reason="Legacy single target preserved from StrategyEvaluator trade plan.",
            requirement_id="AB16-TARGET",
            formula=self._strategy_rule.target_formula,
            calculated_value=target_price,
            inputs={"entry_result": policy_input.entry_result.to_dict()},
            intermediate_values={"target_price": target_price},
            quality_status="VALID",
            evidence={"adapter": type(self).__name__, "trade_plan": trade_plan},
            targets=(target,),
        )


class S21TargetPolicyAdapter(LegacyOptionSellingTargetPolicyAdapter):
    policy_name = "legacy.s21.option_selling.target"


class S23TargetPolicyAdapter(LegacyOptionSellingTargetPolicyAdapter):
    policy_name = "legacy.s23.option_selling.target"


class LegacyOptionSellingMSLPolicyAdapter:
    policy_name = "legacy.option_selling.msl"

    def __init__(self, strategy_rule: StrategyRule) -> None:
        self._strategy_rule = strategy_rule

    def evaluate(self, policy_input: MSLPolicyInput) -> MSLPolicyResult:
        runtime_input = policy_input.runtime_input
        trade_plan = dict(policy_input.entry_result.evidence.get("trade_plan") or {})
        stoploss_price = _float_or_none(trade_plan.get("stoploss_price"))
        if stoploss_price is None:
            return MSLPolicyResult(
                policy_name=self.policy_name,
                evaluated_at=runtime_input.evaluated_at,
                status=PolicyStatus.UNAVAILABLE,
                applicable=True,
                reason="Legacy branch did not provide stoploss/MSL in the evaluated trade plan.",
                requirement_id="AB16-MSL",
                evidence={"adapter": type(self).__name__, "trade_plan": trade_plan},
            )
        return MSLPolicyResult(
            policy_name=self.policy_name,
            evaluated_at=runtime_input.evaluated_at,
            status=PolicyStatus.PASSED,
            applicable=True,
            reason="Legacy MSL/stoploss preserved from StrategyEvaluator trade plan.",
            requirement_id="AB16-MSL",
            formula=self._strategy_rule.stoploss_formula,
            calculated_value=stoploss_price,
            inputs={"entry_result": policy_input.entry_result.to_dict()},
            intermediate_values={"stoploss_price": stoploss_price},
            quality_status="VALID",
            evidence={"adapter": type(self).__name__, "trade_plan": trade_plan},
            stop_price=stoploss_price,
            direction=policy_input.product_result.direction,
            activation_timing="INITIAL",
            quantity=runtime_input.quantity,
        )


class S21MSLPolicyAdapter(LegacyOptionSellingMSLPolicyAdapter):
    policy_name = "legacy.s21.option_selling.msl"


class S23MSLPolicyAdapter(LegacyOptionSellingMSLPolicyAdapter):
    policy_name = "legacy.s23.option_selling.msl"


def _market_levels_from_runtime_input(values: Any) -> MarketLevels:
    data = dict(values or {})
    return MarketLevels(
        previous_month_high=_float_or_none(data.get("previous_month_high")),
        previous_month_low=_float_or_none(data.get("previous_month_low")),
        previous_week_high=_float_or_none(data.get("previous_week_high")),
        previous_week_low=_float_or_none(data.get("previous_week_low")),
        d2hh=_float_or_none(data.get("d2hh")),
        d2ll=_float_or_none(data.get("d2ll")),
        d3hh=_float_or_none(data.get("d3hh")),
        d3ll=_float_or_none(data.get("d3ll")),
        d4hh=_float_or_none(data.get("d4hh")),
        d4ll=_float_or_none(data.get("d4ll")),
        current_day_high=_float_or_none(data.get("current_day_high")),
        current_day_low=_float_or_none(data.get("current_day_low")),
    )


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _date_value(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value)
    return None


def _plain_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _plain_value(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain_value(item) for item in value]
    return value
