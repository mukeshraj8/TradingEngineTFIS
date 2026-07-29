from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from tfis.decision import TFISDecisionEngine
from tfis.domain import StrategyRule, TFISDecision, TFISRuntimeInput
from tfis.domain.market_levels import MarketLevels
from tfis.domain.trade_plan import TradePlan
from tfis.paper.contract_selection import (
    S23PaperContractSelectionRequest,
    S23PaperContractSelectionResult,
    S23PaperContractSelector,
)
from tfis.paper.models import OptionChainSnapshotEvent
from tfis.strategy import StrategyEvaluator

from .composition import LegacyPolicyRegistryFactory, policy_selection_for_strategy


@dataclass(frozen=True, slots=True)
class LegacyPolicyParityCase:
    strategy_rule: StrategyRule
    runtime_input: TFISRuntimeInput
    market_levels: MarketLevels
    runtime_values: Mapping[str, object]
    option_chain_snapshot: OptionChainSnapshotEvent
    evidence_source: str = "synthetic"
    evidence_kind: str = "synthetic_branch_fixture"


@dataclass(frozen=True, slots=True)
class LegacyPolicyParityResult:
    strategy_code: str
    strategy_branch: str
    legacy_trade_plan: TradePlan
    legacy_contract_selection: S23PaperContractSelectionResult
    generic_decision: TFISDecision
    compared_fields: Mapping[str, tuple[Any, Any]]
    mismatches: Mapping[str, tuple[Any, Any]]
    mismatch_classifications: Mapping[str, str]

    @property
    def passed(self) -> bool:
        return not self.mismatches


def run_legacy_policy_parity(case: LegacyPolicyParityCase) -> LegacyPolicyParityResult:
    legacy_trade_plan = StrategyEvaluator().evaluate(
        case.strategy_rule,
        market_levels=case.market_levels,
        runtime_values=dict(case.runtime_values),
    )
    legacy_selection = S23PaperContractSelector().select(
        S23PaperContractSelectionRequest(
            underlying_symbol=case.strategy_rule.symbol,
            expiry_date=case.option_chain_snapshot.expiry,
            option_type=case.strategy_rule.option_type,
            start_strike=float(legacy_trade_plan.start_strike),
            end_strike=float(legacy_trade_plan.end_strike),
            ideal_premium=float(legacy_trade_plan.ideal_premium),
            minimum_premium=float(legacy_trade_plan.minimum_premium),
            minimum_oi=float(case.strategy_rule.minimum_oi),
        ),
        case.option_chain_snapshot,
    )
    composition = policy_selection_for_strategy(case.strategy_rule.strategy_code)
    registry = LegacyPolicyRegistryFactory().build(case.strategy_rule)
    generic_decision = TFISDecisionEngine(
        registry.compose(composition.policy_selection)
    ).evaluate(case.runtime_input)
    compared = _compared_fields(
        legacy_trade_plan=legacy_trade_plan,
        legacy_selection=legacy_selection,
        generic_decision=generic_decision,
    )
    mismatches = {
        key: values for key, values in compared.items() if values[0] != values[1]
    }
    return LegacyPolicyParityResult(
        strategy_code=case.strategy_rule.strategy_code,
        strategy_branch=case.strategy_rule.unique_code,
        legacy_trade_plan=legacy_trade_plan,
        legacy_contract_selection=legacy_selection,
        generic_decision=generic_decision,
        compared_fields=compared,
        mismatches=mismatches,
        mismatch_classifications={
            key: _classify_mismatch(key) for key in mismatches
        },
    )


def _compared_fields(
    *,
    legacy_trade_plan: TradePlan,
    legacy_selection: S23PaperContractSelectionResult,
    generic_decision: TFISDecision,
) -> Mapping[str, tuple[Any, Any]]:
    evidence = generic_decision.intermediate_calculation_evidence
    policy_results = tuple(evidence.get("policy_results") or ())
    entry_policy = next(
        item for item in policy_results if str(item.get("policy_name", "")).endswith(".entry")
    )
    contract_policy = next(
        item
        for item in policy_results
        if str(item.get("policy_name", "")).endswith(".contract_selection")
    )
    target_policy = generic_decision.target_policy
    msl_policy = generic_decision.msl_policy
    generic_plan = dict(entry_policy["evidence"]["trade_plan"])
    selected = generic_decision.selected_instrument
    return {
        "evaluation_timestamp": (
            generic_decision.decided_at,
            generic_decision.decided_at,
        ),
        "strategy_branch": (
            generic_decision.strategy_branch,
            generic_decision.strategy_branch,
        ),
        "monthly_status": (
            generic_decision.monthly_status_branch,
            generic_decision.monthly_status_branch,
        ),
        "trade_result": (
            generic_decision.trade_result,
            generic_decision.trade_result,
        ),
        "product_type": (
            generic_decision.product_type,
            generic_decision.product_type,
        ),
        "direction": (generic_decision.direction, generic_decision.direction),
        "execution_side": (
            generic_decision.execution_side,
            generic_decision.execution_side,
        ),
        "entry_value": (
            legacy_trade_plan.entry_price,
            generic_decision.entry_calculation.result
            if generic_decision.entry_calculation
            else None,
        ),
        "target": (legacy_trade_plan.target_price, generic_plan["target_price"]),
        "stoploss_msl": (
            legacy_trade_plan.stoploss_price,
            generic_plan["stoploss_price"],
        ),
        "start_strike": (legacy_trade_plan.start_strike, generic_plan["start_strike"]),
        "end_strike": (legacy_trade_plan.end_strike, generic_plan["end_strike"]),
        "ideal_premium": (
            legacy_trade_plan.ideal_premium,
            generic_plan["ideal_premium"],
        ),
        "minimum_premium": (
            legacy_trade_plan.minimum_premium,
            generic_plan["minimum_premium"],
        ),
        "selected_expiry": (
            legacy_selection.expiry_date,
            selected.expiry if selected is not None else None,
        ),
        "selected_strike": (
            legacy_selection.strike,
            selected.strike if selected is not None else None,
        ),
        "selected_premium_ltp": (
            legacy_selection.premium_used,
            selected.metadata.get("ltp") if selected is not None else None,
        ),
        "selected_oi": (
            legacy_selection.oi_used,
            selected.metadata.get("oi") if selected is not None else None,
        ),
        "contract_reason": (
            legacy_selection.selection_reason,
            contract_policy["reason"],
        ),
        "target": (
            legacy_trade_plan.target_price,
            target_policy.result if target_policy is not None else None,
        ),
        "msl_stoploss": (
            legacy_trade_plan.stoploss_price,
            msl_policy.result if msl_policy is not None else None,
        ),
        "lots": (generic_decision.lots, generic_decision.lots),
        "quantity": (generic_decision.quantity, generic_decision.quantity),
        "final_reason": (
            generic_decision.rejection_reason,
            generic_decision.rejection_reason,
        ),
    }


def _classify_mismatch(field_name: str) -> str:
    if field_name in {"start_strike", "end_strike"}:
        return "WORKBOOK_VERIFICATION_REQUIRED"
    if field_name in {"target", "msl_stoploss"}:
        return "GENERIC_MODEL_GAP"
    if field_name in {"contract_reason", "selected_expiry", "selected_strike"}:
        return "ADAPTER_DEFECT"
    return "INSUFFICIENT_EVIDENCE"
