from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tfis.adapters.phase4f import build_s23_account_snapshot, build_s23_internal_paper_grant, build_scenario, execute_s23_internal_paper_case, execute_two_account_case
from tfis.execution_intent import IntentValidationDecision
from tfis.execution_intent.reports import build_phase4e_fixture_set
from tfis.internal_paper import (
    AccountCoordinator,
    AccountCoordinatorEnvironment,
    AccountCoordinatorError,
    DeterministicInternalPaperAdapter,
    InternalPaperExecutionScenario,
    InternalPaperOrderEvent,
    InternalPaperOrderEventType,
    InternalPaperOrderState,
    SequentialAccountIntentCandidate,
    SequentialAccountIntentProcessor,
    assess_internal_paper_consistency,
    assess_internal_paper_recovery,
    create_creation_event,
)
from tfis.internal_paper.reports import write_phase4f_reports
from tfis.persistence import IdempotencyConflictError, PersistenceDatabase, UnitOfWork


def _entry():
    return build_phase4e_fixture_set()["valid_bull_call_entry"]


def _coordinator(intent):
    return AccountCoordinator(
        AccountCoordinator.build_identity(broker_account_id=intent.broker_account_id, trading_session_id=intent.trading_session_id),
        build_s23_account_snapshot(intent.broker_account_id),
    )


def test_account_coordinator_identity_and_environment() -> None:
    intent, _ = _entry()
    identity = AccountCoordinator.build_identity(broker_account_id=intent.broker_account_id, trading_session_id=intent.trading_session_id)

    assert identity.environment is AccountCoordinatorEnvironment.INTERNAL_PAPER_ONLY
    assert identity.coordinator_hash == AccountCoordinator.build_identity(broker_account_id=intent.broker_account_id, trading_session_id=intent.trading_session_id).coordinator_hash
    with pytest.raises(ValueError):
        AccountCoordinator.build_identity(broker_account_id=intent.broker_account_id, trading_session_id=intent.trading_session_id, environment=AccountCoordinatorEnvironment.LIVE)


def test_grant_required_scope_and_invalid_intent_blocks() -> None:
    intent, validation = _entry()
    coordinator = _coordinator(intent)
    grant = build_s23_internal_paper_grant(intent)

    with pytest.raises(AccountCoordinatorError):
        coordinator.create_client_order(intent=intent, validation_result=validation, grant=None, evaluated_at=intent.action.authorized_not_before)
    with pytest.raises(AccountCoordinatorError):
        coordinator.create_client_order(intent=intent, validation_result=validation, grant=replace(grant, broker_account_id="wrong"), evaluated_at=intent.action.authorized_not_before)
    with pytest.raises(AccountCoordinatorError):
        coordinator.create_client_order(intent=intent, validation_result=replace(validation, decision=IntentValidationDecision.BLOCKED), grant=grant, evaluated_at=intent.action.authorized_not_before)


def test_client_order_immutability_deterministic_id_and_no_broker_fields() -> None:
    intent, validation = _entry()
    grant = build_s23_internal_paper_grant(intent)
    first = _coordinator(intent).create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=intent.action.authorized_not_before)
    second = _coordinator(intent).create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=intent.action.authorized_not_before)

    assert first.client_order_id == second.client_order_id
    assert first.order_hash == second.order_hash
    assert "broker_order_id" not in str(first.to_dict())
    assert "exchange_order_id" not in str(first.to_dict())
    with pytest.raises(FrozenInstanceError):
        first.client_order_id = "mutated"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("case_name", "state"),
    [
        ("bull_entry_full", InternalPaperOrderState.FILLED_INTERNAL),
        ("bear_entry_ack_full", InternalPaperOrderState.FILLED_INTERNAL),
        ("bull_gap_partial_full", InternalPaperOrderState.FILLED_INTERNAL),
        ("entry_margin_rejected", InternalPaperOrderState.REJECTED_INTERNAL),
        ("target_ack", InternalPaperOrderState.PARTIALLY_FILLED_INTERNAL),
        ("original_sl_ack", InternalPaperOrderState.PARTIALLY_FILLED_INTERNAL),
        ("revised_sl_replace_ack", InternalPaperOrderState.CANCELLED_INTERNAL),
        ("revised_sl_old_fills_before_cancel", InternalPaperOrderState.FILLED_INTERNAL),
        ("eod_exit_full", InternalPaperOrderState.FILLED_INTERNAL),
    ],
)
def test_s23_first_slice_scenarios(case_name: str, state: InternalPaperOrderState) -> None:
    payload = execute_s23_internal_paper_case(case_name)

    assert payload["result"]["final_state"] == state.value
    assert payload["client_order"]["broker_submission_permitted"] is False
    assert payload["client_order"]["live_submission_permitted"] is False
    assert all(event["authority_source"] == "INTERNAL_PAPER_SIMULATION" for event in payload["result"]["events"])


