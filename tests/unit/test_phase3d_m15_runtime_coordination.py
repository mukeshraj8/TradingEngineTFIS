from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tfis.adapters.legacy_policies import s23_runtime_coordination as runtime
from tfis.domain import TradingDayCoordinationState, TradingDayPath
from tfis.domain.carried_position_day import CarriedPositionDayStage, CarriedPositionEodOutcome, CarriedPositionIntradayState
from tfis.runtime import (
    DeterministicRuntimeCoordinator,
    InstrumentStateOwner,
    NormalizedRuntimeEvent,
    RuntimeCoherentSnapshotPolicy,
    RuntimeDeliveryClass,
    RuntimeEventType,
    RuntimeFreshness,
    RuntimeStreamStatus,
    RuntimeSubscriptionIndex,
    validate_snapshot_coherence,
)


def test_normalized_runtime_event_contract_is_immutable_and_deterministic() -> None:
    event = _event("quote", RuntimeEventType.UNDERLYING_QUOTE, 1, payload={"ltp": 22400.0})
    same = _event("quote", RuntimeEventType.UNDERLYING_QUOTE, 1, payload={"ltp": 22400.0})

    assert event.delivery_class is RuntimeDeliveryClass.CONFLATABLE_STATE_UPDATE
    assert event.payload_hash == same.payload_hash
    assert event.to_dict()["effective_timestamp"].endswith("+05:30")
    with pytest.raises(FrozenInstanceError):
        event.event_id = "changed"


def test_delivery_classes_keep_clock_events_critical() -> None:
    assert _event("ltp", RuntimeEventType.UNDERLYING_QUOTE, 1).delivery_class is RuntimeDeliveryClass.CONFLATABLE_STATE_UPDATE
    assert _event("orpt", RuntimeEventType.ORPT_TIME, 2).delivery_class is RuntimeDeliveryClass.NON_CONFLATABLE_CRITICAL_EVENT
    assert _event("rc", RuntimeEventType.RC_TIME, 3).delivery_class is RuntimeDeliveryClass.NON_CONFLATABLE_CRITICAL_EVENT


def test_instrument_state_owner_publishes_immutable_snapshot_and_conflates_quotes() -> None:
    owner = InstrumentStateOwner(runtime.NIFTY)
    first = owner.apply(_event("q1", RuntimeEventType.UNDERLYING_QUOTE, 1, payload={"ltp": 22400.0}))
    second = owner.apply(_event("q2", RuntimeEventType.UNDERLYING_QUOTE, 2, payload={"ltp": 22405.0}))

    assert first.status == "UPDATED"
    assert second.status == "UPDATED"
    assert second.snapshot.ltp == 22405.0
    assert owner.conflation_count == 1
    with pytest.raises(FrozenInstanceError):
        second.snapshot.ltp = 1.0


def test_instrument_state_owner_duplicate_stale_and_wrong_contract_handling() -> None:
    owner = InstrumentStateOwner(runtime.NIFTY, contract_identity=runtime.CONTRACT_A)
    first = _event("c1", RuntimeEventType.OPTION_CONTRACT_QUOTE, 2, contract=runtime.CONTRACT_A, payload={"ltp": 250.0})
    conflict = replace(first, payload={"ltp": 251.0}, payload_hash="")

    assert owner.apply(first).status == "UPDATED"
    assert owner.apply(first).status == "IDEMPOTENT_DUPLICATE"
    assert owner.apply(conflict).status == "CONFLICTING_DUPLICATE"
    assert owner.apply(_event("stale", RuntimeEventType.OPTION_CONTRACT_QUOTE, 1, contract=runtime.CONTRACT_A)).status == "STALE_IGNORED"
    assert owner.apply(_event("wrong", RuntimeEventType.OPTION_CONTRACT_QUOTE, 3, contract=runtime.CONTRACT_B)).status == "REJECTED_WRONG_CONTRACT"


