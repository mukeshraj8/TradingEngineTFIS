from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies import s23_position_lifecycle as lifecycle
from tfis.adapters.legacy_policies import s23_trading_day_coordination as coordination
from tfis.domain import (
    LifecycleActionRequirement,
    LifecycleEconomicGapEffect,
    LifecycleOpeningStatus,
    PositionReconciliationStatus,
)
from tfis.lifecycle import PositionLifecycleBuildInput, PositionLifecycleContextBuilder


M12_CARRIED_HASH = "bd4f5361c703d93c35ce1be3c93cf893c8270bd67e81ba42784ed3819b56dcde"


def test_bull_carried_normal_context_and_handoff_are_offline_only() -> None:
    fixture = lifecycle.build_s23_bull_carried_normal_lifecycle()

    assert fixture.trading_day_coordination_hash == M12_CARRIED_HASH
    assert fixture.context.opening_status is LifecycleOpeningStatus.NORMAL_OPENING_CONTINUATION
    assert fixture.context.action_requirement is LifecycleActionRequirement.NORMAL_SL_PLACEMENT_REQUIRED
    assert fixture.context.gap_observation.direction.value == "NONE"
    assert fixture.context.gap_observation.economic_effect is LifecycleEconomicGapEffect.NEUTRAL
    assert fixture.context.level_observation.any_level_crossed is False
    assert fixture.handoff.broker_mutation_permitted is False
    assert fixture.handoff.paper_mutation_permitted is False
    assert fixture.handoff.live_mutation_permitted is False
    assert fixture.handoff.order_modification_permitted is False
    assert fixture.handoff.order_cancellation_permitted is False
    assert fixture.handoff.square_off_permitted is False
    assert fixture.handoff.position_mutation_permitted is False


def test_bull_carried_gap_observations_use_position_economics() -> None:
    adverse = lifecycle.build_s23_bull_carried_adverse_gap_lifecycle()
    favorable = lifecycle.build_s23_bull_carried_favorable_gap_lifecycle()

    assert adverse.context.opening_status is LifecycleOpeningStatus.PROTECTIVE_LEVEL_CROSSED_AT_OPEN
    assert adverse.context.action_requirement is LifecycleActionRequirement.REVISED_SL_PLACEMENT_REQUIRED
    assert adverse.context.gap_observation.economic_effect is LifecycleEconomicGapEffect.ADVERSE
    assert adverse.context.gap_observation.amount == 56.5
    assert adverse.context.gap_observation.percentage == pytest.approx(27.7641)
    assert favorable.context.opening_status is LifecycleOpeningStatus.NORMAL_OPENING_CONTINUATION
    assert favorable.context.action_requirement is LifecycleActionRequirement.NORMAL_SL_PLACEMENT_REQUIRED
    assert favorable.context.gap_observation.economic_effect is LifecycleEconomicGapEffect.FAVORABLE
    assert favorable.context.gap_observation.amount == -53.5


def test_bull_target_and_protection_crosses_use_authoritative_offline_requirements() -> None:
    target = lifecycle.build_s23_bull_carried_target_crossed_lifecycle()
    protection = lifecycle.build_s23_bull_carried_protection_crossed_lifecycle()

    assert target.context.opening_status is LifecycleOpeningStatus.TARGET_CROSSED_AT_OPEN
    assert target.context.action_requirement is LifecycleActionRequirement.EXIT_REQUIRED
    assert target.context.level_observation.crossed_targets == ("target_1",)
    assert "OPENING_TARGET_CROSSED_ACTION" not in target.context.unresolved_rule_authorities
    assert protection.context.opening_status is LifecycleOpeningStatus.PROTECTIVE_LEVEL_CROSSED_AT_OPEN
    assert protection.context.action_requirement is LifecycleActionRequirement.REVISED_SL_PLACEMENT_REQUIRED
    assert protection.context.level_observation.crossed_protective_levels == ("msl",)
    assert protection.context.protection_state.lifecycle_recalculation_time.isoformat() == "09:29:59"
    assert protection.context.protection_state.revised_protective_formula_policy_id == "S23-CARRIED-CALL-MISSED-BULL-AB6OS-184"


