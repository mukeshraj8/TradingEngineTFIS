from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

from tfis.adapters.legacy_policies import (
    build_s23_synthetic_golden_packet,
    captured_cases_to_packets,
    measure_decision_packet,
    packet_from_captured_case,
    run_decision_packet_parity,
    write_decision_packet_reports,
)
from tfis.adapters.legacy_policies.captured_shadow import load_captured_jsonl_cases
from tfis.domain import (
    DecisionEvidenceCompleteness,
    EvidenceAvailability,
    SelectedContractEvidence,
    EntryBusinessEngineFragment,
    EvidenceProvenance,
    ProvenancedValue,
    TFISDecisionEvidencePacket,
    validate_decision_evidence_packet,
)


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "tests" / "fixtures" / "paper" / "s23_archive_ingress_dry_run.jsonl"
PRELUDE = ROOT / "tests" / "fixtures" / "paper" / "s23_fyers_prelude.jsonl"


def test_packet_round_trip_preserves_decimal_and_is_deterministic() -> None:
    packet = build_s23_synthetic_golden_packet()

    round_tripped = TFISDecisionEvidencePacket.from_json(packet.to_json())

    assert round_tripped.to_json() == packet.to_json()
    assert round_tripped.calculated_decision.entry.value == Decimal("203.5")
    assert round_tripped.option_product_references.ideal_premium.value == Decimal("271.2")
    assert round_tripped.entry is None


def test_packet_can_round_trip_optional_entry_business_engine_fragment() -> None:
    packet = build_s23_synthetic_golden_packet()
    with_entry = replace(
        packet,
        entry=EntryBusinessEngineFragment(
            engine_id="entry",
            policy_key="fixture.entry",
            profile="generic",
            product="OPTION_SELLING",
            branch="fixture_branch",
            selected_or_resolved_instrument="NIFTY_OPT",
            formula_reference="fixture:entry",
            input_references=(
                (
                    "selected_3dll",
                    ProvenancedValue(
                        Decimal("100.25"),
                        EvidenceAvailability.AVAILABLE,
                        EvidenceProvenance.SYNTHETIC,
                        "fixture",
                    ),
                ),
            ),
            base_entry=ProvenancedValue(
                Decimal("100.25"),
                EvidenceAvailability.AVAILABLE,
                EvidenceProvenance.SYNTHETIC,
                "fixture",
            ),
            gap_missed_entry_dependency={"status": "NOT_APPLICABLE"},
            effective_entry=ProvenancedValue(
                Decimal("100.25"),
                EvidenceAvailability.AVAILABLE,
                EvidenceProvenance.SYNTHETIC,
                "fixture",
            ),
            effective_entry_source="BASE_POLICY",
            trigger_condition={"trigger_direction": "PRICE_AT_OR_BELOW"},
            validation=(),
            quality="VALID",
            deterministic_hash="abc123",
        ),
    )

    round_tripped = TFISDecisionEvidencePacket.from_json(with_entry.to_json())

    assert round_tripped.entry is not None
    assert round_tripped.entry.base_entry.value == Decimal("100.25")
    assert round_tripped.entry.gap_missed_entry_dependency["status"] == "NOT_APPLICABLE"


def test_packet_preserves_null_versus_zero() -> None:
    packet = build_s23_synthetic_golden_packet()

    assert packet.market_structure.prv_1d_hh.value is None
    assert packet.market_structure.prv_1d_hh.availability is EvidenceAvailability.NOT_APPLICABLE
    assert packet.price_context.freshness_seconds == Decimal("0")


def test_synthetic_golden_packet_is_full_and_reproduces_legacy_and_generic() -> None:
    packet = build_s23_synthetic_golden_packet()

    validation = validate_decision_evidence_packet(packet)
    parity = run_decision_packet_parity(packet)

    assert validation.completeness is DecisionEvidenceCompleteness.FULL_DECISION_EVIDENCE
    assert not validation.issues
    assert parity.passed is True
    assert parity.mismatches == {}
    assert parity.compared_fields["entry"] == (203.5, 203.5)
    assert parity.compared_fields["selected_strike"] == (22350.0, 22350.0)