def test_no_fill_cancel_before_fill_and_fill_before_cancel_race() -> None:
    intent, validation = _entry()
    grant = build_s23_internal_paper_grant(intent)
    coordinator = _coordinator(intent)
    order = coordinator.create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=intent.action.authorized_not_before)
    adapter = DeterministicInternalPaperAdapter()

    no_fill = adapter.execute(order, build_scenario(intent, InternalPaperExecutionScenario.NO_FILL_BEFORE_EXPIRY), build_s23_account_snapshot(intent.broker_account_id))
    cancel = adapter.execute(order, build_scenario(intent, InternalPaperExecutionScenario.CANCEL_BEFORE_FILL), build_s23_account_snapshot(intent.broker_account_id))
    race = adapter.execute(order, build_scenario(intent, InternalPaperExecutionScenario.FILL_BEFORE_CANCEL_CONFIRMATION), build_s23_account_snapshot(intent.broker_account_id))

    assert no_fill.final_state is InternalPaperOrderState.EXPIRED_INTERNAL
    assert cancel.final_state is InternalPaperOrderState.CANCELLED_INTERNAL
    assert race.final_state is InternalPaperOrderState.FILLED_INTERNAL


def test_duplicate_event_idempotency_conflict_fill_quantity_cap_and_transition() -> None:
    intent, validation = _entry()
    grant = build_s23_internal_paper_grant(intent)
    coordinator = _coordinator(intent)
    order = coordinator.create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=intent.action.authorized_not_before)
    event = create_creation_event(order, intent.action.authorized_not_before)

    assert coordinator.record_event(event) is event
    assert coordinator.record_event(event) is event
    with pytest.raises(AccountCoordinatorError):
        coordinator.record_event(replace(event, reason="changed"))
    bad = replace(event, event_id="bad-event", previous_state=InternalPaperOrderState.CREATED, cumulative_filled_quantity=order.quantity + 1)
    with pytest.raises(AccountCoordinatorError):
        coordinator.record_event(bad)


def test_paper_margin_reservation_and_insufficient_margin_rejection() -> None:
    intent, validation = _entry()
    grant = build_s23_internal_paper_grant(intent)
    order = _coordinator(intent).create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=intent.action.authorized_not_before)
    adapter = DeterministicInternalPaperAdapter()

    reserved = adapter.reserve_margin(order, build_s23_account_snapshot(intent.broker_account_id))
    assert reserved.available_paper_margin < Decimal("1000000")
    with pytest.raises(AccountCoordinatorError):
        adapter.reserve_margin(order, build_s23_account_snapshot(intent.broker_account_id, available_margin=Decimal("1")))


def test_stale_protection_generation_and_replacement_without_old_order_fail_closed() -> None:
    intent, validation = build_phase4e_fixture_set()["valid_revised_sl"]
    grant = build_s23_internal_paper_grant(intent)
    coordinator = _coordinator(intent)

    with pytest.raises(AccountCoordinatorError):
        coordinator.create_client_order(intent=replace(intent, action=replace(intent.action, protection_generation=0)), validation_result=validation, grant=replace(grant, allowed_intent_purposes=("ENTRY",)), evaluated_at=intent.action.authorized_not_before)


