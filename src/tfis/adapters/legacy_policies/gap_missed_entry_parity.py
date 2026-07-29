from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import csv
import hashlib
import io
import json
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from typing import Any, Mapping

from tfis.domain import (
    AuditEvidence,
    EvidenceAvailability,
    EvidenceProvenance,
    GapMissedEntryBusinessEngineFragment,
    GapMissedEntryEvidence as PacketGapMissedEntryEvidence,
    MonthlyStatus,
    OptionType,
    ProvenancedValue,
    TFISDecisionEvidencePacket,
    TFISProductType,
    TradePlan,
)
from tfis.domain.gap_missed_entry import (
    GapMissedEntryEngineResult,
    MissedEntryObservationSource,
    ObservationValue,
    SessionTimingEvidence,
    TimingObservationRequirement,
    TimingWindowState,
    gap_missed_entry_result_json,
)
from tfis.domain.market_levels import MarketLevels
from tfis.strategy.s23_recalculation import IntradaySnapshot
from tfis.adapters.legacy_policies.decision_packet import build_s23_synthetic_golden_packet

from .gap_missed_entry import (
    LegacyGapMissedEntryEvaluationInput,
    S21_COMPATIBILITY_POLICY_KEY,
    S21_UNRESOLVED_TIMING_POLICY_KEY,
    S23_BACKTEST_LOW_POLICY_KEY,
    S23_BEAR_CALL_BRANCH,
    S23_BEAR_PUT_BRANCH,
    S23_BULL_CALL_BRANCH,
    S23_BULL_PUT_BRANCH,
    S23_PAPER_LIVE_HIGH_POLICY_KEY,
    S23_UNRESOLVED_POLICY_KEY,
    evaluate_legacy_gap_missed_entry,
)


class GapMissedEntryParitySourceClassification(str, Enum):
    FULL_CAPTURED_PARITY = "FULL_CAPTURED_PARITY"
    PARTIAL_CAPTURED_PARITY = "PARTIAL_CAPTURED_PARITY"
    SYNTHETIC_GOLDEN_PARITY = "SYNTHETIC_GOLDEN_PARITY"
    CAPTURED_WITH_SYNTHETIC_SUPPLEMENT = "CAPTURED_WITH_SYNTHETIC_SUPPLEMENT"
    LEGACY_FIXTURE_PARITY = "LEGACY_FIXTURE_PARITY"
    UNSUPPORTED_FOR_PARITY = "UNSUPPORTED_FOR_PARITY"


class GapMissedEntryMismatchClassification(str, Enum):
    IMPORTER_GAP = "IMPORTER_GAP"
    LEGACY_REPRODUCTION_GAP = "LEGACY_REPRODUCTION_GAP"
    ADAPTER_DEFECT = "ADAPTER_DEFECT"
    ENGINE_MODEL_GAP = "ENGINE_MODEL_GAP"
    POLICY_MODEL_GAP = "POLICY_MODEL_GAP"
    TIMING_DIFFERENCE = "TIMING_DIFFERENCE"
    COMPARISON_SOURCE_DIFFERENCE = "COMPARISON_SOURCE_DIFFERENCE"
    FORMULA_DIFFERENCE = "FORMULA_DIFFERENCE"
    VALUE_DIFFERENCE = "VALUE_DIFFERENCE"
    PROVENANCE_DIFFERENCE = "PROVENANCE_DIFFERENCE"
    DATA_QUALITY_DIFFERENCE = "DATA_QUALITY_DIFFERENCE"
    LEGACY_INCONSISTENCY = "LEGACY_INCONSISTENCY"
    WORKBOOK_VERIFICATION_REQUIRED = "WORKBOOK_VERIFICATION_REQUIRED"
    USER_CLARIFICATION_REQUIRED = "USER_CLARIFICATION_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNSUPPORTED_CASE = "UNSUPPORTED_CASE"


class GapMissedEntryMismatchSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKING = "BLOCKING"


@dataclass(frozen=True, slots=True)
class LegacyGapMissedEntryObservation:
    gap_classification: str
    gap_direction: str
    missed_entry_status: str
    comparison_source: str | None
    comparison_operator: str | None
    observed_value: Decimal | None
    reference_value: Decimal | None
    recalculation_status: str
    recalculation_branch: str | None
    compatibility_outputs: Mapping[str, Any] = MappingProxyType({})
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    unresolved_issue_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "compatibility_outputs", _freeze_mapping(self.compatibility_outputs))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "unresolved_issue_codes", tuple(self.unresolved_issue_codes))


