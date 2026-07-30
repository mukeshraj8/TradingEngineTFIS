from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from tfis.adapters.legacy_policies import s23_vertical_slice as vertical


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "phase3d" / "s23_call_evidence_fixtures.json"
SCHEMA_VERSION = "tfis.phase3d.s23_call_evidence_fixture.v1"

ALLOWED_EVIDENCE_CLASSIFICATIONS = {
    "FULLY_CAPTURED",
    "CAPTURED_WITH_DERIVED_FIELDS",
    "CAPTURED_WITH_SYNTHETIC_SUPPLEMENT",
    "LEGACY_FIXTURE",
    "LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT",
    "SYNTHETIC_GOLDEN",
}
ALLOWED_FIELD_PROVENANCE = {
    "CAPTURED_DIRECT",
    "CAPTURED_DERIVED",
    "LEGACY_OUTPUT",
    "WORKBOOK_AUTHORITY",
    "SYNTHETIC_SUPPLEMENT",
    "MISSING",
    "NOT_APPLICABLE",
}
ALLOWED_PARITY_CLASSIFICATIONS = {
    "MATCH",
    "ACCEPTABLE_REPRESENTATION_DIFFERENCE",
    "LEGACY_COMPATIBILITY_DIFFERENCE",
    "RULE_AUTHORITY_UNRESOLVED",
    "IMPLEMENTATION_MISMATCH",
    "MISSING_CAPTURED_INPUT",
    "MISSING_LEGACY_OUTPUT",
    "NOT_COMPARABLE",
}
REQUIRED_EVIDENCE_FIELDS = (
    "strategy_identity",
    "strategy_version",
    "strategy_instance_identity",
    "trading_date",
    "monthly_status",
    "resolved_branch",
    "underlying_spot_futures_references",
    "option_chain_snapshot",
    "expiry_candidates",
    "strike_candidates",
    "premium_values",
    "oi_values_and_units",
    "selected_expiry",
    "selected_strike",
    "selected_contract_identity",
    "selected_contract_historical_references",
    "orpt_observation",
    "rc_observation",
    "base_entry_inputs",
    "gap_missed_entry_inputs",
    "gap_missed_entry_outcome",
    "effective_entry",
    "target_inputs_and_output",
    "msl_inputs_and_output",
    "final_legacy_compatible_decision",
    "rejection_or_no_trade_reason",
    "source_timestamps",
    "configuration_policy_identity",
)


@dataclass(frozen=True, slots=True)
class S23CallEvidenceFixture:
    case_key: str
    branch: str
    vertical_spec: str
    evidence_classification: str
    evidence_source: str
    source_artifacts: tuple[Mapping[str, Any], ...]
    field_provenance: Mapping[str, str]
    synthetic_supplements: tuple[str, ...]
    missing_fields: tuple[str, ...]
    trading_date: date | None = None

    def __post_init__(self) -> None:
        if self.evidence_classification not in ALLOWED_EVIDENCE_CLASSIFICATIONS:
            raise ValueError(f"{self.case_key} unsupported evidence classification: {self.evidence_classification}")
        missing_provenance = [field for field in REQUIRED_EVIDENCE_FIELDS if field not in self.field_provenance]
        if missing_provenance:
            raise ValueError(f"{self.case_key} missing field provenance: {', '.join(missing_provenance)}")
        bad_provenance = sorted(
            {
                value
                for value in self.field_provenance.values()
                if value not in ALLOWED_FIELD_PROVENANCE
            }
        )
        if bad_provenance:
            raise ValueError(f"{self.case_key} unsupported field provenance: {', '.join(bad_provenance)}")

    @property
    def is_supplemented(self) -> bool:
        return bool(self.synthetic_supplements)

    def metadata(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                "case_key": self.case_key,
                "branch": self.branch,
                "evidence_classification": self.evidence_classification,
                "evidence_source": self.evidence_source,
                "source_artifacts": tuple(dict(item) for item in self.source_artifacts),
                "field_provenance": dict(self.field_provenance),
                "synthetic_supplements": self.synthetic_supplements,
                "missing_fields": self.missing_fields,
            }
        )


def load_s23_call_evidence_fixtures(path: str | Path = DEFAULT_FIXTURE_PATH) -> tuple[S23CallEvidenceFixture, ...]:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{source} has unsupported schema_version: {data.get('schema_version')}")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"{source} must contain at least one case")
    fixtures = tuple(_fixture_from_dict(item) for item in cases)
    return tuple(sorted(fixtures, key=lambda item: item.case_key))


def run_s23_call_evidence_fixture(case_key: str, capture_observer: Any | None = None) -> Any:
    fixtures = {item.case_key: item for item in load_s23_call_evidence_fixtures()}
    if case_key not in fixtures:
        raise ValueError(f"Unknown S23 Call evidence fixture: {case_key}")
    fixture = fixtures[case_key]
    case = _vertical_case_from_fixture(fixture)
    return vertical.run_s23_vertical_case(case, capture_observer=capture_observer)


def run_all_s23_call_evidence_fixtures() -> tuple[Any, ...]:
    return tuple(
        run_s23_call_evidence_fixture(fixture.case_key)
        for fixture in load_s23_call_evidence_fixtures()
    )