def test_persistence_atomicity_rollback_recovery_and_consistency(tmp_path: Path) -> None:
    payload = execute_s23_internal_paper_case("bull_entry_full")
    db = PersistenceDatabase(tmp_path / "phase4f.sqlite")
    intent = payload["intent"]
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(trading_session_id=intent["trading_session_id"], trading_date=__import__("datetime").date.fromisoformat(intent["trading_date"]), market="NSE", timezone_name="Asia/Kolkata", payload={})
        repo.put_broker_account_identity(broker_account_id=intent["broker_account_id"], provider="fixture", environment="internal_paper", account_hash="acct", payload={})
        repo.put_strategy_instance(strategy_instance_id=intent["strategy_instance_id"], strategy_definition_id=intent["strategy_definition_id"], strategy_version=intent["strategy_version"], configuration_hash=intent["evidence"]["configuration_hash"], payload={})
        repo.put_internal_paper_result(grant=_Obj(payload["grant"]), result=_Obj(payload["result"]), expected_account_projection_version=0)
        repo.put_internal_paper_result(grant=_Obj(payload["grant"]), result=_Obj(payload["result"]), expected_account_projection_version=None)
    with pytest.raises(RuntimeError):
        with UnitOfWork(db) as uow:
            uow.repo.put_internal_paper_result(grant=_Obj(payload["grant"]), result=_Obj(execute_s23_internal_paper_case("bear_entry_ack_full")["result"]), expected_account_projection_version=0)
            raise RuntimeError("rollback")
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM internal_client_order_records").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM internal_paper_fills").fetchone()[0] == 1
    assert assess_internal_paper_recovery(active_order_count=1, fill_count=1, latest_event_sequence=3).status.value == "INTERNAL_PAPER_RECOVERABLE"
    assert assess_internal_paper_consistency(persisted_order_count=1, persisted_event_count=3, persisted_fill_count=1, projection_count=1).status.value == "MATCHED"


def test_multi_account_and_multiple_order_isolation() -> None:
    result = execute_two_account_case()
    fixtures = build_phase4e_fixture_set()
    entry_intent, entry_validation = fixtures["valid_bull_call_entry"]
    target_intent, target_validation = fixtures["valid_target"]
    grant = build_s23_internal_paper_grant(entry_intent)
    coordinator = _coordinator(entry_intent)
    entry_order = coordinator.create_client_order(intent=entry_intent, validation_result=entry_validation, grant=grant, evaluated_at=entry_intent.action.authorized_not_before)
    target_order = coordinator.create_client_order(intent=target_intent, validation_result=target_validation, grant=build_s23_internal_paper_grant(target_intent), evaluated_at=target_intent.action.authorized_not_before)

    assert result["isolation"] == "PASSED"
    assert result["account_b_blocked_error"]
    assert entry_order.client_order_id != target_order.client_order_id
    assert entry_order.order_purpose == "ENTRY"
    assert target_order.order_purpose == "TARGET"


def test_position_cycle_update_candidate_has_no_authority() -> None:
    payload = execute_s23_internal_paper_case("bull_entry_full")
    candidate = payload["result"]["position_update_candidates"][0]

    assert candidate["authority_mode"] == "INTERNAL_PAPER_ONLY"
    assert candidate["update_permitted"] is False


def test_reports_are_generated(tmp_path: Path) -> None:
    written = write_phase4f_reports(tmp_path / "reports", tmp_path / "phase4f.sqlite")

    assert "phase4f_summary.md" in written
    assert "PHASE4F_M1_CONDITIONAL" in (tmp_path / "reports" / "phase4f_summary.md").read_text(encoding="utf-8")
    assert (tmp_path / "reports" / "phase4f_full_suite_failure_classification.json").exists()


