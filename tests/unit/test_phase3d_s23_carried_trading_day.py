from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies import s23_position_lifecycle as lifecycle
from tfis.domain import CarriedPositionDayStage, CarriedPositionEodOutcome, CarriedPositionIntradayState, LifecycleActionRequirement
from tfis.lifecycle import OfflineCarriedPositionTradingDayCoordinator, OfflineCarriedPositionTradingDayInput


def test_m14_normal_carried_day_carry_forward_sequence() -> None:
    fixture = lifecycle.build_s23_bull_carried_normal_day_carry()
    day = fixture.trading_day

    assert day.terminal_stage is CarriedPositionDayStage.COMPLETED_OFFLINE
    assert day.intraday_state is CarriedPositionIntradayState.NORMAL_SL_REQUIRED
    assert day.lifecycle_context.action_requirement is LifecycleActionRequirement.NORMAL_SL_PLACEMENT_REQUIRED
    assert day.eod_decision is not None
    assert day.eod_decision.outcome is CarriedPositionEodOutcome.CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL
    assert day.eod_decision.source_rule_id == "S23-EOD-CARRY-AB6OS-191-USER-EQUALITY"
    assert _stages(day) == (
        CarriedPositionDayStage.POSITION_RECONCILED,
        CarriedPositionDayStage.TARGET_PROTECTION_ASSESSED,
        CarriedPositionDayStage.ORPT_ORIGINAL_SL_ASSESSED,
        CarriedPositionDayStage.INTRADAY_LIFECYCLE_READY,
        CarriedPositionDayStage.EOD_DECISION_READY,
        CarriedPositionDayStage.OFFLINE_HANDOFF_READY,
        CarriedPositionDayStage.COMPLETED_OFFLINE,
    )


def test_m14_equality_carries_forward_with_user_source_rule() -> None:
    fixture = lifecycle.build_s23_bull_carried_normal_day_equal_carry()
    eod = fixture.trading_day.eod_decision

    assert eod is not None
    assert eod.observed_price == eod.original_sl == 300.0
    assert eod.workbook_square_off_operator == ">"
    assert eod.workbook_carry_forward_operator == "<"
    assert eod.effective_carry_forward_operator == "<="
    assert eod.outcome is CarriedPositionEodOutcome.CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL
    assert eod.source_rule_id == "S23-EOD-CARRY-AB6OS-191-USER-EQUALITY"
    assert eod.evidence["equality_rule"] == "USER_CLARIFIED_AND_RECORDED: 15:00 close == original SL carries forward"


def test_m14_above_original_sl_requires_square_off_offline_only() -> None:
    fixture = lifecycle.build_s23_bull_carried_normal_day_square_off()
    day = fixture.trading_day

    assert day.eod_decision is not None
    assert day.eod_decision.outcome is CarriedPositionEodOutcome.SQUARE_OFF_AT_CMP_REQUIRED
    assert day.eod_decision.source_rule_id == "S23-EOD-CARRY-AB6OS-190"
    assert day.square_off_permitted is False
    assert day.lifecycle_handoff.square_off_permitted is False


def test_m14_adverse_day_waits_for_rc_revised_fsl_then_eod_carry() -> None:
    fixture = lifecycle.build_s23_bull_carried_adverse_day_revised_fsl_carry()
    day = fixture.trading_day

    assert day.lifecycle_context.action_requirement is LifecycleActionRequirement.REVISED_SL_PLACEMENT_REQUIRED
    assert day.intraday_state is CarriedPositionIntradayState.REVISED_FSL_REQUIRED
    assert day.eod_decision is not None
    assert day.eod_decision.outcome is CarriedPositionEodOutcome.CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL
    assert CarriedPositionDayStage.RC_REVISED_FSL_ASSESSED in _stages(day)
    assert CarriedPositionDayStage.ORPT_ORIGINAL_SL_ASSESSED not in _stages(day)


def test_m14_target_exit_is_target_first_and_does_not_require_eod() -> None:
    fixture = lifecycle.build_s23_bull_carried_target_exit_day()
    day = fixture.trading_day

    assert day.lifecycle_context.action_requirement is LifecycleActionRequirement.EXIT_REQUIRED
    assert day.intraday_state is CarriedPositionIntradayState.EXIT_REQUIRED_FROM_OPEN
    assert day.eod_decision is None
    assert day.lifecycle_handoff.action_requirement is LifecycleActionRequirement.EXIT_REQUIRED
    assert day.terminal_stage is CarriedPositionDayStage.COMPLETED_OFFLINE


def test_m14_blocks_non_exit_day_without_15_00_decision() -> None:
    fixture = lifecycle.build_s23_bull_carried_normal_lifecycle()
    day = OfflineCarriedPositionTradingDayCoordinator().coordinate(
        OfflineCarriedPositionTradingDayInput(day_id="m14-missing-eod", lifecycle_context=fixture.context)
    )

    assert day.terminal_stage is CarriedPositionDayStage.BLOCKED
    assert day.block_code == "MISSING_EOD_DECISION"
    assert day.eod_decision is None


def test_m14_no_broker_paper_live_authority() -> None:
    fixtures = (
        lifecycle.build_s23_bull_carried_normal_day_carry(),
        lifecycle.build_s23_bull_carried_normal_day_square_off(),
        lifecycle.build_s23_bull_carried_adverse_day_revised_fsl_carry(),
        lifecycle.build_s23_bull_carried_target_exit_day(),
    )

    for fixture in fixtures:
        day = fixture.trading_day
        assert day.runtime_authority == "NONE"
        assert day.broker_authority == "NONE"
        assert day.paper_authority == "NONE"
        assert day.live_authority == "NONE"
        assert day.broker_mutation_permitted is False
        assert day.paper_mutation_permitted is False
        assert day.live_mutation_permitted is False
        assert day.order_modification_permitted is False
        assert day.order_cancellation_permitted is False
        assert day.square_off_permitted is False
        assert day.position_mutation_permitted is False
        assert day.lifecycle_handoff.broker_mutation_permitted is False
        assert day.lifecycle_handoff.paper_mutation_permitted is False
        assert day.lifecycle_handoff.live_mutation_permitted is False


def test_m14_result_is_immutable_and_performance_excluded() -> None:
    day = lifecycle.build_s23_bull_carried_normal_day_carry().trading_day
    changed = replace(day, performance={"coordination_seconds": 999}, day_hash="")

    assert changed.day_hash == day.day_hash
    with pytest.raises(FrozenInstanceError):
        day.terminal_stage = CarriedPositionDayStage.BLOCKED


def test_m14_generic_carried_day_coordinator_has_no_strategy_broker_or_runtime_dependencies() -> None:
    source = Path("src/tfis/lifecycle/carried_day_coordinator.py").read_text(encoding="utf-8")

    assert "S23" not in source
    assert "S21" not in source
    assert "strategy_code ==" not in source
    assert "tfis.paper" not in source
    assert "broker" not in source.lower()
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "scheduler" not in source.lower()
    assert "event_bus" not in source
    assert "write_text" not in source
    assert "open(" not in source
    assert "eval(" not in source
    assert "exec(" not in source


def _stages(day) -> tuple[CarriedPositionDayStage, ...]:
    return tuple(transition.stage for transition in day.transition_evidence)
