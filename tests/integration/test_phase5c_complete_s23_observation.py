from __future__ import annotations

import json
from pathlib import Path

from tfis.internal_paper.observation.phase5c_complete_s23 import (
    BRANCH_OPTION_TYPE,
    build_phase5c_report_set,
    build_phase5c_summary,
    build_session_inventory,
    run_phase5c_observation,
)


def _sessions() -> list[dict]:
    return run_phase5c_observation()["session_results"]


def test_session_inventory_classifies_candidates() -> None:
    inventory = build_session_inventory()

    assert inventory
    assert any(item["completeness"] == "FIXTURE_BACKED_BRANCH_CANDIDATE" for item in inventory)
    assert any(item["completeness"] == "PARTIAL_NATURAL_BRANCH_CANDIDATE" for item in inventory)
    assert all("session_id" in item and "source_path" in item for item in inventory)


def test_natural_bull_call_bear_call_bull_put_and_bear_put_are_reached() -> None:
    observation = run_phase5c_observation()
    branches = set(observation["branch_resolution_report"]["resolved_branches"])

    assert branches == set(BRANCH_OPTION_TYPE)
    assert next(item for item in observation["session_results"] if item["session_id"] == "phase5c_bull_call_normal_target")["resolved_branch"] == "BULL_CALL"
    assert next(item for item in observation["session_results"] if item["session_id"] == "phase5c_bear_call_normal_original_sl")["resolved_branch"] == "BEAR_CALL"
    assert next(item for item in observation["session_results"] if item["session_id"] == "phase5c_bull_put_normal_target")["resolved_branch"] == "BULL_PUT"
    assert next(item for item in observation["session_results"] if item["session_id"] == "phase5c_bear_put_normal_original_sl")["resolved_branch"] == "BEAR_PUT"


def test_no_manual_branch_or_option_override() -> None:
    observation = run_phase5c_observation()

    assert observation["branch_resolution_report"]["manual_branch_override_found"] is False
    assert observation["branch_resolution_report"]["manual_option_type_override_after_resolution_found"] is False
    assert all(session["manual_branch_override"] is False for session in observation["session_results"])
    assert all(session["manual_option_type_override_after_resolution"] is False for session in observation["session_results"])


def test_ce_pe_routing_isolation_blocks_wrong_identity() -> None:
    routing = run_phase5c_observation()["ce_pe_routing_report"]

    assert routing["ce_observations_can_satisfy_pe"] is False
    assert routing["pe_observations_can_satisfy_ce"] is False
    assert routing["wrong_option_type_blocks"] is True
    assert routing["wrong_expiry_blocks"] is True
    assert routing["wrong_strike_blocks"] is True
    assert routing["stale_prior_session_contract_blocks"] is True
    assert routing["contract_identity_structured_not_display_name"] is True


def test_three_run_determinism_and_state_isolation() -> None:
    observation = run_phase5c_observation()

    assert observation["determinism_report"]["status"] == "PASSED"
    assert observation["determinism_report"]["all_identical"] is True
    for session in observation["session_results"]:
        assert session["three_run_deterministic"] is True
        assert len(set(session["three_run_hashes"])) == 1
        assert session["state_isolation"]["no_stale_selected_contract"] is True
        assert session["state_isolation"]["no_stale_authority_grant"] is True
        assert session["state_isolation"]["no_prior_session_pnl_contamination"] is True


def test_normal_gap_trade_no_trade_and_blocked_outcomes_are_distinct() -> None:
    sessions = _sessions()
    outcomes = {session["outcome"] for session in sessions}
    paths = {session["path_kind"] for session in sessions}

    assert "NORMAL" in paths
    assert "GAP_RC" in paths
    assert "TRADE_COMPLETED" in outcomes
    assert "TRADE_OPEN_CARRIED" in outcomes
    assert "NO_TRADE_BY_RULE" in outcomes
    assert "BLOCKED_MISSING_ORPT" in outcomes
    assert next(session for session in sessions if session["outcome"] == "BLOCKED_MISSING_ORPT")["outcome"] != "NO_TRADE_BY_RULE"