def test_sequential_same_account_two_intents_with_sufficient_margin_are_processed_in_order() -> None:
    processor = SequentialAccountIntentProcessor()
    first = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:reliance",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1200,
        sequence=2,
        scenario=InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN,
        qualification_offset_seconds=0,
        fill_quantity=600,
    )
    second = _candidate(
        "valid_bear_call_entry",
        strategy_instance_id="S22_TCS_INTERNAL_PAPER_A",
        execution_intent_id="intent:tcs",
        contract="NSE:TCS26AUG4500CE",
        quantity=1000,
        sequence=3,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        qualification_offset_seconds=5,
    )

    result = processor.process(
        [second, first],
        account_snapshots={
            first.intent.broker_account_id: build_s23_account_snapshot(
                first.intent.broker_account_id,
                available_margin=Decimal("300000"),
            )
        },
    )[first.intent.broker_account_id]

    assert result.ordered_intent_ids == ("intent:reliance", "intent:tcs")
    assert [item.decision for item in result.outcomes] == [
        "PROCESSED_INTERNAL_PAPER",
        "PROCESSED_INTERNAL_PAPER",
    ]
    assert result.outcomes[0].queue_position == 1
    assert result.outcomes[1].queue_position == 2
    assert result.outcomes[0].required_margin == Decimal("120000")
    assert result.outcomes[1].required_margin == Decimal("100000")
    assert result.outcomes[0].effective_available_margin == Decimal("300000")
    assert result.outcomes[1].effective_available_margin == Decimal("180000")
    assert result.final_account_snapshot.active_order_reservation == Decimal("120000")
    assert result.final_account_snapshot.reserved_margin == Decimal("120000")
    assert result.final_account_snapshot.available_paper_margin == Decimal("180000")
    assert all(item.client_order_id for item in result.outcomes)
    assert result.external_broker_order_authority == "NONE"


def test_sequential_same_account_insufficient_margin_yields_warning_not_exception() -> None:
    processor = SequentialAccountIntentProcessor()
    first = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:reliance",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1200,
        sequence=1,
        scenario=InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN,
        fill_quantity=600,
    )
    second = _candidate(
        "valid_bear_call_entry",
        strategy_instance_id="S22_TCS_INTERNAL_PAPER_A",
        execution_intent_id="intent:tcs",
        contract="NSE:TCS26AUG4500CE",
        quantity=1000,
        sequence=2,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        qualification_offset_seconds=1,
    )

    result = processor.process(
        [first, second],
        account_snapshots={
            first.intent.broker_account_id: build_s23_account_snapshot(
                first.intent.broker_account_id,
                available_margin=Decimal("180000"),
            )
        },
    )[first.intent.broker_account_id]

    assert result.outcomes[0].decision == "PROCESSED_INTERNAL_PAPER"
    assert result.outcomes[1].decision == "ORDER_NOT_SUBMITTED_INSUFFICIENT_MARGIN"
    assert result.outcomes[1].warning is not None
    assert result.outcomes[1].warning.severity == "WARNING"
    assert result.outcomes[1].warning.account == first.intent.broker_account_id
    assert result.outcomes[1].warning.strategy_instance_id == "S22_TCS_INTERNAL_PAPER_A"
    assert result.outcomes[1].warning.instrument == "NSE:TCS26AUG4500CE"
    assert result.outcomes[1].warning.required_margin == Decimal("100000")
    assert result.outcomes[1].warning.available_margin == Decimal("180000")
    assert result.outcomes[1].warning.effective_available_margin == Decimal("60000")
    assert result.outcomes[1].warning.shortfall == Decimal("40000")
    assert result.outcomes[1].client_order_id is None
    assert result.final_account_snapshot.active_order_reservation == Decimal("120000")


def test_rejection_releases_reservation_and_next_intent_can_proceed() -> None:
    processor = SequentialAccountIntentProcessor()
    first = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:reliance-reject",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1200,
        sequence=1,
        scenario=InternalPaperExecutionScenario.REJECTED_INVALID_PRICE,
    )
    second = _candidate(
        "valid_bear_call_entry",
        strategy_instance_id="S22_TCS_INTERNAL_PAPER_A",
        execution_intent_id="intent:tcs-after-reject",
        contract="NSE:TCS26AUG4500CE",
        quantity=1000,
        sequence=2,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        qualification_offset_seconds=1,
    )

    result = processor.process(
        [first, second],
        account_snapshots={
            first.intent.broker_account_id: build_s23_account_snapshot(
                first.intent.broker_account_id,
                available_margin=Decimal("180000"),
            )
        },
    )[first.intent.broker_account_id]

    assert result.outcomes[0].final_state == "REJECTED_INTERNAL"
    assert result.outcomes[0].reservation_created is True
    assert result.outcomes[0].reservation_released is True
    assert result.outcomes[1].decision == "PROCESSED_INTERNAL_PAPER"
    assert result.outcomes[1].effective_available_margin == Decimal("180000")
    assert result.final_account_snapshot.active_order_reservation == Decimal("0")
    assert result.final_account_snapshot.available_paper_margin == Decimal("180000")


