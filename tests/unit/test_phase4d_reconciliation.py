from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pytest

from tfis.persistence import ArtifactConflictError, PersistenceDatabase, UnitOfWork, canonical_hash
from tfis.persistence.recovery import assess_recovery
from tfis.reconciliation import (
    BrokerObservedFill,
    BrokerObservedOrder,
    BrokerObservedPosition,
    LocalExpectedFill,
    LocalExpectedOrder,
    LocalExpectedPosition,
    LocalExpectedProtection,
    ReconciliationClassification,
    ReconciliationEngine,
    ReconciliationInput,
    ReconciliationScope,
    RepairRecommendationCode,
    build_s23_first_slice_reconciliation_input,
)
from tfis.reconciliation.reports import write_phase4d_reports


def _base(name: str = "base") -> ReconciliationInput:
    return ReconciliationInput(
        reconciliation_id=f"rec-{name}",
        broker_account_id="acct-a",
        trading_session_id="session-2026-06-05",
        scope=ReconciliationScope.STARTUP_ACCOUNT,
        as_of=datetime.fromisoformat("2026-06-05T09:16:00+05:30"),
        local_state_version=1,
        broker_snapshot_hash=f"broker-{name}",
        reconciliation_policy_version="phase4d.v1",
        account_payload={"broker_account_id": "acct-a", "session_status": "AUTHENTICATED", "completeness": "COMPLETE"},
    )


def _order_pair() -> tuple[LocalExpectedOrder, BrokerObservedOrder]:
    return (
        LocalExpectedOrder("lo-1", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, "OPEN", "ENTRY", "client-1", "bo-1", "xo-1", limit_price=100.0),
        BrokerObservedOrder("bo-1", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, "OPEN", "ENTRY", "client-1", "xo-1", limit_price=100.0),
    )


def _classifications(result) -> set[str]:  # type: ignore[no-untyped-def]
    return {item.classification.value for item in result.items}


def test_account_empty_match_partial_stale_unavailable_and_mismatch() -> None:
    engine = ReconciliationEngine()

    assert engine.reconcile(_base("empty")).account_status.value == "RECONCILED_READY"
    assert "INSUFFICIENT_EVIDENCE" in _classifications(engine.reconcile(replace(_base("partial"), account_payload={"broker_account_id": "acct-a", "session_status": "AUTHENTICATED", "completeness": "PARTIAL"})))
    assert "BROKER_STATE_UNAVAILABLE" in _classifications(engine.reconcile(replace(_base("unavailable"), account_payload={"broker_account_id": "acct-a", "session_status": "UNAUTHORIZED", "completeness": "UNAVAILABLE"})))
    assert "MANUAL_REVIEW_REQUIRED" in _classifications(engine.reconcile(replace(_base("mismatch"), account_payload={"broker_account_id": "acct-b", "session_status": "AUTHENTICATED", "completeness": "COMPLETE"})))
    stale = engine.reconcile(replace(_base("stale"), account_payload={"broker_account_id": "acct-a", "session_status": "AUTHENTICATED", "completeness": "COMPLETE", "captured_at": datetime.fromisoformat("2026-06-05T09:00:00+05:30")}))
    assert "STALE_BROKER_ORDER" in _classifications(stale)


