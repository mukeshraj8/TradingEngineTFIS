from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies import s23_call_captured_evidence as m5
from tfis.adapters.legacy_policies import s23_effective_execution_plan as effective
from tfis.adapters.legacy_policies import s23_opening_context as opening
from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_trading_day_coordination as coord
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.coordination import OfflineTradingDayCoordinationInput, OfflineTradingDayCoordinator
from tfis.domain import CoordinationEventType, OfflineHandoffAuthorityMode, TradingDayCoordinationState, TradingDayPath


BULL_M3_HASH = "4d2e514f05f873c17b7077ce6710c559dac54422ed6898cbb51e6ed9bbb24b84"
BULL_M5_HASH = "4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c"
BEAR_M5_HASH = "3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41"
BULL_M9_PLAN_HASH = "873a7662f321b70af350a5d3b2e0b9fccf72852ae0bfc88e4471faca4cd91f22"
BEAR_M9_PLAN_HASH = "cfb09a5b41ee667a045e89d36cf4167dfe3acb46630bf76dd03e16f51e3e576b"
BULL_M11_NORMAL_HASH = "c30bd67eeeb2063c90ddce7afd9a175cb38c049c2896ed914a6948382c16ebb1"
BULL_M11_GAP_HASH = "45a5106bb1027881abf5d937224fd6def4237476941f2c8d8603d2963526df51"
BEAR_M11_NORMAL_HASH = "3830fd5b913db77e765d2203740ebbd6e16d8549f4cee8a3a5051f26afba8051"
BEAR_M11_GAP_HASH = "f21d868f8e78edd54b5c231848e9b4f820150e2d65d5855b30adde35ea8a505e"


def test_bull_normal_complete_day() -> None:
    result = coord.build_s23_bull_normal_trading_day()

    assert result.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert result.daily_path is TradingDayPath.NORMAL_FRESH_ENTRY
    assert result.premarket_plan_hash == BULL_M9_PLAN_HASH
    assert result.effective_execution_plan_hash == BULL_M11_NORMAL_HASH
    assert result.offline_handoff is not None
    assert result.offline_handoff.authorized_placement_time.isoformat() == "09:19:59"
    assert result.offline_handoff.authority_mode is OfflineHandoffAuthorityMode.OFFLINE_ONLY
    assert result.offline_handoff.broker_submission_permitted is False
    assert result.offline_handoff.paper_submission_permitted is False
    assert result.offline_handoff.live_submission_permitted is False
    assert result.offline_handoff.position_mutation_permitted is False


def test_bull_gap_complete_day() -> None:
    result = coord.build_s23_bull_gap_trading_day()

    assert result.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert result.daily_path is TradingDayPath.GAP_RECALCULATION
    assert result.effective_execution_plan_hash == BULL_M11_GAP_HASH
    assert result.rc_event_id is not None
    assert result.offline_handoff is not None
    assert result.offline_handoff.authorized_placement_time.isoformat() == "09:29:59"


def test_bear_normal_and_gap_complete_days() -> None:
    normal = coord.build_s23_bear_normal_trading_day()
    gap = coord.build_s23_bear_gap_trading_day()

    assert normal.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert normal.daily_path is TradingDayPath.NORMAL_FRESH_ENTRY
    assert normal.premarket_plan_hash == BEAR_M9_PLAN_HASH
    assert normal.effective_execution_plan_hash == BEAR_M11_NORMAL_HASH
    assert gap.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert gap.daily_path is TradingDayPath.GAP_RECALCULATION
    assert gap.effective_execution_plan_hash == BEAR_M11_GAP_HASH


def test_partial_real_blocks_without_handoff() -> None:
    result = coord.build_s23_partial_real_blocked_trading_day()

    assert result.current_state is TradingDayCoordinationState.BLOCKED
    assert result.daily_path is TradingDayPath.INSUFFICIENT_EVIDENCE
    assert result.block_code == "OPENING_CONTEXT_INCOMPLETE"
    assert result.effective_execution_plan_hash == effective.build_s23_partial_real_execution_plan().execution_plan_hash
    assert result.execution_handoff_id is None
    assert result.offline_handoff is None