def test_partial_open_reservation_is_reconciled_without_double_reservation() -> None:
    processor = SequentialAccountIntentProcessor()
    first = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:reliance-open",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1200,
        sequence=1,
        scenario=InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN,
        fill_quantity=600,
    )
    second = _candidate(
        "valid_bear_call_entry",
        strategy_instance_id="S22_TCS_INTERNAL_PAPER_A",
        execution_intent_id="intent:tcs-fill",
        contract="NSE:TCS26AUG4500CE",
        quantity=1000,
        sequence=2,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        qualification_offset_seconds=1,
    )

    result = processor.process(
        [first, second],
        account_snapshots={
            first.intent.broker_account_id: build_s23_account_snapshot(
                first.intent.broker_account_id,
                available_margin=Decimal("250000"),
            )
        },
    )[first.intent.broker_account_id]

    assert result.outcomes[0].final_state == "PARTIALLY_FILLED_INTERNAL"
    assert result.outcomes[0].reservation_released is False
    assert result.outcomes[1].decision == "PROCESSED_INTERNAL_PAPER"
    assert result.outcomes[1].effective_available_margin == Decimal("130000")
    assert result.final_account_snapshot.active_order_reservation == Decimal("120000")
    assert result.final_account_snapshot.reserved_margin == Decimal("120000")
    assert result.final_account_snapshot.available_paper_margin == Decimal("130000")


def test_exact_timestamp_tie_uses_sequence_then_strategy_id_deterministically() -> None:
    processor = SequentialAccountIntentProcessor()
    first = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_A",
        execution_intent_id="intent:a",
        contract="NSE:A26AUG100CE",
        quantity=100,
        sequence=7,
        scenario=InternalPaperExecutionScenario.REJECTED_INVALID_PRICE,
    )
    second = _candidate(
        "valid_bear_call_entry",
        strategy_instance_id="S21_B",
        execution_intent_id="intent:b",
        contract="NSE:B26AUG100CE",
        quantity=100,
        sequence=7,
        scenario=InternalPaperExecutionScenario.REJECTED_INVALID_PRICE,
    )

    first_run = processor.process(
        [first, second],
        account_snapshots={first.intent.broker_account_id: build_s23_account_snapshot(first.intent.broker_account_id)},
    )[first.intent.broker_account_id]
    second_run = processor.process(
        [second, first],
        account_snapshots={first.intent.broker_account_id: build_s23_account_snapshot(first.intent.broker_account_id)},
    )[first.intent.broker_account_id]

    assert first_run.ordered_intent_ids == ("intent:b", "intent:a")
    assert second_run.ordered_intent_ids == ("intent:b", "intent:a")
    assert first_run.result_hash == second_run.result_hash


def test_cross_account_isolation_and_account_halt_behavior() -> None:
    processor = SequentialAccountIntentProcessor()
    blocked = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:halted",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1200,
        sequence=1,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        broker_account_id="ACCOUNT_A",
    )
    allowed = _candidate(
        "valid_bear_call_entry",
        strategy_instance_id="S23_NIFTY_INTERNAL_PAPER_B",
        execution_intent_id="intent:other-account",
        contract="NIFTY_PHASE5C_PUT_FIXTURE",
        quantity=1000,
        sequence=1,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        broker_account_id="ACCOUNT_B",
    )

    results = processor.process(
        [blocked, allowed],
        account_snapshots={
            "ACCOUNT_A": build_s23_account_snapshot("ACCOUNT_A", blocked=True, available_margin=Decimal("300000")),
            "ACCOUNT_B": build_s23_account_snapshot("ACCOUNT_B", available_margin=Decimal("150000")),
        },
    )

    assert results["ACCOUNT_A"].outcomes[0].decision == "ACCOUNT_HALT_BLOCKED"
    assert results["ACCOUNT_A"].outcomes[0].warning is not None
    assert results["ACCOUNT_A"].lifecycle_protection_preserved is True
    assert results["ACCOUNT_B"].outcomes[0].decision == "PROCESSED_INTERNAL_PAPER"
    assert results["ACCOUNT_B"].external_broker_order_authority == "NONE"


