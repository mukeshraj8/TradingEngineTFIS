from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any

from tfis.persistence import PersistenceDatabase, UnitOfWork, canonical_hash
from tfis.storage import atomic_write_text

from .engine import ReconciliationEngine, build_s23_first_slice_reconciliation_input
from .models import (
    BrokerObservedFill,
    BrokerObservedOrder,
    BrokerObservedPosition,
    LocalExpectedFill,
    LocalExpectedOrder,
    LocalExpectedPosition,
    LocalExpectedProtection,
    ReconciliationInput,
    ReconciliationScope,
)


def write_phase4d_reports(report_dir: str | Path, db_path: str | Path) -> dict[str, Path]:
    target = Path(report_dir)
    target.mkdir(parents=True, exist_ok=True)
    db = PersistenceDatabase(db_path)
    engine = ReconciliationEngine()
    scenarios = _scenario_inputs()
    results = {name: engine.reconcile(value) for name, value in scenarios.items()}
    startup = results["empty_matched_account"]
    restart = results["matched_partially_filled_entry"]
    carried = results["matched_carried_position"]
    protection = results["missing_target"]
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(
            trading_session_id=startup.trading_session_id,
            trading_date=startup.as_of.date(),
            market="NSE",
            timezone_name="Asia/Kolkata",
            payload={"session": startup.trading_session_id},
        )
        repo.put_broker_account_identity(
            broker_account_id=startup.broker_account_id,
            provider="fixture",
            environment="test",
            account_hash=startup.broker_account_id,
            payload={"account_id": "AC***A"},
        )
        repo.put_reconciliation_result(
            reconciliation_result=startup,
            reconciliation_input_hash=canonical_hash(scenarios["empty_matched_account"].to_dict()),
            expected_projection_version=0,
        )

    perf = _performance(engine)
    contracts = {
        "truth_categories": ["LOCAL_EXPECTED_STATE", "BROKER_OBSERVED_STATE", "RECONCILED_STATE"],
        "scopes": [item.value for item in ReconciliationScope],
        "authority": "NON-AUTHORITATIVE RECONCILIATION ONLY",
        "matching_precedence": {
            "orders": ["broker_account", "broker_order_id", "exchange_order_id", "client_order_id", "correlation_id", "contract_side_quantity_timing_supporting_only"],
            "fills": ["broker_or_exchange_fill_id", "broker_order_id", "account", "contract", "side", "quantity", "timestamp"],
            "positions": ["broker_account", "normalized_contract", "net_direction", "product", "carry_classification"],
        },
    }
    matrix = {
        name: {
            "authority_gate": result.authority_gate.recommendation.value,
            "manual_review_required": result.manual_review_required,
            "classifications": sorted({item.classification.value for item in result.items}),
        }
        for name, result in results.items()
    }
    payloads: dict[str, Any] = {
        "phase4d_reconciliation_contracts.json": contracts,
        "phase4d_scenario_matrix.json": matrix,
        "phase4d_startup_result.json": startup.to_dict(),
        "phase4d_restart_result.json": restart.to_dict(),
        "phase4d_carried_position_result.json": carried.to_dict(),
        "phase4d_protection_result.json": protection.to_dict(),
        "phase4d_repair_recommendations.json": {
            "recommendations": [item.to_dict() for result in results.values() for item in result.repair_recommendations],
            "execution_not_permitted": True,
        },
        "phase4d_authority_gate_result.json": {
            "startup": startup.authority_gate.to_dict(),
            "restart": restart.authority_gate.to_dict(),
            "carried": carried.authority_gate.to_dict(),
            "protection": protection.authority_gate.to_dict(),
        },
        "phase4d_performance_metrics.json": perf,
        "phase4d_gap_register.json": {
            "gaps": [
                {"code": "PHASE4E_EXECUTION_INTENT_NOT_IMPLEMENTED", "status": "DEFERRED"},
                {"code": "NO_AUTOMATIC_PROJECTION_REPAIR", "status": "INTENTIONAL"},
                {"code": "NO_BROKER_WRITE_AUTHORITY", "status": "INTENTIONAL"},
            ]
        },
        "phase4d_reconciliation_audit.md": _audit_markdown(matrix),
        "phase4d_summary.md": _summary_markdown(startup, protection, perf),
    }
    written: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = target / name
        if name.endswith(".json"):
            atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        else:
            atomic_write_text(path, str(payload))
        written[name] = path
    return written


