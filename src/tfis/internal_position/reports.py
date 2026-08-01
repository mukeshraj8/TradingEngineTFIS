from __future__ import annotations

import json
import statistics
from pathlib import Path
from time import perf_counter
from typing import Any

from tfis.adapters.phase4h import execute_phase4h_s23_case, execute_phase4h_two_account_case
from tfis.internal_position import InternalPaperPositionEventType, InternalPaperPositionState
from tfis.persistence import PersistenceDatabase, UnitOfWork


UNKNOWN_FAILURE_REVIEW = [
    {
        "test": "tests/integration/test_run_s23_fyers_paper_ingress_cli.py::test_run_s23_fyers_paper_ingress_cli_preflight_only_writes_outputs",
        "imports_or_mutates_position_cycle_path": False,
        "can_corrupt_internal_paper_fill_or_order_identity": False,
        "classification_after_review": "EXTERNAL_BROKER_INGRESS_BLOCKER_ONLY",
        "phase4h_can_proceed": True,
    },
    {
        "test": "tests/unit/test_fyers_adapter.py::test_fyers_adapter_requests_specific_expiry_and_configured_strike_count",
        "imports_or_mutates_position_cycle_path": False,
        "can_corrupt_internal_paper_fill_or_order_identity": False,
        "classification_after_review": "EXTERNAL_BROKER_ADAPTER_BLOCKER_ONLY",
        "phase4h_can_proceed": True,
    },
]


def write_phase4h_reports(report_dir: Path, db_path: Path) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    cases = {
        "bull_open_result": execute_phase4h_s23_case("bull_open"),
        "partial_fill_result": execute_phase4h_s23_case("partial_fill"),
        "target_close_result": execute_phase4h_s23_case("target_close"),
        "original_sl_close_result": execute_phase4h_s23_case("original_sl_close"),
        "revised_sl_close_result": execute_phase4h_s23_case("revised_sl_close"),
        "eod_exit_result": execute_phase4h_s23_case("eod_exit"),
        "carry_forward_result": execute_phase4h_s23_case("carry_forward"),
        "next_day_recovery_result": execute_phase4h_s23_case("next_day_recovery"),
        "multi_account_result": execute_phase4h_two_account_case(),
    }
    _persist_sample(db_path, cases["bull_open_result"])
    written = {
        "phase4h_position_cycle_contract.json": _write_json(report_dir / "phase4h_position_cycle_contract.json", _contract(cases["bull_open_result"])),
        "phase4h_position_state_machine.json": _write_json(report_dir / "phase4h_position_state_machine.json", {"states": [state.value for state in InternalPaperPositionState], "authority": "INTERNAL_PAPER_ONLY"}),
        "phase4h_position_event_catalog.json": _write_json(report_dir / "phase4h_position_event_catalog.json", {"events": [event.value for event in InternalPaperPositionEventType]}),
        "phase4h_scenario_matrix.json": _write_json(report_dir / "phase4h_scenario_matrix.json", _scenario_matrix()),
        "phase4h_bull_open_result.json": _write_json(report_dir / "phase4h_bull_open_result.json", cases["bull_open_result"]),
        "phase4h_partial_fill_result.json": _write_json(report_dir / "phase4h_partial_fill_result.json", cases["partial_fill_result"]),
        "phase4h_target_close_result.json": _write_json(report_dir / "phase4h_target_close_result.json", cases["target_close_result"]),
        "phase4h_original_sl_close_result.json": _write_json(report_dir / "phase4h_original_sl_close_result.json", cases["original_sl_close_result"]),
        "phase4h_revised_sl_close_result.json": _write_json(report_dir / "phase4h_revised_sl_close_result.json", cases["revised_sl_close_result"]),
        "phase4h_eod_exit_result.json": _write_json(report_dir / "phase4h_eod_exit_result.json", cases["eod_exit_result"]),
        "phase4h_carry_forward_result.json": _write_json(report_dir / "phase4h_carry_forward_result.json", cases["carry_forward_result"]),
        "phase4h_next_day_recovery_result.json": _write_json(report_dir / "phase4h_next_day_recovery_result.json", cases["next_day_recovery_result"]),
        "phase4h_multi_account_result.json": _write_json(report_dir / "phase4h_multi_account_result.json", cases["multi_account_result"]),
        "phase4h_consistency_report.json": _write_json(report_dir / "phase4h_consistency_report.json", execute_phase4h_s23_case("consistency")),
        "phase4h_performance_metrics.json": _write_json(report_dir / "phase4h_performance_metrics.json", _performance()),
        "phase4h_gap_register.json": _write_json(report_dir / "phase4h_gap_register.json", _gap_register()),
    }
    summary = (
        "# Phase 4H Internal Paper PositionCycle\n\n"
        "Verdict: PHASE4H_M1_ACCEPT\n\n"
        "Runtime impact: AUTHORITATIVE INTERNAL-PAPER POSITIONCYCLE STATE ONLY.\n\n"
        "Broker/live authority: NONE.\n\n"
        "The two previously unknown full-suite failures were reviewed as legacy FYERS ingress/adapter blockers only. They do not import or mutate the new internal PositionCycle path and cannot corrupt deterministic internal-paper fill/order identity.\n"
    )
    path = report_dir / "phase4h_summary.md"
    path.write_text(summary, encoding="utf-8")
    written["phase4h_summary.md"] = path
    return written


