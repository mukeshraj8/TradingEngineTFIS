from __future__ import annotations

import json
from pathlib import Path

from tfis.adapters.legacy_policies import (
    PHASE3C_CERTIFICATION_SCHEMA_VERSION,
    PHASE3C_FINAL_VERDICT,
    build_phase3c_certification,
    run_gap_missed_entry_parity,
    write_phase3c_certification_reports,
)


ROOT = Path(__file__).resolve().parents[2]


def test_phase3c_certification_reports_distinct_readiness_verdicts_and_counts() -> None:
    certification = build_phase3c_certification(run_gap_missed_entry_parity())

    assert certification["schema_version"] == PHASE3C_CERTIFICATION_SCHEMA_VERSION
    assert certification["final_verdict"] == PHASE3C_FINAL_VERDICT
    assert certification["readiness_verdicts"]["architecture"] == "READY"
    assert certification["readiness_verdicts"]["supported_offline_parity"] == "READY"
    assert certification["readiness_verdicts"]["complete_captured_parity"] == "NOT_READY"
    assert certification["readiness_verdicts"]["disabled_runtime_shadow"] == "NOT_READY"
    assert certification["readiness_verdicts"]["paper_decision_authority"] == "NOT_READY"
    assert certification["readiness_verdicts"]["live_money_authority"] == "NOT_READY"
    assert certification["parity_counts"]["total_cases"] == 8
    assert certification["parity_counts"]["passed_cases"] == 8
    assert certification["parity_counts"]["mismatched_cases"] == 0
    assert certification["parity_counts"]["fail_closed_cases"] == 2
    assert certification["parity_counts"]["full_captured_parity_cases"] == 0
    assert certification["parity_counts"]["partial_captured_parity_cases"] == 1
    assert certification["parity_counts"]["synthetic_golden_parity_cases"] == 1
    assert certification["parity_counts"]["legacy_fixture_parity_cases"] == 5
    assert certification["parity_counts"]["unsupported_for_parity_cases"] == 1


def test_phase3c_certification_has_stable_requirement_ids_and_test_mapping() -> None:
    certification = build_phase3c_certification(run_gap_missed_entry_parity())
    requirements = certification["requirements"]

    assert [item["id"] for item in requirements] == [f"TFIS-GME-{index:03d}" for index in range(1, 21)]
    assert all(item["tests"] for item in requirements)
    assert any("test_business_engine_boundary.py" in test for item in requirements for test in item["tests"])
    assert any("test_phase3c_gap_missed_entry_parity_and_evidence.py" in test for item in requirements for test in item["tests"])


def test_phase3c_certification_preserves_open_rules_and_entry_handoff_boundary() -> None:
    certification = build_phase3c_certification(run_gap_missed_entry_parity())
    open_rules = {item["issue_id"]: item for item in certification["open_rules"]}
    handoff = certification["entry_engine_handoff"]

    assert set(open_rules) == {"TFIS-GME-OPEN-001", "TFIS-GME-OPEN-002", "TFIS-GME-OPEN-003"}
    assert open_rules["TFIS-GME-OPEN-001"]["blocks_runtime_shadow"] is True
    assert open_rules["TFIS-GME-OPEN-002"]["blocks_live_money"] is True
    assert open_rules["TFIS-GME-OPEN-003"]["blocks_offline_use"] is False
    assert "missed_entry.comparison_rule.observed_source" in handoff["must_consume"]
    assert "recalculation.compatibility_outputs" in handoff["compatibility_only_fields"]
    assert "select an authoritative S23 PUT profile" in handoff["must_not_do"]


def test_phase3c_certification_report_files_are_deterministic(tmp_path: Path) -> None:
    first = build_phase3c_certification(run_gap_missed_entry_parity())
    second = build_phase3c_certification(run_gap_missed_entry_parity())
    first_paths = write_phase3c_certification_reports(first, tmp_path / "first")
    second_paths = write_phase3c_certification_reports(second, tmp_path / "second")

    for key in ("json", "markdown"):
        assert first_paths[key].read_text(encoding="utf-8") == second_paths[key].read_text(encoding="utf-8")

    payload = json.loads(first_paths["json"].read_text(encoding="utf-8"))
    assert payload["performance_certification"]["evidence_fragment_size_bytes"] > 0
    assert "broker call" in payload["performance_certification"]["verified_absent"]


def test_phase3c_authoritative_spec_contains_all_required_sections_and_ids() -> None:
    spec = (ROOT / "docs" / "architecture" / "tfis_phase3c_gap_missed_entry_engine.md").read_text(encoding="utf-8")
    register = (ROOT / "docs" / "architecture" / "tfis_phase3c_open_rule_register.md").read_text(encoding="utf-8")

    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        assert f"## {letter}." in spec
    for index in range(1, 21):
        assert f"TFIS-GME-{index:03d}" in spec
    for issue in ("TFIS-GME-OPEN-001", "TFIS-GME-OPEN-002", "TFIS-GME-OPEN-003"):
        assert issue in spec
        assert issue in register
