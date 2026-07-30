from __future__ import annotations

from datetime import date

import pytest

from tfis.adapters.legacy_policies import s23_call_captured_evidence as fixtures
from tfis.adapters.legacy_policies import s23_m7_real_capture as m7


BULL_M5_HASH = "4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c"
BEAR_M5_HASH = "3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41"


def test_default_real_capture_remains_disabled() -> None:
    enablement = m7.S23RealCaptureEnablement.disabled()

    assert enablement.enabled is False
    assert enablement.method == "DEFAULT_DISABLED"
    assert not m7.capture_enabled_for_session(
        enablement,
        strategy_instance="S23_NIFTY_ACCOUNT_A_PAPER",
        trading_date=date(2026, 6, 5),
        session_id="live_20260605_090537_prod_pid14520",
    )


def test_explicit_session_only_capture_enablement() -> None:
    enablement = m7.explicit_session_capture_enablement(
        output_dir="reports/phase3d",
        strategy_instance="S23_NIFTY_ACCOUNT_A_PAPER",
        trading_date=date(2026, 6, 5),
        session_id="live_20260605_090537_prod_pid14520",
        reason="M7 non-authoritative post-market capture.",
    )

    assert m7.capture_enabled_for_session(
        enablement,
        strategy_instance="S23_NIFTY_ACCOUNT_A_PAPER",
        trading_date=date(2026, 6, 5),
        session_id="live_20260605_090537_prod_pid14520",
    )
    assert not m7.capture_enabled_for_session(
        enablement,
        strategy_instance="S23_NIFTY_ACCOUNT_A_PAPER",
        trading_date=date(2026, 6, 6),
        session_id="live_20260605_090537_prod_pid14520",
    )


def test_explicit_enablement_rejects_incomplete_scope() -> None:
    with pytest.raises(ValueError):
        m7.explicit_session_capture_enablement(
            output_dir="",
            strategy_instance="S23_NIFTY_ACCOUNT_A_PAPER",
            trading_date=date(2026, 6, 5),
            session_id="live_20260605_090537_prod_pid14520",
            reason="M7",
        )


def test_real_packet_parser_normalizer_redacts_secret_fields() -> None:
    packet = _packet()
    packet["source_session"]["access_token"] = "must-not-leak"

    normalized = m7.normalize_real_capture_packet(packet)

    assert normalized["source_session"]["access_token"] == "REDACTED"


def test_malformed_packet_rejection() -> None:
    issues = m7.validate_real_capture_packet({"schema_version": "wrong"})

    assert "INVALID_SCHEMA_VERSION" in issues
    assert "MISSING_SECTION:opening_context" in issues


def test_provenance_completeness_required() -> None:
    packet = _packet()
    packet["field_provenance"] = {}

    assert "MISSING_FIELD_PROVENANCE" in m7.validate_real_capture_packet(packet)


def test_orpt_timestamp_preservation() -> None:
    packet = _packet()

    assert packet["orpt_observation"]["timestamp"] == "2026-06-05T09:24:59+05:30"


def test_rc_timestamp_preservation() -> None:
    packet = _packet()

    assert packet["rc_observation"]["timestamp"] == "2026-06-05T09:29:59+05:30"


def test_option_chain_snapshot_preservation() -> None:
    packet = _packet()

    assert packet["opening_context"]["option_chain_snapshot"]["contract_count"] == 2
    assert "NIFTY_20260609_22650_CE" in packet["opening_context"]["option_chain_snapshot"]["symbols"]


def test_selected_contract_quote_preservation() -> None:
    packet = _packet()

    assert packet["opening_context"]["selected_contract_quote"]["symbol"] == "NIFTY_20260609_22650_CE"
    assert packet["opening_context"]["selected_contract_quote"]["ltp"] == 850.0


def test_authoritative_and_shadow_results_remain_separate() -> None:
    packet = _packet()

    assert packet["authoritative_legacy_result"]["source"] != packet["refactored_shadow_result"]["source"]
    assert packet["authoritative_legacy_result"]["final_decision_status"] is None
    assert packet["refactored_shadow_result"]["final_decision_status"] == "SHADOW_DECISION_TRADE"


def test_shadow_trade_does_not_create_execution_intent() -> None:
    assert m7.shadow_trade_is_observation_only(_packet()["refactored_shadow_result"])


def test_shadow_trade_with_execution_intent_is_rejected() -> None:
    packet = _packet()
    packet["refactored_shadow_result"]["execution_intent"] = "PLACE_ORDER"

    assert not m7.shadow_trade_is_observation_only(packet["refactored_shadow_result"])
    assert "SHADOW_RESULT_HAS_EXECUTION_INTENT" in m7.validate_real_capture_packet(packet)


def test_partial_packet_classification() -> None:
    packet = _packet()

    assert m7.classify_real_capture_packet(packet) == "PARTIAL_CAPTURE"


def test_carried_position_absent_classification() -> None:
    packet = _packet()

    assert packet["carried_position"]["status"] == "CARRIED_POSITION_NOT_PRESENT"


