from __future__ import annotations

from dataclasses import replace
from datetime import time
from types import MappingProxyType
from typing import Any, Mapping

from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.adapters.legacy_policies.gap_missed_entry import S23_BACKTEST_LOW_POLICY_KEY
from tfis.adapters.legacy_policies.policies import S23MSLPolicyAdapter, S23TargetPolicyAdapter
from tfis.decision import GapPolicyResult, MSLPolicyInput, MissedEntryPolicyResult, PolicyStatus, TargetPolicyInput
from tfis.domain import MonthlyStatus
from tfis.domain.premarket_plan import PreMarketStrategyPlan
from tfis.premarket import (
    PreMarketPlanningContext,
    PreMarketStagePolicies,
    PreMarketStageResult,
    PreMarketStrategyPlanBuilder,
)


S23_PREMARKET_EVIDENCE_CLASSIFICATION = "LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT"
S23_PREMARKET_PLAN_ORPT = time(9, 19, 59)
S23_PREMARKET_PLAN_RC = time(9, 29, 59)


def build_s23_bull_call_premarket_plan() -> PreMarketStrategyPlan:
    return build_s23_call_side_premarket_plan(vertical.build_s23_bull_call_vertical_case())


def build_s23_bear_call_premarket_plan() -> PreMarketStrategyPlan:
    return build_s23_call_side_premarket_plan(vertical.build_s23_bear_call_vertical_case())


def build_s23_call_side_premarket_plan(
    case: vertical.S23VerticalSliceCase,
    *,
    planning_context: PreMarketPlanningContext | None = None,
    builder: PreMarketStrategyPlanBuilder | None = None,
) -> PreMarketStrategyPlan:
    context = planning_context or _planning_context(case)
    return (builder or PreMarketStrategyPlanBuilder()).build(
        case.runtime_input,
        _resolved_configuration(case),
        context,
        _stage_policies(case),
    )


def _stage_policies(case: vertical.S23VerticalSliceCase) -> PreMarketStagePolicies:
    return PreMarketStagePolicies(
        strategy_resolution=lambda context: _strategy_resolution(case, context),
        monthly_status_and_branch=lambda context: _monthly_status_and_branch(case, context),
        underlying_references=lambda context: _underlying_references(case, context),
        contract_selection=lambda context: _contract_selection(case, context),
        base_entry=lambda context: _base_entry(case, context),
        target=lambda context: _target(case, context),
        msl=lambda context: _msl(case, context),
        timing=lambda context: _timing(case, context),
    )


def _strategy_resolution(case: vertical.S23VerticalSliceCase, context: Mapping[str, Any]) -> PreMarketStageResult:
    result = vertical._strategy_resolution({"case": case})
    return _from_vertical_result(result)


def _monthly_status_and_branch(case: vertical.S23VerticalSliceCase, context: Mapping[str, Any]) -> PreMarketStageResult:
    result = vertical._monthly_status_and_branch({"case": case, "product_policy": context["product_policy"]})
    return _from_vertical_result(result)


def _underlying_references(case: vertical.S23VerticalSliceCase, context: Mapping[str, Any]) -> PreMarketStageResult:
    result = vertical._underlying_references({"case": case, "product_policy": context["product_policy"]})
    if result.status != "PASSED":
        return _from_vertical_result(result)
    trade_plan = result.payload["trade_plan"]
    payload = {
        **dict(result.payload),
        "underlying_references": {
            "market_structure": dict(case.runtime_input.market_structure_references),
            "trade_plan_references": {
                "start_strike": trade_plan["start_strike"],
                "end_strike": trade_plan["end_strike"],
                "ideal_premium": trade_plan["ideal_premium"],
                "minimum_premium": trade_plan["minimum_premium"],
            },
        },
        "reference_provenance": {
            "market_structure": "LEGACY_FIXTURE",
            "trade_plan_references": "WORKBOOK_NORMALIZED",
        },
    }
    return PreMarketStageResult(result.stage_name, result.status, payload, result.evidence, result.failure_code, result.reason)


def _contract_selection(case: vertical.S23VerticalSliceCase, context: Mapping[str, Any]) -> PreMarketStageResult:
    result = vertical._contract_selection({"case": case, "product_policy": context["product_policy"], "legacy_entry": context["legacy_entry"]})
    if result.status != "PASSED":
        return _from_vertical_result(result)
    selected = result.payload["selected_contract"]
    trade_plan = context["trade_plan"]
    payload = {
        **dict(result.payload),
        "expiry_candidates": (selected.expiry,),
        "strike_candidates": (float(trade_plan["start_strike"]), float(trade_plan["end_strike"]), float(selected.strike)),
        "oi_unit": "LOTS",
    }
    return PreMarketStageResult(result.stage_name, result.status, payload, result.evidence, result.failure_code, result.reason)


def _base_entry(case: vertical.S23VerticalSliceCase, context: Mapping[str, Any]) -> PreMarketStageResult:
    result = vertical._base_entry(
        {
            "case": case,
            "selected_contract": context["selected_contract"],
            "legacy_entry": context["legacy_entry"],
        }
    )
    if result.status != "PASSED":
        return _from_vertical_result(result)
    selected = context["selected_contract"]
    payload = {
        **dict(result.payload),
        "selected_contract_references": {
            "legacy_entry_value": context["legacy_entry"].entry_value,
            "final_strike": selected.strike,
            "selected_contract_symbol": selected.symbol,
            "selected_contract_premium": selected.metadata.get("ltp"),
            "selected_contract_oi": selected.metadata.get("oi"),
        },
        "entry_policy_identity": vertical.S23VerticalEntryPolicy.policy_key,
    }
    return PreMarketStageResult(result.stage_name, result.status, payload, result.evidence, result.failure_code, result.reason)


