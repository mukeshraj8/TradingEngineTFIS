from __future__ import annotations

import json
from pathlib import Path

from tfis.adapters.phase5e import S22_RELIANCE_REPORT_NAMES, build_s22_reliance_certification, write_s22_reliance_reports


def test_s22_reliance_one_stock_vertical_reaches_accounting() -> None:
    certification = build_s22_reliance_certification()

    assert certification["s22_reliance_time_semantics"]["capture_is_exchange_session"] is False
    assert certification["s22_reliance_metadata_validation"]["verdict"] == "METADATA_GATE_PASSED"
    assert certification["s22_reliance_monthly_status"]["monthly_status"] == "BEAR_CF"
    assert certification["s22_reliance_contract_selection"]["decision"] == "SELECTED"
    assert certification["s22_reliance_contract_selection"]["selected_branch"] == "BEAR_CALL"
    assert certification["s22_reliance_contract_selection"]["selected_contract"]["symbol"] == "NSE:RELIANCE26AUG1260CE"

    target = certification["s22_reliance_target_result"]
    assert target["entry_validation"]["decision"] == "VALIDATED_NOT_SUBMITTABLE"
    assert target["exit_validation"]["decision"] == "VALIDATED_NOT_SUBMITTABLE"
    assert target["entry_internal_paper_result"]["final_state"] == "FILLED_INTERNAL"
    assert target["exit_position_transition"]["projection"]["lifecycle_state"] == "CLOSED"

    accounting = certification["s22_reliance_accounting"]
    assert accounting["trade_fact"]["execution"]["requested_entry_quantity"] == 500
    assert accounting["trade_fact"]["decision_context"]["configured_lots"] == 1
    assert accounting["trade_fact"]["decision_context"]["double_lot_multiplication"] is False
    assert accounting["pnl_facts"][0]["gross_pnl"] == "17250.00"


def test_s22_reliance_lifecycle_and_recovery_scenarios_pass() -> None:
    certification = build_s22_reliance_certification()

    assert certification["s22_reliance_original_sl_result"]["exit_position_transition"]["projection"]["lifecycle_state"] == "CLOSED"
    assert certification["s22_reliance_revised_sl_result"]["effective_plan"]["path_classification"] == "ABNORMAL_RECALCULATED"
    assert certification["s22_reliance_revised_sl_result"]["exit_position_transition"]["projection"]["lifecycle_state"] == "CLOSED"
    assert certification["s22_reliance_eod_carry_result"]["eod_exit"]["terminal_position_state"] == "CLOSED"
    assert certification["s22_reliance_eod_carry_result"]["equality_carry"]["equality_outcome"] == "CARRY_FORWARD"
    assert certification["s22_reliance_recovery_result"]["next_day_recovery"]["status"] == "CARRIED_POSITION_RECOVERABLE"
    assert certification["s22_reliance_recovery_result"]["duplicate_replay"]["duplicate_financial_action_created"] is False
    assert certification["s22_reliance_recovery_result"]["reconciliation_block"]["decision"] == "BLOCKED"


def test_s22_reliance_reports_are_written_without_tokens(tmp_path: Path) -> None:
    written = write_s22_reliance_reports(tmp_path)
    assert sorted(written) == sorted(S22_RELIANCE_REPORT_NAMES)

    for name in S22_RELIANCE_REPORT_NAMES:
        path = tmp_path / name
        assert path.exists(), name
        text = path.read_text(encoding="utf-8")
        assert "access_token" not in text.lower()
        assert "refresh_token" not in text.lower()
        if path.suffix == ".json":
            json.loads(text)