def test_carried_position_never_enters_fresh_entry_path() -> None:
    result = coord.build_s23_carried_position_trading_day()

    assert result.current_state is TradingDayCoordinationState.CARRIED_POSITION_HANDOFF_REQUIRED
    assert result.daily_path is TradingDayPath.CARRIED_POSITION
    assert result.fresh_entry_eligible is False
    assert result.carried_position_status == "DETECTED"
    assert result.premarket_plan_id is None
    assert result.opening_context_id is None
    assert result.effective_execution_plan_id is None
    assert result.execution_handoff_id is None


def test_same_generic_coordinator_serves_all_s23_paths(monkeypatch) -> None:
    calls: list[str] = []
    original = OfflineTradingDayCoordinator.coordinate

    def observe(self, request):
        calls.append(type(self).__name__)
        return original(self, request)

    monkeypatch.setattr(OfflineTradingDayCoordinator, "coordinate", observe)

    coord.build_s23_bull_normal_trading_day()
    coord.build_s23_bull_gap_trading_day()
    coord.build_s23_bear_normal_trading_day()
    coord.build_s23_bear_gap_trading_day()

    assert calls == ["OfflineTradingDayCoordinator"] * 4


def test_illegal_transitions_and_event_ordering_fail_closed() -> None:
    base = _bull_request(events=coord._normal_events(_bull_case().runtime_input.strategy_instance_id))
    premarket_first = replace(base, events=base.events[1:])
    orpt_before_market = replace(base, events=(base.events[0], base.events[1], base.events[3]))
    rc_before_orpt = replace(_bull_gap_request(), events=tuple(item for item in _bull_gap_request().events if item.event_type is not CoordinationEventType.ORPT_REACHED))

    assert OfflineTradingDayCoordinator().coordinate(premarket_first).block_code == "PREMARKET_BEFORE_STARTUP"
    assert OfflineTradingDayCoordinator().coordinate(orpt_before_market).block_code == "ORPT_BEFORE_MARKET_OPEN"
    assert OfflineTradingDayCoordinator().coordinate(rc_before_orpt).block_code == "RC_BEFORE_ORPT"


def test_disabled_invalid_missing_premarket_and_sequence_fail_closed() -> None:
    base = _bull_request(events=coord._normal_events(_bull_case().runtime_input.strategy_instance_id))
    disabled = replace(base, enabled=False)
    invalid = replace(base, configuration_valid=False)
    missing_premarket = replace(base, premarket_plan_factory=None)
    discontinuous = replace(base, events=(base.events[0], replace(base.events[1], sequence_identity=1)))

    assert OfflineTradingDayCoordinator().coordinate(disabled).current_state is TradingDayCoordinationState.DISABLED
    assert OfflineTradingDayCoordinator().coordinate(invalid).block_code == "CONFIGURATION_INVALID"
    assert OfflineTradingDayCoordinator().coordinate(missing_premarket).block_code == "MISSING_PREMARKET_INPUT"
    assert OfflineTradingDayCoordinator().coordinate(discontinuous).block_code == "EVENT_SEQUENCE_DISCONTINUITY"


def test_missing_rc_in_gap_stream_blocks_without_handoff() -> None:
    request = _bull_gap_request()
    without_rc = replace(request, events=tuple(event for event in request.events if event.event_type is not CoordinationEventType.RC_REACHED))

    result = OfflineTradingDayCoordinator().coordinate(without_rc)

    assert result.current_state is TradingDayCoordinationState.BLOCKED
    assert result.block_code == "HANDOFF_REQUESTED_TOO_EARLY"
    assert result.execution_handoff_id is None


def test_duplicate_idempotency_and_conflicting_duplicate() -> None:
    base = _bull_request(events=coord._normal_events(_bull_case().runtime_input.strategy_instance_id))
    duplicate = replace(base, events=(base.events[0], base.events[0]) + base.events[1:])
    conflict_event = replace(base.events[0], source_classification="CONFLICT")
    conflict = replace(base, events=(base.events[0], conflict_event) + base.events[1:])

    assert OfflineTradingDayCoordinator().coordinate(duplicate).current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    blocked = OfflineTradingDayCoordinator().coordinate(conflict)
    assert blocked.current_state is TradingDayCoordinationState.BLOCKED
    assert blocked.block_code == "CONFLICTING_DUPLICATE_EVENT"


