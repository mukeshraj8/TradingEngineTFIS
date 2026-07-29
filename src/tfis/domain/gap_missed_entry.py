from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .business_engine import BusinessEngineMetrics, BusinessEngineStatus
from .runtime_contracts import TFISProductType


class ComparisonOperator(str, Enum):
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    EQUAL = "EQUAL"
    NOT_EQUAL = "NOT_EQUAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class GapClassification(str, Enum):
    NORMAL_OR_NO_GAP = "NORMAL_OR_NO_GAP"
    GAP_UP = "GAP_UP"
    GAP_DOWN = "GAP_DOWN"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INVALID = "INVALID"


class GapDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MissedEntryState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_MISSED = "NOT_MISSED"
    MISSED = "MISSED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"


class MissedEntryObservationSource(str, Enum):
    OPTION_HIGH = "OPTION_HIGH"
    OPTION_LOW = "OPTION_LOW"
    LTP = "LTP"
    BID = "BID"
    ASK = "ASK"
    UNDERLYING_HIGH = "UNDERLYING_HIGH"
    UNDERLYING_LOW = "UNDERLYING_LOW"
    UNDERLYING_OPEN = "UNDERLYING_OPEN"
    UNDERLYING_CLOSE = "UNDERLYING_CLOSE"
    CURRENT_DAY_HIGH = "CURRENT_DAY_HIGH"
    CURRENT_DAY_LOW = "CURRENT_DAY_LOW"
    CUSTOM = "CUSTOM"


class TimingWindowState(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REQUIRED_BUT_MISSING = "REQUIRED_BUT_MISSING"
    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    INVALID_CHRONOLOGY = "INVALID_CHRONOLOGY"


class TimingObservationRequirement(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFIGURED_BUT_UNUSED = "CONFIGURED_BUT_UNUSED"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"
    UNRESOLVED = "UNRESOLVED"


class RecalculationStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    COMPLETED_BY_COMPATIBILITY_POLICY = "COMPLETED_BY_COMPATIBILITY_POLICY"
    REQUIRED_INPUT_MISSING = "REQUIRED_INPUT_MISSING"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID = "INVALID"


class RecalculationDownstreamAction(str, Enum):
    NONE = "NONE"
    DEFER_TO_ENTRY_ENGINE = "DEFER_TO_ENTRY_ENGINE"
    USE_COMPATIBILITY_OUTPUT = "USE_COMPATIBILITY_OUTPUT"
    FAIL_CLOSED = "FAIL_CLOSED"


class GapMissedEntryFailure(str, Enum):
    REQUIRED_OBSERVATION_MISSING = "REQUIRED_OBSERVATION_MISSING"
    INVALID_TIMING_ORDER = "INVALID_TIMING_ORDER"
    STALE_OBSERVATION = "STALE_OBSERVATION"
    UNSUPPORTED_PRODUCT = "UNSUPPORTED_PRODUCT"
    UNSUPPORTED_STRATEGY_FAMILY = "UNSUPPORTED_STRATEGY_FAMILY"
    UNSUPPORTED_MONTHLY_STATUS_BRANCH = "UNSUPPORTED_MONTHLY_STATUS_BRANCH"
    MISSING_MARKET_STRUCTURE_REFERENCE = "MISSING_MARKET_STRUCTURE_REFERENCE"
    UNRESOLVED_COMPARISON_POLICY = "UNRESOLVED_COMPARISON_POLICY"
    CONTRADICTORY_OBSERVATIONS = "CONTRADICTORY_OBSERVATIONS"
    RECALCULATION_INPUT_MISSING = "RECALCULATION_INPUT_MISSING"
    STRATEGY_COMPOSITION_MISMATCH = "STRATEGY_COMPOSITION_MISMATCH"


class GapMissedEntryQuality(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RuleIssueClassification(str, Enum):
    USER_CLARIFICATION_REQUIRED = "USER_CLARIFICATION_REQUIRED"
    WORKBOOK_VERIFICATION_REQUIRED = "WORKBOOK_VERIFICATION_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    LEGACY_INCONSISTENCY = "LEGACY_INCONSISTENCY"
    CONFIRMED = "CONFIRMED"


class RuleExecutionPermission(str, Enum):
    PERMITTED = "PERMITTED"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    FAIL_CLOSED = "FAIL_CLOSED"


@dataclass(frozen=True, slots=True)
class ObservationValue:
    source: MissedEntryObservationSource
    value: Decimal | None
    observed_at: datetime | None
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _decimal_or_none(self.value))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class GapReference:
    reference_key: str
    price: Decimal | None
    source: MissedEntryObservationSource
    formula_reference: str | None = None
    requirement_reference: str | None = None
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "price", _decimal_or_none(self.price))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class GapObservation:
    applicable: bool
    opening_price: ObservationValue | None
    reference: GapReference | None
    policy_key: str
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class GapMeasurement:
    absolute_gap: Decimal | None
    percentage_gap: Decimal | None
    comparison_operator: ComparisonOperator
    threshold_buffer: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "absolute_gap", _decimal_or_none(self.absolute_gap))
        object.__setattr__(self, "percentage_gap", _decimal_or_none(self.percentage_gap))
        object.__setattr__(self, "threshold_buffer", _decimal_or_none(self.threshold_buffer))