def test_duplicate_replay_is_idempotent_and_conflicting_duplicate_fails_closed() -> None:
    processor = SequentialAccountIntentProcessor()
    first = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:dup",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1200,
        sequence=1,
        scenario=InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN,
        fill_quantity=600,
    )
    duplicate = first
    conflicting = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:dup",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1300,
        sequence=3,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
    )

    result = processor.process(
        [first, duplicate, conflicting],
        account_snapshots={
            first.intent.broker_account_id: build_s23_account_snapshot(
                first.intent.broker_account_id,
                available_margin=Decimal("300000"),
            )
        },
    )[first.intent.broker_account_id]

    assert result.outcomes[0].decision == "PROCESSED_INTERNAL_PAPER"
    assert result.outcomes[1].decision == "DUPLICATE_IDEMPOTENT_SKIPPED"
    assert result.outcomes[2].decision == "DUPLICATE_CONFLICT_FAIL_CLOSED"
    assert result.final_account_snapshot.active_order_reservation == Decimal("120000")
    assert result.final_account_snapshot.reserved_margin == Decimal("120000")


def test_three_stock_same_account_fan_out_remains_deterministic_and_recovery_safe() -> None:
    processor = SequentialAccountIntentProcessor()
    reliance = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:reliance-three",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1200,
        sequence=1,
        scenario=InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN,
        fill_quantity=600,
    )
    tcs = _candidate(
        "valid_bear_call_entry",
        strategy_instance_id="S22_TCS_INTERNAL_PAPER_A",
        execution_intent_id="intent:tcs-three",
        contract="NSE:TCS26AUG4500CE",
        quantity=1000,
        sequence=2,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        qualification_offset_seconds=1,
    )
    infy = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_INFY_INTERNAL_PAPER_A",
        execution_intent_id="intent:infy-three",
        contract="NSE:INFY26AUG1140CE",
        quantity=300,
        sequence=3,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        qualification_offset_seconds=2,
    )

    first_run = processor.process(
        [infy, reliance, tcs],
        account_snapshots={
            reliance.intent.broker_account_id: build_s23_account_snapshot(
                reliance.intent.broker_account_id,
                available_margin=Decimal("300000"),
            )
        },
    )[reliance.intent.broker_account_id]
    second_run = processor.process(
        [tcs, infy, reliance],
        account_snapshots={
            reliance.intent.broker_account_id: build_s23_account_snapshot(
                reliance.intent.broker_account_id,
                available_margin=Decimal("300000"),
            )
        },
    )[reliance.intent.broker_account_id]

    assert first_run.ordered_intent_ids == (
        "intent:reliance-three",
        "intent:tcs-three",
        "intent:infy-three",
    )
    assert [item.decision for item in first_run.outcomes] == [
        "PROCESSED_INTERNAL_PAPER",
        "PROCESSED_INTERNAL_PAPER",
        "PROCESSED_INTERNAL_PAPER",
    ]
    assert [item.queue_position for item in first_run.outcomes] == [1, 2, 3]
    assert [item.instrument for item in first_run.outcomes] == [
        "NSE:RELIANCE26AUG2400CE",
        "NSE:TCS26AUG4500CE",
        "NSE:INFY26AUG1140CE",
    ]
    assert first_run.outcomes[0].effective_available_margin == Decimal("300000")
    assert first_run.outcomes[1].effective_available_margin == Decimal("180000")
    assert first_run.outcomes[2].effective_available_margin == Decimal("180000")
    assert first_run.final_account_snapshot.active_order_reservation == Decimal("120000")
    assert first_run.final_account_snapshot.reserved_margin == Decimal("120000")
    assert first_run.final_account_snapshot.available_paper_margin == Decimal("180000")
    assert first_run.lifecycle_protection_preserved is True
    assert first_run.external_broker_order_authority == "NONE"
    assert first_run.result_hash == second_run.result_hash