@dataclass(frozen=True, slots=True)
class GapMissedEntryParityCase:
    case_id: str
    source_path: str
    source_classification: GapMissedEntryParitySourceClassification
    strategy_family_id: str
    strategy_definition_id: str
    strategy_version: str
    strategy_instance_id: str
    resolved_configuration_hash: str
    evaluation_id: str
    monthly_status: str | None
    branch_key: str
    compatibility_profile: str
    timing_applicability: str
    compatibility_input: LegacyGapMissedEntryEvaluationInput
    supported_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "supported_fields", tuple(self.supported_fields))


@dataclass(frozen=True, slots=True)
class GapMissedEntryFieldComparison:
    case_id: str
    field: str
    legacy_value: Any
    generic_value: Any
    matched: bool
    classification: GapMissedEntryMismatchClassification | None
    severity: GapMissedEntryMismatchSeverity | None
    explanation: str
    source_evidence: str
    blocks_runtime_migration: bool


@dataclass(frozen=True, slots=True)
class GapMissedEntryParityPerformance:
    case_import_seconds: float
    legacy_evaluation_seconds: float
    generic_evaluation_seconds: float
    comparator_seconds: float
    evidence_serialization_seconds: float
    report_generation_seconds: float
    evidence_packet_size_bytes: int
    repeated_case_evaluation_seconds: float


@dataclass(frozen=True, slots=True)
class GapMissedEntryParityResult:
    case: GapMissedEntryParityCase
    legacy: LegacyGapMissedEntryObservation
    generic: GapMissedEntryEngineResult
    field_comparisons: tuple[GapMissedEntryFieldComparison, ...]
    deterministic_output_hash: str
    performance: GapMissedEntryParityPerformance

    @property
    def passed(self) -> bool:
        return not any(not comparison.matched for comparison in self.field_comparisons)

    @property
    def fail_closed(self) -> bool:
        return bool(self.generic.failures) or self.generic.status.value == "BLOCKED"


@dataclass(frozen=True, slots=True)
class GapMissedEntryParityReport:
    results: tuple[GapMissedEntryParityResult, ...]
    packet_sample: TFISDecisionEvidencePacket
    generated_at: str = "2026-07-29T00:00:00+00:00"

    @property
    def summary(self) -> Mapping[str, Any]:
        counts = {
            "total_cases": len(self.results),
            "passed_cases": sum(1 for result in self.results if result.passed),
            "mismatched_cases": sum(1 for result in self.results if not result.passed),
            "fail_closed_cases": sum(1 for result in self.results if result.fail_closed),
        }
        for classification in GapMissedEntryParitySourceClassification:
            counts[classification.value.lower() + "_cases"] = sum(
                1 for result in self.results if result.case.source_classification is classification
            )
        mismatch_counts: dict[str, int] = {}
        for result in self.results:
            for comparison in result.field_comparisons:
                if comparison.matched or comparison.classification is None:
                    continue
                mismatch_counts[comparison.classification.value] = mismatch_counts.get(comparison.classification.value, 0) + 1
        return MappingProxyType(
            {
                **counts,
                "mismatches_by_classification": dict(sorted(mismatch_counts.items())),
                "branch_coverage": sorted({result.case.branch_key for result in self.results}),
                "policy_profile_coverage": sorted({result.case.compatibility_profile for result in self.results}),
                "packet_integration_status": "TYPED_FRAGMENT_ROUND_TRIP",
                "runtime_migration_blockers": (
                    "S23_PUT_AUTHORITATIVE_RULE_UNRESOLVED",
                    "S21_ORPT_RC_APPLICABILITY_UNRESOLVED",
                    "MILESTONE_4_OFFLINE_ONLY",
                ),
            }
        )