def test_order_match_broker_only_local_only_status_quantity_price_and_linkage() -> None:
    engine = ReconciliationEngine()
    local, broker = _order_pair()

    assert "MATCHED" in _classifications(engine.reconcile(replace(_base("order_match"), local_orders=(local,), broker_orders=(broker,))))
    assert "BROKER_ONLY_ORDER" in _classifications(engine.reconcile(replace(_base("broker_only"), broker_orders=(broker,))))
    assert "LOCAL_ONLY_ORDER" in _classifications(engine.reconcile(replace(_base("local_only"), local_orders=(replace(local, status="SUBMITTED"),))))
    assert "ORDER_STATUS_MISMATCH" in _classifications(engine.reconcile(replace(_base("status"), local_orders=(local,), broker_orders=(replace(broker, status="FILLED"),))))
    assert "ORDER_QUANTITY_MISMATCH" in _classifications(engine.reconcile(replace(_base("qty"), local_orders=(local,), broker_orders=(replace(broker, quantity=50),))))
    assert "ORDER_PRICE_MISMATCH" in _classifications(engine.reconcile(replace(_base("price"), local_orders=(local,), broker_orders=(replace(broker, limit_price=101.0),))))
    ambiguous = BrokerObservedOrder("", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, "OPEN")
    assert "UNKNOWN_LINKAGE" in _classifications(engine.reconcile(replace(_base("ambiguous"), broker_orders=(ambiguous,))))
    duplicate = engine.reconcile(replace(_base("duplicate"), broker_orders=(broker, broker)))
    assert "DUPLICATE_BROKER_ORDER" in _classifications(duplicate)


def test_fill_match_broker_only_local_only_duplicate_quantity_and_price() -> None:
    engine = ReconciliationEngine()
    local = LocalExpectedFill("fill-1", "lo-1", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, 100.0, "bo-1")
    broker = BrokerObservedFill("fill-1", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, 100.0, "bo-1")

    assert "MATCHED" in _classifications(engine.reconcile(replace(_base("fill_match"), local_fills=(local,), broker_fills=(broker,))))
    assert "BROKER_ONLY_FILL" in _classifications(engine.reconcile(replace(_base("broker_fill"), broker_fills=(broker,))))
    assert "LOCAL_ONLY_FILL" in _classifications(engine.reconcile(replace(_base("local_fill"), local_fills=(local,))))
    assert "DUPLICATE_FILL" in _classifications(engine.reconcile(replace(_base("dup_fill"), broker_fills=(broker, broker))))
    assert "FILL_QUANTITY_MISMATCH" in _classifications(engine.reconcile(replace(_base("fill_qty"), local_fills=(local,), broker_fills=(replace(broker, quantity=50),))))
    assert "FILL_PRICE_MISMATCH" in _classifications(engine.reconcile(replace(_base("fill_price"), local_fills=(local,), broker_fills=(replace(broker, price=101.0),))))


def test_position_match_broker_only_local_only_quantity_direction_and_closed_open() -> None:
    engine = ReconciliationEngine()
    local = LocalExpectedPosition("pc-1", "acct-a", "NIFTY_20260609_22650_CE", -75, "SHORT", "NRML", "OPEN")
    broker = BrokerObservedPosition("acct-a", "NIFTY_20260609_22650_CE", -75, "SHORT", "NRML")

    assert "MATCHED" in _classifications(engine.reconcile(replace(_base("pos_match"), local_positions=(local,), broker_positions=(broker,))))
    assert "BROKER_ONLY_POSITION" in _classifications(engine.reconcile(replace(_base("broker_pos"), broker_positions=(broker,))))
    assert "LOCAL_ONLY_POSITION" in _classifications(engine.reconcile(replace(_base("local_pos"), local_positions=(local,))))
    assert "POSITION_QUANTITY_MISMATCH" in _classifications(engine.reconcile(replace(_base("pos_qty"), local_positions=(local,), broker_positions=(replace(broker, net_quantity=-50),))))
    assert "POSITION_DIRECTION_MISMATCH" in _classifications(engine.reconcile(replace(_base("pos_dir"), local_positions=(local,), broker_positions=(replace(broker, net_quantity=75, side="LONG"),))))
    assert "LOCAL_CLOSED_BROKER_OPEN" in _classifications(engine.reconcile(replace(_base("closed_open"), local_positions=(replace(local, status="CLOSED"),), broker_positions=(broker,))))


