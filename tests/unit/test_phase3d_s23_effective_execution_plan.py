from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies import s23_call_captured_evidence as m5
from tfis.adapters.legacy_policies import s23_effective_execution_plan as execution_plan
from tfis.adapters.legacy_policies import s23_opening_context as opening
from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.domain import (
    BusinessEngineStatus,
    EffectiveExecutionPath,
    EffectiveExecutionPlanStatus,
    EffectiveRiskValueStatus,
    EntryDownstreamPermission,
    OpeningContextStatus,
)
from tfis.execution_plan import EffectiveExecutionPlanComposer, EffectiveExecutionPolicies


BULL_M3_HASH = "4d2e514f05f873c17b7077ce6710c559dac54422ed6898cbb51e6ed9bbb24b84"
BULL_M5_HASH = "4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c"
BEAR_M5_HASH = "3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41"
BULL_M9_PLAN_HASH = "873a7662f321b70af350a5d3b2e0b9fccf72852ae0bfc88e4471faca4cd91f22"
BEAR_M9_PLAN_HASH = "cfb09a5b41ee667a045e89d36cf4167dfe3acb46630bf76dd03e16f51e3e576b"
BULL_M10_CONTEXT_HASH = "cd49e501b4470dc278724c0abf8dc54b32f2ea0befb3d3c3576cf2a0e91bd38a"
BEAR_M10_CONTEXT_HASH = "7590f983c4fb7ee5087a7e8909d81a7feb9713c9903fdd778f556ece9f34875e"


def test_bull_normal_retains_premarket_values_and_orpt() -> None:
    plan = execution_plan.build_s23_bull_normal_execution_plan()

    assert plan.plan_status is EffectiveExecutionPlanStatus.READY_OFFLINE
    assert plan.path_classification is EffectiveExecutionPath.NORMAL_RETAINED
    assert plan.values.base_entry == plan.values.effective_entry == 203.5
    assert plan.values.preliminary_target == plan.values.effective_target == 81.4
    assert plan.values.preliminary_msl == plan.values.effective_msl == 321.0
    assert plan.values.revised_authorized_time.isoformat() == "09:19:59"
    assert plan.values.target_status is EffectiveRiskValueStatus.RETAINED_FROM_PREMARKET
    assert plan.values.msl_status is EffectiveRiskValueStatus.RETAINED_FROM_PREMARKET
    assert plan.downstream_execution_permission == "NONE"
    assert plan.runtime_authority == "NONE"
    assert plan.lifecycle_action == "NONE"
    assert plan.offline_execution_candidate is True
    assert plan.gap_missed_entry_applicability == "NOT_APPLICABLE"


def test_bear_normal_retains_premarket_values_and_orpt() -> None:
    plan = execution_plan.build_s23_bear_normal_execution_plan()

    assert plan.plan_status is EffectiveExecutionPlanStatus.READY_OFFLINE
    assert plan.path_classification is EffectiveExecutionPath.NORMAL_RETAINED
    assert plan.values.base_entry == plan.values.effective_entry == 194.25
    assert plan.values.preliminary_target == plan.values.effective_target == 77.7
    assert plan.values.preliminary_msl == plan.values.effective_msl == 310.8
    assert plan.values.revised_authorized_time.isoformat() == "09:19:59"
    assert plan.downstream_execution_permission == "NONE"


@pytest.mark.parametrize(
    "builder",
    (
        execution_plan.build_s23_bull_gap_execution_plan,
        execution_plan.build_s23_bear_gap_execution_plan,
    ),
)
def test_gap_path_recalculates_effective_entry_target_msl_and_authorized_time(builder) -> None:
    plan = builder()

    assert plan.plan_status is EffectiveExecutionPlanStatus.READY_OFFLINE
    assert plan.path_classification is EffectiveExecutionPath.GAP_RECALCULATED
    assert plan.values.effective_entry != plan.values.base_entry
    assert plan.values.effective_target != plan.values.preliminary_target
    assert plan.values.effective_msl != plan.values.preliminary_msl
    assert plan.values.target_status is EffectiveRiskValueStatus.RECALCULATED
    assert plan.values.msl_status is EffectiveRiskValueStatus.RECALCULATED
    assert plan.values.revised_authorized_time.isoformat() == "09:29:59"
    assert plan.supersedes_plan_id == plan.source_premarket_plan_id
    assert plan.recalculation_required is True
    assert plan.recalculation_output["recalculated_entry_price"]
    assert plan.downstream_execution_permission == "NONE"


