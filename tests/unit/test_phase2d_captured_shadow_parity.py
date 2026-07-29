from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies import (
    CapturedEvidenceQuality,
    CapturedMismatchClassification,
    build_captured_parity_report,
    discover_captured_evidence,
    evaluate_captured_case_with_generic,
    evaluate_captured_case_with_legacy,
    load_captured_jsonl_cases,
    run_captured_shadow_parity,
    runtime_input_from_captured_case,
    write_captured_parity_reports,
)
from tfis.domain import TFISTradeResult


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "tests" / "fixtures" / "paper" / "s23_archive_ingress_dry_run.jsonl"
PRELUDE = ROOT / "tests" / "fixtures" / "paper" / "s23_fyers_prelude.jsonl"


def test_captured_importer_preserves_ordering_timestamps_and_null_vs_zero(tmp_path: Path) -> None:
    source = tmp_path / "captured.jsonl"
    rows = [_event("TRADE_PLAN_INPUT", 3), _event("MONTHLY_STATUS_INPUT", 1), _event("UNDERLYING_SNAPSHOT", 2)]
    rows[0]["payload"] = {
        "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        "order_side": "SELL",
        "lots": 0,
        "quantity": 0,
        "planned_entry_price": 0.0,
        "target_price": 0.0,
        "stoploss_price": 0.0,
        "start_strike": 0.0,
        "end_strike": 0.0,
        "ideal_premium": 0.0,
        "minimum_premium": 0.0,
    }
    rows[1]["payload"] = {"monthly_status": "BEAR"}
    rows[2]["payload"] = {
        "snapshot_label": "ORPT",
        "open": None,
        "high": 0.0,
        "low": 0.0,
        "close": 0.0,
        "bar_start": "2026-05-08T09:23:59+05:30",
        "bar_end": "2026-05-08T09:24:59+05:30",
        "complete": True,
    }
    source.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    case = load_captured_jsonl_cases((source,))[0]

    assert case.capture_timestamp == datetime.fromisoformat("2026-05-08T09:30:03+05:30")
    assert case.expected_legacy_decision["lots"] == 0
    assert case.current_day_references["orpt_high"] == 0.0
    assert case.orpt_rc_evidence["status"] == "MISSING_ORPT_RC"
    assert case.missing_fields == tuple(sorted(case.missing_fields))


def test_captured_importer_fails_closed_on_missing_mandatory_schema(tmp_path: Path) -> None:
    source = tmp_path / "bad.jsonl"
    source.write_text(json.dumps({"event_type": "TRADE_PLAN_INPUT"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing envelope fields"):
        load_captured_jsonl_cases((source,))


def test_captured_cases_are_deterministically_serialized_and_classified_partial() -> None:
    cases = load_captured_jsonl_cases((PRELUDE, ARCHIVE))

    assert [case.source_file.name for case in cases] == [
        "s23_archive_ingress_dry_run.jsonl",
        "s23_fyers_prelude.jsonl",
    ]
    assert cases[0].to_json() == cases[0].to_json()
    assert cases[0].evidence_quality is CapturedEvidenceQuality.PARTIAL_CAPTURED_PARITY
    assert "market_structure_references" in cases[0].missing_fields
    assert "option_reference_values" in cases[0].missing_fields
    assert "option_chain_snapshot" not in cases[0].missing_fields
    assert "option_chain_snapshot" in cases[1].missing_fields


def test_evidence_inventory_documents_captured_and_reference_artifacts() -> None:
    inventory = discover_captured_evidence(ROOT)
    rows = {Path(row.file_path).name: row for row in inventory}

    assert rows["s23_archive_ingress_dry_run.jsonl"].classification == "captured"
    assert "OPTION_CHAIN_SNAPSHOT" in rows["s23_archive_ingress_dry_run.jsonl"].available_fields
    assert rows["s23_archive_ingress_dry_run.jsonl"].can_reproduce_complete_decision is False
    assert rows["s23_fyers_prelude.jsonl"].classification == "captured"
    assert "OPTION_CHAIN_SNAPSHOT" in rows["s23_fyers_prelude.jsonl"].missing_fields
    assert rows["s23_bear_put_live_decision_reference.json"].classification == "reference_packet"


def test_legacy_offline_evaluation_uses_captured_outputs_and_selector_when_available() -> None:
    case = load_captured_jsonl_cases((ARCHIVE,))[0]

    observation = evaluate_captured_case_with_legacy(case)

    assert observation.trade_result is TFISTradeResult.TRADE
    assert observation.trade_plan is not None
    assert observation.trade_plan.entry_price == 798.3
    assert observation.contract_selection is not None
    assert observation.contract_selection.selected is False
    assert observation.status == "REPRODUCED_CONTRACT_SELECTION"


def test_generic_evaluation_fails_closed_when_captured_formula_inputs_are_missing() -> None:
    case = load_captured_jsonl_cases((ARCHIVE,))[0]

    decision = evaluate_captured_case_with_generic(case)

    assert decision.trade_result is TFISTradeResult.REJECTED
    assert decision.rejection_reason_code == "POLICY_EVALUATION_ERROR"
    assert "Market level PRV_3DHH is not available" in (decision.rejection_reason or "")


def test_runtime_input_from_captured_case_preserves_timestamps_and_no_broker_state() -> None:
    case = load_captured_jsonl_cases((ARCHIVE,))[0]

    runtime_input = runtime_input_from_captured_case(case)

    assert runtime_input.evaluated_at == case.capture_timestamp
    assert runtime_input.provenance["source"] == "phase2d-captured-shadow"
    assert runtime_input.product_specific["option_chain_snapshot"] is case.option_chain_snapshot


def test_parity_comparator_classifies_missing_formula_evidence_without_coercion() -> None:
    case = load_captured_jsonl_cases((ARCHIVE,))[0]

    result = run_captured_shadow_parity((case,))[0]
    mismatches = {item.field_name: item for item in result.field_comparisons if not item.passed}

    assert result.passed is False
    assert mismatches["entry"].classification is CapturedMismatchClassification.LEGACY_REPRODUCTION_GAP
    assert mismatches["target_sequence"].classification is CapturedMismatchClassification.LEGACY_REPRODUCTION_GAP
    assert mismatches["strike"].classification is CapturedMismatchClassification.LEGACY_REPRODUCTION_GAP


def test_report_generation_is_deterministic(tmp_path: Path) -> None:
    report = build_captured_parity_report(
        root=ROOT,
        case_paths=(ARCHIVE, PRELUDE),
        generated_at=datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc),
    )

    first = write_captured_parity_reports(report, tmp_path / "first")
    second = write_captured_parity_reports(report, tmp_path / "second")

    assert report.summary["total_cases"] == 2
    assert report.summary["partial_captured_cases"] == 2
    assert report.summary["full_captured_cases"] == 0
    assert report.summary["synthetic_cases"] == 0
    assert first["json"].read_text(encoding="utf-8") == second["json"].read_text(encoding="utf-8")
    assert "LEGACY_REPRODUCTION_GAP" in first["markdown"].read_text(encoding="utf-8")


def _event(event_type: str, source_sequence: int) -> dict[str, object]:
    timestamp = f"2026-05-08T09:30:0{source_sequence}+05:30"
    return {
        "event_type": event_type,
        "session_date": "2026-05-08",
        "effective_timestamp": timestamp,
        "captured_at": timestamp,
        "timezone": "Asia/Kolkata",
        "source_type": "test",
        "source_id": f"test:{source_sequence}",
        "synthetic_fixture": False,
        "normalized_by": "test",
        "source_sequence": source_sequence,
        "data_quality_flags": [],
        "payload": {},
    }