def test_protection_missing_duplicate_stale_quantity_price_generation_and_match() -> None:
    engine = ReconciliationEngine()
    protection = LocalExpectedProtection("sl-1", "pc-1", "acct-a", "NIFTY_20260609_22650_CE", "REVISED_SL", "BUY", 75, 130.0, 2)
    broker = BrokerObservedOrder("sl-broker", "acct-a", "NIFTY_20260609_22650_CE", "BUY", 75, "OPEN", "REVISED_SL", trigger_price=130.0, protection_generation=2)

    assert "PROTECTION_MATCHED" in _classifications(engine.reconcile(replace(_base("prot_match"), local_protections=(protection,), broker_orders=(broker,))))
    assert "PROTECTION_MISSING" in _classifications(engine.reconcile(replace(_base("prot_missing"), local_protections=(protection,), broker_orders=())))
    assert "DUPLICATE_PROTECTION" in _classifications(engine.reconcile(replace(_base("prot_dup"), local_protections=(protection,), broker_orders=(broker, replace(broker, broker_order_id="sl-broker-2")))))
    assert "STALE_PROTECTION" in _classifications(engine.reconcile(replace(_base("prot_stale"), broker_orders=(broker,))))
    assert "PROTECTION_QUANTITY_MISMATCH" in _classifications(engine.reconcile(replace(_base("prot_qty"), local_protections=(protection,), broker_orders=(replace(broker, quantity=50),))))
    assert "PROTECTION_PRICE_MISMATCH" in _classifications(engine.reconcile(replace(_base("prot_price"), local_protections=(protection,), broker_orders=(replace(broker, trigger_price=131.0),))))
    assert "PROTECTION_GENERATION_MISMATCH" in _classifications(engine.reconcile(replace(_base("prot_gen"), local_protections=(protection,), broker_orders=(replace(broker, protection_generation=1),))))


def test_carried_position_s23_first_slice_and_mismatch() -> None:
    engine = ReconciliationEngine()
    matched = engine.reconcile(build_s23_first_slice_reconciliation_input())
    mismatch = engine.reconcile(build_s23_first_slice_reconciliation_input(mismatch=True))

    assert matched.carried_position_status is ReconciliationClassification.MATCHED
    assert matched.authority_gate.grants_authority is False
    assert "POSITION_QUANTITY_MISMATCH" in _classifications(mismatch)


def test_repair_recommendations_and_authority_gate_are_non_authoritative() -> None:
    engine = ReconciliationEngine()
    local, _ = _order_pair()
    result = engine.reconcile(replace(_base("repair"), local_orders=(local,)))

    assert RepairRecommendationCode.BLOCK_NEW_ENTRY.value in {item.code.value for item in result.repair_recommendations}
    assert result.authority_gate.recommendation.value in {"NEW_ENTRY_BLOCKED", "MANUAL_REVIEW_REQUIRED"}
    assert result.authority_gate.grants_authority is False
    assert all(item.execution_not_permitted for item in result.repair_recommendations)


def test_persisted_result_idempotency_conflict_and_rollback(tmp_path: Path) -> None:
    db = PersistenceDatabase(tmp_path / "phase4d.sqlite")
    result_input = _base("persist")
    result = ReconciliationEngine().reconcile(result_input)
    with UnitOfWork(db) as uow:
        uow.repo.put_trading_session(trading_session_id=result.trading_session_id, trading_date=date(2026, 6, 5), market="NSE", timezone_name="Asia/Kolkata", payload={})
        uow.repo.put_broker_account_identity(broker_account_id=result.broker_account_id, provider="fixture", environment="test", account_hash=result.broker_account_id, payload={"account_id": "AC***A"})
        assert uow.repo.put_reconciliation_result(reconciliation_result=result, reconciliation_input_hash=canonical_hash(result_input.to_dict()), expected_projection_version=0) == result.reconciliation_id
        assert uow.repo.put_reconciliation_result(reconciliation_result=result, reconciliation_input_hash=canonical_hash(result_input.to_dict()), expected_projection_version=1) == result.reconciliation_id
        with pytest.raises(ArtifactConflictError):
            uow.repo.put_reconciliation_result(reconciliation_result=replace(result, broker_snapshot_hash="different"), reconciliation_input_hash="different", expected_projection_version=1)
    with pytest.raises(RuntimeError):
        with UnitOfWork(db) as uow:
            uow.repo.put_reconciliation_result(reconciliation_result=ReconciliationEngine().reconcile(_base("rollback")), reconciliation_input_hash=canonical_hash(_base("rollback").to_dict()), expected_projection_version=0)
            raise RuntimeError("rollback")
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM reconciliation_results WHERE reconciliation_id='rec-rollback'").fetchone()[0] == 0