def test_partial_real_context_blocks_honestly_without_fabricated_evidence() -> None:
    plan = execution_plan.build_s23_partial_real_execution_plan()

    assert plan.plan_status is EffectiveExecutionPlanStatus.INSUFFICIENT_EVIDENCE
    assert plan.path_classification is EffectiveExecutionPath.BLOCKED_OPENING_VALIDATION
    assert plan.block_code == "INSUFFICIENT_OPENING_EVIDENCE"
    assert "orpt_observation" in plan.missing_fields
    assert "selected_contract_opening.oi" in plan.missing_fields
    assert plan.source_opening_context_id == "m10-s23-partial-real-opening-context"
    assert plan.offline_execution_candidate is False
    assert plan.downstream_execution_permission == "NONE"


def test_same_generic_composer_serves_bull_and_bear(monkeypatch) -> None:
    calls: list[str] = []
    original = EffectiveExecutionPlanComposer.compose

    def observe(self, premarket_plan, opening_context, policies, **kwargs):
        calls.append(type(self).__name__)
        return original(self, premarket_plan, opening_context, policies, **kwargs)

    monkeypatch.setattr(EffectiveExecutionPlanComposer, "compose", observe)

    execution_plan.build_s23_bull_normal_execution_plan()
    execution_plan.build_s23_bear_normal_execution_plan()

    assert calls == ["EffectiveExecutionPlanComposer", "EffectiveExecutionPlanComposer"]


def test_plan_context_hash_mismatch_blocks_before_business_evaluation() -> None:
    case = vertical.build_s23_bull_call_vertical_case()
    plan = premarket.build_s23_call_side_premarket_plan(case)
    context = replace(opening.build_s23_bull_call_opening_context(), source_plan_hash="different", context_hash="")

    result = execution_plan._compose(case, context, plan=plan)

    assert result.plan_status is EffectiveExecutionPlanStatus.BLOCKED
    assert result.block_code == "PLAN_CONTEXT_HASH_MISMATCH"
    assert result.offline_execution_candidate is False


def test_missing_plan_and_context_fail_closed() -> None:
    composer = EffectiveExecutionPlanComposer()
    policies = _policies()

    assert composer.compose(None, opening.build_s23_bull_call_opening_context(), policies).block_code == "MISSING_PLAN"
    assert composer.compose(premarket.build_s23_bull_call_premarket_plan(), None, policies).block_code == "MISSING_CONTEXT"


def test_entry_target_msl_and_timing_policy_failures_block(monkeypatch) -> None:
    plan = premarket.build_s23_bull_call_premarket_plan()
    context = execution_plan._normal_context("bull")
    composer = EffectiveExecutionPlanComposer()

    blocked_entry = composer.compose(plan, context, replace(_policies(), entry_finalizer=lambda p, c, g: _blocked_entry()))
    blocked_target = composer.compose(plan, context, replace(_policies(), target_policy=lambda p, c, g, e: {"status": "BLOCKED", "reason": "RULE_AUTHORITY_UNRESOLVED"}))
    blocked_msl = composer.compose(plan, context, replace(_policies(), msl_policy=lambda p, c, g, e, t: {"status": "BLOCKED", "reason": "RULE_AUTHORITY_UNRESOLVED"}))
    blocked_timing = composer.compose(plan, context, replace(_policies(), timing_policy=lambda p, c, g: {"authorized_time": None}))

    assert blocked_entry.block_code == "ENTRY_FINALIZATION_FAILED"
    assert blocked_target.block_code == "TARGET_POLICY_FAILURE"
    assert blocked_msl.block_code == "MSL_POLICY_FAILURE"
    assert blocked_timing.block_code == "INVALID_AUTHORIZED_TIME"
    assert {blocked_entry.offline_execution_candidate, blocked_target.offline_execution_candidate, blocked_msl.offline_execution_candidate, blocked_timing.offline_execution_candidate} == {False}


def test_immutable_deterministic_and_material_change_changes_hash() -> None:
    first = execution_plan.build_s23_bull_normal_execution_plan()
    second = execution_plan.build_s23_bull_normal_execution_plan()
    changed = replace(first, values=replace(first.values, effective_entry=first.values.effective_entry + 1), execution_plan_hash="")

    assert first.execution_plan_hash == second.execution_plan_hash
    assert first._business_payload() == second._business_payload()
    assert first.execution_plan_hash != changed.execution_plan_hash
    with pytest.raises(FrozenInstanceError):
        first.plan_status = EffectiveExecutionPlanStatus.BLOCKED


