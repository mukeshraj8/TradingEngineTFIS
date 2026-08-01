from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tfis.adapters.phase4f import execute_s23_internal_paper_case
from tfis.adapters.phase4h import execute_phase4h_s23_case, execute_phase4h_two_account_case
from tfis.internal_position import (
    InternalPaperPositionState,
    LifecycleRequirementType,
    PositionCycleCoordinator,
    PositionCycleCoordinatorError,
)
from tfis.internal_position.reports import write_phase4h_reports
from tfis.persistence import OptimisticConcurrencyError, PersistenceDatabase, UnitOfWork


def test_position_cycle_identity_first_fill_and_acknowledgement_boundary() -> None:
    payload = execute_phase4h_s23_case("bull_open")
    projection = payload["projection"]

    assert projection["identity"]["authority_classification"] == "INTERNAL_PAPER_ONLY"
    assert projection["lifecycle_state"] == InternalPaperPositionState.OPEN_UNPROTECTED.value
    assert projection["confirmed_entry_quantity"] == projection["remaining_quantity"] > 0
    assert projection["entry_fill_ids"]
    assert payload["transition"]["event"]["event_type"] == "ENTRY_FULL_FILL_APPLIED"
    assert payload["broker_live_authority"] == "NONE"


def test_partial_entry_fill_weighted_average_and_protection_resize() -> None:
    payload = execute_phase4h_s23_case("partial_fill")

    assert payload["first_partial"]["projection"]["lifecycle_state"] == "ENTRY_PARTIALLY_FILLED"
    assert payload["first_partial"]["projection"]["remaining_quantity"] < payload["second_fill"]["projection"]["remaining_quantity"]
    assert payload["second_fill"]["projection"]["realized_quantity"] == 0
    assert payload["projection"]["average_entry_price"] == payload["first_partial"]["projection"]["average_entry_price"]
    assert payload["protection_resize_observed"] is True


@pytest.mark.parametrize(
    ("case_name", "event_type"),
    [
        ("target_close", "TARGET_EXIT_APPLIED"),
        ("original_sl_close", "SL_EXIT_APPLIED"),
        ("revised_sl_close", "SL_EXIT_APPLIED"),
        ("eod_exit", "EOD_EXIT_APPLIED"),
    ],
)
def test_exit_fills_reduce_quantity_and_close_only_after_fill(case_name: str, event_type: str) -> None:
    payload = execute_phase4h_s23_case(case_name)
    projection = payload["projection"]

    assert projection["remaining_quantity"] == 0
    assert projection["realized_quantity"] == projection["confirmed_entry_quantity"]
    assert projection["lifecycle_state"] == InternalPaperPositionState.CLOSED.value
    assert payload["transition"]["event"]["event_type"] == event_type


def test_eod_unfilled_carry_forward_equality_and_next_day_recovery() -> None:
    unfilled = execute_phase4h_s23_case("eod_unfilled")
    carry = execute_phase4h_s23_case("carry_forward")
    recovery = execute_phase4h_s23_case("next_day_recovery")

    assert unfilled["projection"]["lifecycle_state"] == "EXIT_PENDING"
    assert carry["projection"]["lifecycle_state"] == "CARRIED_FORWARD"
    assert carry["projection"]["carry_forward_status"] == "EOD_EQUAL_OR_BELOW_ORIGINAL_SL_CARRY_FORWARD"
    assert carry["evidence"]["equality_behavior"] == "CARRY_FORWARD"
    assert recovery["evidence"]["recovery"]["status"] == "CARRIED_POSITION_RECOVERABLE"


def test_multiple_accounts_and_positions_are_isolated() -> None:
    result = execute_phase4h_two_account_case()
    first = execute_phase4h_s23_case("bull_open")["projection"]
    second = execute_phase4h_s23_case("bear_open")["projection"]

    assert result["isolation"] == "PASSED"
    assert result["position_cycles_independent"] is True
    assert result["broker_accounts_independent"] is True
    assert first["identity"]["position_cycle_id"] != second["identity"]["position_cycle_id"]


