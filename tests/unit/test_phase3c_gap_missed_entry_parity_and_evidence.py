from __future__ import annotations

import json
from pathlib import Path

from tfis.adapters.legacy_policies import (
    GapMissedEntryParitySourceClassification,
    build_gap_missed_entry_evidence_packet_sample,
    build_gap_missed_entry_parity_cases,
    run_gap_missed_entry_parity,
    write_gap_missed_entry_parity_reports,
)
from tfis.domain import TFISDecisionEvidencePacket, validate_decision_evidence_packet


def test_gap_missed_entry_parity_cases_cover_sources_branches_and_profiles() -> None:
    cases = build_gap_missed_entry_parity_cases()

    assert len(cases) == 8
    assert {
        GapMissedEntryParitySourceClassification.SYNTHETIC_GOLDEN_PARITY,
        GapMissedEntryParitySourceClassification.PARTIAL_CAPTURED_PARITY,
        GapMissedEntryParitySourceClassification.LEGACY_FIXTURE_PARITY,
        GapMissedEntryParitySourceClassification.UNSUPPORTED_FOR_PARITY,
    }.issubset({case.source_classification for case in cases})
    assert {
        "legacy.s23.gap_missed_entry.backtest_low_v1",
        "legacy.s23.gap_missed_entry.paper_live_high_v1",
        "legacy.s23.gap_missed_entry.unresolved_put_v1",
        "legacy.s21.gap_missed_entry.evidence_only_v1",
    }.issubset({case.compatibility_profile for case in cases})


def test_gap_missed_entry_parity_report_passes_supported_fields_and_keeps_fail_closed_cases_visible() -> None:
    report = run_gap_missed_entry_parity()
    summary = report.summary

    assert summary["total_cases"] == 8
    assert summary["passed_cases"] == 8
    assert summary["mismatched_cases"] == 0
    assert summary["fail_closed_cases"] == 2
    assert "S23_PUT_AUTHORITATIVE_RULE_UNRESOLVED" in summary["runtime_migration_blockers"]


def test_put_dual_profiles_can_diverge_on_same_candle_without_generic_auto_selection() -> None:
    report = run_gap_missed_entry_parity()
    low = next(result for result in report.results if result.case.case_id == "S23:BULL_PUT:MISSED_BACKTEST_LOW")
    high = next(result for result in report.results if result.case.case_id == "S23:BEAR_PUT:PAPER_LIVE_HIGH_NOT_MISSED")

    assert low.case.compatibility_profile.endswith("backtest_low_v1")
    assert high.case.compatibility_profile.endswith("paper_live_high_v1")
    assert low.generic.missed_entry.comparison_rule.observed_source.value == "OPTION_LOW"
    assert high.generic.missed_entry.comparison_rule.observed_source.value == "OPTION_HIGH"
    assert low.generic.missed_entry.status.value == "MISSED"
    assert high.generic.missed_entry.status.value == "NOT_MISSED"


def test_typed_decision_evidence_packet_fragment_round_trips_and_preserves_audit_values() -> None:
    packet = build_gap_missed_entry_evidence_packet_sample()
    round_tripped = TFISDecisionEvidencePacket.from_json(packet.to_json())
    validation = validate_decision_evidence_packet(round_tripped)
    fragment = round_tripped.gap_missed_entry.business_engine_fragment

    assert validation.is_valid is True
    assert fragment is not None
    assert fragment.profile == "legacy.s23.gap_missed_entry.backtest_low_v1"
    assert fragment.comparison_source == "OPTION_LOW"
    assert fragment.observed_value.value == packet.gap_missed_entry.business_engine_fragment.observed_value.value
    assert "gap_missed_entry_profile" in round_tripped.audit.compatibility_payload


def test_gap_missed_entry_reports_are_deterministic(tmp_path: Path) -> None:
    first = run_gap_missed_entry_parity()
    second = run_gap_missed_entry_parity()
    first_paths = write_gap_missed_entry_parity_reports(first, tmp_path / "first")
    second_paths = write_gap_missed_entry_parity_reports(second, tmp_path / "second")

    for key in ("json", "csv", "markdown", "packet"):
        assert first_paths[key].read_text(encoding="utf-8") == second_paths[key].read_text(encoding="utf-8")

    payload = json.loads(first_paths["json"].read_text(encoding="utf-8"))
    assert payload["summary"]["partial_captured_parity_cases"] == 1
    assert payload["summary"]["unsupported_for_parity_cases"] == 1
