from __future__ import annotations

import json
from pathlib import Path

from tfis.adapters.phase5d import S21_FIRST_BRANCH_REPORT_NAMES, build_s21_first_branch_certification, write_s21_first_branch_reports


def test_s21_first_branch_runs_complete_internal_paper_path() -> None:
    certification = build_s21_first_branch_certification()
    trace = certification["s21_complete_trace"]

    assert certification["s21_selected_first_branch"]["selected_branch"] == "BULL_CALL"
    assert certification["s21_selected_first_branch"]["source_monthly_status"] == "BULL_CF"
    assert trace["authority"]["broker_submission_permitted"] is False
    assert trace["authority"]["external_paper_submission_permitted"] is False
    assert trace["authority"]["live_submission_permitted"] is False
    assert trace["authority"]["real_position_mutation_permitted"] is False

    expected_pipeline = [
        "workbook_rule",
        "generic_monthly_status",
        "s21_branch_policy",
        "contract_selection",
        "premarket_plan",
        "opening_market_context",
        "orpt_rc",
        "effective_execution_plan",
        "execution_intent",
        "internal_paper_client_order",
        "simulated_fill",
        "position_cycle",
        "lifecycle",
        "trade_fact",
        "pnl_fact",
        "projection",
    ]
    assert trace["pipeline"] == expected_pipeline

    scenarios = trace["scenarios"]
    assert scenarios["normal_entry_target_exit"]["terminal_position_state"] == "CLOSED"
    assert scenarios["normal_entry_target_exit"]["remaining_quantity"] == 0
    assert scenarios["normal_entry_original_sl_exit"]["terminal_position_state"] == "CLOSED"
    assert scenarios["orpt_missed_rc_revised_sl_exit"]["terminal_position_state"] == "CLOSED"
    assert scenarios["near_fails_next_selected"]["decision"] == "SELECTED"
    assert scenarios["near_fails_next_selected"]["selected_expiry_kind"] == "NEXT"
    assert scenarios["near_and_next_fail_no_trade"]["decision"] == "NO_TRADE"
    assert scenarios["eod_exit"]["terminal_position_state"] == "CLOSED"
    assert scenarios["eod_equal_carry_forward"]["equality_outcome"] == "CARRY_FORWARD"
    assert scenarios["eod_equal_carry_forward"]["operator"] == "<="
    assert scenarios["next_day_carried_recovery"]["status"] == "CARRIED_POSITION_RECOVERABLE"
    assert scenarios["duplicate_replay_no_duplicate_action"]["duplicate_financial_action_created"] is False
    assert scenarios["restart_after_entry_fill"]["status"] == "MATCHED"
    assert scenarios["reconciliation_block_no_order"]["decision"] == "BLOCKED"
    assert scenarios["reconciliation_block_no_order"]["client_order_created"] is False
    assert scenarios["s21_s23_isolated"]["isolated"] is True

    trade = certification["s21_trade_fact"]
    pnl = certification["s21_pnl_fact"]
    assert trade["instrument"]["underlying"] == "BANKNIFTY"
    assert trade["execution"]["requested_entry_quantity"] == 15
    assert trade["decision_context"]["configured_lots"] == 1
    assert pnl["realized_unrealized"] == "REALIZED"


def test_s21_reports_are_written_and_secret_sanitized(tmp_path: Path) -> None:
    written = write_s21_first_branch_reports(tmp_path)
    assert sorted(written) == sorted(S21_FIRST_BRANCH_REPORT_NAMES)

    for report_name in S21_FIRST_BRANCH_REPORT_NAMES:
        path = tmp_path / report_name
        assert path.exists(), report_name
        if path.suffix == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            assert "token" not in json.dumps(payload).lower()