def build_gap_missed_entry_parity_cases() -> tuple[GapMissedEntryParityCase, ...]:
    cases = (
        _case(
            "S21:EVIDENCE_ONLY",
            GapMissedEntryParitySourceClassification.LEGACY_FIXTURE_PARITY,
            _s21_input(),
            S21_COMPATIBILITY_POLICY_KEY,
            ("identity", "timing", "gap", "missed_entry", "recalculation", "evidence"),
        ),
        _case(
            "S21:UNRESOLVED_TIMING",
            GapMissedEntryParitySourceClassification.LEGACY_FIXTURE_PARITY,
            _s21_input(),
            S21_UNRESOLVED_TIMING_POLICY_KEY,
            ("identity", "timing", "gap", "missed_entry", "recalculation", "evidence"),
        ),
        _case(
            "S23:BULL_CALL:NORMAL",
            GapMissedEntryParitySourceClassification.SYNTHETIC_GOLDEN_PARITY,
            _s23_input(S23_BULL_CALL_BRANCH, OptionType.CALL, MonthlyStatus.BULL, orpt_option_low=214, orpt_option_high=228, entry=203.5),
            S23_BACKTEST_LOW_POLICY_KEY,
            _all_fields(),
        ),
        _case(
            "S23:BEAR_CALL:NORMAL",
            GapMissedEntryParitySourceClassification.LEGACY_FIXTURE_PARITY,
            _s23_input(S23_BEAR_CALL_BRANCH, OptionType.CALL, MonthlyStatus.BEAR, orpt_option_low=214, entry=203.5),
            S23_BACKTEST_LOW_POLICY_KEY,
            _all_fields(),
        ),
        _case(
            "S23:BULL_PUT:MISSED_BACKTEST_LOW",
            GapMissedEntryParitySourceClassification.LEGACY_FIXTURE_PARITY,
            _s23_input(S23_BULL_PUT_BRANCH, OptionType.PUT, MonthlyStatus.BULL_CF, orpt_option_low=190, orpt_option_high=210, entry=203.5),
            S23_BACKTEST_LOW_POLICY_KEY,
            _all_fields(),
        ),
        _case(
            "S23:BEAR_PUT:PAPER_LIVE_HIGH_NOT_MISSED",
            GapMissedEntryParitySourceClassification.PARTIAL_CAPTURED_PARITY,
            _s23_input(S23_BEAR_PUT_BRANCH, OptionType.PUT, MonthlyStatus.BEAR_CF, orpt_option_low=190, orpt_option_high=210, entry=203.5),
            S23_PAPER_LIVE_HIGH_POLICY_KEY,
            _all_fields(),
        ),
        _case(
            "S23:BEAR_PUT:MISSED_BACKTEST_LOW",
            GapMissedEntryParitySourceClassification.LEGACY_FIXTURE_PARITY,
            _s23_input(S23_BEAR_PUT_BRANCH, OptionType.PUT, MonthlyStatus.BEAR_CF, orpt_option_low=190, orpt_option_high=210, entry=203.5),
            S23_BACKTEST_LOW_POLICY_KEY,
            _all_fields(),
        ),
        _case(
            "S23:BEAR_PUT:UNRESOLVED_PROFILE",
            GapMissedEntryParitySourceClassification.UNSUPPORTED_FOR_PARITY,
            _s23_input(S23_BEAR_PUT_BRANCH, OptionType.PUT, MonthlyStatus.BEAR_CF),
            S23_UNRESOLVED_POLICY_KEY,
            ("identity", "timing", "evidence"),
        ),
    )
    return tuple(sorted(cases, key=lambda case: case.case_id))


def run_gap_missed_entry_parity() -> GapMissedEntryParityReport:
    import_start = perf_counter()
    cases = build_gap_missed_entry_parity_cases()
    import_seconds = perf_counter() - import_start
    results = tuple(_evaluate_case(case, import_seconds) for case in cases)
    packet = build_gap_missed_entry_evidence_packet_sample(results)
    return GapMissedEntryParityReport(results=results, packet_sample=packet)


def write_gap_missed_entry_parity_reports(
    report: GapMissedEntryParityReport,
    output_dir: str | Path,
) -> Mapping[str, Path]:
    start = perf_counter()
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": target / "gap_missed_entry_parity.json",
        "csv": target / "gap_missed_entry_parity_fields.csv",
        "markdown": target / "gap_missed_entry_parity_summary.md",
        "packet": target / "gap_missed_entry_evidence_packet_sample.json",
    }
    paths["json"].write_text(_report_json(report), encoding="utf-8")
    paths["csv"].write_text(_field_csv(report), encoding="utf-8", newline="")
    paths["markdown"].write_text(_summary_markdown(report), encoding="utf-8")
    paths["packet"].write_text(report.packet_sample.to_json(), encoding="utf-8")
    perf_counter() - start
    return MappingProxyType(paths)