def test_subscription_index_routes_and_removes_independently() -> None:
    index = RuntimeSubscriptionIndex()
    index.add_strategy("S1", underlying=runtime.NIFTY, contract=runtime.CONTRACT_A)
    index.add_strategy("S2", underlying=runtime.BANKNIFTY)
    index.add_position("P1", underlying=runtime.NIFTY, contract=runtime.CONTRACT_A)
    snapshot = index.snapshot()

    assert snapshot.interested_strategies(instrument=runtime.NIFTY, contract=None) == ("S1",)
    assert snapshot.interested_positions(instrument=runtime.NIFTY, contract=runtime.CONTRACT_A) == ("P1",)
    index.remove_strategy("S1")
    assert index.snapshot().interested_strategies(instrument=runtime.NIFTY, contract=runtime.CONTRACT_A) == ()


def test_snapshot_coherence_accepts_fresh_related_snapshots() -> None:
    owner = InstrumentStateOwner(runtime.NIFTY)
    snapshot = owner.apply(_event("open", RuntimeEventType.SESSION_OPEN_OBSERVATION, 1, payload={"opening_value": 22400.0})).snapshot

    result = validate_snapshot_coherence(trading_date=runtime.TRADING_DATE, evaluation_timestamp=_ts(), underlying=snapshot)

    assert result.status == "COHERENT"
    assert result.underlying_snapshot_hash == snapshot.snapshot_hash


def test_snapshot_coherence_rejects_stale_and_mixed_dates() -> None:
    owner = InstrumentStateOwner(runtime.NIFTY)
    snapshot = owner.apply(_event("old", RuntimeEventType.UNDERLYING_QUOTE, 1, payload={"ltp": 22400.0})).snapshot
    stale = validate_snapshot_coherence(trading_date=runtime.TRADING_DATE, evaluation_timestamp=_ts() + timedelta(minutes=10), underlying=snapshot, policy=RuntimeCoherentSnapshotPolicy(60, 60))
    mixed = validate_snapshot_coherence(trading_date=runtime.TRADING_DATE.replace(day=29), evaluation_timestamp=_ts(), underlying=snapshot)

    assert stale.status == "STALE_SNAPSHOT"
    assert mixed.status == "MIXED_TRADING_DATE"


def test_bull_normal_runtime_stream_uses_offline_business_path() -> None:
    result = runtime.build_s23_runtime_normal_stream()
    day = result.fresh_entry_results["bull-normal"]

    assert day.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert day.daily_path is TradingDayPath.NORMAL_FRESH_ENTRY
    assert day.offline_handoff is not None
    assert day.offline_handoff.authority_mode.value == "OFFLINE_ONLY"
    assert day.rc_event_id is None


def test_bull_gap_runtime_stream_preserves_rc_event() -> None:
    result = runtime.build_s23_runtime_gap_stream()
    day = result.fresh_entry_results["bull-gap"]

    assert day.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert day.daily_path is TradingDayPath.GAP_RECALCULATION
    assert day.rc_event_id is not None
    assert any(event_id.endswith("-rc-7") for event_id in result.critical_event_ids)


def test_bear_normal_and_gap_runtime_streams() -> None:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(runtime.S23_BEAR_A, underlying=runtime.NIFTY, contract=runtime.CONTRACT_A)
    normal = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=runtime._fresh_events(runtime.S23_BEAR_A, gap=False),
        subscriptions=subscriptions,
        fresh_streams={"bear-normal": runtime._fresh_stream(runtime.S23_BEAR_A, "bear", "normal")},
    )
    gap = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=runtime._fresh_events(runtime.S23_BEAR_A, gap=True),
        subscriptions=subscriptions,
        fresh_streams={"bear-gap": runtime._fresh_stream(runtime.S23_BEAR_A, "bear", "gap")},
    )

    assert normal.fresh_entry_results["bear-normal"].daily_path is TradingDayPath.NORMAL_FRESH_ENTRY
    assert gap.fresh_entry_results["bear-gap"].daily_path is TradingDayPath.GAP_RECALCULATION


def test_carried_target_exit_stream_no_eod_needed() -> None:
    result = runtime.build_s23_runtime_carried_target_stream()
    day = result.position_cycle_results["target"]

    assert day.terminal_stage is CarriedPositionDayStage.COMPLETED_OFFLINE
    assert day.intraday_state is CarriedPositionIntradayState.EXIT_REQUIRED_FROM_OPEN
    assert day.eod_decision is None


