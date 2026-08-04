from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from tfis.runtime.multi_strategy.fast_track_development import (
    build_current_entry_actions,
    build_explanation_facts,
    write_fast_track_reports,
)
from tfis.runtime.multi_strategy.registry import EnabledStrategyInstance
from tfis.execution_intent.pricing import normalize_executable_price


IST = ZoneInfo("Asia/Calcutta")


def _instance(strategy_instance_id: str, symbol: str, lot_size: int) -> EnabledStrategyInstance:
    return EnabledStrategyInstance(
        strategy_definition_id=f"{strategy_instance_id}_DEF",
        strategy_version="test.v1",
        strategy_instance_id=strategy_instance_id,
        account_reference="INTERNAL_PAPER_ACCOUNT_A",
        underlying={"exchange": "NSE", "symbol": symbol, "instrument_type": "INDEX"},
        product="OPTION_SELLING",
        enabled=True,
        configured_quantity={"lots": 1, "lot_size": lot_size},
        authority_mode="INTERNAL_PAPER_CONTROLLED",
        market_data_source="FYERS_READ_ONLY",
        rule_config_hash="rule-hash",
        risk_allocation={"max_positions": 1, "max_margin_usage_pct": 25},
        operator_approval_status="APPROVED_INTERNAL_PAPER",
        evidence_quality="LIVE_READ_ONLY_RUNTIME_SELECTION",
        deterministic_projection={"branch": "BULL_CALL", "entry": "100.00", "target": "40.00", "original_sl": "140.00"},
    )


def test_build_current_entry_actions_processes_only_still_valid_entries() -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=IST)
    s21 = _instance("S21_BANKNIFTY_INTERNAL_PAPER_A", "BANKNIFTY", 15)
    s22 = _instance("S22_RELIANCE_INTERNAL_PAPER_A", "RELIANCE", 500)

    result = build_current_entry_actions(
        registry_instances=(s21, s22),
        continuities={
            "S21_BANKNIFTY_INTERNAL_PAPER_A": {
                "current_entry_state": "NORMAL_ENTRY_STILL_VALID",
                "recovery_mode": "HISTORICALLY_RECONSTRUCTED",
                "selected_contract": "NSE:BANKNIFTY26AUG57000CE",
                "selected_option_type": "CALL",
                "selected_expiry": "2026-08-27",
                "selected_strike": "57000",
                "entry": "812.00",
                "target": "301.00",
                "original_sl": "1184.10",
                "evidence": "HISTORICAL_UNDERLYING_PLUS_CURRENT_CHAIN_RECONSTRUCTION",
                "orpt_result": "ORPT_ENTRY_NOT_MISSED",
                "rc_result": "RC_NOT_REQUIRED",
                "quote": {"ltp": "812.00"},
                "plan_payload": {"plan_hash": "plan-hash"},
                "reconstruction": {"option_evidence_quality": "COMPLETE_REQUIRED_INTERVAL_BARS"},
            },
            "S22_RELIANCE_INTERNAL_PAPER_A": {
                "current_entry_state": "RC_ENTRY_ALREADY_MISSED",
                "recovery_mode": "HISTORICALLY_RECONSTRUCTED",
                "selected_contract": "NSE:RELIANCE26AUG1260CE",
                "entry": "57.50",
                "evidence": "REPORT_TRACE_PLUS_FYERS_HISTORY",
                "reconstruction": {"option_evidence_quality": "COMPLETE_REQUIRED_INTERVAL_BARS"},
            },
        },
        now=now,
        trading_session_id="NSE:2026-08-04:FAST_TRACK_DEVELOPMENT",
    )

    assert result["external_broker_order_authority"] == "NONE"
    assert result["outcomes"]["S21_BANKNIFTY_INTERNAL_PAPER_A"]["decision"] == "PROCESSED_INTERNAL_PAPER"
    assert result["outcomes"]["S21_BANKNIFTY_INTERNAL_PAPER_A"]["final_state"] == "FILLED_INTERNAL"
    assert result["outcomes"]["S22_RELIANCE_INTERNAL_PAPER_A"]["decision"] == "NO_ORDER"
    assert result["outcomes"]["S22_RELIANCE_INTERNAL_PAPER_A"]["reason"] == "RC_ENTRY_ALREADY_MISSED"