def test_target_priority_wins_when_target_and_protection_cross_together() -> None:
    fixture = lifecycle.build_s23_bull_carried_adverse_gap_lifecycle()
    protection = replace(fixture.context.protection_state, target_levels={"target_1": 350.0}, protective_levels={"msl": 250.0})
    request = PositionLifecycleBuildInput(
        context_id="m13b-target-and-protection-priority",
        trading_date=fixture.context.trading_date,
        strategy_family=fixture.context.strategy_family,
        strategy_definition=fixture.context.strategy_definition,
        strategy_version=fixture.context.strategy_version,
        strategy_instance_id=fixture.context.strategy_instance_id,
        configuration_hash=fixture.context.configuration_hash,
        position_snapshot=fixture.context.position_snapshot,
        protection_state=protection,
        opening_evidence=fixture.context.opening_evidence,
        policy_identities=fixture.context.policy_identities,
    )

    result = PositionLifecycleContextBuilder().build(request)

    assert result.level_observation.crossed_targets == ("target_1",)
    assert result.level_observation.crossed_protective_levels == ("msl",)
    assert result.opening_status is LifecycleOpeningStatus.TARGET_CROSSED_AT_OPEN
    assert result.action_requirement is LifecycleActionRequirement.EXIT_REQUIRED
    assert "OPENING_TARGET_AND_PROTECTION_PRIORITY" not in result.unresolved_rule_authorities


def test_bear_carried_normal_and_adverse_gap() -> None:
    normal = lifecycle.build_s23_bear_carried_normal_lifecycle()
    adverse = lifecycle.build_s23_bear_carried_adverse_gap_lifecycle()

    assert normal.context.opening_status is LifecycleOpeningStatus.NORMAL_OPENING_CONTINUATION
    assert normal.context.action_requirement is LifecycleActionRequirement.NORMAL_SL_PLACEMENT_REQUIRED
    assert normal.context.position_snapshot.contract.symbol == "NIFTY_20260806_22150_CALL"
    assert normal.context.protection_state.revised_protective_formula_policy_id == "S23-CARRIED-CALL-MISSED-BEAR-AB6OS-185"
    assert adverse.context.opening_status is LifecycleOpeningStatus.PROTECTIVE_LEVEL_CROSSED_AT_OPEN
    assert adverse.context.action_requirement is LifecycleActionRequirement.REVISED_SL_PLACEMENT_REQUIRED
    assert adverse.context.gap_observation.economic_effect is LifecycleEconomicGapEffect.ADVERSE
    assert adverse.context.gap_observation.amount == 55.75


def test_missing_quote_stale_quote_and_reconciliation_mismatch_fail_closed() -> None:
    missing = lifecycle.build_s23_missing_quote_lifecycle()
    stale = lifecycle.build_s23_stale_quote_lifecycle()
    mismatch = lifecycle.build_s23_reconciliation_mismatch_lifecycle()

    assert missing.context.opening_status is LifecycleOpeningStatus.OPENING_QUOTE_UNAVAILABLE
    assert missing.context.action_requirement is LifecycleActionRequirement.BLOCKED_INSUFFICIENT_EVIDENCE
    assert missing.handoff.broker_mutation_permitted is False
    assert stale.context.opening_status is LifecycleOpeningStatus.OPENING_QUOTE_STALE
    assert stale.context.action_requirement is LifecycleActionRequirement.WAIT_FOR_AUTHORIZED_OBSERVATION
    assert mismatch.context.opening_status is LifecycleOpeningStatus.BLOCKED_LIFECYCLE_CONTEXT
    assert mismatch.context.action_requirement is LifecycleActionRequirement.BLOCKED_INSUFFICIENT_EVIDENCE
    assert mismatch.context.position_snapshot.reconciliation_status is PositionReconciliationStatus.MISMATCH