def test_fail_closed_wrong_account_wrong_contract_overexit_stale_generation_and_closed_mutation() -> None:
    coordinator = PositionCycleCoordinator()
    payload = execute_s23_internal_paper_case("bull_entry_full")
    intent = payload["intent"]
    order = dict(payload["client_order"]) | {"lot_size": intent["instrument"]["lot_size"], "multiplier": intent["instrument"]["multiplier"], "currency": intent["instrument"]["currency"]}
    fill = payload["result"]["fills"][0]
    identity = coordinator.build_identity(
        trading_session_id=intent["trading_session_id"],
        originating_trading_date=date.fromisoformat(intent["trading_date"]),
        broker_account_id=order["broker_account_id"],
        logical_account_reference="INTERNAL_PAPER_ACCOUNT",
        strategy_family_id=intent["strategy_family_id"],
        strategy_definition_id=intent["strategy_definition_id"],
        strategy_version=intent["strategy_version"],
        strategy_instance_id=intent["strategy_instance_id"],
        originating_execution_plan_id=intent["source_artifact_id"],
        originating_entry_execution_intent_id=intent["execution_intent_id"],
        normalized_contract=order["normalized_contract"],
        direction="CALL_SIDE_VERTICAL",
        side=order["side"],
    )

    with pytest.raises(PositionCycleCoordinatorError):
        coordinator.apply_entry_fill(None, identity=identity, client_order=order, fill=dict(fill) | {"broker_account_id": "wrong"}, requested_quantity=order["quantity"], source_rule_ids=("rule",))
    with pytest.raises(PositionCycleCoordinatorError):
        coordinator.apply_entry_fill(None, identity=identity, client_order=order, fill=dict(fill) | {"contract": "wrong"}, requested_quantity=order["quantity"], source_rule_ids=("rule",))
    opened = coordinator.apply_entry_fill(None, identity=identity, client_order=order, fill=fill, requested_quantity=order["quantity"], source_rule_ids=("rule",))
    exit_order = {
        "client_order_id": "exit",
        "order_purpose": "TARGET",
        "position_cycle_id": identity.position_cycle_id,
        "authorized_time": "2026-06-05T10:00:00+05:30",
    }
    exit_fill = dict(fill) | {"internal_fill_id": "exit-fill", "client_order_id": "exit", "position_cycle_id": identity.position_cycle_id, "side": "BUY", "fill_quantity": order["quantity"] + 1}
    with pytest.raises(PositionCycleCoordinatorError):
        coordinator.apply_exit_fill(opened.projection, client_order=exit_order, fill=exit_fill, source_rule_ids=("rule",))
    closed = execute_phase4h_s23_case("target_close")["projection"]
    with pytest.raises(PositionCycleCoordinatorError):
        coordinator.record_carry_forward(_projection_from_payload(closed), next_trading_session_id="NSE:next", source_rule_id="rule", observed_price=Decimal("1"), original_sl=Decimal("1"), timestamp=datetime.now())


def test_consistency_and_pnl_input_facts() -> None:
    result = execute_phase4h_s23_case("consistency")

    assert result["evidence"]["consistency"]["status"] == "MATCHED"
    assert result["evidence"]["pnl_input_facts"]["entry_fill_ids"]
    assert result["evidence"]["pnl_input_facts"]["remaining_quantity"] > 0


def test_persistence_atomicity_idempotency_and_optimistic_concurrency(tmp_path: Path) -> None:
    payload = execute_phase4h_s23_case("bull_open")
    db = PersistenceDatabase(tmp_path / "phase4h.sqlite")
    projection = payload["projection"]
    identity = projection["identity"]
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(trading_session_id=identity["trading_session_id"], trading_date=date.fromisoformat(identity["originating_trading_date"]), market="NSE", timezone_name="Asia/Kolkata", payload={})
        repo.put_broker_account_identity(broker_account_id=identity["broker_account_id"], provider="fixture", environment="internal_paper", account_hash="acct", payload={})
        repo.put_strategy_instance(strategy_instance_id=identity["strategy_instance_id"], strategy_definition_id=identity["strategy_definition_id"], strategy_version=identity["strategy_version"], configuration_hash="phase4h", payload={})
        repo.put_position_cycle_identity(position_cycle_id=identity["position_cycle_id"], strategy_instance_id=identity["strategy_instance_id"], trading_session_id=identity["trading_session_id"], payload=identity)
        repo.put_internal_position_transition(transition=payload["transition"], expected_projection_version=0)
        repo.put_internal_position_transition(transition=payload["transition"], expected_projection_version=None)
    with pytest.raises(OptimisticConcurrencyError):
        with UnitOfWork(db) as uow:
            mutated = dict(payload["transition"])
            mutated["projection"] = dict(payload["projection"]) | {"remaining_quantity": payload["projection"]["remaining_quantity"] + 1, "projection_hash": "different"}
            uow.repo.put_internal_position_transition(transition=mutated, expected_projection_version=0)
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM internal_position_cycle_projections").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_reports_are_generated(tmp_path: Path) -> None:
    written = write_phase4h_reports(tmp_path / "reports", tmp_path / "phase4h.sqlite")

    assert "phase4h_summary.md" in written
    assert (tmp_path / "reports" / "phase4h_position_cycle_contract.json").exists()
    assert "PHASE4H_M1_ACCEPT" in (tmp_path / "reports" / "phase4h_summary.md").read_text(encoding="utf-8")


def _projection_from_payload(payload):
    from tfis.adapters.phase4h.s23_position_cycle import _projection

    return _projection(payload)