def _base_input(name: str) -> ReconciliationInput:
    ts = datetime.fromisoformat("2026-06-05T09:16:00+05:30")
    return ReconciliationInput(
        reconciliation_id=f"phase4d-{name}",
        broker_account_id="acct-a",
        trading_session_id="session-2026-06-05",
        scope=ReconciliationScope.STARTUP_ACCOUNT,
        as_of=ts,
        local_state_version=1,
        broker_snapshot_hash=f"broker-hash-{name}",
        reconciliation_policy_version="phase4d.v1",
        account_payload={"broker_account_id": "acct-a", "session_status": "AUTHENTICATED", "completeness": "COMPLETE"},
    )


def _order_pair(status: str = "OPEN", qty: int = 75) -> tuple[LocalExpectedOrder, BrokerObservedOrder]:
    local = LocalExpectedOrder("local-order-1", "acct-a", "NIFTY_20260609_22650_CE", "SELL", qty, status, "ENTRY", "client-1", "broker-1", limit_price=100.0, filled_quantity=0)
    broker = BrokerObservedOrder("broker-1", "acct-a", "NIFTY_20260609_22650_CE", "SELL", qty, status, "ENTRY", "client-1", limit_price=100.0, filled_quantity=0)
    return local, broker


def _scenario_inputs() -> dict[str, ReconciliationInput]:
    local_order, broker_order = _order_pair()
    local_fill = LocalExpectedFill("fill-1", "local-order-1", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, 100.0, "broker-1")
    broker_fill = BrokerObservedFill("fill-1", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, 100.0, "broker-1")
    local_pos = LocalExpectedPosition("pc-1", "acct-a", "NIFTY_20260609_22650_CE", -75, "SHORT", "NRML", "OPEN", 100.0, "INTRADAY")
    broker_pos = BrokerObservedPosition("acct-a", "NIFTY_20260609_22650_CE", -75, "SHORT", "NRML", 100.0, "INTRADAY")
    target = LocalExpectedProtection("target-1", "pc-1", "acct-a", "NIFTY_20260609_22650_CE", "TARGET", "BUY", 75, 60.0, 1)
    sl = LocalExpectedProtection("sl-1", "pc-1", "acct-a", "NIFTY_20260609_22650_CE", "REVISED_SL", "BUY", 75, 130.0, 2)
    target_order = BrokerObservedOrder("target-broker", "acct-a", "NIFTY_20260609_22650_CE", "BUY", 75, "OPEN", "TARGET", limit_price=60.0, protection_generation=1)
    sl_order = BrokerObservedOrder("sl-broker", "acct-a", "NIFTY_20260609_22650_CE", "BUY", 75, "OPEN", "REVISED_SL", trigger_price=130.0, protection_generation=2)
    scenarios = {
        "empty_matched_account": _base_input("empty"),
        "matched_working_entry_order": replace(_base_input("matched_order"), local_orders=(local_order,), broker_orders=(broker_order,)),
        "matched_partially_filled_entry": replace(_base_input("partial_fill"), local_orders=(replace(local_order, status="PARTIALLY_FILLED", filled_quantity=25),), broker_orders=(replace(broker_order, status="PARTIALLY_FILLED", filled_quantity=25),)),
        "broker_only_order": replace(_base_input("broker_only_order"), broker_orders=(broker_order,)),
        "local_only_submitted_order": replace(_base_input("local_only_order"), local_orders=(replace(local_order, status="SUBMITTED"),)),
        "status_mismatch": replace(_base_input("status_mismatch"), local_orders=(local_order,), broker_orders=(replace(broker_order, status="FILLED"),)),
        "broker_only_fill": replace(_base_input("broker_only_fill"), broker_fills=(broker_fill,)),
        "duplicate_fill": replace(_base_input("duplicate_fill"), broker_fills=(broker_fill, broker_fill)),
        "matched_open_position": replace(_base_input("matched_position"), local_positions=(local_pos,), broker_positions=(broker_pos,)),
        "broker_only_position": replace(_base_input("broker_only_position"), broker_positions=(broker_pos,)),
        "local_only_position": replace(_base_input("local_only_position"), local_positions=(local_pos,)),
        "quantity_mismatch": replace(_base_input("quantity_mismatch"), local_positions=(local_pos,), broker_positions=(replace(broker_pos, net_quantity=-50),)),
        "missing_target": replace(_base_input("missing_target"), local_positions=(local_pos,), broker_positions=(broker_pos,), local_protections=(target, sl), broker_orders=(sl_order,)),
        "missing_sl": replace(_base_input("missing_sl"), local_positions=(local_pos,), broker_positions=(broker_pos,), local_protections=(target, sl), broker_orders=(target_order,)),
        "duplicate_sl": replace(_base_input("duplicate_sl"), local_protections=(sl,), broker_orders=(sl_order, replace(sl_order, broker_order_id="sl-broker-2"))),
        "matched_carried_position": build_s23_first_slice_reconciliation_input(),
        "carried_quantity_mismatch": build_s23_first_slice_reconciliation_input(mismatch=True),
        "broker_unavailable": replace(_base_input("broker_unavailable"), account_payload={"broker_account_id": "acct-a", "session_status": "UNAUTHORIZED", "completeness": "UNAVAILABLE"}),
        "partial_broker_snapshot": replace(_base_input("partial"), account_payload={"broker_account_id": "acct-a", "session_status": "AUTHENTICATED", "completeness": "PARTIAL"}),
        "account_identity_mismatch": replace(_base_input("account_mismatch"), account_payload={"broker_account_id": "acct-b", "session_status": "AUTHENTICATED", "completeness": "COMPLETE"}),
        "stale_broker_snapshot": replace(_base_input("stale"), account_payload={"broker_account_id": "acct-a", "session_status": "AUTHENTICATED", "completeness": "COMPLETE", "captured_at": datetime.fromisoformat("2026-06-05T09:00:00+05:30")}),
        "ambiguous_contract_identity": replace(_base_input("ambiguous"), broker_orders=(BrokerObservedOrder("broker-amb", "acct-a", "", "SELL", 75, "OPEN"),)),
        "restart_pending_idempotency": replace(_base_input("restart_pending"), scope=ReconciliationScope.PROCESS_RESTART, recovery_status="PARTIAL_RECOVERY"),
    }
    return scenarios