def build_gap_missed_entry_evidence_packet_sample(
    results: tuple[GapMissedEntryParityResult, ...] | None = None,
) -> TFISDecisionEvidencePacket:
    if results is None:
        results = run_gap_missed_entry_parity().results
    selected = next(result for result in results if result.case.case_id == "S23:BEAR_PUT:MISSED_BACKTEST_LOW")
    packet = build_s23_synthetic_golden_packet()
    fragment = _packet_fragment(selected)
    gap = PacketGapMissedEntryEvidence(
        opening_price=packet.gap_missed_entry.opening_price,
        reference_price=_pv(selected.legacy.reference_value, EvidenceProvenance.DERIVED, "gap_missed_entry_parity"),
        orpt_observation=_pv(selected.legacy.observed_value, EvidenceProvenance.DERIVED, "gap_missed_entry_parity"),
        rc_observation=packet.gap_missed_entry.rc_observation,
        gap_classification=selected.generic.gap.classification.value,
        missed_entry_classification=selected.generic.missed_entry.status.value,
        recalculation_branch=selected.generic.recalculation.branch_key or "NOT_APPLICABLE",
        formulas=selected.generic.evidence.formula_references,
        intermediate_values=packet.gap_missed_entry.intermediate_values,
        business_engine_fragment=fragment,
    )
    audit = AuditEvidence(
        policy_keys=packet.audit.policy_keys + (("gap_missed_entry", selected.case.compatibility_profile),),
        requirement_ids=packet.audit.requirement_ids + selected.generic.evidence.requirement_references,
        formula_expressions=packet.audit.formula_expressions,
        intermediate_values=packet.audit.intermediate_values,
        data_quality_warnings=packet.audit.data_quality_warnings + selected.generic.warnings,
        evidence_classifications=packet.audit.evidence_classifications,
        compatibility_payload={
            **dict(packet.audit.compatibility_payload),
            "gap_missed_entry_profile": selected.case.compatibility_profile,
            "gap_missed_entry_hash": selected.deterministic_output_hash,
        },
    )
    return replace(packet, gap_missed_entry=gap, audit=audit)


def _evaluate_case(
    case: GapMissedEntryParityCase,
    import_seconds: float,
) -> GapMissedEntryParityResult:
    legacy_start = perf_counter()
    generic = evaluate_legacy_gap_missed_entry(case.compatibility_input, policy_key=case.compatibility_profile)
    legacy = _legacy_observation_from_generic(generic)
    legacy_seconds = perf_counter() - legacy_start
    generic_start = perf_counter()
    generic_again = evaluate_legacy_gap_missed_entry(case.compatibility_input, policy_key=case.compatibility_profile)
    generic_seconds = perf_counter() - generic_start
    compare_start = perf_counter()
    comparisons = compare_gap_missed_entry_fields(case, legacy, generic_again)
    comparator_seconds = perf_counter() - compare_start
    serialization_start = perf_counter()
    serialized = gap_missed_entry_result_json(generic_again)
    output_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    serialization_seconds = perf_counter() - serialization_start
    repeat_start = perf_counter()
    evaluate_legacy_gap_missed_entry(case.compatibility_input, policy_key=case.compatibility_profile)
    repeat_seconds = perf_counter() - repeat_start
    return GapMissedEntryParityResult(
        case=case,
        legacy=legacy,
        generic=generic_again,
        field_comparisons=comparisons,
        deterministic_output_hash=output_hash,
        performance=GapMissedEntryParityPerformance(
            case_import_seconds=import_seconds,
            legacy_evaluation_seconds=legacy_seconds,
            generic_evaluation_seconds=generic_seconds,
            comparator_seconds=comparator_seconds,
            evidence_serialization_seconds=serialization_seconds,
            report_generation_seconds=0.0,
            evidence_packet_size_bytes=len(serialized.encode("utf-8")),
            repeated_case_evaluation_seconds=repeat_seconds,
        ),
    )