def test_carried_normal_sl_eod_carry_stream() -> None:
    result = _carried_result("normal_carry", include_eod=True)
    day = result.position_cycle_results["normal_carry"]

    assert day.intraday_state is CarriedPositionIntradayState.NORMAL_SL_REQUIRED
    assert day.eod_decision.outcome is CarriedPositionEodOutcome.CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL


def test_carried_revised_sl_stream_uses_m14_logic() -> None:
    result = runtime.build_s23_runtime_carried_revised_sl_stream()
    day = result.position_cycle_results["revised-sl"]

    assert day.intraday_state is CarriedPositionIntradayState.REVISED_FSL_REQUIRED
    assert day.eod_decision.source_rule_id
    assert result.authority["position_mutation"] is False


def test_carried_eod_square_off_and_equality_carry_are_shadow_only() -> None:
    square = _carried_result("square_off", include_eod=True).position_cycle_results["square_off"]
    equal = _carried_result("normal_equal", include_eod=True).position_cycle_results["normal_equal"]

    assert square.eod_decision.outcome is CarriedPositionEodOutcome.SQUARE_OFF_AT_CMP_REQUIRED
    assert square.square_off_permitted is False
    assert equal.eod_decision.outcome is CarriedPositionEodOutcome.CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL


def test_missing_rc_blocks_only_affected_carried_stream() -> None:
    result = _carried_result("missing_rc", include_eod=True)
    day = result.position_cycle_results["missing_rc"]

    assert day.terminal_stage is CarriedPositionDayStage.BLOCKED
    assert result.blocked_streams["missing_rc"] == "WAIT_FOR_AUTHORIZED_OBSERVATION"


def test_multiple_strategy_instances_share_underlying_but_keep_artifacts_independent() -> None:
    result = runtime.build_s23_runtime_multi_instance_stream()
    a = result.fresh_entry_results["bull-a"]
    b = result.fresh_entry_results["bull-b"]

    assert a.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert b.current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert a.strategy_instance_id != b.strategy_instance_id
    assert a.coordination_hash != b.coordination_hash
    assert set(result.subscription_snapshot.interested_strategies(instrument=runtime.NIFTY, contract=None)) == {runtime.S23_BEAR_A, runtime.S23_BULL_A, runtime.S23_BULL_B}


def test_one_disabled_instance_does_not_block_enabled_instance() -> None:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(runtime.S23_BULL_A, underlying=runtime.NIFTY)
    subscriptions.add_strategy(runtime.S23_BULL_B, underlying=runtime.NIFTY)
    disabled = replace(runtime._fresh_stream(runtime.S23_BULL_B, "bull", "normal"), status=RuntimeStreamStatus.DISABLED)
    result = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=runtime._fresh_events(runtime.S23_BULL_A, gap=False),
        subscriptions=subscriptions,
        fresh_streams={"enabled": runtime._fresh_stream(runtime.S23_BULL_A, "bull", "normal"), "disabled": disabled},
    )

    assert result.fresh_entry_results["enabled"].current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert "disabled" not in result.fresh_entry_results


def test_multiple_position_cycles_are_isolated() -> None:
    result = runtime.build_s23_runtime_multi_position_stream()

    assert result.position_cycle_results["target-position"].intraday_state is CarriedPositionIntradayState.EXIT_REQUIRED_FROM_OPEN
    assert result.position_cycle_results["normal-position"].intraday_state is CarriedPositionIntradayState.NORMAL_SL_REQUIRED
    assert result.position_cycle_results["target-position"].position_cycle_id != result.position_cycle_results["normal-position"].position_cycle_id