def test_wrong_strategy_date_and_instrument_events_block() -> None:
    base = _bull_request(events=coord._normal_events(_bull_case().runtime_input.strategy_instance_id))
    wrong_strategy = replace(base, events=(base.events[0], replace(base.events[1], strategy_instance_id="OTHER")))
    wrong_date = replace(base, events=(base.events[0], replace(base.events[1], trading_date=base.trading_date.replace(day=29))))
    wrong_instrument = replace(base, events=(base.events[0], base.events[1], replace(base.events[2], instrument="NSE:BANKNIFTY")))

    assert OfflineTradingDayCoordinator().coordinate(wrong_strategy).block_code == "WRONG_STRATEGY_INSTANCE_EVENT"
    assert OfflineTradingDayCoordinator().coordinate(wrong_date).block_code == "WRONG_TRADING_DATE_EVENT"
    assert OfflineTradingDayCoordinator().coordinate(wrong_instrument).block_code == "WRONG_INSTRUMENT_EVENT"


def test_handoff_requested_too_early_and_session_end_block() -> None:
    base = _bull_request(events=coord._normal_events(_bull_case().runtime_input.strategy_instance_id))
    early_handoff = replace(base, events=(base.events[0], base.events[1], base.events[-1]))
    session_end = replace(base, events=base.events[:-1] + (replace(base.events[-1], event_type=CoordinationEventType.SESSION_ENDED),))

    assert OfflineTradingDayCoordinator().coordinate(early_handoff).block_code == "HANDOFF_REQUESTED_TOO_EARLY"
    assert OfflineTradingDayCoordinator().coordinate(session_end).block_code == "SESSION_ENDED_BEFORE_HANDOFF"


def test_multiple_instance_independence_and_one_block_does_not_contaminate_another() -> None:
    case = _bull_case()
    plan_a = premarket.build_s23_bull_call_premarket_plan()
    plan_b = replace(plan_a, plan_id=f"{plan_a.plan_id}:account-b", strategy_instance_id="S23_NIFTY_ACCOUNT_B_PAPER", business_hash="account-b-plan", plan_hash="account-b-plan")
    context_b = replace(effective._normal_context("bull"), context_id="m12-account-b-context", source_plan_id=plan_b.plan_id, source_plan_hash=plan_b.plan_hash, context_hash="")
    effective_b = lambda: effective._compose(case, context_b, plan=plan_b)
    events_b = coord._normal_events("S23_NIFTY_ACCOUNT_B_PAPER")
    ready_b = replace(
        _bull_request(events=events_b),
        coordination_id="m12-account-b",
        strategy_instance_id="S23_NIFTY_ACCOUNT_B_PAPER",
        premarket_plan_factory=lambda: plan_b,
        opening_context_factory=lambda: context_b,
        effective_execution_plan_factory=effective_b,
    )
    blocked_b = replace(ready_b, opening_context_factory=lambda: replace(context_b, source_plan_hash="wrong", context_hash=""))

    ready_a_result = coord.build_s23_bull_normal_trading_day()
    ready_b_result = OfflineTradingDayCoordinator().coordinate(ready_b)
    blocked_b_result = OfflineTradingDayCoordinator().coordinate(blocked_b)

    assert ready_a_result.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert ready_b_result.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert blocked_b_result.current_state is TradingDayCoordinationState.BLOCKED
    assert ready_a_result.strategy_instance_id != ready_b_result.strategy_instance_id
    assert ready_a_result.coordination_hash != ready_b_result.coordination_hash