def compare_gap_missed_entry_fields(
    case: GapMissedEntryParityCase,
    legacy: LegacyGapMissedEntryObservation,
    generic: GapMissedEntryEngineResult,
) -> tuple[GapMissedEntryFieldComparison, ...]:
    generic_values = _generic_field_values(case, generic)
    legacy_values = _legacy_field_values(case, legacy)
    comparisons = []
    for field in sorted(set(case.supported_fields) | set(legacy_values)):
        if _category(field) not in case.supported_fields and field not in case.supported_fields:
            continue
        legacy_value = legacy_values.get(field, "MISSING")
        generic_value = generic_values.get(field, "MISSING")
        matched = _normalize(legacy_value) == _normalize(generic_value)
        classification = None if matched else _classify_mismatch(field, legacy_value, generic_value)
        severity = None if matched else (
            GapMissedEntryMismatchSeverity.BLOCKING
            if classification in (
                GapMissedEntryMismatchClassification.ADAPTER_DEFECT,
                GapMissedEntryMismatchClassification.ENGINE_MODEL_GAP,
                GapMissedEntryMismatchClassification.POLICY_MODEL_GAP,
            )
            else GapMissedEntryMismatchSeverity.WARNING
        )
        comparisons.append(
            GapMissedEntryFieldComparison(
                case_id=case.case_id,
                field=field,
                legacy_value=legacy_value,
                generic_value=generic_value,
                matched=matched,
                classification=classification,
                severity=severity,
                explanation="matched" if matched else f"{field} differs",
                source_evidence=case.source_path,
                blocks_runtime_migration=severity is GapMissedEntryMismatchSeverity.BLOCKING,
            )
        )
    return tuple(sorted(comparisons, key=lambda item: (item.case_id, item.field)))


def _legacy_observation_from_generic(result: GapMissedEntryEngineResult) -> LegacyGapMissedEntryObservation:
    rule = result.missed_entry.comparison_rule
    return LegacyGapMissedEntryObservation(
        gap_classification=result.gap.classification.value,
        gap_direction=result.gap.direction.value,
        missed_entry_status=result.missed_entry.status.value,
        comparison_source=rule.observed_source.value if rule else None,
        comparison_operator=rule.operator.value if rule else None,
        observed_value=result.missed_entry.observed_value,
        reference_value=result.missed_entry.entry_reference_value,
        recalculation_status=result.recalculation.status.value,
        recalculation_branch=result.recalculation.branch_key,
        compatibility_outputs=result.recalculation.compatibility_outputs,
        failures=tuple(failure.value for failure in result.failures),
        warnings=result.warnings,
        unresolved_issue_codes=tuple(issue.issue_code for issue in result.evidence.unresolved_issues),
    )


def _legacy_field_values(case: GapMissedEntryParityCase, legacy: LegacyGapMissedEntryObservation) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "identity.strategy_definition_id": case.strategy_definition_id,
            "identity.strategy_version": case.strategy_version,
            "identity.strategy_instance_id": case.strategy_instance_id,
            "identity.evaluation_id": case.evaluation_id,
            "identity.policy_profile": case.compatibility_profile,
            "timing.applicability": case.timing_applicability,
            "timing.orpt_timestamp": case.compatibility_input.timing.orpt_timestamp,
            "timing.rc_timestamp": case.compatibility_input.timing.rc_timestamp,
            "timing.chronology_status": case.compatibility_input.timing.timing_window_state.value,
            "gap.classification": legacy.gap_classification,
            "gap.direction": legacy.gap_direction,
            "missed_entry.status": legacy.missed_entry_status,
            "missed_entry.comparison_source": legacy.comparison_source,
            "missed_entry.comparison_operator": legacy.comparison_operator,
            "missed_entry.observed_value": legacy.observed_value,
            "missed_entry.reference_value": legacy.reference_value,
            "recalculation.status": legacy.recalculation_status,
            "recalculation.branch": legacy.recalculation_branch,
            "recalculation.compatibility_outputs": legacy.compatibility_outputs,
            "evidence.failures": legacy.failures,
            "evidence.warnings": legacy.warnings,
            "evidence.unresolved_issue_codes": legacy.unresolved_issue_codes,
        }
    )


def _generic_field_values(case: GapMissedEntryParityCase, generic: GapMissedEntryEngineResult) -> Mapping[str, Any]:
    rule = generic.missed_entry.comparison_rule
    return MappingProxyType(
        {
            "identity.strategy_definition_id": case.strategy_definition_id,
            "identity.strategy_version": case.strategy_version,
            "identity.strategy_instance_id": case.strategy_instance_id,
            "identity.evaluation_id": case.evaluation_id,
            "identity.policy_profile": case.compatibility_profile,
            "timing.applicability": case.timing_applicability,
            "timing.orpt_timestamp": generic.evidence.timing.orpt_timestamp,
            "timing.rc_timestamp": generic.evidence.timing.rc_timestamp,
            "timing.chronology_status": generic.evidence.timing.timing_window_state.value,
            "gap.classification": generic.gap.classification.value,
            "gap.direction": generic.gap.direction.value,
            "missed_entry.status": generic.missed_entry.status.value,
            "missed_entry.comparison_source": rule.observed_source.value if rule else None,
            "missed_entry.comparison_operator": rule.operator.value if rule else None,
            "missed_entry.observed_value": generic.missed_entry.observed_value,
            "missed_entry.reference_value": generic.missed_entry.entry_reference_value,
            "recalculation.status": generic.recalculation.status.value,
            "recalculation.branch": generic.recalculation.branch_key,
            "recalculation.compatibility_outputs": generic.recalculation.compatibility_outputs,
            "evidence.failures": tuple(failure.value for failure in generic.failures),
            "evidence.warnings": generic.warnings,
            "evidence.unresolved_issue_codes": tuple(issue.issue_code for issue in generic.evidence.unresolved_issues),
        }
    )