def _target(case: vertical.S23VerticalSliceCase, context: Mapping[str, Any]) -> PreMarketStageResult:
    gap, missed = _pre_market_gap_placeholders(case)
    result = S23TargetPolicyAdapter(case.strategy_rule).evaluate(
        TargetPolicyInput(
            case.runtime_input,
            context["product_policy"],
            context["legacy_entry"],
            gap,
            missed,
            context["contract_selection"],
        )
    )
    if result.status is not PolicyStatus.PASSED:
        return PreMarketStageResult("target", "BLOCKED", {"target": result}, failure_code="TARGET_ADAPTER_FAILURE", reason=result.reason)
    return PreMarketStageResult("target", "PASSED", {"target": result, "pre_market_gap_policy": gap, "pre_market_missed_entry_policy": missed})


def _msl(case: vertical.S23VerticalSliceCase, context: Mapping[str, Any]) -> PreMarketStageResult:
    gap, missed = _pre_market_gap_placeholders(case)
    result = S23MSLPolicyAdapter(case.strategy_rule).evaluate(
        MSLPolicyInput(
            case.runtime_input,
            context["product_policy"],
            context["legacy_entry"],
            gap,
            missed,
            context["contract_selection"],
            context["target"],
        )
    )
    if result.status is not PolicyStatus.PASSED:
        return PreMarketStageResult("msl", "BLOCKED", {"msl": result}, failure_code="MSL_ADAPTER_FAILURE", reason=result.reason)
    return PreMarketStageResult("msl", "PASSED", {"msl": result})


def _timing(case: vertical.S23VerticalSliceCase, context: Mapping[str, Any]) -> PreMarketStageResult:
    return PreMarketStageResult(
        "timing",
        "PASSED",
        {
            "normal_orpt": S23_PREMARKET_PLAN_ORPT,
            "rc_time": S23_PREMARKET_PLAN_RC,
            "gap_missed_entry_policy_identity": S23_BACKTEST_LOW_POLICY_KEY,
            "execution_risk_policy_identity": "OFFLINE_PREMARKET_NO_EXECUTION",
        },
        evidence={
            "orpt": S23_PREMARKET_PLAN_ORPT.isoformat(),
            "rc_time": S23_PREMARKET_PLAN_RC.isoformat(),
            "source": "S23 fixture timing policy",
        },
    )


def _pre_market_gap_placeholders(case: vertical.S23VerticalSliceCase) -> tuple[GapPolicyResult, MissedEntryPolicyResult]:
    return (
        GapPolicyResult("premarket.gap.not_evaluated", case.runtime_input.evaluated_at, PolicyStatus.NOT_APPLICABLE, False, "Current-session gap is not evaluated pre-market."),
        MissedEntryPolicyResult("premarket.missed_entry.not_evaluated", case.runtime_input.evaluated_at, PolicyStatus.NOT_APPLICABLE, False, "Current-session missed-entry is not evaluated pre-market.", missed=False),
    )


def _planning_context(case: vertical.S23VerticalSliceCase) -> PreMarketPlanningContext:
    return PreMarketPlanningContext(
        underlying_instrument=f"NSE:{case.strategy_rule.symbol}",
        expected_configuration_hash=case.runtime_input.resolved_configuration_hash,
        evidence_classification=S23_PREMARKET_EVIDENCE_CLASSIFICATION,
        derived_fields=("plan_id", "plan_hash", "business_hash", "strike_candidates"),
        supplemented_fields=(
            "single qualifying option-chain candidate",
            "offline ORPT/RC fixture timing",
            "selected-contract historical references from fixture trade plan",
        ),
        field_provenance=_field_provenance(),
    )


def _resolved_configuration(case: vertical.S23VerticalSliceCase) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "strategy_code": case.strategy_rule.strategy_code,
            "strategy_definition": case.runtime_input.strategy_definition_id,
            "strategy_branch": case.strategy_rule.unique_code,
            "configuration_hash": case.runtime_input.resolved_configuration_hash,
            "minimum_oi": case.strategy_rule.minimum_oi,
            "entry_formula": case.strategy_rule.entry_formula,
            "target_formula": case.strategy_rule.target_formula,
            "stoploss_formula": case.strategy_rule.stoploss_formula,
            "evidence_classification": S23_PREMARKET_EVIDENCE_CLASSIFICATION,
        }
    )


def _field_provenance() -> Mapping[str, str]:
    return MappingProxyType(
        {
            "strategy_identity": "LEGACY_CONFIG",
            "resolved_configuration_hash": "DERIVED",
            "monthly_status": "LEGACY_FIXTURE",
            "resolved_branch": "WORKBOOK_NORMALIZED",
            "underlying_historical_references": "LEGACY_FIXTURE",
            "expiry_candidates": "SYNTHETIC_SUPPLEMENT",
            "strike_candidates": "DERIVED",
            "selected_contract": "SYNTHETIC_SUPPLEMENT",
            "selected_contract_historical_references": "SYNTHETIC_SUPPLEMENT",
            "base_entry": "WORKBOOK_NORMALIZED",
            "preliminary_target": "WORKBOOK_NORMALIZED",
            "preliminary_msl": "WORKBOOK_NORMALIZED",
            "normal_orpt": "SYNTHETIC_SUPPLEMENT",
            "rc_time": "SYNTHETIC_SUPPLEMENT",
            "policy_identities": "DERIVED",
        }
    )


def _from_vertical_result(result: Any) -> PreMarketStageResult:
    return PreMarketStageResult(result.stage_name, result.status, result.payload, result.evidence, result.failure_code, result.reason)
