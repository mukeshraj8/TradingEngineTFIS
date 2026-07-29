from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
import csv
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from tfis.decision import TFISDecisionEngine
from tfis.domain import (
    MonthlyStatus,
    Segment,
    StrategyRule,
    TFISDecision,
    TFISProductType,
    TFISRuntimeInput,
    TFISTradeResult,
    product_type_from_segment,
)
from tfis.domain.market_levels import MarketLevels
from tfis.domain.trade_plan import TradePlan
from tfis.importers import load_strategy_rule
from tfis.paper.contract_selection import (
    S23PaperContractSelectionRequest,
    S23PaperContractSelectionResult,
    S23PaperContractSelector,
)
from tfis.paper.models import (
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    SelectedContractQuoteEvent,
)

from .composition import LegacyPolicyRegistryFactory, policy_selection_for_strategy


class CapturedEvidenceQuality(str, Enum):
    FULL_CAPTURED_PARITY = "FULL_CAPTURED_PARITY"
    PARTIAL_CAPTURED_PARITY = "PARTIAL_CAPTURED_PARITY"
    CAPTURED_WITH_SYNTHETIC_SUPPLEMENT = "CAPTURED_WITH_SYNTHETIC_SUPPLEMENT"
    SYNTHETIC_PARITY = "SYNTHETIC_PARITY"
    UNSUPPORTED = "UNSUPPORTED"


class CapturedMismatchClassification(str, Enum):
    IMPORTER_GAP = "IMPORTER_GAP"
    LEGACY_REPRODUCTION_GAP = "LEGACY_REPRODUCTION_GAP"
    ADAPTER_DEFECT = "ADAPTER_DEFECT"
    GENERIC_MODEL_GAP = "GENERIC_MODEL_GAP"
    FORMULA_DIFFERENCE = "FORMULA_DIFFERENCE"
    TIMING_DIFFERENCE = "TIMING_DIFFERENCE"
    DATA_QUALITY_DIFFERENCE = "DATA_QUALITY_DIFFERENCE"
    WORKBOOK_VERIFICATION_REQUIRED = "WORKBOOK_VERIFICATION_REQUIRED"
    INSUFFICIENT_CAPTURED_EVIDENCE = "INSUFFICIENT_CAPTURED_EVIDENCE"


@dataclass(frozen=True, slots=True)
class CapturedDecisionCase:
    case_id: str
    source_file: Path
    capture_timestamp: datetime
    strategy_instance: str
    monthly_status: MonthlyStatus | None
    runtime_inputs: Mapping[str, Any]
    orpt_rc_evidence: Mapping[str, Any]
    current_day_references: Mapping[str, Any]
    option_chain_snapshot: OptionChainSnapshotEvent | None
    selected_contract_quote: SelectedContractQuoteEvent | None
    expected_legacy_decision: Mapping[str, Any]
    evidence_quality: CapturedEvidenceQuality
    missing_fields: tuple[str, ...]
    parser_warnings: tuple[str, ...] = ()
    captured_classification: str = "captured"

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must be a non-empty string")
        if not self.strategy_instance.strip():
            raise ValueError("strategy_instance must be a non-empty string")
        object.__setattr__(self, "source_file", Path(self.source_file))
        object.__setattr__(self, "runtime_inputs", _freeze(self.runtime_inputs))
        object.__setattr__(self, "orpt_rc_evidence", _freeze(self.orpt_rc_evidence))
        object.__setattr__(self, "current_day_references", _freeze(self.current_day_references))
        object.__setattr__(
            self,
            "expected_legacy_decision",
            _freeze(self.expected_legacy_decision),
        )
        object.__setattr__(self, "missing_fields", tuple(sorted(self.missing_fields)))
        object.__setattr__(self, "parser_warnings", tuple(sorted(self.parser_warnings)))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self)


@dataclass(frozen=True, slots=True)
class EvidenceInventoryRow:
    file_path: str
    format: str
    strategy: str | None
    branch: str | None
    classification: str
    timestamps: tuple[str, ...]
    available_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    can_reproduce_complete_decision: bool

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class LegacyDecisionObservation:
    case_id: str
    status: str
    trade_result: TFISTradeResult
    reason: str
    trade_plan: TradePlan | None
    contract_selection: S23PaperContractSelectionResult | None
    evidence: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class CapturedFieldComparison:
    case_id: str
    field_name: str
    legacy_value: Any
    generic_value: Any
    passed: bool
    classification: CapturedMismatchClassification | None

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class CapturedParityResult:
    case: CapturedDecisionCase
    legacy_observation: LegacyDecisionObservation
    generic_decision: TFISDecision
    field_comparisons: tuple[CapturedFieldComparison, ...]

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.field_comparisons)

    @property
    def mismatch_classifications(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    item.classification.value
                    for item in self.field_comparisons
                    if item.classification is not None
                }
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.to_dict(),
            "legacy_observation": self.legacy_observation.to_dict(),
            "generic_decision": self.generic_decision.to_dict(),
            "field_comparisons": [item.to_dict() for item in self.field_comparisons],
            "passed": self.passed,
            "mismatch_classifications": self.mismatch_classifications,
        }