@dataclass(frozen=True, slots=True)
class GapClassificationResult:
    applicable: bool
    classification: GapClassification
    direction: GapDirection
    observation: GapObservation
    measurement: GapMeasurement
    formula_reference: str | None = None
    requirement_reference: str | None = None
    quality: GapMissedEntryQuality = GapMissedEntryQuality.VALID
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class SessionTimingEvidence:
    timezone: str
    market_open_timestamp: datetime | None
    evaluation_timestamp: datetime
    source_event_timestamp: datetime
    processing_timestamp: datetime
    timing_window_state: TimingWindowState
    orpt_requirement: TimingObservationRequirement = TimingObservationRequirement.NOT_APPLICABLE
    rc_requirement: TimingObservationRequirement = TimingObservationRequirement.NOT_APPLICABLE
    orpt_timestamp: datetime | None = None
    rc_timestamp: datetime | None = None
    orpt_observation: ObservationValue | None = None
    rc_observation: ObservationValue | None = None
    current_day_high: ObservationValue | None = None
    current_day_low: ObservationValue | None = None
    missing_observations: tuple[str, ...] = ()
    late_observations: tuple[str, ...] = ()
    stale_observations: tuple[str, ...] = ()
    chronology_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "missing_observations", tuple(self.missing_observations))
        object.__setattr__(self, "late_observations", tuple(self.late_observations))
        object.__setattr__(self, "stale_observations", tuple(self.stale_observations))
        object.__setattr__(self, "chronology_warnings", tuple(self.chronology_warnings))


@dataclass(frozen=True, slots=True)
class MissedEntryComparisonRule:
    rule_id: str
    observed_source: MissedEntryObservationSource
    operator: ComparisonOperator
    reference_key: str
    branch_key: str
    policy_key: str
    formula_reference: str | None = None
    requirement_reference: str | None = None
    compatibility_metadata: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "compatibility_metadata", _freeze_mapping(self.compatibility_metadata))