def test_three_stock_same_account_insufficient_margin_blocks_one_and_continues_safely() -> None:
    processor = SequentialAccountIntentProcessor()
    reliance = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_RELIANCE_INTERNAL_PAPER_A",
        execution_intent_id="intent:reliance-margin",
        contract="NSE:RELIANCE26AUG2400CE",
        quantity=1200,
        sequence=1,
        scenario=InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN,
        fill_quantity=600,
    )
    tcs = _candidate(
        "valid_bear_call_entry",
        strategy_instance_id="S22_TCS_INTERNAL_PAPER_A",
        execution_intent_id="intent:tcs-margin",
        contract="NSE:TCS26AUG4500CE",
        quantity=1000,
        sequence=2,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        qualification_offset_seconds=1,
    )
    infy = _candidate(
        "valid_bull_call_entry",
        strategy_instance_id="S22_INFY_INTERNAL_PAPER_A",
        execution_intent_id="intent:infy-margin",
        contract="NSE:INFY26AUG1140CE",
        quantity=300,
        sequence=3,
        scenario=InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL,
        qualification_offset_seconds=2,
    )

    result = processor.process(
        [reliance, tcs, infy],
        account_snapshots={
            reliance.intent.broker_account_id: build_s23_account_snapshot(
                reliance.intent.broker_account_id,
                available_margin=Decimal("200000"),
            )
        },
    )[reliance.intent.broker_account_id]

    assert result.ordered_intent_ids == (
        "intent:reliance-margin",
        "intent:tcs-margin",
        "intent:infy-margin",
    )
    assert [item.decision for item in result.outcomes] == [
        "PROCESSED_INTERNAL_PAPER",
        "ORDER_NOT_SUBMITTED_INSUFFICIENT_MARGIN",
        "PROCESSED_INTERNAL_PAPER",
    ]
    assert result.outcomes[1].warning is not None
    assert result.outcomes[1].warning.strategy_instance_id == "S22_TCS_INTERNAL_PAPER_A"
    assert result.outcomes[1].warning.shortfall == Decimal("20000")
    assert result.outcomes[2].strategy_instance_id == "S22_INFY_INTERNAL_PAPER_A"
    assert result.outcomes[2].effective_available_margin == Decimal("80000")
    assert result.final_account_snapshot.active_order_reservation == Decimal("120000")
    assert result.final_account_snapshot.available_paper_margin == Decimal("80000")


class _Obj:
    def __init__(self, data):
        self.data = data

    def to_dict(self):
        return self.data


def _candidate(
    fixture_name: str,
    *,
    strategy_instance_id: str,
    execution_intent_id: str,
    contract: str,
    quantity: int,
    sequence: int,
    scenario: InternalPaperExecutionScenario,
    qualification_offset_seconds: int = 0,
    fill_quantity: int | None = None,
    broker_account_id: str = "INTERNAL_PAPER_ACCOUNT_A",
) -> SequentialAccountIntentCandidate:
    intent, validation = build_phase4e_fixture_set()[fixture_name]
    qualification_timestamp = intent.action.authorized_not_before + timedelta(seconds=qualification_offset_seconds)
    intent = replace(
        intent,
        execution_intent_id=execution_intent_id,
        strategy_instance_id=strategy_instance_id,
        broker_account_id=broker_account_id,
        idempotency_key=f"idem:{execution_intent_id}",
        instrument=replace(intent.instrument, contract=contract, underlying=contract.split(":")[-1].split("26")[0]),
        action=replace(intent.action, requested_quantity=quantity),
    )
    validation = replace(
        validation,
        execution_intent_id=intent.execution_intent_id,
        intent_hash=intent.intent_hash,
    )
    grant = build_s23_internal_paper_grant(intent, maximum_quantity=max(5000, quantity))
    return SequentialAccountIntentCandidate(
        intent=intent,
        validation_result=validation,
        grant=grant,
        scenario=build_scenario(
            intent,
            scenario,
            scenario_id=f"{execution_intent_id}:{scenario.value}",
            fill_quantity=fill_quantity,
        ),
        qualification_timestamp=qualification_timestamp,
        intent_creation_sequence=sequence,
    )