def test_captured_cases_become_partial_packets_with_exact_missing_dependencies() -> None:
    packets = captured_cases_to_packets((ARCHIVE, PRELUDE))
    validations = {
        packet.identity.packet_id: validate_decision_evidence_packet(packet)
        for packet in packets
    }

    assert all(
        result.completeness is DecisionEvidenceCompleteness.PARTIAL_DECISION_EVIDENCE
        for result in validations.values()
    )
    archive_codes = {issue.code for issue in validations[next(key for key in validations if "archive" in key)].issues}
    prelude_codes = {issue.code for issue in validations[next(key for key in validations if "prelude" in key)].issues}
    assert "MISSING_FORMULA_INPUT" in archive_codes
    assert "INCOMPLETE_OPTION_CHAIN_EVIDENCE" in prelude_codes
    assert "MISSING_SELECTED_CONTRACT" in prelude_codes


def test_selected_contract_must_be_present_in_candidate_chain() -> None:
    packet = build_s23_synthetic_golden_packet()
    broken = replace(
        packet,
        selected_contract=SelectedContractEvidence(
            selected_identity=replace(packet.selected_contract.selected_identity, symbol="DIFFERENT_SYMBOL"),
            selection_reason=packet.selected_contract.selection_reason,
            selected_quote=packet.selected_contract.selected_quote,
            rejected_candidate_reasons=(),
            availability=EvidenceAvailability.AVAILABLE,
        ),
    )

    validation = validate_decision_evidence_packet(broken)

    assert validation.completeness is DecisionEvidenceCompleteness.INVALID_DECISION_EVIDENCE
    assert "SELECTED_CONTRACT_NOT_IN_CANDIDATES" in {issue.code for issue in validation.issues}


def test_invalid_timestamp_order_is_invalid() -> None:
    packet = build_s23_synthetic_golden_packet()
    broken = replace(
        packet,
        identity=replace(
            packet.identity,
            event_timestamp=packet.identity.processing_timestamp,
            processing_timestamp=packet.identity.event_timestamp,
        ),
    )

    validation = validate_decision_evidence_packet(broken)

    assert validation.completeness is DecisionEvidenceCompleteness.INVALID_DECISION_EVIDENCE
    assert "INVALID_TIMESTAMP_ORDER" in {issue.code for issue in validation.issues}


def test_captured_derived_synthetic_provenance_is_explicit() -> None:
    golden = build_s23_synthetic_golden_packet()
    captured_case = load_captured_jsonl_cases((ARCHIVE,))[0]
    captured_packet = packet_from_captured_case(captured_case)

    assert [item.value for item in golden.audit.evidence_classifications] == ["SYNTHETIC"]
    assert [item.value for item in captured_packet.audit.evidence_classifications] == ["CAPTURED"]
    assert captured_packet.calculated_decision.entry.source == "captured"


def test_packet_performance_measurement_reports_size_and_scale_risk() -> None:
    packet = build_s23_synthetic_golden_packet()

    measurement = measure_decision_packet(packet)

    assert measurement.serialized_size_bytes > 0
    assert measurement.serialization_seconds >= 0
    assert measurement.deserialization_seconds >= 0
    assert measurement.validation_seconds >= 0
    assert measurement.parity_evaluation_seconds >= 0
    assert measurement.option_chain_candidate_count == 1
    assert measurement.scale_risk == "LOW"


def test_packet_reports_are_deterministic_for_packet_content(tmp_path: Path) -> None:
    packet = build_s23_synthetic_golden_packet()

    first = write_decision_packet_reports((packet,), tmp_path / "first")
    second = write_decision_packet_reports((packet,), tmp_path / "second")

    assert first["golden_packet"].read_text(encoding="utf-8") == second["golden_packet"].read_text(encoding="utf-8")
    report = json.loads(first["json"].read_text(encoding="utf-8"))
    assert report["validations"][0]["completeness"] == "FULL_DECISION_EVIDENCE"
    assert report["parity"][0]["passed"] is True