@dataclass(frozen=True, slots=True)
class MissedEntryClassificationResult:
    applicable: bool
    status: MissedEntryState
    comparison_rule: MissedEntryComparisonRule | None
    observed_value: Decimal | None
    entry_reference_value: Decimal | None
    branch_key: str
    direction: GapDirection
    quality: GapMissedEntryQuality = GapMissedEntryQuality.VALID
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_value", _decimal_or_none(self.observed_value))
        object.__setattr__(self, "entry_reference_value", _decimal_or_none(self.entry_reference_value))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class RecalculationInstruction:
    applicable: bool
    status: RecalculationStatus
    branch_key: str | None = None
    required_input_refs: tuple[str, ...] = ()
    supplied_values: Mapping[str, Any] = MappingProxyType({})
    policy_key: str | None = None
    formula_reference: str | None = None
    requirement_reference: str | None = None
    intermediate_evidence: Mapping[str, Any] = MappingProxyType({})
    compatibility_outputs: Mapping[str, Any] = MappingProxyType({})
    downstream_action: RecalculationDownstreamAction = RecalculationDownstreamAction.NONE
    failures: tuple[GapMissedEntryFailure, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_input_refs", tuple(self.required_input_refs))
        object.__setattr__(self, "supplied_values", _freeze_mapping(self.supplied_values))
        object.__setattr__(self, "intermediate_evidence", _freeze_mapping(self.intermediate_evidence))
        object.__setattr__(self, "compatibility_outputs", _freeze_mapping(self.compatibility_outputs))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class CompetingRuleBehavior:
    behavior_key: str
    observed_source: MissedEntryObservationSource
    operator: ComparisonOperator
    source_context: str
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "notes", tuple(self.notes))


@dataclass(frozen=True, slots=True)
class UnresolvedRuleIssue:
    issue_code: str
    classification: RuleIssueClassification
    affected_strategy_definition_id: str
    affected_strategy_version: str
    affected_branch: str
    competing_observed_behaviors: tuple[CompetingRuleBehavior, ...]
    authoritative_source_status: RuleIssueClassification
    execution_permission: RuleExecutionPermission
    fail_closed_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "competing_observed_behaviors",
            tuple(self.competing_observed_behaviors),
        )


@dataclass(frozen=True, slots=True)
class GapMissedEntryValidationIssue:
    failure: GapMissedEntryFailure
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class GapMissedEntryValidation:
    issues: tuple[GapMissedEntryValidationIssue, ...] = ()
    unresolved_issues: tuple[UnresolvedRuleIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "unresolved_issues", tuple(self.unresolved_issues))

    @property
    def passed(self) -> bool:
        return not self.issues and not any(
            issue.execution_permission is RuleExecutionPermission.FAIL_CLOSED
            for issue in self.unresolved_issues
        )


@dataclass(frozen=True, slots=True)
class GapMissedEntryEvidence:
    timing: SessionTimingEvidence
    gap: GapClassificationResult
    missed_entry: MissedEntryClassificationResult
    recalculation: RecalculationInstruction
    unresolved_issues: tuple[UnresolvedRuleIssue, ...] = ()
    formula_references: tuple[str, ...] = ()
    requirement_references: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    failures: tuple[GapMissedEntryFailure, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "unresolved_issues", tuple(self.unresolved_issues))
        object.__setattr__(self, "formula_references", tuple(self.formula_references))
        object.__setattr__(self, "requirement_references", tuple(self.requirement_references))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_decision_evidence_fragment(self) -> dict[str, Any]:
        return {
            "engine_id": "gap",
            "contract": "gap_missed_entry",
            "evidence": _serializable(self),
        }


