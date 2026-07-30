from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from tfis.adapters.legacy_policies import s23_opening_context as opening
from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.adapters.legacy_policies.gap_missed_entry import (
    LegacyGapMissedEntryEvaluationInput,
    S23_BACKTEST_LOW_POLICY_KEY,
    evaluate_legacy_gap_missed_entry,
)
from tfis.domain import BusinessEngineStatus, EntryPolicyOutcome, EntrySource, EntryStatus, OptionType
from tfis.domain.effective_execution_plan import EffectiveExecutionPlan
from tfis.domain.gap_missed_entry import MissedEntryObservationSource, ObservationValue, SessionTimingEvidence, TimingObservationRequirement, TimingWindowState
from tfis.domain.opening_market_context import OpeningGapClassification, OpeningGapDirection
from tfis.entry import EntryEngine
from tfis.execution_plan import EffectiveExecutionPlanComposer, EffectiveExecutionPolicies
from tfis.strategy import StrategyEvaluator
from tfis.strategy.s23_recalculation import IntradaySnapshot


def build_s23_bull_normal_execution_plan() -> EffectiveExecutionPlan:
    case = vertical.build_s23_bull_call_vertical_case()
    return _compose(case, _normal_context("bull"))


def build_s23_bear_normal_execution_plan() -> EffectiveExecutionPlan:
    case = vertical.build_s23_bear_call_vertical_case()
    return _compose(case, _normal_context("bear"))


def build_s23_bull_gap_execution_plan() -> EffectiveExecutionPlan:
    case = vertical.build_s23_bull_call_vertical_case()
    return _compose(case, opening.build_s23_bull_call_opening_context(), force_missed=True)


def build_s23_bear_gap_execution_plan() -> EffectiveExecutionPlan:
    case = vertical.build_s23_bear_call_vertical_case()
    return _compose(case, opening.build_s23_bear_call_opening_context(), force_missed=True)


def build_s23_partial_real_execution_plan() -> EffectiveExecutionPlan:
    case = vertical.build_s23_bull_call_vertical_case()
    context = opening.build_s23_partial_real_opening_context()
    selected = context.selected_contract
    plan = opening._replace_plan_selected_contract_for_partial_real(
        premarket.build_s23_call_side_premarket_plan(case),
        selected,
        context.trading_date,
        context.source_plan_hash,
    )
    return _compose(case, context, plan=plan)


def _compose(case: vertical.S23VerticalSliceCase, context, *, force_missed: bool = False, plan=None) -> EffectiveExecutionPlan:
    plan = plan or premarket.build_s23_call_side_premarket_plan(case)
    policies = EffectiveExecutionPolicies(
        gap_missed_entry=lambda p, c: _gme(case, p, c, force_missed=force_missed),
        entry_finalizer=lambda p, c, g: _entry(case, p, g),
        target_policy=lambda p, c, g, e: _target(case, p, g, e),
        msl_policy=lambda p, c, g, e, t: _msl(case, p, g, e),
        timing_policy=lambda p, c, g: _timing(p, g),
    )
    return EffectiveExecutionPlanComposer().compose(plan, context, policies, supersedes_plan_id=plan.plan_id if force_missed else None)


def _normal_context(branch: str):
    base = opening.build_s23_bull_call_opening_context() if branch == "bull" else opening.build_s23_bear_call_opening_context()
    return replace(
        base,
        gap_context=replace(
            base.gap_context,
            classification=OpeningGapClassification.NO_GAP,
            direction=OpeningGapDirection.NONE,
            gap_amount=0.0,
            gap_percentage=0.0,
        ),
        context_hash="",
    )


class S23ExecutionEntryPolicy(vertical.S23VerticalEntryPolicy):
    policy_key = "legacy.s23.execution_plan.entry"

    def finalize_effective(self, engine_input, base_candidate, gap_missed_entry_result):
        outcome = super().finalize_effective(engine_input, base_candidate, gap_missed_entry_result)
        recalc = getattr(gap_missed_entry_result, "recalculation", None)
        value = None
        if recalc is not None:
            value = recalc.compatibility_outputs.get("recalculated_entry_price")
        if value is None or outcome.effective_trigger is None:
            return outcome
        effective = replace(
            outcome.effective_trigger,
            value=Decimal(str(value)),
            status=EntryStatus.EFFECTIVE_ENTRY_RECALCULATED,
            source=EntrySource.GAP_MISSED_ENTRY_RECALCULATION,
            provenance={"adapter": type(self).__name__, "source": "Phase 3C compatibility output"},
        )
        return EntryPolicyOutcome(status=EntryStatus.EFFECTIVE_ENTRY_RECALCULATED, base_candidate=base_candidate, effective_trigger=effective)