def test_adverse_gap_without_revised_sl_policy_does_not_infer_formula() -> None:
    fixture = lifecycle.build_s23_bull_carried_adverse_gap_lifecycle()
    protection = replace(fixture.context.protection_state, revised_protective_formula_policy_id=None)
    request = PositionLifecycleBuildInput(
        context_id="m13-adverse-gap-missing-formula",
        trading_date=fixture.context.trading_date,
        strategy_family=fixture.context.strategy_family,
        strategy_definition=fixture.context.strategy_definition,
        strategy_version=fixture.context.strategy_version,
        strategy_instance_id=fixture.context.strategy_instance_id,
        configuration_hash=fixture.context.configuration_hash,
        position_snapshot=fixture.context.position_snapshot,
        protection_state=protection,
        opening_evidence=fixture.context.opening_evidence,
        policy_identities=fixture.context.policy_identities,
    )

    result = PositionLifecycleContextBuilder().build(request)

    assert result.opening_status is LifecycleOpeningStatus.PROTECTIVE_LEVEL_CROSSED_AT_OPEN
    assert result.action_requirement is LifecycleActionRequirement.RULE_AUTHORITY_UNRESOLVED
    assert "CARRIED_POSITION_REVISED_SL_FORMULA_MISSING" in result.unresolved_rule_authorities


def test_missing_rc_observation_blocks_revised_sl_requirement() -> None:
    fixture = lifecycle.build_s23_missing_rc_lifecycle()

    assert fixture.context.opening_status is LifecycleOpeningStatus.PARTIAL_CONTEXT
    assert fixture.context.action_requirement is LifecycleActionRequirement.WAIT_FOR_AUTHORIZED_OBSERVATION
    assert "CARRIED_POSITION_RC_OBSERVATION_MISSING" in fixture.context.unresolved_rule_authorities


def test_fresh_entry_coordination_remains_isolated_from_carried_lifecycle() -> None:
    fresh = coordination.build_s23_bull_normal_trading_day()
    carried = lifecycle.build_s23_bull_carried_normal_lifecycle()

    assert fresh.execution_handoff_id is not None
    assert fresh.carried_position_status == "NOT_DETECTED"
    assert carried.context.position_snapshot.position_cycle_id != fresh.execution_handoff_id
    assert carried.context.evidence["classification_scope"] == "observation_only"


def test_multiple_position_and_account_isolation() -> None:
    first = lifecycle.build_s23_bull_carried_normal_lifecycle()
    base = first.context.position_snapshot
    second_snapshot = replace(
        base,
        reconciliation_id="m13-second-position:reconciliation",
        strategy_instance_id="S23_NIFTY_ACCOUNT_B_PAPER",
        account_reference="ACCOUNT_B_PAPER_LOGICAL",
        position_cycle_id="S23_NIFTY_ACCOUNT_B_PAPER:CARRY:NIFTY_20260806_22250_CALL",
    )
    request = PositionLifecycleBuildInput(
        context_id="m13-second-account",
        trading_date=first.context.trading_date,
        strategy_family=first.context.strategy_family,
        strategy_definition=first.context.strategy_definition,
        strategy_version=first.context.strategy_version,
        strategy_instance_id="S23_NIFTY_ACCOUNT_B_PAPER",
        configuration_hash=first.context.configuration_hash,
        position_snapshot=second_snapshot,
        protection_state=first.context.protection_state,
        opening_evidence=first.context.opening_evidence,
        policy_identities=first.context.policy_identities,
    )

    second = PositionLifecycleContextBuilder().build(request)

    assert second.opening_status is LifecycleOpeningStatus.NORMAL_OPENING_CONTINUATION
    assert second.action_requirement is LifecycleActionRequirement.NORMAL_SL_PLACEMENT_REQUIRED
    assert first.context.strategy_instance_id != second.strategy_instance_id
    assert first.context.position_snapshot.account_reference != second.position_snapshot.account_reference
    assert first.context.context_hash != second.context_hash


def test_replay_resume_and_checkpoint_mismatch_are_deterministic() -> None:
    fixture = lifecycle.build_s23_bull_carried_normal_lifecycle()
    request = PositionLifecycleBuildInput(
        context_id=fixture.context.context_id,
        trading_date=fixture.context.trading_date,
        strategy_family=fixture.context.strategy_family,
        strategy_definition=fixture.context.strategy_definition,
        strategy_version=fixture.context.strategy_version,
        strategy_instance_id=fixture.context.strategy_instance_id,
        configuration_hash=fixture.context.configuration_hash,
        position_snapshot=fixture.context.position_snapshot,
        protection_state=fixture.context.protection_state,
        opening_evidence=fixture.context.opening_evidence,
        policy_identities=fixture.context.policy_identities,
    )
    replay = PositionLifecycleContextBuilder().build(request)
    resumed = PositionLifecycleContextBuilder().build(replace(request, checkpoint_hash=fixture.context.context_hash, expected_checkpoint_hash=fixture.context.context_hash))
    mismatch = PositionLifecycleContextBuilder().build(replace(request, checkpoint_hash="wrong", expected_checkpoint_hash=fixture.context.context_hash))

    assert fixture.context.context_hash == replay.context_hash == resumed.context_hash
    assert mismatch.opening_status is LifecycleOpeningStatus.BLOCKED_LIFECYCLE_CONTEXT
    assert any(failure.code == "CHECKPOINT_HASH_MISMATCH" for failure in mismatch.failures)


