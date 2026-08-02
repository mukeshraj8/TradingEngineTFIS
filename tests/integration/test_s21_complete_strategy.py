from __future__ import annotations

import json
from pathlib import Path

from tfis.adapters.phase5d import S21_COMPLETE_REPORT_NAMES, build_s21_complete_certification, write_s21_complete_reports


EXPECTED_BRANCHES = {"BULL_CALL", "BULL_PUT", "BEAR_CALL", "BEAR_PUT"}


def test_s21_complete_strategy_certifies_all_source_verified_branches() -> None:
    certification = build_s21_complete_certification()

    inventory = certification["s21_branch_inventory"]
    assert {row["branch_identity"] for row in inventory["branches"]} == EXPECTED_BRANCHES
    assert inventory["legacy_authority_used"] is False

    natural = certification["s21_natural_branch_selection"]
    assert natural["status"] == "PASSED"
    assert natural["manual_branch_override_found"] is False
    assert natural["manual_option_type_override_after_resolution_found"] is False
    assert {session["resolved_branch"] for session in natural["sessions"]} == EXPECTED_BRANCHES
    assert all(session["runner_told_call_or_put_after_resolution"] is False for session in natural["sessions"])

    contracts = certification["s21_contract_selection_matrix"]
    for branch in EXPECTED_BRANCHES:
        assert contracts[branch]["normal"]["decision"] == "SELECTED"
        assert contracts[branch]["normal"]["selected_expiry_kind"] == "NEAR"
        assert contracts[branch]["near_fails_next_selected"]["decision"] == "SELECTED"
        assert contracts[branch]["near_fails_next_selected"]["selected_expiry_kind"] == "NEXT"
        assert contracts[branch]["near_and_next_fail"]["decision"] == "NO_TRADE"

    trace = certification["s21_complete_trace"]
    assert set(trace["branches"]) == EXPECTED_BRANCHES
    for branch, result in trace["branches"].items():
        assert result["normal_target"]["terminal_position_state"] == "CLOSED", branch
        assert result["normal_original_sl"]["terminal_position_state"] == "CLOSED", branch
        assert result["orpt_rc_revised_sl"]["terminal_position_state"] == "CLOSED", branch
        assert result["eod_exit"]["terminal_position_state"] == "CLOSED", branch
        assert result["eod_equality_carry"]["equality_outcome"] == "CARRY_FORWARD", branch
        assert result["next_day_recovery"]["status"] == "CARRIED_POSITION_RECOVERABLE", branch
        assert result["duplicate_replay"]["duplicate_financial_action_created"] is False, branch
        assert result["restart_after_fill"]["status"] == "MATCHED", branch
        assert result["reconciliation_block"]["decision"] == "BLOCKED", branch


def test_s21_complete_strategy_uses_corrected_generic_accounting_provenance() -> None:
    certification = build_s21_complete_certification()

    for branch, accounting in certification["s21_accounting_results"].items():
        trade = accounting["trade_fact"]
        assert trade["trade_fact_version"] == "tfis.short_option_accounting.v1", branch
        assert trade["execution"]["requested_entry_quantity"] == 15, branch
        assert trade["decision_context"]["configured_lots"] == 1, branch
        assert trade["decision_context"]["lot_size"] == 15, branch
        assert trade["instrument"]["underlying"] == "BANKNIFTY", branch
        assert trade["instrument"]["product"] == "OPTION_SELLING", branch
        assert all(fact["calculation_version"] == "tfis.short_option_accounting.v1" for fact in accounting["pnl_facts"])

    reuse = certification["s21_platform_reuse_report"]
    assert "src/tfis/accounting/builders.py" in reuse["generic_files_changed"]
    assert reuse["runtime_generic_change_count"] == 0
    assert reuse["architecture_boundary_verdict"] == "PASS"


def test_s21_complete_reports_are_written(tmp_path: Path) -> None:
    written = write_s21_complete_reports(tmp_path)
    assert sorted(written) == sorted(S21_COMPLETE_REPORT_NAMES)

    for report_name in S21_COMPLETE_REPORT_NAMES:
        path = tmp_path / report_name
        assert path.exists(), report_name
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert "token" not in json.dumps(payload).lower()