def test_multiple_instrument_isolation_ignores_banknifty_for_nifty_stream() -> None:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(runtime.S23_BULL_A, underlying=runtime.NIFTY)
    result = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=runtime._fresh_events(runtime.S23_BULL_A, gap=False) + (_event("bank", RuntimeEventType.UNDERLYING_QUOTE, 99, instrument=runtime.BANKNIFTY),),
        subscriptions=subscriptions,
        fresh_streams={"nifty": runtime._fresh_stream(runtime.S23_BULL_A, "bull", "normal")},
    )

    assert result.fresh_entry_results["nifty"].current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert all("BANKNIFTY" not in event_id for event_id in result.fresh_entry_results["nifty"].transition_evidence[0].artifact_hashes)


def test_subscription_removal_stops_business_evaluation() -> None:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(runtime.S23_BULL_A, underlying=runtime.NIFTY)
    subscriptions.remove_strategy(runtime.S23_BULL_A)
    result = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=tuple(replace(event, strategy_instance_target=None) for event in runtime._fresh_events(runtime.S23_BULL_A, gap=False)),
        subscriptions=subscriptions,
        fresh_streams={"removed": runtime._fresh_stream(runtime.S23_BULL_A, "bull", "normal")},
    )

    assert result.fresh_entry_results == {}


def test_ordinary_tick_conflation_is_bounded_and_preserves_critical_events() -> None:
    result = runtime.build_s23_runtime_backpressure_stream(quote_count=40)

    assert result.performance["quote_burst_size"] == 40
    assert result.performance["maximum_pending_conflatable_updates"] == 1
    assert result.performance["critical_event_processing_count"] == 2
    assert any(event_id.endswith("-orpt-41") for event_id in result.critical_event_ids)
    assert any(event_id.endswith("-rc-42") for event_id in result.critical_event_ids)


def test_critical_event_ordering_blocks_orpt_before_market_open() -> None:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(runtime.S23_BULL_A, underlying=runtime.NIFTY)
    events = tuple(event for event in runtime._fresh_events(runtime.S23_BULL_A, gap=False) if event.event_type is not RuntimeEventType.SESSION_OPEN_OBSERVATION)
    result = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=events,
        subscriptions=subscriptions,
        fresh_streams={"bull": runtime._fresh_stream(runtime.S23_BULL_A, "bull", "normal")},
    )

    assert result.blocked_streams["bull"] == "ORPT_BEFORE_MARKET_OPEN"


def test_session_end_rejects_later_business_events() -> None:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(runtime.S23_BULL_A, underlying=runtime.NIFTY)
    events = (_event("end", RuntimeEventType.SESSION_END_TIME, 1),) + runtime._fresh_events(runtime.S23_BULL_A, gap=False)
    result = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=events,
        subscriptions=subscriptions,
        fresh_streams={"bull": runtime._fresh_stream(runtime.S23_BULL_A, "bull", "normal")},
    )

    assert result.processed_event_ids[-1] == events[0].event_id
    assert "bull" in result.fresh_entry_results


def test_duplicate_conflict_and_wrong_date_fail_closed() -> None:
    subscriptions = RuntimeSubscriptionIndex()
    e1 = _event("dup", RuntimeEventType.UNDERLYING_QUOTE, 1, payload={"ltp": 1})
    conflict = replace(e1, payload={"ltp": 2}, payload_hash="")
    wrong_date = replace(_event("wrong-date", RuntimeEventType.UNDERLYING_QUOTE, 2), trading_date=runtime.TRADING_DATE.replace(day=29))
    result = DeterministicRuntimeCoordinator().run(trading_date=runtime.TRADING_DATE, events=(e1, conflict, wrong_date), subscriptions=subscriptions)

    assert result.blocked_streams[f"event:{conflict.event_id}"] == "CONFLICTING_DUPLICATE"
    assert result.blocked_streams[f"event:{wrong_date.event_id}"] == "WRONG_TRADING_DATE"


def test_wrong_instrument_and_wrong_contract_are_isolated() -> None:
    owner = InstrumentStateOwner(runtime.NIFTY, contract_identity=runtime.CONTRACT_A)

    assert owner.apply(_event("wrong-inst", RuntimeEventType.OPTION_CONTRACT_QUOTE, 1, instrument=runtime.BANKNIFTY, contract=runtime.CONTRACT_A)).status == "REJECTED_WRONG_INSTRUMENT"
    assert owner.apply(_event("wrong-contract", RuntimeEventType.OPTION_CONTRACT_QUOTE, 2, contract=runtime.CONTRACT_B)).status == "REJECTED_WRONG_CONTRACT"