@dataclass(frozen=True, slots=True)
class CapturedParityReport:
    generated_at: datetime
    inventory: tuple[EvidenceInventoryRow, ...]
    results: tuple[CapturedParityResult, ...]

    @property
    def summary(self) -> dict[str, int]:
        results = self.results
        return {
            "total_cases": len(results),
            "full_captured_cases": sum(
                item.case.evidence_quality is CapturedEvidenceQuality.FULL_CAPTURED_PARITY
                for item in results
            ),
            "partial_captured_cases": sum(
                item.case.evidence_quality is CapturedEvidenceQuality.PARTIAL_CAPTURED_PARITY
                for item in results
            ),
            "synthetic_cases": sum(
                item.case.evidence_quality
                in {
                    CapturedEvidenceQuality.CAPTURED_WITH_SYNTHETIC_SUPPLEMENT,
                    CapturedEvidenceQuality.SYNTHETIC_PARITY,
                }
                for item in results
            ),
            "passed_cases": sum(item.passed for item in results),
            "mismatched_cases": sum(not item.passed for item in results),
            "unsupported_cases": sum(
                item.case.evidence_quality is CapturedEvidenceQuality.UNSUPPORTED
                for item in results
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "summary": self.summary,
            "inventory": [item.to_dict() for item in self.inventory],
            "results": [item.to_dict() for item in self.results],
        }


def discover_captured_evidence(root: str | Path) -> tuple[EvidenceInventoryRow, ...]:
    base = Path(root)
    paths = sorted(
        (
            path
            for path in (
                *base.glob("tests/fixtures/**/*.jsonl"),
                *base.glob("config/reference_packets/*.json"),
                *base.glob("config/runtime_fixtures/*.json"),
            )
            if path.is_file()
        ),
        key=lambda item: item.as_posix(),
    )
    rows: list[EvidenceInventoryRow] = []
    for path in paths:
        if path.suffix == ".jsonl":
            rows.append(_inventory_jsonl(path))
        else:
            rows.append(_inventory_json(path))
    return tuple(rows)


def load_captured_jsonl_cases(paths: Iterable[str | Path]) -> tuple[CapturedDecisionCase, ...]:
    cases = [_load_captured_jsonl_case(Path(path)) for path in paths]
    return tuple(sorted(cases, key=lambda item: item.case_id))


def run_captured_shadow_parity(cases: Iterable[CapturedDecisionCase]) -> tuple[CapturedParityResult, ...]:
    results = [_run_one_case(case) for case in cases]
    return tuple(sorted(results, key=lambda item: item.case.case_id))


def build_captured_parity_report(
    *,
    root: str | Path,
    case_paths: Iterable[str | Path],
    generated_at: datetime,
) -> CapturedParityReport:
    cases = load_captured_jsonl_cases(case_paths)
    return CapturedParityReport(
        generated_at=generated_at,
        inventory=discover_captured_evidence(root),
        results=run_captured_shadow_parity(cases),
    )


def write_captured_parity_reports(report: CapturedParityReport, output_dir: str | Path) -> Mapping[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "captured_shadow_parity.json"
    csv_path = directory / "captured_shadow_parity_fields.csv"
    md_path = directory / "captured_shadow_parity_summary.md"
    json_path.write_text(_canonical_json(report.to_dict()) + "\n", encoding="utf-8")
    _write_csv(report, csv_path)
    md_path.write_text(_markdown_summary(report), encoding="utf-8")
    return MappingProxyType({"json": json_path, "csv": csv_path, "markdown": md_path})


def _run_one_case(case: CapturedDecisionCase) -> CapturedParityResult:
    rule = _strategy_rule_for_case(case)
    legacy = evaluate_captured_case_with_legacy(case, rule)
    generic = evaluate_captured_case_with_generic(case, rule)
    return CapturedParityResult(
        case=case,
        legacy_observation=legacy,
        generic_decision=generic,
        field_comparisons=_compare_case(case, legacy, generic),
    )


def evaluate_captured_case_with_legacy(
    case: CapturedDecisionCase,
    strategy_rule: StrategyRule | None = None,
) -> LegacyDecisionObservation:
    rule = strategy_rule or _strategy_rule_for_case(case)
    plan = _trade_plan_from_expected(rule, case.expected_legacy_decision)
    selection = None
    reason = "Captured trade-plan output preserved as legacy observation."
    status = "OBSERVED_FROM_CAPTURE"
    if case.option_chain_snapshot is not None and plan is not None:
        selection = S23PaperContractSelector().select(
            S23PaperContractSelectionRequest(
                underlying_symbol=rule.symbol,
                expiry_date=case.option_chain_snapshot.expiry,
                option_type=rule.option_type,
                start_strike=float(plan.start_strike),
                end_strike=float(plan.end_strike),
                ideal_premium=float(plan.ideal_premium),
                minimum_premium=float(plan.minimum_premium),
                minimum_oi=float(rule.minimum_oi),
            ),
            case.option_chain_snapshot,
        )
        reason = "Captured trade plan plus current legacy option-chain selector."
        status = "REPRODUCED_CONTRACT_SELECTION"
    return LegacyDecisionObservation(
        case_id=case.case_id,
        status=status,
        trade_result=TFISTradeResult.TRADE if plan is not None else TFISTradeResult.REJECTED,
        reason=reason,
        trade_plan=plan,
        contract_selection=selection,
        evidence={
            "source_file": str(case.source_file.as_posix()),
            "missing_fields": case.missing_fields,
            "parser_warnings": case.parser_warnings,
        },
    )


def evaluate_captured_case_with_generic(
    case: CapturedDecisionCase,
    strategy_rule: StrategyRule | None = None,
) -> TFISDecision:
    rule = strategy_rule or _strategy_rule_for_case(case)
    runtime_input = runtime_input_from_captured_case(case, rule)
    composition = policy_selection_for_strategy(rule.strategy_code)
    registry = LegacyPolicyRegistryFactory().build(rule)
    return TFISDecisionEngine(registry.compose(composition.policy_selection)).evaluate(
        runtime_input
    )


def runtime_input_from_captured_case(
    case: CapturedDecisionCase,
    strategy_rule: StrategyRule | None = None,
) -> TFISRuntimeInput:
    rule = strategy_rule or _strategy_rule_for_case(case)
    expected = dict(case.expected_legacy_decision)
    runtime_inputs = dict(case.runtime_inputs)
    current_day = dict(case.current_day_references)
    trade_plan = dict(runtime_inputs.get("trade_plan") or {})
    return TFISRuntimeInput(
        evaluation_id=f"phase2d-{case.case_id}",
        evaluated_at=case.capture_timestamp,
        strategy_code=rule.strategy_code,
        strategy_version="phase2d-captured-shadow",
        strategy_branch=rule.unique_code,
        symbol=rule.symbol,
        segment=rule.segment,
        product_type=product_type_from_segment(rule.segment),
        account_id=None,
        lots=_int_or_none(expected.get("lots")),
        quantity=_int_or_none(expected.get("quantity")),
        session_date=_date_value(runtime_inputs.get("session_date")) or case.capture_timestamp.date(),
        session_label="phase2d-captured-shadow",
        timezone=str(runtime_inputs.get("timezone") or "Asia/Kolkata"),
        price_source=str(runtime_inputs.get("price_source") or "captured_jsonl"),
        cmp=_float_or_none(current_day.get("rc_close") or current_day.get("underlying_ltp")),
        contract=None,
        monthly_status=case.monthly_status,
        monthly_status_evidence={
            "source": "captured_jsonl",
            "source_file": str(case.source_file.as_posix()),
            "quality": case.evidence_quality.value,
        },
        market_structure_references=dict(runtime_inputs.get("market_structure_references") or {}),
        current_week_references=dict(runtime_inputs.get("current_week_references") or {}),
        current_month_references=dict(runtime_inputs.get("current_month_references") or {}),
        gap_context={
            "orpt_rc_timing": case.orpt_rc_evidence,
        },
        option_chain_context=None,
        data_quality={
            "evidence_quality": case.evidence_quality.value,
            "missing_fields": case.missing_fields,
            "parser_warnings": case.parser_warnings,
        },
        provenance={
            "source": "phase2d-captured-shadow",
            "source_file": str(case.source_file.as_posix()),
            "captured_classification": case.captured_classification,
        },
        configuration_snapshot={"strategy_unique_code": rule.unique_code},
        configuration_version="phase2d-captured-shadow",
        runtime_values=dict(runtime_inputs.get("runtime_values") or {}),
        product_specific={
            "option_chain_snapshot": case.option_chain_snapshot,
            "selected_contract_quote": case.selected_contract_quote,
            "expiry_date": (
                case.option_chain_snapshot.expiry
                if case.option_chain_snapshot is not None
                else _date_value(trade_plan.get("expiry"))
            ),
        },
    )


def _compare_case(
    case: CapturedDecisionCase,
    legacy: LegacyDecisionObservation,
    generic: TFISDecision,
) -> tuple[CapturedFieldComparison, ...]:
    legacy_plan = legacy.trade_plan
    legacy_selection = legacy.contract_selection
    expected = dict(case.expected_legacy_decision)
    fields_to_compare: dict[str, tuple[Any, Any]] = {
        "case_id": (case.case_id, case.case_id),
        "evaluation_timestamp": (case.capture_timestamp, generic.decided_at),
        "strategy_instance": (case.strategy_instance, generic.strategy_branch),
        "strategy_branch": (case.strategy_instance, generic.strategy_branch),
        "monthly_status": (
            case.monthly_status.value if case.monthly_status is not None else None,
            generic.monthly_status_branch,
        ),
        "trade_result": (legacy.trade_result, generic.trade_result),
        "product_type": (TFISProductType.OPTION_SELLING, generic.product_type),
        "direction": ("SHORT", generic.direction.value if generic.direction else None),
        "buy_sell_side": (expected.get("order_side"), generic.execution_side.value if generic.execution_side else None),
        "entry": (
            legacy_plan.entry_price if legacy_plan is not None else None,
            generic.entry_calculation.result if generic.entry_calculation else None,
        ),
        "gap_state": (
            case.orpt_rc_evidence.get("status"),
            generic.gap_result.get("branch") if generic.gap_result else None,
        ),
        "missed_entry_recalculation_result": (
            case.orpt_rc_evidence.get("status"),
            generic.missed_entry_result.get("branch") if generic.missed_entry_result else None,
        ),
        "expiry": (
            (
                legacy_selection.expiry_date
                if legacy_selection is not None and legacy_selection.selected
                else _selected_quote_value(case, "expiry")
            ),
            generic.selected_instrument.expiry if generic.selected_instrument is not None else None,
        ),
        "strike": (
            (
                legacy_selection.strike
                if legacy_selection is not None and legacy_selection.selected
                else _selected_quote_value(case, "strike")
            ),
            generic.selected_instrument.strike if generic.selected_instrument is not None else None,
        ),
        "premium_ltp": (
            (
                legacy_selection.premium_used
                if legacy_selection is not None and legacy_selection.selected
                else _selected_quote_value(case, "ltp")
            ),
            (
                generic.selected_instrument.metadata.get("ltp")
                if generic.selected_instrument is not None
                else None
            ),
        ),
        "oi": (
            (
                legacy_selection.oi_used
                if legacy_selection is not None and legacy_selection.selected
                else _selected_quote_value(case, "oi")
            ),
            (
                generic.selected_instrument.metadata.get("oi")
                if generic.selected_instrument is not None
                else None
            ),
        ),
        "target_sequence": (
            (legacy_plan.target_price,) if legacy_plan is not None else None,
            _target_sequence(generic),
        ),
        "msl": (
            legacy_plan.stoploss_price if legacy_plan is not None else None,
            generic.msl_policy.result if generic.msl_policy is not None else None,
        ),
        "lots": (expected.get("lots"), generic.lots),
        "quantity": (expected.get("quantity"), generic.quantity),
        "final_decision_reason": (legacy.reason, generic.rejection_reason),
        "formula_references": (
            (expected.get("source_workbook_rule"), expected.get("workbook_row_number")),
            _formula_references(generic),
        ),
        "requirement_references": (
            expected.get("source_workbook_rule"),
            _requirement_references(generic),
        ),
        "selected_policy_keys": (
            policy_selection_for_strategy("S23").policy_selection.to_dict()
            if hasattr(policy_selection_for_strategy("S23").policy_selection, "to_dict")
            else _policy_selection_dict(policy_selection_for_strategy("S23").policy_selection),
            _executed_policy_names(generic),
        ),
        "evidence_completeness": (case.evidence_quality.value, case.evidence_quality.value),
    }
    comparisons = []
    for name in sorted(fields_to_compare):
        legacy_value, generic_value = fields_to_compare[name]
        passed = _normalized_compare_value(legacy_value) == _normalized_compare_value(generic_value)
        comparisons.append(
            CapturedFieldComparison(
                case_id=case.case_id,
                field_name=name,
                legacy_value=legacy_value,
                generic_value=generic_value,
                passed=passed,
                classification=None if passed else _classify_captured_mismatch(name, case),
            )
        )
    return tuple(comparisons)


def _load_captured_jsonl_case(path: Path) -> CapturedDecisionCase:
    events = _load_jsonl_events(path)
    if not events:
        raise ValueError(f"No JSONL events found in {path}")
    ordered = sorted(events, key=lambda item: int(item.get("source_sequence") or 0))
    by_type: dict[str, list[dict[str, Any]]] = {}
    for event in ordered:
        event_type = str(event.get("event_type") or "")
        if not event_type:
            raise ValueError(f"Captured event missing event_type in {path}")
        _validate_event_envelope(event, path)
        by_type.setdefault(event_type, []).append(event)

    monthly_event = _single_optional(by_type, "MONTHLY_STATUS_INPUT")
    trade_event = _single_optional(by_type, "TRADE_PLAN_INPUT")
    if monthly_event is None:
        raise ValueError(f"{path} is missing mandatory MONTHLY_STATUS_INPUT")
    if trade_event is None:
        raise ValueError(f"{path} is missing mandatory TRADE_PLAN_INPUT")

    trade_plan = dict(trade_event.get("payload") or {})
    strategy_instance = str(trade_plan.get("strategy_branch") or "")
    if not strategy_instance:
        raise ValueError(f"{path} TRADE_PLAN_INPUT missing strategy_branch")

    monthly_payload = dict(monthly_event.get("payload") or {})
    monthly_status = _monthly_status(monthly_payload.get("monthly_status"))
    snapshots = _snapshot_payloads(by_type.get("UNDERLYING_SNAPSHOT", ()))
    option_chain = _option_chain_event(_single_optional(by_type, "OPTION_CHAIN_SNAPSHOT"))
    selected_quote = _selected_quote_event(_single_optional(by_type, "SELECTED_CONTRACT_QUOTE"))
    missing_fields = _missing_fields(
        monthly_status=monthly_status,
        trade_plan=trade_plan,
        snapshots=snapshots,
        option_chain=option_chain,
        selected_quote=selected_quote,
    )
    quality = (
        CapturedEvidenceQuality.FULL_CAPTURED_PARITY
        if not missing_fields
        else CapturedEvidenceQuality.PARTIAL_CAPTURED_PARITY
    )
    capture_timestamp = max(_datetime_value(event["captured_at"]) for event in ordered)
    return CapturedDecisionCase(
        case_id=f"{path.stem}:{strategy_instance}:{capture_timestamp.isoformat()}",
        source_file=path,
        capture_timestamp=capture_timestamp,
        strategy_instance=strategy_instance,
        monthly_status=monthly_status,
        runtime_inputs={
            "session_date": trade_event.get("session_date"),
            "timezone": trade_event.get("timezone"),
            "source_type": trade_event.get("source_type"),
            "source_id": trade_event.get("source_id"),
            "trade_plan": trade_plan,
        },
        orpt_rc_evidence=_orpt_rc_evidence(snapshots),
        current_day_references=_current_day_references(snapshots, by_type),
        option_chain_snapshot=option_chain,
        selected_contract_quote=selected_quote,
        expected_legacy_decision=trade_plan,
        evidence_quality=quality,
        missing_fields=missing_fields,
        parser_warnings=tuple(_parser_warnings(path, snapshots, option_chain, selected_quote)),
        captured_classification=(
            "captured" if not any(bool(event.get("synthetic_fixture", True)) for event in ordered) else "synthetic"
        ),
    )


def _inventory_jsonl(path: Path) -> EvidenceInventoryRow:
    try:
        events = _load_jsonl_events(path)
    except ValueError as exc:
        return EvidenceInventoryRow(
            file_path=path.as_posix(),
            format="jsonl",
            strategy=None,
            branch=None,
            classification="unsupported",
            timestamps=(),
            available_fields=(),
            missing_fields=(str(exc),),
            can_reproduce_complete_decision=False,
        )
    event_types = tuple(sorted({str(item.get("event_type")) for item in events}))
    timestamps = tuple(
        sorted(
            {
                str(item.get("effective_timestamp") or item.get("captured_at"))
                for item in events
                if item.get("effective_timestamp") or item.get("captured_at")
            }
        )
    )
    trade_plan = next(
        (
            dict(item.get("payload") or {})
            for item in events
            if item.get("event_type") == "TRADE_PLAN_INPUT"
        ),
        {},
    )
    missing = []
    for required in ("MONTHLY_STATUS_INPUT", "TRADE_PLAN_INPUT", "OPTION_CHAIN_SNAPSHOT", "SELECTED_CONTRACT_QUOTE"):
        if required not in event_types:
            missing.append(required)
    if not _has_market_reference_inputs(events):
        missing.append("market_structure_references")
        missing.append("option_reference_values")
    return EvidenceInventoryRow(
        file_path=path.as_posix(),
        format="jsonl",
        strategy="S23" if "s23" in path.name.lower() else None,
        branch=trade_plan.get("strategy_branch"),
        classification=(
            "captured"
            if events and not any(bool(item.get("synthetic_fixture", True)) for item in events)
            else "synthetic"
        ),
        timestamps=timestamps,
        available_fields=event_types,
        missing_fields=tuple(sorted(missing)),
        can_reproduce_complete_decision=not missing,
    )


def _inventory_json(path: Path) -> EvidenceInventoryRow:
    data = json.loads(path.read_text(encoding="utf-8"))
    keys = tuple(sorted(str(key) for key in data.keys()))
    branch = data.get("strategy_branch") or data.get("unique_code")
    return EvidenceInventoryRow(
        file_path=path.as_posix(),
        format="json",
        strategy="S23" if "s23" in path.name.lower() else ("S21" if "s21" in path.name.lower() else None),
        branch=branch,
        classification="reference_packet" if "reference_packets" in path.as_posix() else "runtime_fixture",
        timestamps=(),
        available_fields=keys,
        missing_fields=("captured_event_envelope",),
        can_reproduce_complete_decision=False,
    )


def _load_jsonl_events(path: Path) -> list[dict[str, Any]]:
    rows = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{index} invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{index} must be a JSON object")
        rows.append(row)
    return rows


def _validate_event_envelope(event: Mapping[str, Any], path: Path) -> None:
    required = (
        "event_type",
        "session_date",
        "effective_timestamp",
        "captured_at",
        "timezone",
        "source_type",
        "source_id",
        "synthetic_fixture",
        "normalized_by",
        "payload",
    )
    missing = [field for field in required if field not in event]
    if missing:
        raise ValueError(f"{path} captured event missing envelope fields: {', '.join(missing)}")
    if not isinstance(event.get("payload"), dict):
        raise ValueError(f"{path} captured event payload must be an object")


def _single_optional(by_type: Mapping[str, list[dict[str, Any]]], event_type: str) -> dict[str, Any] | None:
    values = by_type.get(event_type) or []
    if not values:
        return None
    return values[-1]


def _snapshot_payloads(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    snapshots = {}
    for event in events:
        payload = dict(event.get("payload") or {})
        label = str(payload.get("snapshot_label") or "").upper()
        if label:
            snapshots[label] = payload
    return snapshots


def _option_chain_event(event: Mapping[str, Any] | None) -> OptionChainSnapshotEvent | None:
    if event is None:
        return None
    payload = dict(event.get("payload") or {})
    contracts = tuple(
        OptionChainContract(
            symbol=str(item.get("symbol") or ""),
            option_type=_option_type(item.get("option_type")),
            strike=_float_or_none(item.get("strike")),
            expiry=_date_value(item.get("expiry")),
            bid=_float_or_none(item.get("bid")),
            ask=_float_or_none(item.get("ask")),
            ltp=_float_or_none(item.get("ltp")),
            oi=_float_or_none(item.get("oi")),
            volume=_float_or_none(item.get("volume")),
        )
        for item in payload.get("contracts") or ()
    )
    return OptionChainSnapshotEvent(
        envelope=_event_envelope(event),
        underlying_symbol=str(payload.get("underlying_symbol") or ""),
        expiry=_date_value(payload.get("expiry")),
        contracts=contracts,
    )


def _selected_quote_event(event: Mapping[str, Any] | None) -> SelectedContractQuoteEvent | None:
    if event is None:
        return None
    payload = dict(event.get("payload") or {})
    return SelectedContractQuoteEvent(
        envelope=_event_envelope(event),
        symbol=str(payload.get("symbol") or ""),
        option_type=_option_type(payload.get("option_type")),
        strike=_float_or_none(payload.get("strike")),
        expiry=_date_value(payload.get("expiry")),
        bid=_float_or_none(payload.get("bid")),
        ask=_float_or_none(payload.get("ask")),
        ltp=_float_or_none(payload.get("ltp")),
        oi=_float_or_none(payload.get("oi")),
        volume=_float_or_none(payload.get("volume")),
    )


def _event_envelope(event: Mapping[str, Any]) -> EventEnvelope:
    return EventEnvelope(
        event_type=PaperEventType(str(event["event_type"])),
        session_date=_date_value(event["session_date"]),
        effective_timestamp=_datetime_value(event["effective_timestamp"]),
        captured_at=_datetime_value(event["captured_at"]),
        timezone=str(event["timezone"]),
        source_type=str(event["source_type"]),
        source_id=str(event["source_id"]),
        synthetic_fixture=bool(event["synthetic_fixture"]),
        normalized_by=str(event["normalized_by"]),
        source_sequence=_int_or_none(event.get("source_sequence")),
        data_quality_flags=tuple(str(item) for item in event.get("data_quality_flags") or ()),
    )


def _missing_fields(
    *,
    monthly_status: MonthlyStatus | None,
    trade_plan: Mapping[str, Any],
    snapshots: Mapping[str, Mapping[str, Any]],
    option_chain: OptionChainSnapshotEvent | None,
    selected_quote: SelectedContractQuoteEvent | None,
) -> tuple[str, ...]:
    missing: list[str] = []
    if monthly_status is None:
        missing.append("monthly_status")
    for field in (
        "planned_entry_price",
        "target_price",
        "stoploss_price",
        "start_strike",
        "end_strike",
        "ideal_premium",
        "minimum_premium",
        "lots",
        "quantity",
    ):
        if field not in trade_plan:
            missing.append(f"trade_plan.{field}")
    if "ORPT" not in snapshots:
        missing.append("orpt_snapshot")
    if "RC" not in snapshots:
        missing.append("rc_snapshot")
    if option_chain is None:
        missing.append("option_chain_snapshot")
    if selected_quote is None:
        missing.append("selected_contract_quote")
    missing.append("market_structure_references")
    missing.append("option_reference_values")
    return tuple(sorted(set(missing)))


def _parser_warnings(
    path: Path,
    snapshots: Mapping[str, Mapping[str, Any]],
    option_chain: OptionChainSnapshotEvent | None,
    selected_quote: SelectedContractQuoteEvent | None,
) -> Iterable[str]:
    if "ORPT" in snapshots and "RC" in snapshots:
        yield "ORPT_RC_TIMING_IMPORTED_AS_CAPTURED_EVIDENCE_NOT_RECALCULATED"
    if option_chain is None:
        yield "OPTION_CHAIN_MISSING"
    if selected_quote is None:
        yield "SELECTED_CONTRACT_QUOTE_MISSING"
    yield f"SOURCE_FILE={path.as_posix()}"


def _orpt_rc_evidence(snapshots: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if "ORPT" not in snapshots or "RC" not in snapshots:
        return {
            "status": "MISSING_ORPT_RC",
            "reason": "Captured evidence does not include both ORPT and RC snapshots.",
        }
    return {
        "status": "CAPTURED_ORPT_RC_AVAILABLE",
        "reason": "Captured ORPT and RC snapshots preserved for offline shadow parity.",
        "orpt": dict(snapshots["ORPT"]),
        "rc": dict(snapshots["RC"]),
    }


def _current_day_references(
    snapshots: Mapping[str, Mapping[str, Any]],
    by_type: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if "0915" in snapshots:
        values["at_0915"] = dict(snapshots["0915"])
    if "ORPT" in snapshots:
        values["orpt_high"] = snapshots["ORPT"].get("high")
        values["orpt_low"] = snapshots["ORPT"].get("low")
        values["orpt_close"] = snapshots["ORPT"].get("close")
    if "RC" in snapshots:
        values["rc_high"] = snapshots["RC"].get("high")
        values["rc_low"] = snapshots["RC"].get("low")
        values["rc_close"] = snapshots["RC"].get("close")
    quote = _single_optional(by_type, "UNDERLYING_QUOTE")
    if quote is not None:
        values["underlying_ltp"] = dict(quote.get("payload") or {}).get("ltp")
    return values


def _trade_plan_from_expected(
    rule: StrategyRule,
    expected: Mapping[str, Any],
) -> TradePlan | None:
    required = (
        "start_strike",
        "end_strike",
        "ideal_premium",
        "minimum_premium",
        "planned_entry_price",
        "stoploss_price",
        "target_price",
    )
    if any(expected.get(field) is None for field in required):
        return None
    return TradePlan(
        strategy_code=rule.strategy_code,
        symbol=rule.symbol,
        option_type=rule.option_type,
        start_strike=int(float(expected["start_strike"])),
        end_strike=int(float(expected["end_strike"])),
        ideal_premium=float(expected["ideal_premium"]),
        minimum_premium=float(expected["minimum_premium"]),
        entry_price=float(expected["planned_entry_price"]),
        stoploss_price=float(expected["stoploss_price"]),
        target_price=float(expected["target_price"]),
    )


def _strategy_rule_for_case(case: CapturedDecisionCase) -> StrategyRule:
    branch = case.strategy_instance
    if branch.startswith("NIFTY_"):
        path = (
            Path("config")
            / "strategies"
            / "options_sell"
            / "nifty"
            / f"S23_{branch}"
        )
    elif branch.startswith("S23_"):
        path = Path("config") / "strategies" / "options_sell" / "nifty" / branch
    else:
        raise ValueError(f"Unsupported captured strategy instance: {branch}")
    return load_strategy_rule(path)


def _classify_captured_mismatch(
    field_name: str,
    case: CapturedDecisionCase,
) -> CapturedMismatchClassification:
    if field_name in {"entry", "target_sequence", "msl", "formula_references"}:
        if "market_structure_references" in case.missing_fields or "option_reference_values" in case.missing_fields:
            return CapturedMismatchClassification.LEGACY_REPRODUCTION_GAP
        return CapturedMismatchClassification.FORMULA_DIFFERENCE
    if field_name in {"gap_state", "missed_entry_recalculation_result"}:
        return CapturedMismatchClassification.TIMING_DIFFERENCE
    if field_name in {"expiry", "strike", "premium_ltp", "oi"}:
        if "option_chain_snapshot" in case.missing_fields:
            return CapturedMismatchClassification.INSUFFICIENT_CAPTURED_EVIDENCE
        if "market_structure_references" in case.missing_fields or "option_reference_values" in case.missing_fields:
            return CapturedMismatchClassification.LEGACY_REPRODUCTION_GAP
        return CapturedMismatchClassification.ADAPTER_DEFECT
    if field_name in {"selected_policy_keys", "requirement_references"}:
        return CapturedMismatchClassification.GENERIC_MODEL_GAP
    if field_name == "evidence_completeness":
        return CapturedMismatchClassification.DATA_QUALITY_DIFFERENCE
    return CapturedMismatchClassification.INSUFFICIENT_CAPTURED_EVIDENCE


def _write_csv(report: CapturedParityReport, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "case_id",
                "field_name",
                "legacy_value",
                "generic_value",
                "passed",
                "classification",
            ),
        )
        writer.writeheader()
        for result in report.results:
            for comparison in result.field_comparisons:
                writer.writerow(
                    {
                        "case_id": comparison.case_id,
                        "field_name": comparison.field_name,
                        "legacy_value": _canonical_json(comparison.legacy_value),
                        "generic_value": _canonical_json(comparison.generic_value),
                        "passed": str(comparison.passed).lower(),
                        "classification": (
                            comparison.classification.value
                            if comparison.classification is not None
                            else ""
                        ),
                    }
                )


def _markdown_summary(report: CapturedParityReport) -> str:
    lines = [
        "# Phase 2D Captured Shadow Parity Report",
        "",
        f"Generated at: {report.generated_at.isoformat()}",
        "",
        "## Summary",
        "",
    ]
    for key, value in sorted(report.summary.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Cases", ""])
    for result in report.results:
        lines.append(f"### {result.case.case_id}")
        lines.append("")
        lines.append(f"- evidence_quality: {result.case.evidence_quality.value}")
        lines.append(f"- passed: {str(result.passed).lower()}")
        lines.append(f"- missing_fields: {', '.join(result.case.missing_fields) or 'none'}")
        lines.append(
            f"- mismatch_classifications: {', '.join(result.mismatch_classifications) or 'none'}"
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def _has_market_reference_inputs(events: Iterable[Mapping[str, Any]]) -> bool:
    for event in events:
        payload = dict(event.get("payload") or {})
        if "market_structure_references" in payload or "option_reference_values" in payload:
            return True
    return False


def _target_sequence(decision: TFISDecision) -> tuple[Any, ...] | None:
    if decision.target_policy is None:
        return None
    result = decision.target_policy.result
    if result is None:
        return None
    return tuple(result) if isinstance(result, list | tuple) else (result,)


def _formula_references(decision: TFISDecision) -> tuple[Any, ...]:
    refs = []
    for item in decision.intermediate_calculation_evidence.get("policy_results") or ():
        reference = item.get("named_reference") or item.get("formula")
        if reference:
            refs.append(reference)
    return tuple(refs)


def _requirement_references(decision: TFISDecision) -> tuple[Any, ...]:
    return tuple(
        item.get("requirement_id")
        for item in decision.intermediate_calculation_evidence.get("policy_results") or ()
        if item.get("requirement_id")
    )


def _executed_policy_names(decision: TFISDecision) -> tuple[str, ...]:
    return tuple(
        str(item.get("policy_name"))
        for item in decision.intermediate_calculation_evidence.get("policy_results") or ()
    )


def _policy_selection_dict(selection: Any) -> dict[str, Any]:
    return {
        field.name: getattr(selection, field.name)
        for field in fields(selection)
    }


def _selected_quote_value(case: CapturedDecisionCase, field_name: str) -> Any:
    quote = case.selected_contract_quote
    return getattr(quote, field_name) if quote is not None else None


def _monthly_status(value: Any) -> MonthlyStatus | None:
    if value is None or value == "":
        return None
    return MonthlyStatus(str(value))


def _option_type(value: Any) -> Any:
    from tfis.domain.enums import OptionType

    if value is None or value == "":
        return None
    return OptionType(str(value))


def _date_value(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value))


def _datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _normalized_compare_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return tuple(_normalized_compare_value(item) for item in value)
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _normalized_compare_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, tuple | list):
        return tuple(_freeze(item) for item in value)
    return value


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _serializable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {
            str(key): _serializable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _serializable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
