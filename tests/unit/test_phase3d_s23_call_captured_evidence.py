from __future__ import annotations

import json
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies import s23_call_captured_evidence as m5
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.domain import TFISTradeResult


BULL_CALL_M3_HASH = "4d2e514f05f873c17b7077ce6710c559dac54422ed6898cbb51e6ed9bbb24b84"
BEAR_CALL_M4_HASH = "39113635711a32f33036bae3f29efab0fe1a3ede898c7d6e0a39df88b238d053"


def test_m5_loads_two_call_side_evidence_fixtures() -> None:
    fixtures = m5.load_s23_call_evidence_fixtures()

    assert tuple(item.case_key for item in fixtures) == (
        "s23_bear_call_workbook_fixture",
        "s23_bull_call_workbook_fixture",
    )
    assert {item.evidence_classification for item in fixtures} == {"LEGACY_FIXTURE"}


@pytest.mark.parametrize(
    "case_key,branch",
    (
        ("s23_bull_call_workbook_fixture", "S23_BULL_CALL"),
        ("s23_bear_call_workbook_fixture", "S23_BEAR_CALL"),
    ),
)
def test_m5_call_evidence_fixture_runs_existing_vertical_pipeline(case_key: str, branch: str) -> None:
    result = m5.run_s23_call_evidence_fixture(case_key)
    summary = m5.summarize_s23_call_evidence_result(result)

    assert result.decision.trade_result is TFISTradeResult.TRADE
    assert summary["branch"] == branch
    assert summary["evidence_classification"] == "LEGACY_FIXTURE"
    assert summary["parity_result"] == "PASSED"
    assert summary["runtime_impact"] == "NONE"
    assert result.decision.compatibility_payload["m5_evidence"]["case_key"] == case_key


def test_m5_field_provenance_is_complete_and_uses_allowed_classifications() -> None:
    for fixture in m5.load_s23_call_evidence_fixtures():
        assert set(fixture.field_provenance) == set(m5.REQUIRED_EVIDENCE_FIELDS)
        assert set(fixture.field_provenance.values()) <= m5.ALLOWED_FIELD_PROVENANCE


def test_m5_synthetic_supplements_are_disclosed() -> None:
    result = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")
    summary = m5.summarize_s23_call_evidence_result(result)

    assert "single qualifying option-chain candidate" in summary["synthetic_supplements"]
    assert "captured selected-contract quote" in summary["missing_fields"]
    assert "single qualifying option-chain candidate" in result.evidence_packet.audit.compatibility_payload["m5_synthetic_supplements"]


def test_m5_captured_versus_vertical_field_comparison_uses_m5_classifications() -> None:
    result = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture")
    summary = m5.summarize_s23_call_evidence_result(result)

    assert summary["field_comparisons"]["branch"]["classification"] == "MATCH"
    assert summary["field_comparisons"]["base_entry"]["classification"] == "MATCH"
    assert summary["field_comparisons"]["target"]["classification"] == "MATCH"
    assert summary["field_comparisons"]["msl"]["classification"] == "MATCH"
    assert not summary["mismatch_classifications"]


def test_m5_evidence_fixture_output_is_deterministic() -> None:
    first = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")
    second = m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")

    assert first.deterministic_hash == second.deterministic_hash
    assert first.decision.comparison_key() == second.decision.comparison_key()
    assert first.evidence_packet.to_json() == second.evidence_packet.to_json()


def test_m5_preserves_m3_and_m4_synthetic_golden_regressions() -> None:
    assert vertical.run_s23_bull_call_vertical_slice().deterministic_hash == BULL_CALL_M3_HASH
    assert vertical.run_s23_bear_call_vertical_slice().deterministic_hash == BEAR_CALL_M4_HASH


def test_m5_missing_required_fixture_field_fails_closed(tmp_path: Path) -> None:
    data = json.loads(m5.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    data["cases"][0].pop("field_provenance")
    fixture = tmp_path / "bad_s23_call_fixture.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="missing fields"):
        m5.load_s23_call_evidence_fixtures(fixture)


def test_m5_malformed_field_provenance_fails_closed(tmp_path: Path) -> None:
    data = json.loads(m5.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    data["cases"][0]["field_provenance"]["strategy_identity"] = "GUESSED"
    fixture = tmp_path / "bad_s23_call_fixture.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported field provenance"):
        m5.load_s23_call_evidence_fixtures(fixture)


def test_m5_business_evaluation_does_not_write_files(monkeypatch) -> None:
    def fail_write(self, *args, **kwargs):
        raise AssertionError(f"unexpected write during M5 business evaluation: {self}")

    monkeypatch.setattr(Path, "write_text", fail_write)

    result = m5.run_s23_call_evidence_fixture("s23_bull_call_workbook_fixture")

    assert result.decision.trade_result is TFISTradeResult.TRADE


def test_m5_does_not_mutate_source_fixture() -> None:
    before = m5.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8")

    m5.run_all_s23_call_evidence_fixtures()

    assert m5.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8") == before


def test_m5_has_no_runtime_authority_or_live_api_dependency() -> None:
    source = Path(m5.__file__).read_text(encoding="utf-8")

    assert "Fyers" not in source
    assert "fyers" not in source
    assert "requests" not in source
    assert m5.summarize_s23_call_evidence_result(
        m5.run_s23_call_evidence_fixture("s23_bear_call_workbook_fixture")
    )["runtime_impact"] == "NONE"


def test_m5_evidence_gap_matrix_keeps_captured_and_synthetic_metrics_separate() -> None:
    matrix = m5.build_s23_call_evidence_gap_matrix(m5.run_all_s23_call_evidence_fixtures())

    assert len(matrix["cases"]) == 2
    assert {case["evidence_classification"] for case in matrix["cases"]} == {"LEGACY_FIXTURE"}
    assert all(case["synthetic_supplements"] for case in matrix["cases"])