def summarize_s23_call_evidence_result(result: Any) -> Mapping[str, Any]:
    metadata = dict(result.decision.compatibility_payload.get("m5_evidence") or {})
    comparisons = {
        field: {
            "legacy": row["legacy"],
            "vertical": row["vertical"],
            "classification": _parity_classification(row["classification"]),
        }
        for field, row in result.field_comparison.items()
    }
    return MappingProxyType(
        {
            "case_key": metadata.get("case_key"),
            "branch": metadata.get("branch"),
            "evidence_classification": metadata.get("evidence_classification"),
            "evidence_source": metadata.get("evidence_source"),
            "deterministic_hash": result.deterministic_hash,
            "trade_result": result.decision.trade_result.value,
            "selected_contract": (
                result.decision.selected_instrument.symbol
                if result.decision.selected_instrument is not None
                else None
            ),
            "field_provenance": metadata.get("field_provenance") or {},
            "synthetic_supplements": tuple(metadata.get("synthetic_supplements") or ()),
            "missing_fields": tuple(metadata.get("missing_fields") or ()),
            "source_artifacts": tuple(metadata.get("source_artifacts") or ()),
            "parity_result": "PASSED" if not result.mismatch_classifications else "FAILED",
            "field_comparisons": comparisons,
            "mismatch_classifications": dict(result.mismatch_classifications),
            "runtime_impact": "NONE",
        }
    )


def build_s23_call_evidence_gap_matrix(results: tuple[Any, ...]) -> Mapping[str, Any]:
    summaries = [dict(summarize_s23_call_evidence_result(result)) for result in results]
    return MappingProxyType(
        {
            "schema_version": "tfis.phase3d.milestone5.evidence_gap_matrix.v1",
            "generated_at": datetime(2026, 7, 30, 0, 0, 0).isoformat(),
            "cases": [
                {
                    "case_key": item["case_key"],
                    "branch": item["branch"],
                    "evidence_classification": item["evidence_classification"],
                    "synthetic_supplements": item["synthetic_supplements"],
                    "missing_fields": item["missing_fields"],
                    "field_provenance": item["field_provenance"],
                }
                for item in summaries
            ],
        }
    )


def _fixture_from_dict(data: Mapping[str, Any]) -> S23CallEvidenceFixture:
    required = (
        "case_key",
        "branch",
        "vertical_spec",
        "evidence_classification",
        "evidence_source",
        "source_artifacts",
        "field_provenance",
        "synthetic_supplements",
        "missing_fields",
    )
    missing = [field for field in required if field not in data]
    if missing:
        raise ValueError(f"S23 Call evidence fixture missing fields: {', '.join(missing)}")
    trading_date = data.get("trading_date")
    return S23CallEvidenceFixture(
        case_key=str(data["case_key"]),
        branch=str(data["branch"]),
        vertical_spec=str(data["vertical_spec"]),
        evidence_classification=str(data["evidence_classification"]),
        evidence_source=str(data["evidence_source"]),
        source_artifacts=tuple(dict(item) for item in data["source_artifacts"]),
        field_provenance=MappingProxyType({str(key): str(value) for key, value in dict(data["field_provenance"]).items()}),
        synthetic_supplements=tuple(str(item) for item in data["synthetic_supplements"]),
        missing_fields=tuple(str(item) for item in data["missing_fields"]),
        trading_date=date.fromisoformat(str(trading_date)) if trading_date else None,
    )


def _vertical_case_from_fixture(fixture: S23CallEvidenceFixture) -> vertical.S23VerticalSliceCase:
    spec = _spec_from_fixture(fixture)
    case = vertical.build_s23_vertical_case(spec)
    metadata = fixture.metadata()
    runtime_input = replace(
        case.runtime_input,
        price_source="legacy_fixture",
        monthly_status_evidence={
            "classification": fixture.evidence_classification,
            "source": fixture.evidence_source,
            "field_provenance": dict(fixture.field_provenance),
        },
        data_quality={
            "classification": fixture.evidence_classification,
            "synthetic_supplements": fixture.synthetic_supplements,
            "missing_fields": fixture.missing_fields,
        },
        provenance={
            "source": "phase3d_m5_call_evidence_fixture",
            "case_key": fixture.case_key,
            "evidence_source": fixture.evidence_source,
        },
    )
    branch_suffix = "BULL_CALL" if fixture.branch == "S23_BULL_CALL" else "BEAR_CALL"
    return replace(
        case,
        runtime_input=runtime_input,
        evidence_label=f"{fixture.evidence_classification}:S23:{branch_suffix}:PHASE3D_M5",
        phase_label="phase3d_m5",
        session_reason=f"S23 {branch_suffix.replace('_', ' ').title()} workbook-backed evidence fixture.",
        final_reason=f"S23 {branch_suffix.replace('_', ' ').title()} fixture reproduced legacy-compatible TRADE.",
        evidence_classification=fixture.evidence_classification,
        evidence_metadata=metadata,
    )


def _spec_from_fixture(fixture: S23CallEvidenceFixture) -> vertical.S23VerticalBranchSpec:
    if fixture.vertical_spec == "BULL_CALL_SPEC":
        return vertical.BULL_CALL_SPEC
    if fixture.vertical_spec == "BEAR_CALL_SPEC":
        return vertical.BEAR_CALL_SPEC
    raise ValueError(f"{fixture.case_key} references unsupported vertical_spec: {fixture.vertical_spec}")


def _parity_classification(value: Any) -> str:
    text = str(value)
    if text not in ALLOWED_PARITY_CLASSIFICATIONS:
        raise ValueError(f"Unsupported M5 parity classification: {text}")
    return text