def test_build_explanation_facts_preserves_candidate_rejections() -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=IST)
    instance = _instance("S23_NIFTY_INTERNAL_PAPER_A", "NIFTY", 50)

    facts = build_explanation_facts(
        instance=instance,
        continuity={
            "selected_contract": "NSE:NIFTY26AUG22500PE",
            "selected_branch": "BULL_PUT",
            "selected_option_type": "PUT",
            "selected_expiry": "2026-08-27",
            "selected_strike": "22500",
            "candidate_count": 3,
            "rejected_candidates": [{"symbol": "NSE:NIFTY26AUG22600PE", "reason": "IDEAL_PREMIUM_NOT_MET"}],
            "entry": "194.25",
            "current_entry_state": "NORMAL_ENTRY_STILL_VALID",
            "orpt_result": "ORPT_ENTRY_NOT_MISSED",
            "rc_result": "RC_NOT_REQUIRED",
            "evidence": "HISTORICAL_UNDERLYING_PLUS_CURRENT_CHAIN_RECONSTRUCTION",
            "recovery_mode": "HISTORICALLY_RECONSTRUCTED",
            "quote": {"ltp": "194.25"},
            "reconstruction": {
                "option_evidence_quality": "COMPLETE_REQUIRED_INTERVAL_BARS",
                "normal_entry": {"breach_timestamp": None},
            },
            "plan_payload": {"plan_hash": "abc123"},
        },
        now=now,
        trading_session_id="NSE:2026-08-04:FAST_TRACK_DEVELOPMENT",
    )

    assert len(facts) == 2
    assert facts[0]["stage"] == "CONTRACT_SELECTION"
    assert facts[0]["candidate_evidence"]["rejected_candidates"][0]["reason"] == "IDEAL_PREMIUM_NOT_MET"
    assert facts[1]["stage"] == "ENTRY_ELIGIBILITY"
    assert facts[1]["evidence_mode"] == "HISTORICALLY_RECONSTRUCTED"


def test_write_fast_track_reports_writes_expected_files(tmp_path: Path) -> None:
    now = datetime(2026, 8, 4, 12, 0, tzinfo=IST)
    written = write_fast_track_reports(
        report_dir=tmp_path,
        session_date=now.date(),
        trading_session_id="NSE:2026-08-04:FAST_TRACK_DEVELOPMENT",
        baseline_results={
            "S21_BANKNIFTY_INTERNAL_PAPER_A": {
                "selection": {"selected_contract": "NSE:BANKNIFTY26AUG57000CE", "recovery_mode": "HISTORICALLY_RECONSTRUCTED"},
                "reconstruction": {"current_entry_state": "NORMAL_ENTRY_STILL_VALID"},
            },
        },
        current_entry_actions={
            "captured_at": now.isoformat(),
            "outcomes": {"S21_BANKNIFTY_INTERNAL_PAPER_A": {"decision": "PROCESSED_INTERNAL_PAPER"}},
            "explanation_facts": [{"decision_id": "x"}],
        },
        tcs_result={"symbol": "TCS", "status": "DEVELOPMENT_READY_BUT_NOT_ACTIVATED"},
        infy_result={"symbol": "INFY", "status": "DEVELOPMENT_READY_BUT_NOT_ACTIVATED"},
    )

    assert "current_entry_actions.json" in written
    payload = json.loads((tmp_path / "dashboard_explainability_result.json").read_text(encoding="utf-8"))
    assert payload["status"] == "BACKEND_FACTS_READY_FOR_DASHBOARD_CONSUMPTION"


def test_normalize_executable_price_uses_nearest_tick_half_up() -> None:
    assert normalize_executable_price(Decimal("127.23"), Decimal("0.05")) == Decimal("127.25")
    assert normalize_executable_price(Decimal("203.57"), Decimal("0.05")) == Decimal("203.55")
    assert normalize_executable_price(Decimal("57.50"), Decimal("0.05")) == Decimal("57.50")


def test_build_current_entry_actions_normalizes_raw_entry_to_tick_size() -> None:
    now = datetime(2026, 8, 4, 13, 24, tzinfo=IST)
    s23 = _instance("S23_NIFTY_INTERNAL_PAPER_A", "NIFTY", 65)

    result = build_current_entry_actions(
        registry_instances=(s23,),
        continuities={
            "S23_NIFTY_INTERNAL_PAPER_A": {
                "current_entry_state": "NORMAL_ENTRY_STILL_VALID",
                "recovery_mode": "HISTORICALLY_RECONSTRUCTED",
                "selected_contract": "NSE:NIFTY2680424150CE",
                "selected_option_type": "CALL",
                "selected_expiry": "2026-08-04",
                "selected_strike": "24150",
                "entry": "127.23",
                "target": "80.00",
                "original_sl": "203.57",
                "evidence": "HISTORICAL_UNDERLYING_PLUS_CURRENT_CHAIN_RECONSTRUCTION",
                "orpt_result": "ORPT_ENTRY_NOT_MISSED",
                "rc_result": "RC_NOT_REQUIRED",
                "quote": {"ltp": "337.40"},
                "plan_payload": {"plan_hash": "plan-hash"},
                "reconstruction": {"option_evidence_quality": "COMPLETE_REQUIRED_INTERVAL_BARS"},
            },
        },
        now=now,
        trading_session_id="NSE:2026-08-04:FAST_TRACK_DEVELOPMENT",
    )

    outcome = result["outcomes"]["S23_NIFTY_INTERNAL_PAPER_A"]
    assert outcome["decision"] == "PROCESSED_INTERNAL_PAPER"
    assert outcome["final_state"] == "FILLED_INTERNAL"
    entry_fact = next(
        item
        for item in result["explanation_facts"]
        if item["strategy_instance_id"] == "S23_NIFTY_INTERNAL_PAPER_A" and item["stage"] == "ENTRY_ELIGIBILITY"
    )
    assert entry_fact["input_values"]["base_entry"] == "127.23"