def test_context_is_immutable_and_performance_excluded_from_hash() -> None:
    fixture = lifecycle.build_s23_bull_carried_normal_lifecycle()
    changed = replace(fixture.context, performance={"build_ms": 999}, context_hash="")

    assert changed.context_hash == fixture.context.context_hash
    with pytest.raises(FrozenInstanceError):
        fixture.context.opening_status = LifecycleOpeningStatus.BLOCKED_LIFECYCLE_CONTEXT


def test_generic_lifecycle_builder_has_no_strategy_broker_or_mutation_dependencies() -> None:
    source = Path("src/tfis/lifecycle/context_builder.py").read_text(encoding="utf-8")

    assert "S23" not in source
    assert "S21" not in source
    assert "strategy_code ==" not in source
    assert "tfis.paper" not in source
    assert "broker" not in source.lower()
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "square_off" not in source
    assert "scheduler" not in source.lower()
    assert "event_bus" not in source
    assert "write_text" not in source
    assert "open(" not in source
    assert "eval(" not in source
    assert "exec(" not in source


def test_no_diagnostic_gap_label_alone_produces_revised_sl_requirement() -> None:
    fixture = lifecycle.build_s23_bull_carried_adverse_gap_lifecycle()
    evidence = replace(fixture.context.opening_evidence, orpt_contract_observation=None)
    request = PositionLifecycleBuildInput(
        context_id="m13-diagnostic-gap-only",
        trading_date=fixture.context.trading_date,
        strategy_family=fixture.context.strategy_family,
        strategy_definition=fixture.context.strategy_definition,
        strategy_version=fixture.context.strategy_version,
        strategy_instance_id=fixture.context.strategy_instance_id,
        configuration_hash=fixture.context.configuration_hash,
        position_snapshot=fixture.context.position_snapshot,
        protection_state=fixture.context.protection_state,
        opening_evidence=evidence,
        policy_identities=fixture.context.policy_identities,
    )

    result = PositionLifecycleContextBuilder().build(request)

    assert result.gap_observation.economic_effect is LifecycleEconomicGapEffect.ADVERSE
    assert result.action_requirement is LifecycleActionRequirement.WAIT_FOR_AUTHORIZED_OBSERVATION
    assert result.action_requirement is not LifecycleActionRequirement.REVISED_SL_PLACEMENT_REQUIRED
    assert "CARRIED_POSITION_ORPT_ORIGINAL_SL_OBSERVATION_MISSING" in result.unresolved_rule_authorities


def test_authoritative_rule_matrix_has_source_ids_and_blocks_missing_authority() -> None:
    matrix = json.loads(Path("reports/phase3d/milestone13a_authoritative_rule_matrix.json").read_text(encoding="utf-8"))
    rules = {item["rule_id"]: item for item in matrix["rules"]}

    assert rules["S23-CARRIED-TARGET-USER-2026-07-31"]["authority_status"] == "USER_CLARIFIED_AND_RECORDED"
    assert rules["S23-CARRIED-CALL-NOT-MISSED-AB6OS-183"]["authority_status"] == "WORKBOOK_CELL_VERIFIED"
    assert rules["S23-CARRIED-CALL-MISSED-BULL-AB6OS-184"]["authority_status"] == "WORKBOOK_CELL_VERIFIED"
    assert rules["S23-NONPOSITIVE-RISK"]["authority_status"] == "WORKBOOK_FORMULA_DOMAIN_VERIFIED"
    assert rules["S23-NONPOSITIVE-RISK"]["output"] == "valid positive premium inputs keep S23 option-selling outputs positive; invalid market inputs fail closed"