def test_replay_and_resume_are_deterministic_and_checkpoint_invalidates() -> None:
    first = runtime.build_s23_runtime_normal_stream()
    replay = runtime.build_s23_runtime_normal_stream()
    stream_id, checkpoint = next(iter(first.checkpoints.items()))
    mismatch = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=runtime._fresh_events(runtime.S23_BULL_A, gap=False),
        subscriptions=RuntimeSubscriptionIndex(),
        fresh_streams={stream_id: runtime._fresh_stream(runtime.S23_BULL_A, "bull", "normal")},
        expected_checkpoint_hashes={stream_id: checkpoint.checkpoint_hash},
    )

    assert first.result_hash == replay.result_hash
    assert mismatch.blocked_streams[stream_id] == "CHECKPOINT_MISMATCH"


def test_one_stream_failure_does_not_contaminate_other_stream() -> None:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(runtime.S23_BULL_A, underlying=runtime.NIFTY)
    subscriptions.add_strategy(runtime.S23_BULL_B, underlying=runtime.NIFTY)
    blocked_events = tuple(event for event in runtime._fresh_events(runtime.S23_BULL_B, gap=True, sequence_offset=100) if event.event_type is not RuntimeEventType.RC_TIME)
    result = DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=runtime._fresh_events(runtime.S23_BULL_A, gap=False) + blocked_events,
        subscriptions=subscriptions,
        fresh_streams={"ready": runtime._fresh_stream(runtime.S23_BULL_A, "bull", "normal"), "blocked": runtime._fresh_stream(runtime.S23_BULL_B, "bull", "gap", account_b=True)},
    )

    assert result.fresh_entry_results["ready"].current_state is TradingDayCoordinationState.COMPLETED_OFFLINE
    assert result.blocked_streams["blocked"] == "HANDOFF_REQUESTED_TOO_EARLY"


def test_authority_flags_are_false_and_runtime_is_shadow_only() -> None:
    result = runtime.build_s23_runtime_carried_revised_sl_stream()

    assert result.authority["mode"] == "SHADOW_ONLY"
    for key, value in result.authority.items():
        if key != "mode":
            assert value is False


def test_runtime_boundaries_have_no_formula_or_authority_dependencies() -> None:
    source = Path("src/tfis/runtime/coordination.py").read_text(encoding="utf-8")

    assert "S23" not in source
    assert "S21" not in source
    assert "strategy_code ==" not in source
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "fyers" not in source.lower()
    assert "kiteconnect" not in source.lower()
    assert "eval(" not in source
    assert "exec(" not in source
    assert "datetime.now" not in source
    assert "thread" not in source.lower()


def test_runtime_json_serialization_is_deterministic() -> None:
    result = runtime.build_s23_runtime_normal_stream()

    assert result.to_json() == runtime.build_s23_runtime_normal_stream().to_json()
    assert result.to_dict()["performance"]["event_count"] >= 5


def _carried_result(fixture: str, *, include_eod: bool):
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_position(runtime.POSITION_A, underlying=runtime.NIFTY, contract=runtime.CONTRACT_A)
    return DeterministicRuntimeCoordinator().run(
        trading_date=runtime.TRADING_DATE,
        events=runtime._carried_events(runtime.POSITION_A, runtime.CONTRACT_A, include_rc=fixture in {"revised_sl", "missing_rc"}, include_eod=include_eod),
        subscriptions=subscriptions,
        position_streams={fixture: runtime._position_stream(runtime.POSITION_A, fixture)},
    )


def _event(
    label: str,
    event_type: RuntimeEventType,
    sequence: int,
    *,
    instrument: str = runtime.NIFTY,
    contract: str | None = None,
    payload: dict | None = None,
) -> NormalizedRuntimeEvent:
    return runtime._event(label, event_type, sequence, instrument=instrument, contract=contract, payload=payload)


def _ts() -> datetime:
    return datetime(2026, 7, 30, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