def test_carried_position_observation_mapping_when_present() -> None:
    packet = _packet()
    packet["carried_position"] = {
        "status": "CARRIED_POSITION_PRESENT",
        "position_identity": "cycle-1",
        "contract": "NIFTY_20260609_22650_CE",
        "side": "SELL",
        "quantity": 50,
        "prior_trading_date": "2026-06-04",
        "opening_quote": {"ltp": 850.0},
        "gap_context": "NO_OFFICIAL_OPEN_CAPTURED",
        "protective_levels": {"source": "MISSING_LEGACY_OUTPUT"},
        "authoritative_lifecycle_action": None,
        "unavailable_lifecycle_rule_fields": ["carried_position_gap_rule"],
    }

    normalized = m7.normalize_real_capture_packet(packet)

    assert normalized["carried_position"]["status"] == "CARRIED_POSITION_PRESENT"
    assert normalized["carried_position"]["contract"] == "NIFTY_20260609_22650_CE"


def test_parity_classifies_missing_legacy_outputs() -> None:
    compared = m7.compare_reference_to_shadow(
        reference={"strategy_branch": None},
        shadow={"strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D"},
        fields=("strategy_branch",),
    )

    assert compared["strategy_branch"]["classification"] == "MISSING_LEGACY_OUTPUT"


def test_gap_matrix_uses_m7_classifications() -> None:
    matrix = m7.build_real_capture_gap_matrix(_packet())

    assert matrix["schema_version"] == "tfis.phase3d.m7.real_capture_gap_matrix.v1"
    assert any(row["classification"] == "MISSING_CAPTURED_INPUT" for row in matrix["gaps"])


def test_existing_m3_to_m6_regression_hashes_are_preserved() -> None:
    bull = fixtures.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture")
    bear = fixtures.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")

    assert bull.deterministic_hash == BULL_M5_HASH
    assert bear.deterministic_hash == BEAR_M5_HASH


def test_real_packet_passes_architecture_authority_checks() -> None:
    packet = _packet()

    assert m7.validate_real_capture_packet(packet) == ()
    assert packet["execution_authority"]["refactored_authority"] == "NONE"
    assert packet["decision_runtime_influence"] == "NONE"


def _packet() -> dict:
    return {
        "schema_version": m7.SCHEMA_VERSION,
        "session_comparable": True,
        "evidence_classification": "PARTIAL_CAPTURE",
        "enablement": {
            "default_capture_state": "DISABLED",
            "method": "EXPLICIT_SESSION_DEBUG_OVERRIDE",
            "output_dir": "reports/phase3d",
            "strategy_instance": "S23_NIFTY_ACCOUNT_A_PAPER",
            "trading_date": "2026-06-05",
            "session_id": "live_20260605_090537_prod_pid14520",
        },
        "source_session": {
            "source_repository_process": "D:/TradingData captured post-market session",
            "session_type": "post-market",
        },
        "pre_market_plan": {
            "strategy_instance": "S23_NIFTY_ACCOUNT_A_PAPER",
            "branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
            "plan_status": "PARTIAL",
        },
        "opening_context": {
            "exchange_open_timestamp": "2026-06-05T09:15:00+05:30",
            "option_chain_snapshot": {
                "contract_count": 2,
                "symbols": ["NIFTY_20260609_22650_CE", "NIFTY_20260609_24250_PE"],
            },
            "selected_contract_quote": {
                "symbol": "NIFTY_20260609_22650_CE",
                "ltp": 850.0,
            },
        },
        "orpt_observation": {
            "timestamp": "2026-06-05T09:24:59+05:30",
            "selected_contract_observation": {"status": "MISSING_CAPTURED_INPUT"},
        },
        "rc_observation": {
            "timestamp": "2026-06-05T09:29:59+05:30",
            "selected_contract_observation": {"ltp": 850.0},
        },
        "authoritative_legacy_result": {
            "source": "D:/TradingData/logs/trade/trade_evaluation_20260605_090537_prod_pid14520.log",
            "final_decision_status": None,
        },
        "refactored_shadow_result": {
            "source": "TFISRefactored offline S23 Call-side vertical with capture observer",
            "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
            "final_decision_status": "SHADOW_DECISION_TRADE",
            "execution_intent": "NONE",
        },
        "parity": {
            "strategy_branch": {"classification": "MISSING_LEGACY_OUTPUT"},
        },
        "carried_position": {
            "status": "CARRIED_POSITION_NOT_PRESENT",
        },
        "provenance": {
            "capture_created_by": "phase3d_m7_real_capture",
        },
        "field_provenance": {
            "orpt_observation.timestamp": "capture_adapter_window",
            "rc_observation.timestamp": "capture_adapter_window",
            "opening_context.option_chain_snapshot": "real_option_quote_archive",
        },
        "missing_or_derived_fields": {
            "missing": ["authoritative_s23_call_decision", "orpt_selected_contract_quote", "oi"],
            "derived": ["exchange_open_timestamp"],
            "supplemented": [],
        },
        "execution_authority": {
            "refactored_authority": "NONE",
            "can_place_order": False,
            "can_modify_order": False,
            "can_cancel_order": False,
        },
        "decision_runtime_influence": "NONE",
    }