def test_recovery_integration_and_multi_account_isolation(tmp_path: Path) -> None:
    db = PersistenceDatabase(tmp_path / "phase4d.sqlite")
    with UnitOfWork(db) as uow:
        uow.repo.put_trading_session(trading_session_id="session-2026-06-05", trading_date=date(2026, 6, 5), market="NSE", timezone_name="Asia/Kolkata", payload={})
        for account in ("acct-a", "acct-b"):
            uow.repo.put_broker_account_identity(broker_account_id=account, provider="fixture", environment="test", account_hash=account, payload={"account_id": f"{account[:2]}***"})
            result_input = replace(_base(account), reconciliation_id=f"rec-{account}", broker_account_id=account, broker_snapshot_hash=f"hash-{account}")
            result = ReconciliationEngine().reconcile(result_input)
            uow.repo.put_reconciliation_result(reconciliation_result=result, reconciliation_input_hash=canonical_hash(result_input.to_dict()), expected_projection_version=0)
    with db.connect() as connection:
        assessment = assess_recovery(connection)
        assert assessment.status.value in {"RECONCILIATION_REQUIRED", "RECOVERABLE_OFFLINE"}
        assert connection.execute("SELECT COUNT(*) FROM latest_reconciliation_projection").fetchone()[0] == 2


def test_multiple_order_and_position_isolation_no_projection_repair() -> None:
    engine = ReconciliationEngine()
    local1, broker1 = _order_pair()
    local2 = replace(local1, local_order_id="lo-2", broker_order_id="bo-2", client_order_id="client-2", exchange_order_id="xo-2")
    pos1 = LocalExpectedPosition("pc-1", "acct-a", "C1", -75, "SHORT", "NRML", "OPEN")
    pos2 = LocalExpectedPosition("pc-2", "acct-a", "C2", -75, "SHORT", "NRML", "OPEN")
    result = engine.reconcile(replace(_base("isolation"), local_orders=(local1, local2), broker_orders=(broker1,), local_positions=(pos1, pos2), broker_positions=(BrokerObservedPosition("acct-a", "C1", -75, "SHORT", "NRML"),)))

    assert "LOCAL_ONLY_ORDER" in _classifications(result)
    assert "LOCAL_ONLY_POSITION" in _classifications(result)
    assert any(item.classification is ReconciliationClassification.MATCHED for item in result.items)


def test_reports_generated_and_phase4c_phase4b_regression(tmp_path: Path) -> None:
    written = write_phase4d_reports(tmp_path / "reports", tmp_path / "phase4d.sqlite")
    assert {
        "phase4d_reconciliation_audit.md",
        "phase4d_reconciliation_contracts.json",
        "phase4d_scenario_matrix.json",
        "phase4d_startup_result.json",
        "phase4d_restart_result.json",
        "phase4d_carried_position_result.json",
        "phase4d_protection_result.json",
        "phase4d_repair_recommendations.json",
        "phase4d_authority_gate_result.json",
        "phase4d_performance_metrics.json",
        "phase4d_gap_register.json",
        "phase4d_summary.md",
    } == set(written)
    summary = (tmp_path / "reports" / "phase4d_summary.md").read_text(encoding="utf-8")
    assert "NON-AUTHORITATIVE RECONCILIATION ONLY" in summary