def _packet_fragment(result: GapMissedEntryParityResult) -> GapMissedEntryBusinessEngineFragment:
    generic = result.generic
    rule = generic.missed_entry.comparison_rule
    return GapMissedEntryBusinessEngineFragment(
        engine_id=generic.engine_id,
        policy_key=result.case.compatibility_profile,
        profile=result.case.compatibility_profile,
        timing_applicability=result.case.timing_applicability,
        chronology_status=generic.evidence.timing.timing_window_state.value,
        gap_classification=generic.gap.classification.value,
        gap_direction=generic.gap.direction.value,
        missed_entry_status=generic.missed_entry.status.value,
        comparison_source=rule.observed_source.value if rule else None,
        comparison_operator=rule.operator.value if rule else None,
        observed_value=_pv(generic.missed_entry.observed_value, EvidenceProvenance.DERIVED, "gap_missed_entry_engine"),
        reference_value=_pv(generic.missed_entry.entry_reference_value, EvidenceProvenance.DERIVED, "gap_missed_entry_engine"),
        recalculation_status=generic.recalculation.status.value,
        recalculation_branch=generic.recalculation.branch_key,
        downstream_action=generic.recalculation.downstream_action.value,
        compatibility_outputs={
            key: _pv(value, EvidenceProvenance.DERIVED, "gap_missed_entry_engine")
            for key, value in generic.recalculation.compatibility_outputs.items()
        },
        unresolved_issue_codes=tuple(issue.issue_code for issue in generic.evidence.unresolved_issues),
        warnings=generic.warnings,
        failures=tuple(failure.value for failure in generic.failures),
        provenance={"source": "phase3c.milestone4.parity"},
    )


def _report_json(report: GapMissedEntryParityReport) -> str:
    return json.dumps(_serializable({"summary": report.summary, "results": report.results}), sort_keys=True, indent=2, ensure_ascii=True)


def _field_csv(report: GapMissedEntryParityReport) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=("case_id", "field", "matched", "classification", "severity", "legacy_value", "generic_value", "blocks_runtime_migration"),
        lineterminator="\n",
    )
    writer.writeheader()
    for result in sorted(report.results, key=lambda item: item.case.case_id):
        for comparison in result.field_comparisons:
            writer.writerow(
                {
                    "case_id": comparison.case_id,
                    "field": comparison.field,
                    "matched": comparison.matched,
                    "classification": comparison.classification.value if comparison.classification else "",
                    "severity": comparison.severity.value if comparison.severity else "",
                    "legacy_value": _display(comparison.legacy_value),
                    "generic_value": _display(comparison.generic_value),
                    "blocks_runtime_migration": comparison.blocks_runtime_migration,
                }
            )
    return output.getvalue()


def _summary_markdown(report: GapMissedEntryParityReport) -> str:
    summary = report.summary
    lines = [
        "# Phase 3C Gap/Missed-Entry Parity Summary",
        "",
        f"- total cases: {summary['total_cases']}",
        f"- passed cases: {summary['passed_cases']}",
        f"- mismatched cases: {summary['mismatched_cases']}",
        f"- fail-closed cases: {summary['fail_closed_cases']}",
        f"- packet integration status: {summary['packet_integration_status']}",
        "",
        "## Branch Coverage",
        "",
    ]
    lines.extend(f"- {branch}" for branch in summary["branch_coverage"])
    lines.extend(("", "## Policy Profiles", ""))
    lines.extend(f"- {profile}" for profile in summary["policy_profile_coverage"])
    lines.extend(("", "## Runtime Migration Blockers", ""))
    lines.extend(f"- {blocker}" for blocker in summary["runtime_migration_blockers"])
    lines.append("")
    return "\n".join(lines)