@pytest.mark.parametrize(
    ("option_side", "option_close", "expected_decision", "expected_rule_id", "expected_source_cell"),
    [
        ("CALL", 250.0, "CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL", "S23-EOD-CARRY-AB6OS-191-USER-EQUALITY", "AB6 OS!F191:J191"),
        ("CALL", 300.0, "CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL", "S23-EOD-CARRY-AB6OS-191-USER-EQUALITY", "AB6 OS!F191:J191"),
        ("CALL", 350.0, "SQUARE_OFF_AT_CMP_REQUIRED", "S23-EOD-CARRY-AB6OS-190", "AB6 OS!F190:J190"),
        ("PUT", 250.0, "CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL", "S23-EOD-CARRY-AB6OS-191-USER-EQUALITY", "AB6 OS!Q191:U191"),
        ("PUT", 300.0, "CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL", "S23-EOD-CARRY-AB6OS-191-USER-EQUALITY", "AB6 OS!Q191:U191"),
        ("PUT", 350.0, "SQUARE_OFF_AT_CMP_REQUIRED", "S23-EOD-CARRY-AB6OS-190", "AB6 OS!Q190:U190"),
    ],
)
def test_s23_eod_carry_decision_uses_verified_workbook_cells(
    option_side: str,
    option_close: float,
    expected_decision: str,
    expected_rule_id: str,
    expected_source_cell: str,
) -> None:
    result = lifecycle.evaluate_s23_eod_carry_decision(option_close=option_close, original_sl=300.0, option_side=option_side)

    assert result.decision == expected_decision
    assert result.rule_id == expected_rule_id
    assert expected_source_cell in result.source_cells
    assert result.rule_id.startswith("S23-EOD-CARRY-")
    assert result.evidence["source_authority"] == "TFISRulesAndSpec/All in One - TFIS 26-12-2023.xlsx"
    assert result.evidence["equality_rule"] == "USER_CLARIFIED_AND_RECORDED: 15:00 close == original SL carries forward"
    assert result.evidence.get("broker_authority") is None
    assert result.evidence.get("paper_authority") is None
    assert result.evidence.get("live_authority") is None


def test_s23_carried_revised_fsl_formulas_are_exact_cell_backed() -> None:
    bull_call = lifecycle.calculate_s23_carried_revised_fsl(branch="BULL", option_side="CALL", rc_option_high=335.0)
    bear_call = lifecycle.calculate_s23_carried_revised_fsl(branch="BEAR", option_side="CALL", rc_option_high=325.0)
    bull_put = lifecycle.calculate_s23_carried_revised_fsl(branch="BULL", option_side="PUT", rc_option_high=200.0)
    invalid = lifecycle.calculate_s23_carried_revised_fsl(branch="BULL", option_side="CALL", rc_option_high=0.0)

    assert bull_call.rule_id == "S23-CARRIED-CALL-MISSED-BULL-AB6OS-184"
    assert bull_call.source_cell == "AB6 OS!M184"
    assert bull_call.revised_fsl == pytest.approx(358.45)
    assert bear_call.rule_id == "S23-CARRIED-CALL-MISSED-BEAR-AB6OS-185"
    assert bear_call.revised_fsl == pytest.approx(357.5)
    assert bull_put.rule_id == "S23-CARRIED-PUT-MISSED-BULL-AB6OS-187"
    assert bull_put.revised_fsl == pytest.approx(220.0)
    assert invalid.status == "RULE_AUTHORITY_UNRESOLVED"
    assert invalid.revised_fsl is None


def test_s23_adapter_records_future_requirements_without_genericizing_them() -> None:
    fixture = lifecycle.build_s23_bull_carried_normal_lifecycle()
    source = Path("src/tfis/lifecycle/context_builder.py").read_text(encoding="utf-8")

    assert any("near-expiry to next-expiry fallback" in item for item in fixture.observed_requirements)
    assert any("MIN/MAX bounded Target or MSL formulas" in item for item in fixture.observed_requirements)
    assert any("fresh-entry Gap/Missed-Entry and carried-position SL recalculation" in item for item in fixture.observed_requirements)
    assert "ideal_premium" not in source.lower()
    assert "minimum_premium" not in source.lower()
    assert "next-expiry" not in source.lower()
