from __future__ import annotations

from pathlib import Path

from tfis.adapters.legacy_policies import s23_replay_shadow
from tfis.runtime import RuntimeDeliveryClass, RuntimeEventType
from tfis.runtime.replay import load_captured_runtime_events


def test_captured_fixture_normalizes_into_m15_runtime_events() -> None:
    s23_replay_shadow.write_phase4a_reports()
    session = load_captured_runtime_events(
        s23_replay_shadow.SOURCE_MARKET_EVENTS,
        session_id="live_20260527_090535_dev_pid16276",
        strategy_instance_id=s23_replay_shadow.PRIMARY_STRATEGY_INSTANCE,
        selected_contract=s23_replay_shadow.NORMALIZED_SELECTED_CONTRACT,
    )

    event_types = {event.event_type for event in session.events}

    assert RuntimeEventType.CONFIGURATION_READY in event_types
    assert RuntimeEventType.STRATEGY_ENABLED in event_types
    assert RuntimeEventType.PREMARKET_PREPARATION_TIME in event_types
    assert RuntimeEventType.SESSION_OPEN_OBSERVATION in event_types
    assert RuntimeEventType.OPTION_CONTRACT_QUOTE in event_types
    assert RuntimeEventType.OI_UPDATE in event_types
    assert RuntimeEventType.ORPT_TIME in event_types
    assert RuntimeEventType.RC_TIME in event_types
    assert RuntimeEventType.EOD_EVALUATION_TIME not in event_types
    assert any(event.delivery_class is RuntimeDeliveryClass.NON_CONFLATABLE_CRITICAL_EVENT for event in session.events)


def test_phase4a_shadow_reports_are_shadow_only_and_honest_partial_capture() -> None:
    reports = s23_replay_shadow.write_phase4a_reports()

    assert reports.shadow_result["authority_mode"] == "SHADOW_ONLY"
    assert reports.shadow_result["classification"] == "PARTIAL_CAPTURED_SHADOW_CASE"
    assert reports.shadow_result["broker_order_path_reached"] is False
    assert reports.shadow_result["paper_order_path_reached"] is False
    assert reports.legacy_comparison["parity_claimed"] is False
    assert reports.legacy_comparison["comparison_classification"] == "MISSING_LEGACY_OUTPUT"
    assert reports.shadow_result["authority"]["broker_submission_permitted"] is False
    assert reports.shadow_result["authority"]["order_creation_permitted"] is False
    assert reports.shadow_result["authority"]["position_mutation_permitted"] is False


def test_phase4a_three_replays_and_checkpoint_resume_are_deterministic() -> None:
    reports = s23_replay_shadow.write_phase4a_reports()

    assert reports.performance_metrics["deterministic_three_replay"] is True
    hashes = reports.performance_metrics["three_replay_hashes"]
    assert len(hashes) == 3
    assert len(set(hashes)) == 1
    assert reports.performance_metrics["checkpoint_resume"]["matches_full_replay"] is True
    assert reports.performance_metrics["conflation_result_unchanged"] is True


def test_phase4a_multi_instance_reuses_market_stream_but_keeps_state_independent() -> None:
    reports = s23_replay_shadow.write_phase4a_reports()
    multi = reports.performance_metrics["multi_instance"]

    assert multi["account_credentials_required"] is False
    assert multi["independent_results"] is True
    assert multi["strategy_instances"] == ["primary", "secondary"]
    assert multi["shared_subscription_hash"]


def test_phase4a_fail_closed_cases_are_precise_and_non_authoritative() -> None:
    reports = s23_replay_shadow.write_phase4a_reports()

    cases = reports.performance_metrics["fail_closed_cases"]
    assert len(cases) >= 15
    assert {case["classification"] for case in cases} >= {
        "MISSING_ORPT_OBSERVATION",
        "MISSING_RC_OBSERVATION",
        "REJECTED_WRONG_CONTRACT",
        "WRONG_TRADING_DATE",
        "CHECKPOINT_MISMATCH",
    }
    assert all(case["authoritative_action"] == "NONE" for case in cases)
    assert all(case["fabricated_replacement_values"] is False for case in cases)


def test_phase4a_reports_are_written_to_expected_paths() -> None:
    s23_replay_shadow.write_phase4a_reports()
    expected = {
        "phase4a_capture_inventory.json",
        "phase4a_selected_session.json",
        "phase4a_normalized_event_summary.json",
        "phase4a_shadow_result.json",
        "phase4a_shadow_evidence_packet.json",
        "phase4a_legacy_comparison.json",
        "phase4a_field_provenance_matrix.json",
        "phase4a_capture_gap_register.json",
        "phase4a_performance_metrics.json",
        "phase4a_replay_summary.md",
    }
    report_dir = Path("reports/phase4a")
    assert expected <= {path.name for path in report_dir.iterdir()}