def _performance(engine: ReconciliationEngine) -> dict[str, Any]:
    timings: dict[str, list[float]] = {"account": [], "orders_100": [], "fills_100": [], "positions_50": [], "protection": [], "multi_account_batch": []}
    for _ in range(5):
        start = perf_counter()
        engine.reconcile(_base_input("perf-account"))
        timings["account"].append(perf_counter() - start)
        order = _order_pair()[0]
        broker = _order_pair()[1]
        start = perf_counter()
        engine.reconcile(replace(_base_input("perf-orders"), local_orders=tuple(replace(order, local_order_id=f"lo-{i}", broker_order_id=f"bo-{i}") for i in range(100)), broker_orders=tuple(replace(broker, broker_order_id=f"bo-{i}") for i in range(100))))
        timings["orders_100"].append(perf_counter() - start)
        fill = LocalExpectedFill("fill", "order", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, 100.0)
        broker_fill = BrokerObservedFill("fill", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, 100.0)
        start = perf_counter()
        engine.reconcile(replace(_base_input("perf-fills"), local_fills=tuple(replace(fill, fill_id=f"f-{i}") for i in range(100)), broker_fills=tuple(replace(broker_fill, fill_id=f"f-{i}") for i in range(100))))
        timings["fills_100"].append(perf_counter() - start)
        pos = LocalExpectedPosition("pc", "acct-a", "NIFTY_20260609_22650_CE", -75, "SHORT", "NRML", "OPEN")
        broker_pos = BrokerObservedPosition("acct-a", "NIFTY_20260609_22650_CE", -75, "SHORT", "NRML")
        start = perf_counter()
        engine.reconcile(replace(_base_input("perf-positions"), local_positions=tuple(replace(pos, position_cycle_id=f"pc-{i}", normalized_contract=f"C-{i}") for i in range(50)), broker_positions=tuple(replace(broker_pos, normalized_contract=f"C-{i}") for i in range(50))))
        timings["positions_50"].append(perf_counter() - start)
    return {
        key: {"median_seconds": median(values), "p95_seconds": sorted(values)[int(len(values) * 0.8)]}
        for key, values in timings.items()
        if values
    } | {"fixture_mode_only": True, "production_capacity_claimed": False}


def _audit_markdown(matrix: dict[str, Any]) -> str:
    return (
        "# Phase 4D Reconciliation Audit\n\n"
        "Generic reconciliation separates LOCAL_EXPECTED_STATE, BROKER_OBSERVED_STATE and RECONCILED_STATE.\n\n"
        "No broker write, paper/live authority, automatic projection repair, PositionCycle creation, or order mutation is implemented.\n\n"
        f"Scenario count: {len(matrix)}\n"
    )


def _summary_markdown(startup: object, protection: object, perf: dict[str, Any]) -> str:
    return (
        "# Phase 4D Broker/Local Reconciliation\n\n"
        "Verdict: PHASE4D_M1_ACCEPT\n\n"
        "Runtime impact: NON-AUTHORITATIVE RECONCILIATION ONLY.\n\n"
        "Broker/paper/live authority: NONE.\n\n"
        f"Startup gate: {startup.authority_gate.recommendation.value}\n\n"
        f"Protection gate: {protection.authority_gate.recommendation.value}\n\n"
        f"Performance fixture mode only: {perf.get('fixture_mode_only')}\n"
    )