def test_performance_diagnostics_do_not_enter_hash() -> None:
    plan = execution_plan.build_s23_bull_normal_execution_plan()
    changed = replace(plan, performance={"composition_seconds": 999.0}, execution_plan_hash="")

    assert plan.execution_plan_hash == changed.execution_plan_hash


def test_multiple_strategy_instance_isolation() -> None:
    plan_a = premarket.build_s23_bull_call_premarket_plan()
    plan_b = replace(plan_a, plan_id=f"{plan_a.plan_id}:account-b", strategy_instance_id="S23_NIFTY_ACCOUNT_B_PAPER", business_hash="account-b-plan", plan_hash="account-b-plan")
    context_a = execution_plan._normal_context("bull")
    context_b = replace(context_a, context_id="m11-account-b-context", source_plan_id=plan_b.plan_id, source_plan_hash=plan_b.plan_hash, context_hash="")
    bad_context_b = replace(context_b, source_plan_hash="wrong", context_hash="")

    ready_a = execution_plan._compose(vertical.build_s23_bull_call_vertical_case(), context_a, plan=plan_a)
    ready_b = execution_plan._compose(vertical.build_s23_bull_call_vertical_case(), context_b, plan=plan_b)
    blocked_b = execution_plan._compose(vertical.build_s23_bull_call_vertical_case(), bad_context_b, plan=plan_b)

    assert ready_a.plan_status is EffectiveExecutionPlanStatus.READY_OFFLINE
    assert ready_b.plan_status is EffectiveExecutionPlanStatus.READY_OFFLINE
    assert blocked_b.plan_status is EffectiveExecutionPlanStatus.BLOCKED
    assert ready_a.strategy_instance_id != ready_b.strategy_instance_id
    assert ready_a.execution_plan_hash != ready_b.execution_plan_hash
    assert blocked_b.block_code == "PLAN_CONTEXT_HASH_MISMATCH"


def test_generic_composer_has_no_runtime_or_strategy_branching_dependencies() -> None:
    source = Path("src/tfis/execution_plan/composer.py").read_text(encoding="utf-8")

    assert "S23" not in source
    assert "S21" not in source
    assert "strategy_code ==" not in source
    assert "tfis.paper" not in source
    assert "broker" not in source.lower()
    assert "place_order" not in source
    assert "scheduler" not in source.lower()
    assert "event_bus" not in source
    assert "thread" not in source.lower()
    assert "write_text" not in source
    assert "open(" not in source
    assert "eval(" not in source
    assert "exec(" not in source


def test_existing_m3_m10_hashes_remain_unchanged() -> None:
    assert premarket.build_s23_bull_call_premarket_plan().plan_hash == BULL_M9_PLAN_HASH
    assert premarket.build_s23_bear_call_premarket_plan().plan_hash == BEAR_M9_PLAN_HASH
    assert opening.build_s23_bull_call_opening_context().context_hash == BULL_M10_CONTEXT_HASH
    assert opening.build_s23_bear_call_opening_context().context_hash == BEAR_M10_CONTEXT_HASH
    assert vertical.run_s23_bull_call_vertical_slice().deterministic_hash == BULL_M3_HASH
    assert m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture").deterministic_hash == BULL_M5_HASH
    assert m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture").deterministic_hash == BEAR_M5_HASH


def _policies() -> EffectiveExecutionPolicies:
    case = vertical.build_s23_bull_call_vertical_case()
    return EffectiveExecutionPolicies(
        gap_missed_entry=lambda p, c: execution_plan._gme(case, p, c, force_missed=False),
        entry_finalizer=lambda p, c, g: execution_plan._entry(case, p, g),
        target_policy=lambda p, c, g, e: execution_plan._target(case, p, g, e),
        msl_policy=lambda p, c, g, e, t: execution_plan._msl(case, p, g, e),
        timing_policy=lambda p, c, g: execution_plan._timing(p, g),
    )


def _blocked_entry():
    result = execution_plan._entry(vertical.build_s23_bull_call_vertical_case(), premarket.build_s23_bull_call_premarket_plan(), None)
    return replace(result, status=BusinessEngineStatus.BLOCKED, downstream_permission=EntryDownstreamPermission.BLOCKED)