def test_replay_checkpoint_resume_and_checkpoint_mismatch() -> None:
    request = _bull_request(events=coord._normal_events(_bull_case().runtime_input.strategy_instance_id))
    first = OfflineTradingDayCoordinator().coordinate(request)
    replay = OfflineTradingDayCoordinator().coordinate(request)
    resumed = OfflineTradingDayCoordinator().coordinate(replace(request, checkpoint_hash=first.coordination_hash, expected_checkpoint_hash=first.coordination_hash))
    mismatch = OfflineTradingDayCoordinator().coordinate(replace(request, checkpoint_hash="wrong", expected_checkpoint_hash=first.coordination_hash))

    assert first.coordination_hash == replay.coordination_hash == resumed.coordination_hash
    assert first.offline_handoff.evidence_hash == replay.offline_handoff.evidence_hash == resumed.offline_handoff.evidence_hash
    assert mismatch.current_state is TradingDayCoordinationState.BLOCKED
    assert mismatch.block_code == "CHECKPOINT_HASH_MISMATCH"


def test_coordination_result_is_immutable_and_performance_excluded() -> None:
    result = coord.build_s23_bull_normal_trading_day()
    changed = replace(result, performance={"coordination_seconds": 999}, coordination_hash="")

    assert result.coordination_hash == changed.coordination_hash
    with pytest.raises(FrozenInstanceError):
        result.current_state = TradingDayCoordinationState.BLOCKED


def test_generic_coordinator_has_no_runtime_or_strategy_branching_dependencies() -> None:
    source = Path("src/tfis/coordination/offline_trading_day.py").read_text(encoding="utf-8")

    assert "S23" not in source
    assert "S21" not in source
    assert "strategy_code ==" not in source
    assert "tfis.paper" not in source
    assert "broker" not in source.lower()
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "scheduler" not in source.lower()
    assert "event_bus" not in source
    assert "thread" not in source.lower()
    assert "write_text" not in source
    assert "open(" not in source
    assert "eval(" not in source
    assert "exec(" not in source


def test_existing_m3_m11_hashes_remain_unchanged() -> None:
    assert premarket.build_s23_bull_call_premarket_plan().plan_hash == BULL_M9_PLAN_HASH
    assert premarket.build_s23_bear_call_premarket_plan().plan_hash == BEAR_M9_PLAN_HASH
    assert effective.build_s23_bull_normal_execution_plan().execution_plan_hash == BULL_M11_NORMAL_HASH
    assert effective.build_s23_bull_gap_execution_plan().execution_plan_hash == BULL_M11_GAP_HASH
    assert effective.build_s23_bear_normal_execution_plan().execution_plan_hash == BEAR_M11_NORMAL_HASH
    assert effective.build_s23_bear_gap_execution_plan().execution_plan_hash == BEAR_M11_GAP_HASH
    assert vertical.run_s23_bull_call_vertical_slice().deterministic_hash == BULL_M3_HASH
    assert m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture").deterministic_hash == BULL_M5_HASH
    assert m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture").deterministic_hash == BEAR_M5_HASH


def _bull_case():
    return vertical.build_s23_bull_call_vertical_case()


def _bull_request(*, events):
    case = _bull_case()
    runtime = case.runtime_input
    return OfflineTradingDayCoordinationInput(
        coordination_id="m12-test-bull",
        trading_date=runtime.evaluated_at.date(),
        strategy_family=runtime.strategy_family_id,
        strategy_definition=runtime.strategy_definition_id,
        strategy_version="1.0.0",
        strategy_instance_id=runtime.strategy_instance_id,
        configuration_hash=runtime.resolved_configuration_hash,
        events=events,
        premarket_plan_factory=premarket.build_s23_bull_call_premarket_plan,
        opening_context_factory=lambda: effective._normal_context("bull"),
        effective_execution_plan_factory=effective.build_s23_bull_normal_execution_plan,
    )


def _bull_gap_request():
    case = _bull_case()
    runtime = case.runtime_input
    return replace(
        _bull_request(events=coord._gap_events(runtime.strategy_instance_id)),
        coordination_id="m12-test-bull-gap",
        opening_context_factory=opening.build_s23_bull_call_opening_context,
        effective_execution_plan_factory=effective.build_s23_bull_gap_execution_plan,
    )