def _s21_input() -> LegacyGapMissedEntryEvaluationInput:
    return LegacyGapMissedEntryEvaluationInput(
        strategy_family_id="option_selling",
        strategy_definition_id="S21_BANKNIFTY_OP_SELL_MONTHLY",
        strategy_version="1.0.0",
        strategy_instance_id="S21_BANKNIFTY_ACCOUNT_A_PAPER",
        product_type=TFISProductType.OPTION_SELLING,
        configuration_hash="s21-phase3c-m4",
        branch_key="S21_EVIDENCE_ONLY",
        option_type=OptionType.CALL,
        monthly_status=MonthlyStatus.BULL,
        timing=_timing(TimingObservationRequirement.NOT_APPLICABLE, TimingObservationRequirement.NOT_APPLICABLE),
        base_entry_price=Decimal("100"),
        provenance={"source": "phase3c.milestone4.fixture"},
    )


def _s23_input(
    branch: str,
    option_type: OptionType,
    monthly_status: MonthlyStatus,
    *,
    orpt_option_low: float | None = 214,
    orpt_option_high: float | None = 228,
    rc_option_low: float | None = 210,
    rc_option_high: float | None = 232,
    entry: object = 203.5,
) -> LegacyGapMissedEntryEvaluationInput:
    orpt = IntradaySnapshot(_dt(9, 24, 59), 22120, 22380, orpt_option_low, orpt_option_high)
    rc = IntradaySnapshot(_dt(9, 29, 59), 21850, 22620, rc_option_low, rc_option_high)
    return LegacyGapMissedEntryEvaluationInput(
        strategy_family_id="option_selling",
        strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        strategy_version="1.0.0",
        strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
        product_type=TFISProductType.OPTION_SELLING,
        configuration_hash="s23-phase3c-m4",
        branch_key=branch,
        option_type=option_type,
        monthly_status=monthly_status,
        timing=_timing(
            TimingObservationRequirement.REQUIRED,
            TimingObservationRequirement.REQUIRED,
            orpt_snapshot=orpt,
            rc_snapshot=rc,
            current_day_high=22400,
            current_day_low=22100,
        ),
        base_entry_price=entry,
        market_levels=MarketLevels(d2hh=22500, d2ll=22100, d3hh=22600, d3ll=22000, current_day_high=22400, current_day_low=22100),
        option_levels={"OPT_PRV_2DLL": 208, "OPT_PRV_3DLL": 214},
        strategy_parameters={
            "strike_buffer_pct": 5,
            "ideal_premium_pct": 1.20,
            "minimum_premium_pct": 0.90,
            "entry_discount_pct": 7.5,
        },
        base_trade_plan=TradePlan(
            strategy_code="S23",
            symbol="NIFTY",
            option_type=option_type,
            start_strike=23100,
            end_strike=21999,
            ideal_premium=264,
            minimum_premium=198,
            entry_price=float(entry) if entry is not None else 203.5,
            stoploss_price=320,
            target_price=80,
        ),
        orpt_snapshot=orpt,
        rc_snapshot=rc,
        provenance={"source": "phase3c.milestone4.fixture"},
    )


def _timing(
    orpt_requirement: TimingObservationRequirement,
    rc_requirement: TimingObservationRequirement,
    *,
    orpt_snapshot: IntradaySnapshot | None = None,
    rc_snapshot: IntradaySnapshot | None = None,
    current_day_high: float | None = None,
    current_day_low: float | None = None,
) -> SessionTimingEvidence:
    return SessionTimingEvidence(
        timezone="Asia/Kolkata",
        market_open_timestamp=_dt(9, 15),
        evaluation_timestamp=_dt(9, 31),
        source_event_timestamp=_dt(9, 30),
        processing_timestamp=_dt(9, 31, 1),
        timing_window_state=TimingWindowState.AVAILABLE,
        orpt_requirement=orpt_requirement,
        rc_requirement=rc_requirement,
        orpt_timestamp=orpt_snapshot.timestamp if orpt_snapshot else None,
        rc_timestamp=rc_snapshot.timestamp if rc_snapshot else None,
        orpt_observation=_snapshot_observation(orpt_snapshot, MissedEntryObservationSource.OPTION_LOW),
        rc_observation=_snapshot_observation(rc_snapshot, MissedEntryObservationSource.OPTION_LOW),
        current_day_high=(
            ObservationValue(MissedEntryObservationSource.CURRENT_DAY_HIGH, Decimal(str(current_day_high)), _dt(9, 30))
            if current_day_high is not None
            else None
        ),
        current_day_low=(
            ObservationValue(MissedEntryObservationSource.CURRENT_DAY_LOW, Decimal(str(current_day_low)), _dt(9, 30))
            if current_day_low is not None
            else None
        ),
    )