def test_call_and_put_carry_recovery_are_covered() -> None:
    carry = run_phase5c_observation()["carry_recovery_report"]

    assert carry["status"] == "PASSED"
    assert carry["call_supported"] is True
    assert carry["put_supported"] is True
    assert carry["same_position_cycle_identity"] is True
    assert carry["no_opposite_side_contract_leakage"] is True


def test_duplicate_action_audit_has_no_financial_duplicates() -> None:
    audit = run_phase5c_observation()["duplicate_action_audit"]

    assert audit["status"] == "PASSED"
    assert audit["identical_replay"] == "IDEMPOTENT"
    assert audit["conflicting_duplicate"] == "FAIL_CLOSED"
    assert set(audit["unexplained_duplicates"].values()) == {0}


def test_position_protection_and_accounting_cover_ce_and_pe() -> None:
    observation = run_phase5c_observation()
    protection = observation["position_protection_report"]
    accounting = observation["accounting_report"]

    assert protection["status"] == "PASSED"
    assert protection["over_protection"] is False
    assert protection["wrong_side_exit_order"] is False
    assert accounting["status"] == "PASSED"
    assert accounting["separate_put_accounting_implementation"] is False
    assert accounting["short_option_pnl_policy_shared"] is True
    assert {item["option_type"] for item in accounting["sessions"]} == {"CALL", "PUT"}


def test_profitability_block_funnel_reuse_and_readiness_are_honest() -> None:
    observation = run_phase5c_observation()

    assert observation["profitability_observation"]["rule_change_recommendation"] == "NONE_INSUFFICIENT_SAMPLE"
    assert observation["block_funnel"]["by_fixture_backed"] > observation["block_funnel"]["by_partial_capture"]
    assert observation["reuse_assessment"]["zero_duplicated_operational_stacks"] is True
    assert observation["readiness_scorecard"]["continued_complete_s23_observation"] == "READY"
    assert observation["readiness_scorecard"]["second_authoritative_internal_paper_instance"].startswith("NOT_READY")


def test_execution_authenticity_and_external_authority() -> None:
    observation = run_phase5c_observation()

    assert observation["external_authority"]["live_submission"] == "NONE"
    assert observation["external_authority"]["external_order_mutation"] == "NONE"
    assert observation["external_authority"]["external_position_mutation"] == "NONE"
    assert observation["defect_register"][-1]["classification"] == "NO_DEFECT"


def test_reports_are_generated(tmp_path: Path) -> None:
    written = build_phase5c_report_set(tmp_path)
    required = {
        "phase5c_session_inventory.json",
        "phase5c_selected_sessions.json",
        "phase5c_execution_authenticity_audit.json",
        "phase5c_session_results.json",
        "phase5c_branch_resolution_report.json",
        "phase5c_ce_pe_routing_report.json",
        "phase5c_determinism_report.json",
        "phase5c_call_put_regression_matrix.json",
        "phase5c_carry_recovery_report.json",
        "phase5c_duplicate_action_audit.json",
        "phase5c_position_protection_report.json",
        "phase5c_accounting_report.json",
        "phase5c_profitability_observation.json",
        "phase5c_block_funnel.json",
        "phase5c_performance_metrics.json",
        "phase5c_defect_register.json",
        "phase5c_reuse_assessment.json",
        "phase5c_readiness_scorecard.json",
        "phase5c_gap_register.json",
        "phase5c_summary.md",
    }

    assert required.issubset(set(written))
    summary = json.loads((tmp_path / "phase5c_readiness_scorecard.json").read_text(encoding="utf-8"))
    assert summary["continued_complete_s23_observation"] == "READY"


def test_phase5c_summary_contract() -> None:
    summary = build_phase5c_summary()

    assert summary["verdict"] == "PHASE5C_M1_CONDITIONAL"
    assert summary["all_four_branches_reached"] is True
    assert summary["runtime_impact"] == "MULTI-SESSION COMPLETE-S23 INTERNAL-PAPER OBSERVATION"
