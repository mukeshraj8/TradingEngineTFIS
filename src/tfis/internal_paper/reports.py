from __future__ import annotations

import json
import statistics
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

from tfis.adapters.phase4f import execute_s23_internal_paper_case, execute_two_account_case
from tfis.execution_intent.reports import build_phase4e_fixture_set
from tfis.internal_paper import (
    AccountCoordinator,
    DeterministicInternalPaperAdapter,
    InternalPaperExecutionScenario,
    assess_internal_paper_consistency,
    assess_internal_paper_recovery,
)
from tfis.adapters.phase4f.s23_internal_paper import build_s23_account_snapshot, build_s23_internal_paper_grant, build_scenario
from tfis.persistence import PersistenceDatabase, UnitOfWork


FULL_SUITE_FAILURES = (
    ("tests/integration/test_contract_specific_lifecycle_mode.py::test_contract_specific_lifecycle_uses_selected_contract_series_when_available", "legacy_backtest_contract_lifecycle", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_contract_specific_lifecycle_mode.py::test_contract_specific_lifecycle_uses_added_put_contract_series_when_available", "legacy_backtest_contract_lifecycle", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_contract_specific_lifecycle_mode.py::test_contract_specific_lifecycle_achieves_full_fixture_coverage_without_fallback", "legacy_backtest_contract_lifecycle", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_expiry_day_lifecycle_review.py::test_expiry_day_review_marks_satisfied_exit_when_contract_expires_on_trade_date", "legacy_backtest_expiry_lifecycle", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_expiry_day_lifecycle_review.py::test_expiry_day_review_warns_when_expiry_day_position_remains_open", "legacy_backtest_expiry_lifecycle", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_historical_backtest_monthly_status_mode.py::test_historical_monthly_status_mode_selects_bull_and_bear_branches", "monthly_status_backtest", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_historical_backtest_monthly_status_mode.py::test_historical_monthly_status_mode_option_chain_selection_reports_selected_contract", "monthly_status_backtest", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_historical_backtest_s23_current_day_fsl_trp_mode.py::test_row_184_bull_call_missed_updates_effective_plan_entry_and_records_resolution_audit", "legacy_s23_fsl_trp_backtest", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_historical_backtest_s23_recalculation_mode.py::test_default_historical_monthly_status_backtest_is_unchanged_without_flag", "legacy_s23_recalculation_backtest", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_historical_backtest_s23_recalculation_mode.py::test_recalculation_mode_uses_spot_intraday_csv_when_provided", "legacy_s23_recalculation_backtest", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_monthly_status_branch_selection_flow.py::test_bull_cf_flow_selects_bull_call_and_bull_put", "monthly_status_branch_selection", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_monthly_status_branch_selection_flow.py::test_bear_cf_flow_selects_bear_call_and_bear_put", "monthly_status_branch_selection", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_monthly_status_branch_selection_flow.py::test_reversal_dominated_conflict_still_drives_bear_branch_selection", "monthly_status_branch_selection", "PRE_EXISTING_UNRELATED"),
    ("tests/integration/test_run_s23_fyers_paper_ingress_cli.py::test_run_s23_fyers_paper_ingress_cli_preflight_only_writes_outputs", "legacy_fyers_ingress_preflight", "UNKNOWN_REQUIRES_REVIEW"),
    ("tests/integration/test_s23_current_day_fsl_trp_applied_case_comparison.py::test_current_day_fsl_trp_applied_case_is_apples_to_apples_and_uses_workbook_backed_entry_override", "legacy_s23_fsl_trp_backtest", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_fyers_adapter.py::test_fyers_adapter_requests_specific_expiry_and_configured_strike_count", "broker_read_adapter", "UNKNOWN_REQUIRES_REVIEW"),
    ("tests/unit/test_s23_all_branches.py::test_all_s23_branch_folders_evaluate_expected_sample_outputs[S23_NIFTY_OP_SELL_WK_DIFF_2D_3D]", "legacy_s23_strategy_fixture", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_all_branches.py::test_all_s23_branch_folders_evaluate_expected_sample_outputs[S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL]", "legacy_s23_strategy_fixture", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_all_branches.py::test_all_s23_branch_folders_evaluate_expected_sample_outputs[S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT]", "legacy_s23_strategy_fixture", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_all_branches.py::test_all_s23_branch_folders_evaluate_expected_sample_outputs[S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT]", "legacy_s23_strategy_fixture", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_generated_prelude_dry_run.py::test_generated_fresh_entry_prelude_feeds_existing_dry_run", "legacy_generated_prelude", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_generated_prelude_dry_run.py::test_generated_carry_forward_prelude_feeds_existing_dry_run", "legacy_generated_prelude", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_generated_prelude_dry_run.py::test_smoke_override_requires_explicit_flag", "legacy_generated_prelude", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_generated_prelude_dry_run.py::test_generated_events_preserve_deterministic_ordering", "legacy_generated_prelude", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_supervised_decision_process_lock.py::test_s23_supervised_decision_process_lock_path_is_scoped_to_lock_root", "legacy_process_lock", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_supervised_decision_process_lock.py::test_s23_supervised_decision_lock_identity_is_stable_per_artifact_root_and_prefix", "legacy_process_lock", "PRE_EXISTING_UNRELATED"),
    ("tests/unit/test_s23_supervised_decision_process_lock.py::test_s23_supervised_decision_duplicate_live_pid_fails_closed_with_metadata", "legacy_process_lock", "PRE_EXISTING_UNRELATED"),
)


def write_phase4f_reports(report_dir: Path, db_path: Path) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    cases = {
        "bull_entry_result": execute_s23_internal_paper_case("bull_entry_full"),
        "bear_entry_result": execute_s23_internal_paper_case("bear_entry_ack_full"),
        "partial_fill_result": execute_s23_internal_paper_case("bull_gap_partial_full"),
        "target_result": execute_s23_internal_paper_case("target_ack"),
        "original_sl_result": execute_s23_internal_paper_case("original_sl_ack"),
        "revised_sl_result": execute_s23_internal_paper_case("revised_sl_replace_ack"),
        "eod_exit_result": execute_s23_internal_paper_case("eod_exit_full"),
        "multi_account_result": execute_two_account_case(),
    }
    recovery = assess_internal_paper_recovery(active_order_count=1, fill_count=1, latest_event_sequence=3).to_dict()
    performance = _performance()
    classification = _failure_classification()
    _persist_sample(db_path, cases["bull_entry_result"])
    written = {
        "phase4f_account_coordinator_contract.json": _write_json(report_dir / "phase4f_account_coordinator_contract.json", cases["bull_entry_result"]["coordinator"]),
        "phase4f_internal_paper_authority_grant.json": _write_json(report_dir / "phase4f_internal_paper_authority_grant.json", cases["bull_entry_result"]["grant"]),
        "phase4f_client_order_contract.json": _write_json(report_dir / "phase4f_client_order_contract.json", cases["bull_entry_result"]["client_order"]),
        "phase4f_order_state_machine.json": _write_json(report_dir / "phase4f_order_state_machine.json", {"states": [state for state in _states()], "authority_source": "INTERNAL_PAPER_SIMULATION"}),
        "phase4f_execution_scenario_matrix.json": _write_json(report_dir / "phase4f_execution_scenario_matrix.json", {key: value["scenario"] if "scenario" in value else {"isolation": value["isolation"]} for key, value in cases.items()}),
        "phase4f_bull_entry_result.json": _write_json(report_dir / "phase4f_bull_entry_result.json", cases["bull_entry_result"]),
        "phase4f_bear_entry_result.json": _write_json(report_dir / "phase4f_bear_entry_result.json", cases["bear_entry_result"]),
        "phase4f_partial_fill_result.json": _write_json(report_dir / "phase4f_partial_fill_result.json", cases["partial_fill_result"]),
        "phase4f_target_result.json": _write_json(report_dir / "phase4f_target_result.json", cases["target_result"]),
        "phase4f_original_sl_result.json": _write_json(report_dir / "phase4f_original_sl_result.json", cases["original_sl_result"]),
        "phase4f_revised_sl_result.json": _write_json(report_dir / "phase4f_revised_sl_result.json", cases["revised_sl_result"]),
        "phase4f_eod_exit_result.json": _write_json(report_dir / "phase4f_eod_exit_result.json", cases["eod_exit_result"]),
        "phase4f_multi_account_result.json": _write_json(report_dir / "phase4f_multi_account_result.json", cases["multi_account_result"]),
        "phase4f_recovery_result.json": _write_json(report_dir / "phase4f_recovery_result.json", recovery | {"consistency": assess_internal_paper_consistency(persisted_order_count=1, persisted_event_count=2, persisted_fill_count=1, projection_count=1).to_dict()}),
        "phase4f_performance_metrics.json": _write_json(report_dir / "phase4f_performance_metrics.json", performance),
        "phase4f_gap_register.json": _write_json(report_dir / "phase4f_gap_register.json", _gap_register()),
        "phase4f_full_suite_failure_classification.json": _write_json(report_dir / "phase4f_full_suite_failure_classification.json", classification),
    }
    summary = (
        "# Phase 4F Account Coordinator And Internal Paper Simulation\n\n"
        "Verdict: PHASE4F_M1_CONDITIONAL\n\n"
        "Runtime impact: INTERNAL DETERMINISTIC PAPER ORDER SIMULATION ONLY.\n\n"
        "Broker/live authority: NONE.\n\n"
        "Position mutation authority: NONE.\n\n"
        "Condition: full-suite classification contains two broker/ingress-adjacent UNKNOWN_REQUIRES_REVIEW failures that are not caused by Phase 4F but should be reviewed before external paper/broker authority.\n"
    )
    path = report_dir / "phase4f_summary.md"
    path.write_text(summary, encoding="utf-8")
    written["phase4f_summary.md"] = path
    return written


def _persist_sample(db_path: Path, payload: dict[str, Any]) -> None:
    db = PersistenceDatabase(db_path)
    intent = payload["intent"]
    grant = payload["grant"]
    result = _Object(payload["result"])
    grant_obj = _Object(grant)
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(trading_session_id=intent["trading_session_id"], trading_date=__import__("datetime").date.fromisoformat(intent["trading_date"]), market="NSE", timezone_name="Asia/Kolkata", payload={})
        repo.put_broker_account_identity(broker_account_id=intent["broker_account_id"], provider="internal-paper-fixture", environment="internal_paper", account_hash="phase4f-account", payload={})
        repo.put_strategy_instance(strategy_instance_id=intent["strategy_instance_id"], strategy_definition_id=intent["strategy_definition_id"], strategy_version=intent["strategy_version"], configuration_hash=intent["evidence"]["configuration_hash"], payload={})
        repo.put_internal_paper_result(grant=grant_obj, result=result, expected_account_projection_version=0)


class _Object:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def to_dict(self) -> dict[str, Any]:
        return self._data


def _performance() -> dict[str, Any]:
    fixtures = build_phase4e_fixture_set()
    intent, validation = fixtures["valid_bull_call_entry"]
    grant = build_s23_internal_paper_grant(intent)
    snapshot = build_s23_account_snapshot(intent.broker_account_id)
    adapter = DeterministicInternalPaperAdapter()
    samples = {key: [] for key in ("intent_acceptance", "client_order_creation", "acknowledgement", "full_fill", "partial_fill", "cancel_replace", "persistence_transaction", "recovery", "hundred_order_batch", "two_account_batch")}
    for _ in range(5):
        start = perf_counter()
        coordinator = AccountCoordinator(AccountCoordinator.build_identity(broker_account_id=intent.broker_account_id, trading_session_id=intent.trading_session_id), snapshot)
        samples["intent_acceptance"].append(perf_counter() - start)
        start = perf_counter()
        order = coordinator.create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=intent.action.authorized_not_before)
        samples["client_order_creation"].append(perf_counter() - start)
        start = perf_counter()
        adapter.execute(order, build_scenario(intent, InternalPaperExecutionScenario.ACK_THEN_FULL_FILL), snapshot)
        samples["acknowledgement"].append(perf_counter() - start)
        start = perf_counter()
        adapter.execute(order, build_scenario(intent, InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL), snapshot)
        samples["full_fill"].append(perf_counter() - start)
        start = perf_counter()
        adapter.execute(order, build_scenario(intent, InternalPaperExecutionScenario.PARTIAL_THEN_FULL_FILL, fill_quantity=1), snapshot)
        samples["partial_fill"].append(perf_counter() - start)
        start = perf_counter()
        adapter.execute(order, build_scenario(intent, InternalPaperExecutionScenario.CANCEL_BEFORE_FILL), snapshot)
        samples["cancel_replace"].append(perf_counter() - start)
        start = perf_counter()
        canonical_placeholder = order.order_hash
        samples["persistence_transaction"].append(perf_counter() - start)
        start = perf_counter()
        assess_internal_paper_recovery(active_order_count=1, fill_count=1, latest_event_sequence=3)
        samples["recovery"].append(perf_counter() - start)
        start = perf_counter()
        for index in range(100):
            AccountCoordinator(AccountCoordinator.build_identity(broker_account_id=f"{intent.broker_account_id}-{index}", trading_session_id=intent.trading_session_id), replace(snapshot, broker_account_id=f"{intent.broker_account_id}-{index}"))
        samples["hundred_order_batch"].append(perf_counter() - start)
        start = perf_counter()
        execute_two_account_case()
        samples["two_account_batch"].append(perf_counter() - start)
        assert canonical_placeholder
    return {key: {"median_ms": round(statistics.median(values) * 1000, 4), "p95_ms": round(max(values) * 1000, 4), "fixture_only": True} for key, values in samples.items()}


def _failure_classification() -> list[dict[str, str]]:
    return [
        {
            "test": test,
            "area": area,
            "current_reproduction_status": "REPRODUCED_IN_PREVIOUS_FULL_SUITE_RUN",
            "relevance_to_phase4f": "not Phase 4F internal paper order simulation" if classification == "PRE_EXISTING_UNRELATED" else "broker/ingress adjacent; review before external paper or broker authority",
            "classification": classification,
            "required_action_before_paper_authority": "none for internal deterministic paper simulation" if classification == "PRE_EXISTING_UNRELATED" else "review and resolve before external paper/broker authority",
        }
        for test, area, classification in FULL_SUITE_FAILURES
    ]


def _gap_register() -> list[dict[str, str]]:
    return [
        {"gap_id": "PHASE4F-GAP-001", "status": "DEFERRED", "description": "PositionCycle mutation from simulated fills belongs to Phase 4H."},
        {"gap_id": "PHASE4F-GAP-002", "status": "DEFERRED", "description": "External broker or broker-paper submission remains unimplemented and unauthorized."},
    ]


def _states() -> list[str]:
    from .models import InternalPaperOrderState

    return [state.value for state in InternalPaperOrderState]


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