@dataclass(frozen=True, slots=True)
class GapMissedEntryEngineInput:
    strategy_family_id: str
    strategy_definition_id: str
    strategy_version: str
    strategy_instance_id: str
    product_type: TFISProductType
    resolved_configuration_hash: str
    policy_key: str
    timing: SessionTimingEvidence
    monthly_status: str | None = None
    market_structure_refs: Mapping[str, str] = MappingProxyType({})
    entry_reference_value: Decimal | None = None
    policy_configuration: Mapping[str, Any] = MappingProxyType({})
    unresolved_issues: tuple[UnresolvedRuleIssue, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_reference_value", _decimal_or_none(self.entry_reference_value))
        object.__setattr__(self, "market_structure_refs", _freeze_mapping(self.market_structure_refs))
        object.__setattr__(self, "policy_configuration", _freeze_mapping(self.policy_configuration))
        object.__setattr__(self, "unresolved_issues", tuple(self.unresolved_issues))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class GapMissedEntryPolicyOutcome:
    gap: GapClassificationResult
    missed_entry: MissedEntryClassificationResult
    recalculation: RecalculationInstruction
    unresolved_issues: tuple[UnresolvedRuleIssue, ...] = ()
    warnings: tuple[str, ...] = ()
    failures: tuple[GapMissedEntryFailure, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "unresolved_issues", tuple(self.unresolved_issues))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


class GapMissedEntryRulePolicy(Protocol):
    policy_key: str

    def evaluate(self, engine_input: GapMissedEntryEngineInput) -> GapMissedEntryPolicyOutcome:
        ...


@dataclass(frozen=True, slots=True)
class GapMissedEntryEngineResult:
    engine_id: str
    status: BusinessEngineStatus
    quality: GapMissedEntryQuality
    validation: GapMissedEntryValidation
    gap: GapClassificationResult
    missed_entry: MissedEntryClassificationResult
    recalculation: RecalculationInstruction
    evidence: GapMissedEntryEvidence
    warnings: tuple[str, ...] = ()
    failures: tuple[GapMissedEntryFailure, ...] = ()
    metrics: BusinessEngineMetrics = BusinessEngineMetrics()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_json(self) -> str:
        return json.dumps(
            _serializable(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )


class GapMissedEntryEngine:
    engine_id = "gap"

    def __init__(self, policy: GapMissedEntryRulePolicy) -> None:
        self._policy = policy

    def execute(self, engine_input: GapMissedEntryEngineInput) -> GapMissedEntryEngineResult:
        input_validation = validate_gap_missed_entry_input(engine_input)
        outcome = self._policy.evaluate(engine_input)
        unresolved = tuple(engine_input.unresolved_issues) + tuple(outcome.unresolved_issues)
        validation = GapMissedEntryValidation(
            issues=input_validation.issues,
            unresolved_issues=unresolved,
        )
        failures = tuple(input_validation_issue.failure for input_validation_issue in input_validation.issues) + tuple(outcome.failures)
        fail_closed = not validation.passed
        evidence = GapMissedEntryEvidence(
            timing=engine_input.timing,
            gap=outcome.gap,
            missed_entry=outcome.missed_entry,
            recalculation=outcome.recalculation,
            unresolved_issues=unresolved,
            formula_references=_ordered_unique(
                item
                for item in (
                    outcome.gap.formula_reference,
                    outcome.missed_entry.comparison_rule.formula_reference if outcome.missed_entry.comparison_rule else None,
                    outcome.recalculation.formula_reference,
                )
                if item
            ),
            requirement_references=_ordered_unique(
                item
                for item in (
                    outcome.gap.requirement_reference,
                    outcome.missed_entry.comparison_rule.requirement_reference if outcome.missed_entry.comparison_rule else None,
                    outcome.recalculation.requirement_reference,
                )
                if item
            ),
            warnings=tuple(outcome.warnings),
            failures=failures,
            provenance=outcome.provenance,
        )
        return GapMissedEntryEngineResult(
            engine_id=self.engine_id,
            status=BusinessEngineStatus.BLOCKED if fail_closed else BusinessEngineStatus.PASSED,
            quality=GapMissedEntryQuality.INVALID if fail_closed else _lowest_quality(
                outcome.gap.quality,
                outcome.missed_entry.quality,
            ),
            validation=validation,
            gap=outcome.gap,
            missed_entry=outcome.missed_entry,
            recalculation=outcome.recalculation,
            evidence=evidence,
            warnings=tuple(outcome.warnings),
            failures=failures,
            provenance=outcome.provenance,
        )


def validate_gap_missed_entry_input(
    engine_input: GapMissedEntryEngineInput,
) -> GapMissedEntryValidation:
    issues: list[GapMissedEntryValidationIssue] = []
    timing = engine_input.timing
    if engine_input.product_type not in set(TFISProductType):
        issues.append(_validation_issue(GapMissedEntryFailure.UNSUPPORTED_PRODUCT, "product_type", "unsupported product type"))
    if not engine_input.strategy_family_id.strip():
        issues.append(_validation_issue(GapMissedEntryFailure.UNSUPPORTED_STRATEGY_FAMILY, "strategy_family_id", "strategy family is required"))
    if not engine_input.policy_key.strip() or not engine_input.resolved_configuration_hash.strip():
        issues.append(_validation_issue(GapMissedEntryFailure.STRATEGY_COMPOSITION_MISMATCH, "policy_key", "resolved policy key and configuration hash are required"))
    required_refs = tuple(engine_input.policy_configuration.get("required_market_structure_refs", ()))
    missing_refs = tuple(ref for ref in required_refs if ref not in engine_input.market_structure_refs)
    if missing_refs:
        issues.append(_validation_issue(GapMissedEntryFailure.MISSING_MARKET_STRUCTURE_REFERENCE, "market_structure_refs", "required market structure references are missing"))
    supported_monthly = tuple(engine_input.policy_configuration.get("supported_monthly_statuses", ()))
    if supported_monthly and engine_input.monthly_status not in supported_monthly:
        issues.append(_validation_issue(GapMissedEntryFailure.UNSUPPORTED_MONTHLY_STATUS_BRANCH, "monthly_status", "monthly status branch is not supported by the policy"))
    if timing.orpt_requirement is TimingObservationRequirement.REQUIRED and timing.orpt_observation is None:
        issues.append(_validation_issue(GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING, "timing.orpt_observation", "required ORPT observation is missing"))
    if timing.rc_requirement is TimingObservationRequirement.REQUIRED and timing.rc_observation is None:
        issues.append(_validation_issue(GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING, "timing.rc_observation", "required RC observation is missing"))
    if timing.timing_window_state is TimingWindowState.REQUIRED_BUT_MISSING:
        issues.append(_validation_issue(GapMissedEntryFailure.REQUIRED_OBSERVATION_MISSING, "timing.timing_window_state", "timing window reports a required missing observation"))
    if timing.timing_window_state is TimingWindowState.STALE or timing.stale_observations:
        issues.append(_validation_issue(GapMissedEntryFailure.STALE_OBSERVATION, "timing.stale_observations", "stale timing observations cannot drive trading behavior"))
    if _invalid_chronology(timing):
        issues.append(_validation_issue(GapMissedEntryFailure.INVALID_TIMING_ORDER, "timing", "timing evidence is not chronological"))
    return GapMissedEntryValidation(
        issues=tuple(issues),
        unresolved_issues=engine_input.unresolved_issues,
    )


def gap_missed_entry_result_json(result: GapMissedEntryEngineResult) -> str:
    return result.to_json()


def _invalid_chronology(timing: SessionTimingEvidence) -> bool:
    if timing.source_event_timestamp > timing.evaluation_timestamp:
        return True
    if timing.evaluation_timestamp > timing.processing_timestamp:
        return True
    ordered = tuple(
        timestamp
        for timestamp in (
            timing.market_open_timestamp,
            timing.orpt_timestamp,
            timing.rc_timestamp,
        )
        if timestamp is not None
    )
    return any(left > right for left, right in zip(ordered, ordered[1:]))


def _validation_issue(
    failure: GapMissedEntryFailure,
    field: str,
    message: str,
) -> GapMissedEntryValidationIssue:
    return GapMissedEntryValidationIssue(failure=failure, field=field, message=message)


def _lowest_quality(*qualities: GapMissedEntryQuality) -> GapMissedEntryQuality:
    order = {
        GapMissedEntryQuality.INVALID: 0,
        GapMissedEntryQuality.DEGRADED: 1,
        GapMissedEntryQuality.PARTIAL: 2,
        GapMissedEntryQuality.VALID: 3,
        GapMissedEntryQuality.NOT_APPLICABLE: 4,
    }
    return min(qualities, key=lambda quality: order[quality])


def _decimal_or_none(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _ordered_unique(values: Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values))


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _freeze_value(item) for key, item in sorted(value.items())})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (Decimal, int, float, str)) or value is None:
        return _decimal_or_none(value) if isinstance(value, (Decimal, int, float)) else value
    return value


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _serializable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_serializable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value