def _entry(case, plan, gme):
    selected = plan.contract_resolution.selected_contract
    context = {"case": case}
    context.update(vertical._strategy_resolution(context).payload)
    context.update(vertical._monthly_status_and_branch(context).payload)
    context.update(vertical._underlying_references(context).payload)
    legacy_entry = context["legacy_entry"]
    engine_input = replace(
        vertical._entry_input(case, selected, legacy_entry, gme),
        entry_policy_key=S23ExecutionEntryPolicy.policy_key,
        gap_missed_entry_required=gme is not None,
    )
    return EntryEngine({S23ExecutionEntryPolicy.policy_key: S23ExecutionEntryPolicy()}).execute(engine_input)


def _gme(case, plan, context, *, force_missed: bool):
    ts = datetime.combine(plan.trading_date, plan.planned_values.rc_time, tzinfo=ZoneInfo("Asia/Kolkata"))
    option_low = 1.0 if force_missed else float(plan.planned_values.base_entry) + 10.0
    timing = SessionTimingEvidence(
        "Asia/Kolkata",
        ts.replace(hour=9, minute=15, second=0),
        ts,
        ts.replace(hour=plan.planned_values.normal_orpt.hour, minute=plan.planned_values.normal_orpt.minute, second=plan.planned_values.normal_orpt.second),
        ts,
        TimingWindowState.AVAILABLE,
        TimingObservationRequirement.REQUIRED,
        TimingObservationRequirement.REQUIRED,
        ts.replace(hour=plan.planned_values.normal_orpt.hour, minute=plan.planned_values.normal_orpt.minute, second=plan.planned_values.normal_orpt.second),
        ts,
        ObservationValue(MissedEntryObservationSource.OPTION_LOW, Decimal(str(option_low)), ts),
        ObservationValue(MissedEntryObservationSource.OPTION_LOW, Decimal(str(option_low + 2)), ts),
    )
    trade_plan = StrategyEvaluator().evaluate(case.strategy_rule, market_levels=case.market_levels, runtime_values=case.runtime_values)
    return evaluate_legacy_gap_missed_entry(
        LegacyGapMissedEntryEvaluationInput(
            "S23",
            case.runtime_input.strategy_definition_id or case.strategy_rule.unique_code,
            "1.0.0",
            case.runtime_input.strategy_instance_id or "S23_NIFTY_ACCOUNT_A_PAPER",
            plan.product,
            plan.resolved_configuration_hash,
            case.branch_key,
            OptionType.CALL,
            plan.monthly_status,
            timing,
            plan.planned_values.base_entry,
            market_levels=case.market_levels,
            option_levels=case.runtime_values["OPT_LEVELS"],
            strategy_parameters=case.strategy_rule.parameters or {},
            base_trade_plan=trade_plan,
            orpt_snapshot=IntradaySnapshot(timestamp=ts, spot_low=22100.0, spot_high=22400.0, option_low=option_low, option_high=option_low + 20),
            rc_snapshot=IntradaySnapshot(timestamp=ts, spot_low=22120.0, spot_high=22420.0, option_low=option_low + 2, option_high=option_low + 22),
            provenance={"source": "phase3d_m11_execution_plan"},
        ),
        policy_key=S23_BACKTEST_LOW_POLICY_KEY,
    )


def _target(case, plan, gme, entry):
    if gme is not None and gme.recalculation.status.value == "COMPLETED_BY_COMPATIBILITY_POLICY":
        value = round(float(entry.effective_entry.value) * (1 - float(case.strategy_rule.parameters["target_pct"]) / 100.0), 2)
        return {"status": "PASSED", "value": value, "recalculated": True, "reason": "S23 target recalculated from effective entry by accepted target percentage."}
    return {"status": "PASSED", "value": plan.planned_values.preliminary_target, "recalculated": False, "reason": "Target retained from pre-market plan."}


def _msl(case, plan, gme, entry):
    if gme is not None and gme.recalculation.status.value == "COMPLETED_BY_COMPATIBILITY_POLICY":
        entry_sl = float(entry.effective_entry.value) * (1 + float(case.strategy_rule.parameters["sl_entry_pct"]) / 100.0)
        value = round(min(entry_sl, plan.planned_values.preliminary_msl), 2)
        return {"status": "PASSED", "value": value, "recalculated": True, "reason": "S23 MSL recalculated with bounded existing S23 rule authority."}
    return {"status": "PASSED", "value": plan.planned_values.preliminary_msl, "recalculated": False, "reason": "MSL retained from pre-market plan."}


def _timing(plan, gme):
    if gme is not None and gme.recalculation.status.value == "COMPLETED_BY_COMPATIBILITY_POLICY":
        return {"authorized_time": plan.planned_values.rc_time, "order_type": "LIMIT", "reason": "Recalculated path authorized at RC time."}
    return {"authorized_time": plan.planned_values.normal_orpt, "order_type": "LIMIT", "reason": "Retained path authorized at normal ORPT."}