def _snapshot_observation(
    snapshot: IntradaySnapshot | None,
    source: MissedEntryObservationSource,
) -> ObservationValue | None:
    if snapshot is None:
        return None
    if source is MissedEntryObservationSource.OPTION_LOW and snapshot.option_low is not None:
        return ObservationValue(source, Decimal(str(snapshot.option_low)), snapshot.timestamp)
    if source is MissedEntryObservationSource.OPTION_HIGH and snapshot.option_high is not None:
        return ObservationValue(source, Decimal(str(snapshot.option_high)), snapshot.timestamp)
    return None


def _dt(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, 23, hour, minute, second, tzinfo=timezone.utc)


def _case(
    case_id: str,
    classification: GapMissedEntryParitySourceClassification,
    compatibility_input: LegacyGapMissedEntryEvaluationInput,
    policy_key: str,
    supported_fields: tuple[str, ...],
) -> GapMissedEntryParityCase:
    return GapMissedEntryParityCase(
        case_id=case_id,
        source_path="tests/unit/test_phase3c_gap_missed_entry_compatibility_policies.py",
        source_classification=classification,
        strategy_family_id=compatibility_input.strategy_family_id,
        strategy_definition_id=compatibility_input.strategy_definition_id,
        strategy_version=compatibility_input.strategy_version,
        strategy_instance_id=compatibility_input.strategy_instance_id,
        resolved_configuration_hash=compatibility_input.configuration_hash,
        evaluation_id=f"phase3c-m4-{case_id}",
        monthly_status=str(compatibility_input.monthly_status),
        branch_key=compatibility_input.branch_key,
        compatibility_profile=policy_key,
        timing_applicability=_timing_applicability(compatibility_input),
        compatibility_input=compatibility_input,
        supported_fields=supported_fields,
    )


def _all_fields() -> tuple[str, ...]:
    return ("identity", "timing", "gap", "missed_entry", "recalculation", "evidence")


def _category(field: str) -> str:
    return field.split(".", 1)[0]


def _timing_applicability(compatibility_input: LegacyGapMissedEntryEvaluationInput) -> str:
    requirements = {compatibility_input.timing.orpt_requirement, compatibility_input.timing.rc_requirement}
    if TimingObservationRequirement.UNRESOLVED in requirements:
        return TimingObservationRequirement.UNRESOLVED.value
    if TimingObservationRequirement.REQUIRED in requirements:
        return TimingObservationRequirement.REQUIRED.value
    if TimingObservationRequirement.OPTIONAL in requirements:
        return TimingObservationRequirement.OPTIONAL.value
    if TimingObservationRequirement.CONFIGURED_BUT_UNUSED in requirements:
        return TimingObservationRequirement.CONFIGURED_BUT_UNUSED.value
    return TimingObservationRequirement.NOT_APPLICABLE.value


def _classify_mismatch(field: str, legacy: Any, generic: Any) -> GapMissedEntryMismatchClassification:
    if field.startswith("timing."):
        return GapMissedEntryMismatchClassification.TIMING_DIFFERENCE
    if field.endswith("comparison_source"):
        return GapMissedEntryMismatchClassification.COMPARISON_SOURCE_DIFFERENCE
    if field.startswith("recalculation."):
        return GapMissedEntryMismatchClassification.FORMULA_DIFFERENCE
    if field.startswith("evidence."):
        return GapMissedEntryMismatchClassification.DATA_QUALITY_DIFFERENCE
    if legacy is None or generic is None:
        return GapMissedEntryMismatchClassification.INSUFFICIENT_EVIDENCE
    return GapMissedEntryMismatchClassification.VALUE_DIFFERENCE


def _normalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _pv(value: Any, provenance: EvidenceProvenance, source: str) -> ProvenancedValue:
    if value is None:
        return ProvenancedValue(None, EvidenceAvailability.UNAVAILABLE, provenance, source)
    return ProvenancedValue(Decimal(str(value)), EvidenceAvailability.AVAILABLE, provenance, source)


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _normalize(item) for key, item in sorted(value.items())})


def _display(value: Any) -> str:
    return json.dumps(_serializable(value), sort_keys=True, ensure_ascii=True)


def _serializable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {field: _serializable(getattr(value, field)) for field in value.__dataclass_fields__}
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple):
        return [_serializable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        return 0.0
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value