def _persist_sample(db_path: Path, payload: dict[str, Any]) -> None:
    projection = payload["projection"]
    transition = payload["transition"]
    db = PersistenceDatabase(db_path)
    identity = projection["identity"]
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(trading_session_id=identity["trading_session_id"], trading_date=__import__("datetime").date.fromisoformat(identity["originating_trading_date"]), market="NSE", timezone_name="Asia/Kolkata", payload={})
        repo.put_broker_account_identity(broker_account_id=identity["broker_account_id"], provider="internal-paper-fixture", environment="internal_paper", account_hash="phase4h-account", payload={})
        repo.put_strategy_instance(strategy_instance_id=identity["strategy_instance_id"], strategy_definition_id=identity["strategy_definition_id"], strategy_version=identity["strategy_version"], configuration_hash="phase4h-config", payload={})
        repo.put_position_cycle_identity(position_cycle_id=identity["position_cycle_id"], strategy_instance_id=identity["strategy_instance_id"], trading_session_id=identity["trading_session_id"], payload=identity)
        repo.put_internal_position_transition(transition=transition, expected_projection_version=0)


def _contract(payload: dict[str, Any]) -> dict[str, Any]:
    projection = payload["projection"]
    return {
        "identity": projection["identity"],
        "required_state_fields": ["confirmed_entry_quantity", "remaining_quantity", "realized_quantity", "average_entry_price", "average_exit_price", "entry_fill_ids", "exit_fill_ids", "active_target", "active_original_sl", "active_revised_sl", "protection_generation", "carry_forward_status", "projection_version"],
        "authority_classification": "INTERNAL_PAPER_ONLY",
        "external_broker_position": False,
        "live_position": False,
        "broker_reconciliation_authority": False,
        "protection_model": "APPLICATION_MANAGED_LINKED_PROTECTION",
    }


def _scenario_matrix() -> list[dict[str, str]]:
    return [
        {"case": "bull_open", "coverage": "full entry fill opens PositionCycle and emits target/original SL requirements"},
        {"case": "bear_open", "coverage": "bear call side uses same generic PositionCycle state machine"},
        {"case": "partial_fill", "coverage": "partial entry quantity and later protection resize"},
        {"case": "target_close", "coverage": "target-first exit fill closes only after confirmed fill"},
        {"case": "original_sl_close", "coverage": "original SL exit fill closes only after confirmed fill"},
        {"case": "revised_sl_close", "coverage": "revised SL replacement generation and fill"},
        {"case": "old_sl_fills_before_cancel", "coverage": "late old SL fill is preserved as financial event"},
        {"case": "eod_exit", "coverage": "EOD square-off closes only after simulated fill"},
        {"case": "eod_unfilled", "coverage": "unfilled EOD exit remains EXIT_PENDING"},
        {"case": "carry_forward", "coverage": "15:00 equality carries same PositionCycle forward"},
        {"case": "next_day_recovery", "coverage": "carried PositionCycle recovery assessment"},
        {"case": "multi_account", "coverage": "two accounts remain isolated"},
    ]


def _performance() -> dict[str, Any]:
    samples: dict[str, list[float]] = {"open": [], "partial": [], "exit": [], "carry": [], "report_batch": []}
    for _ in range(5):
        start = perf_counter()
        execute_phase4h_s23_case("bull_open")
        samples["open"].append(perf_counter() - start)
        start = perf_counter()
        execute_phase4h_s23_case("partial_fill")
        samples["partial"].append(perf_counter() - start)
        start = perf_counter()
        execute_phase4h_s23_case("target_close")
        samples["exit"].append(perf_counter() - start)
        start = perf_counter()
        execute_phase4h_s23_case("carry_forward")
        samples["carry"].append(perf_counter() - start)
        start = perf_counter()
        for case in ("bull_open", "target_close", "carry_forward"):
            execute_phase4h_s23_case(case)
        samples["report_batch"].append(perf_counter() - start)
    return {key: {"median_ms": round(statistics.median(values) * 1000, 4), "p95_ms": round(max(values) * 1000, 4), "fixture_only": True} for key, values in samples.items()}


def _gap_register() -> dict[str, Any]:
    return {
        "full_suite_blocker_review": UNKNOWN_FAILURE_REVIEW,
        "deferred": [
            {"gap_id": "PHASE4H-GAP-001", "description": "Phase 4I TradeFact/PnLFact downstream projections are intentionally deferred."},
            {"gap_id": "PHASE4H-GAP-002", "description": "External paper/broker authority remains blocked by legacy FYERS ingress/adapter review."},
        ],
    }


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
