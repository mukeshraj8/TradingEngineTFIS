from __future__ import annotations

import json
from pathlib import Path

import pytest

from tfis.internal_paper.end_to_end import (
    STARTUP_SEQUENCE,
    build_phase5a_pre_certification,
    write_phase5a_pre_reports,
)


@pytest.fixture(scope="module")
def certification() -> dict:
    return build_phase5a_pre_certification()


def _scenario(certification: dict, scenario_id: str) -> dict:
    return next(item for item in certification["scenarios"] if item["scenario_id"] == scenario_id)


def test_certification_identity_authority_and_startup_sequence(certification: dict) -> None:
    assert certification["scorecard"]["overall_status"] == "END_TO_END_INTERNAL_PAPER_CERTIFIED"
    assert certification["initial_schema_version"] >= 6
    assert certification["run_hash"]
    for scenario in certification["scenarios"]:
        authority = scenario["authority"]
        assert authority["authority_mode"] == "INTERNAL_PAPER_CERTIFICATION_ONLY"
        assert authority["external_broker_submission_permitted"] is False
        assert authority["broker_sandbox_submission_permitted"] is False
        assert authority["live_submission_permitted"] is False
        assert authority["external_order_mutation_permitted"] is False
        assert authority["external_position_mutation_permitted"] is False
        assert tuple(scenario["startup_sequence"]) == STARTUP_SEQUENCE
        assert scenario["startup_sequence"].index("AUTHORITY_GRANT_VALIDATION") < scenario["startup_sequence"].index("RUNTIME_EVENT_PROCESSING")


@pytest.mark.parametrize(
    ("scenario_id", "exit_reason", "win_loss"),
    [
        ("bull_target", "TARGET", "WIN"),
        ("bear_sl", "ORIGINAL_SL", "LOSS"),
        ("gap_revised_sl", "REVISED_SL", "WIN"),
        ("eod_exit", "EOD_EXIT", "WIN"),
    ],
)
def test_financial_closure_scenarios(certification: dict, scenario_id: str, exit_reason: str, win_loss: str) -> None:
    scenario = _scenario(certification, scenario_id)

    assert scenario["status"] == "PASSED"
    assert scenario["order_counts"]["entry_orders"] == 1
    assert scenario["fill_counts"]["entry_fills"] >= 1
    assert scenario["accounting_result"]["exit_reason"] == exit_reason
    assert scenario["accounting_result"]["win_loss"] == win_loss
    assert scenario["position_result"]["remaining_quantity"] == 0
    assert scenario["projection_result"]["reconciled"] is True


def test_gap_rc_partial_fill_eod_and_carry_recovery(certification: dict) -> None:
    gap = _scenario(certification, "gap_revised_sl")
    partial = _scenario(certification, "partial_fill")
    carry = _scenario(certification, "carry_recovery")

    assert gap["trace"]
    assert gap["idempotency"]["collision_scope"]
    assert partial["position_result"]["realized_quantity"] > 0
    assert partial["fill_counts"]["duplicate_fills"] == 0
    assert carry["position_result"]["carry_forward_count"] >= 1
    assert carry["warnings"] == ["NEXT_DAY_EXIT_USES_ACCEPTED_ACCOUNTING_OPEN_CARRY_FIXTURE"]


@pytest.mark.parametrize(
    "scenario_id",
    ["crash_after_order", "crash_after_partial_fill", "crash_protected_position"],
)
def test_crash_restart_scenarios_are_deterministic(certification: dict, scenario_id: str) -> None:
    scenario = _scenario(certification, scenario_id)

    assert scenario["status"] == "PASSED"
    assert scenario["component_artifacts"]["restart_recovery"] == "PASSED"
    assert scenario["order_counts"]["duplicate_client_orders"] == 0
    assert scenario["fill_counts"]["duplicate_fills"] == 0
    assert scenario["position_result"]["duplicate_position_cycles"] == 0
    assert scenario["idempotency"]["resume_requires_explicit_certification_input"] is True


def test_duplicate_replay_blocked_reconciliation_multi_account_and_kill_switch(certification: dict) -> None:
    duplicate = _scenario(certification, "duplicate_replay")
    blocked = _scenario(certification, "blocked_reconciliation")
    multi = _scenario(certification, "multi_account")
    kill = _scenario(certification, "kill_switch")

    assert duplicate["idempotency"]["identical_duplicates"] == "IDEMPOTENT"
    assert duplicate["idempotency"]["conflicting_duplicates"] == "FAIL_CLOSED"
    assert duplicate["order_counts"]["duplicate_client_orders"] == 0
    assert blocked["position_result"]["blocked_before_execution_intent"] is True
    assert blocked["order_counts"]["client_orders"] == 0
    assert multi["position_result"]["independent_cycles"] is True
    assert multi["projection_result"]["reconciled"] is True
    assert kill["position_result"]["existing_protection_removed"] is False
    assert kill["accounting_result"]["financial_mutation"] == "NONE"


def test_complete_trace_idempotency_catalog_and_known_failure_register(certification: dict) -> None:
    for scenario in certification["scenarios"]:
        node_types = [node["node_type"] for node in scenario["trace"]]
        if scenario["scenario_id"] not in {"blocked_reconciliation", "multi_account", "kill_switch"}:
            assert "ExecutionIntent" in node_types
            assert "TradeFact" in node_types
            assert "PnLFact" in node_types
            assert all(node["stable_id"] and node["hash"] for node in scenario["trace"])
        assert scenario["idempotency"]
    register = certification["known_failure_register"]
    assert len(register) == 27
    assert {item["classification"] for item in register} == {"PRE_EXISTING_UNRELATED"}


def test_reports_are_generated(tmp_path: Path) -> None:
    written = write_phase5a_pre_reports(tmp_path)

    required = {
        "phase5a_pre_certification_contract.json",
        "phase5a_pre_scenario_matrix.json",
        "phase5a_pre_bull_target_result.json",
        "phase5a_pre_bear_sl_result.json",
        "phase5a_pre_gap_revised_sl_result.json",
        "phase5a_pre_partial_fill_result.json",
        "phase5a_pre_eod_exit_result.json",
        "phase5a_pre_carry_recovery_result.json",
        "phase5a_pre_crash_order_result.json",
        "phase5a_pre_crash_partial_fill_result.json",
        "phase5a_pre_crash_protected_position_result.json",
        "phase5a_pre_duplicate_replay_result.json",
        "phase5a_pre_blocked_reconciliation_result.json",
        "phase5a_pre_multi_account_result.json",
        "phase5a_pre_kill_switch_result.json",
        "phase5a_pre_end_to_end_trace.json",
        "phase5a_pre_idempotency_catalog.json",
        "phase5a_pre_certification_scorecard.json",
        "phase5a_pre_performance_metrics.json",
        "phase5a_pre_known_failure_register.json",
        "phase5a_pre_gap_register.json",
        "phase5a_pre_certification_summary.md",
    }
    assert required.issubset(set(written))
    scorecard = json.loads((tmp_path / "phase5a_pre_certification_scorecard.json").read_text(encoding="utf-8"))
    assert scorecard["overall_status"] == "END_TO_END_INTERNAL_PAPER_CERTIFIED"
