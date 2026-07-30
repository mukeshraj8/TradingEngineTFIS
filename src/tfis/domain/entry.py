from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from .business_engine import BusinessEngineMetrics, BusinessEngineStatus
from .gap_missed_entry import (
    GapMissedEntryEngineResult,
    MissedEntryState,
    RecalculationDownstreamAction,
    RecalculationStatus,
)
from .runtime_contracts import TFISContractIdentity, TFISExecutionSide, TFISProductType
from .strategy_identity import PositionCycleIdentity, StrategyEvaluationIdentity


class EntryMarketBias(str, Enum):
    BULLISH = "BULLISH"
    BULLISH_CONFIRMED = "BULLISH_CONFIRMED"
    BEARISH = "BEARISH"
    BEARISH_CONFIRMED = "BEARISH_CONFIRMED"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EntryInstrumentType(str, Enum):
    UNDERLYING_SPOT = "UNDERLYING_SPOT"
    UNDERLYING_FUTURE = "UNDERLYING_FUTURE"
    SELECTED_OPTION_CONTRACT = "SELECTED_OPTION_CONTRACT"
    EQUITY_INSTRUMENT = "EQUITY_INSTRUMENT"
    OTHER = "OTHER"


class EntryOptionRight(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class EntryPositionIntent(str, Enum):
    LONG_OPTION = "LONG_OPTION"
    SHORT_OPTION = "SHORT_OPTION"
    LONG_FUTURE = "LONG_FUTURE"
    SHORT_FUTURE = "SHORT_FUTURE"
    LONG_EQUITY = "LONG_EQUITY"
    SHORT_EQUITY = "SHORT_EQUITY"
    FLAT = "FLAT"
    UNKNOWN = "UNKNOWN"


class EntryTriggerDirection(str, Enum):
    PRICE_AT_OR_ABOVE = "PRICE_AT_OR_ABOVE"
    PRICE_AT_OR_BELOW = "PRICE_AT_OR_BELOW"
    PRICE_CROSSES_ABOVE = "PRICE_CROSSES_ABOVE"
    PRICE_CROSSES_BELOW = "PRICE_CROSSES_BELOW"
    IMMEDIATE = "IMMEDIATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class EntryReferenceSource(str, Enum):
    UNDERLYING_SPOT = "UNDERLYING_SPOT"
    UNDERLYING_FUTURE = "UNDERLYING_FUTURE"
    SELECTED_OPTION_CONTRACT = "SELECTED_OPTION_CONTRACT"
    EQUITY_INSTRUMENT = "EQUITY_INSTRUMENT"
    FINAL_STRIKE_VALUE = "FINAL_STRIKE_VALUE"
    ENTRY_VALUE = "ENTRY_VALUE"
    CURRENT_DAY_OBSERVATION = "CURRENT_DAY_OBSERVATION"
    OTHER_EXPLICIT_REFERENCE = "OTHER_EXPLICIT_REFERENCE"


class EntryReferenceValueType(str, Enum):
    PRICE = "PRICE"
    STRIKE = "STRIKE"
    PERCENTAGE = "PERCENTAGE"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"
    COUNT = "COUNT"
    UNKNOWN = "UNKNOWN"


class EntryReferenceRequirement(str, Enum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EntryFormulaOperandRole(str, Enum):
    LEFT_OPERAND = "LEFT_OPERAND"
    RIGHT_OPERAND = "RIGHT_OPERAND"
    PERCENTAGE_BASE = "PERCENTAGE_BASE"
    BASE_ENTRY = "BASE_ENTRY"
    RECALCULATED_THRESHOLD = "RECALCULATED_THRESHOLD"
    OUTPUT = "OUTPUT"


class EntryFormulaOperator(str, Enum):
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    MAX = "MAX"
    MIN = "MIN"
    SUPPLIED_VALUE = "SUPPLIED_VALUE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EntryRoundingRule(str, Enum):
    NONE = "NONE"
    ROUND_UP = "ROUND_UP"
    ROUND_DOWN = "ROUND_DOWN"
    NEAREST = "NEAREST"
    POLICY_DEFINED = "POLICY_DEFINED"


class EntryStatus(str, Enum):
    BASE_ENTRY_READY = "BASE_ENTRY_READY"
    EFFECTIVE_ENTRY_EQUALS_BASE = "EFFECTIVE_ENTRY_EQUALS_BASE"
    EFFECTIVE_ENTRY_RECALCULATED = "EFFECTIVE_ENTRY_RECALCULATED"
    ENTRY_NOT_MISSED = "ENTRY_NOT_MISSED"
    ENTRY_MISSED = "ENTRY_MISSED"
    RECALCULATION_REQUIRED = "RECALCULATION_REQUIRED"
    DEFERRED_UNTIL_RECALCULATION = "DEFERRED_UNTIL_RECALCULATION"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EntrySource(str, Enum):
    BASE_POLICY = "BASE_POLICY"
    GAP_MISSED_ENTRY_RECALCULATION = "GAP_MISSED_ENTRY_RECALCULATION"
    COMPATIBILITY_OUTPUT = "COMPATIBILITY_OUTPUT"
    SUPPLIED_NOT_APPLICABLE = "SUPPLIED_NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"


class EntryQuality(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EntryDownstreamPermission(str, Enum):
    PERMITTED = "PERMITTED"
    EVIDENCE_ONLY = "EVIDENCE_ONLY"
    DEFERRED = "DEFERRED"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EntryUnresolvedSemantics(str, Enum):
    NONE = "NONE"
    IMAGE_VERIFICATION_REQUIRED = "IMAGE_VERIFICATION_REQUIRED"
    WORKBOOK_CONFIRMATION_REQUIRED = "WORKBOOK_CONFIRMATION_REQUIRED"
    USER_CLARIFICATION_REQUIRED = "USER_CLARIFICATION_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    LEGACY_INCONSISTENCY = "LEGACY_INCONSISTENCY"


class EntryFailure(str, Enum):
    MISSING_STRATEGY_IDENTITY = "MISSING_STRATEGY_IDENTITY"
    MISSING_POSITION_CYCLE_IDENTITY = "MISSING_POSITION_CYCLE_IDENTITY"
    MISSING_RESOLVED_CONFIGURATION_HASH = "MISSING_RESOLVED_CONFIGURATION_HASH"
    MISSING_ENTRY_POLICY = "MISSING_ENTRY_POLICY"
    UNKNOWN_ENTRY_POLICY = "UNKNOWN_ENTRY_POLICY"
    POLICY_COMPOSITION_MISMATCH = "POLICY_COMPOSITION_MISMATCH"
    MISSING_RESOLVED_INSTRUMENT = "MISSING_RESOLVED_INSTRUMENT"
    MISSING_SELECTED_OPTION_CONTRACT = "MISSING_SELECTED_OPTION_CONTRACT"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    AMBIGUOUS_REFERENCE_IDENTITY = "AMBIGUOUS_REFERENCE_IDENTITY"
    MISSING_FORMULA_DESCRIPTOR = "MISSING_FORMULA_DESCRIPTOR"
    UNSUPPORTED_FORMULA_COMPONENT = "UNSUPPORTED_FORMULA_COMPONENT"
    FORMULA_EVALUATION_ERROR = "FORMULA_EVALUATION_ERROR"
    INVALID_ENTRY_VALUE = "INVALID_ENTRY_VALUE"
    INVALID_TRIGGER_DIRECTION = "INVALID_TRIGGER_DIRECTION"
    INVALID_ORDER_SIDE = "INVALID_ORDER_SIDE"
    GAP_MISSED_ENTRY_REQUIRED_BUT_MISSING = "GAP_MISSED_ENTRY_REQUIRED_BUT_MISSING"
    GAP_MISSED_ENTRY_BLOCKED = "GAP_MISSED_ENTRY_BLOCKED"
    RECALCULATION_REQUIRED_BUT_MISSING = "RECALCULATION_REQUIRED_BUT_MISSING"
    RECALCULATION_OUTPUT_INCOMPATIBLE = "RECALCULATION_OUTPUT_INCOMPATIBLE"
    UNRESOLVED_ENTRY_SEMANTICS = "UNRESOLVED_ENTRY_SEMANTICS"
    UNSUPPORTED_PRODUCT = "UNSUPPORTED_PRODUCT"
    TIMESTAMP_CHRONOLOGY_INVALID = "TIMESTAMP_CHRONOLOGY_INVALID"
    STALE_REFERENCE_EVIDENCE = "STALE_REFERENCE_EVIDENCE"
    NONDETERMINISTIC_OUTPUT = "NONDETERMINISTIC_OUTPUT"


class EntryWarning(str, Enum):
    OPTIONAL_REFERENCE_MISSING = "OPTIONAL_REFERENCE_MISSING"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    COMPATIBILITY_ONLY = "COMPATIBILITY_ONLY"
    GAP_MISSED_ENTRY_NOT_APPLICABLE = "GAP_MISSED_ENTRY_NOT_APPLICABLE"
    UNRESOLVED_RULE_PRESENT = "UNRESOLVED_RULE_PRESENT"


@dataclass(frozen=True, slots=True)
class EntryResolvedBranch:
    market_bias: EntryMarketBias
    strategy_branch: str
    product: TFISProductType
    instrument_type: EntryInstrumentType
    option_right: EntryOptionRight
    position_intent: EntryPositionIntent
    order_side: TFISExecutionSide | None
    trigger_direction: EntryTriggerDirection
    branch_label: str | None = None
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class EntryReference:
    reference_id: str
    source: EntryReferenceSource
    instrument_id: str
    segment: str
    product: TFISProductType
    reference_type: str
    lookback: str
    value: Decimal | str | bool | int | None
    value_type: EntryReferenceValueType
    event_timestamp: datetime | None
    effective_date: date | None
    provenance: Mapping[str, str]
    quality: EntryQuality
    requirement: EntryReferenceRequirement = EntryReferenceRequirement.REQUIRED

    def __post_init__(self) -> None:
        if not self.reference_id.strip():
            raise ValueError("reference_id must be non-empty")
        if self.source is not EntryReferenceSource.OTHER_EXPLICIT_REFERENCE and not self.instrument_id.strip():
            raise ValueError("instrument_id must be non-empty for explicit references")
        object.__setattr__(self, "value", _decimal_if_numeric(self.value))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class EntryFormulaComponent:
    component_id: str
    operand_role: EntryFormulaOperandRole
    operand_source: EntryReferenceSource
    operator: EntryFormulaOperator
    reference_id: str | None = None
    percentage_value: Decimal | None = None
    percentage_base_reference_id: str | None = None
    rounding_rule: EntryRoundingRule = EntryRoundingRule.NONE
    output_precision: int | None = None
    formula_reference: str | None = None
    requirement_reference: str | None = None
    intermediate_result: Decimal | None = None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.component_id.strip():
            raise ValueError("component_id must be non-empty")
        object.__setattr__(self, "percentage_value", _decimal_or_none(self.percentage_value))
        object.__setattr__(self, "intermediate_result", _decimal_or_none(self.intermediate_result))
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence))


@dataclass(frozen=True, slots=True)
class EntryFormulaDescriptor:
    formula_id: str
    formula_reference: str
    formula_family: str
    components: tuple[EntryFormulaComponent, ...]
    requirement_references: tuple[str, ...] = ()
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.formula_id.strip():
            raise ValueError("formula_id must be non-empty")
        object.__setattr__(self, "components", tuple(self.components))
        object.__setattr__(self, "requirement_references", tuple(self.requirement_references))


@dataclass(frozen=True, slots=True)
class EntryTriggerCondition:
    trigger_direction: EntryTriggerDirection
    comparison_value: Decimal | None
    order_side: TFISExecutionSide | None
    position_intent: EntryPositionIntent
    reference_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_value", _decimal_or_none(self.comparison_value))


@dataclass(frozen=True, slots=True)
class EntryValidationIssue:
    failure: EntryFailure
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class EntryValidation:
    issues: tuple[EntryValidationIssue, ...] = ()
    unresolved_semantics: tuple[EntryUnresolvedSemantics, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues))
        object.__setattr__(self, "unresolved_semantics", tuple(self.unresolved_semantics))

    @property
    def passed(self) -> bool:
        return not self.issues and not any(
            item is not EntryUnresolvedSemantics.NONE
            for item in self.unresolved_semantics
        )


@dataclass(frozen=True, slots=True)
class EntryBaseCandidate:
    value: Decimal | None
    source: EntrySource
    trigger_condition: EntryTriggerCondition
    formula_descriptor: EntryFormulaDescriptor
    component_evidence: tuple[EntryFormulaComponent, ...]
    quality: EntryQuality
    validation: EntryValidation
    downstream_permission: EntryDownstreamPermission
    warnings: tuple[EntryWarning, ...] = ()
    failures: tuple[EntryFailure, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _decimal_or_none(self.value))
        object.__setattr__(self, "component_evidence", tuple(self.component_evidence))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class EntryEffectiveTrigger:
    value: Decimal | None
    status: EntryStatus
    source: EntrySource
    trigger_condition: EntryTriggerCondition
    base_candidate: EntryBaseCandidate
    gap_missed_entry_status: str
    recalculation_status: str | None
    quality: EntryQuality
    validation: EntryValidation
    downstream_permission: EntryDownstreamPermission
    warnings: tuple[EntryWarning, ...] = ()
    failures: tuple[EntryFailure, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _decimal_or_none(self.value))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class EntryPolicyOutcome:
    status: EntryStatus
    base_candidate: EntryBaseCandidate | None = None
    effective_trigger: EntryEffectiveTrigger | None = None
    warnings: tuple[EntryWarning, ...] = ()
    failures: tuple[EntryFailure, ...] = ()
    quality: EntryQuality = EntryQuality.VALID
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


class EntryPolicy(Protocol):
    policy_key: str

    def evaluate_base(self, engine_input: EntryEngineInput) -> EntryPolicyOutcome:
        ...

    def finalize_effective(
        self,
        engine_input: EntryEngineInput,
        base_candidate: EntryBaseCandidate,
        gap_missed_entry_result: GapMissedEntryEngineResult | None,
    ) -> EntryPolicyOutcome:
        ...


@dataclass(frozen=True, slots=True)
class EntryEvidence:
    strategy_identity: Mapping[str, str]
    policy_key: str
    product: TFISProductType
    branch: EntryResolvedBranch
    resolved_instrument: TFISContractIdentity | None
    formula_descriptor: EntryFormulaDescriptor | None
    input_references: tuple[EntryReference, ...]
    base_entry: EntryBaseCandidate | None
    gap_missed_entry_dependency: Mapping[str, Any]
    effective_entry: EntryEffectiveTrigger | None
    validation: EntryValidation
    warnings: tuple[EntryWarning, ...]
    failures: tuple[EntryFailure, ...]
    quality: EntryQuality
    provenance: Mapping[str, str]
    deterministic_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategy_identity", _freeze_mapping(self.strategy_identity))
        object.__setattr__(self, "input_references", tuple(self.input_references))
        object.__setattr__(self, "gap_missed_entry_dependency", _freeze_mapping(self.gap_missed_entry_dependency))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_decision_evidence_fragment(self) -> dict[str, Any]:
        return {
            "engine_id": "entry",
            "contract": "entry",
            "evidence": _serializable(self),
        }


@dataclass(frozen=True, slots=True)
class EntryMetrics:
    validation_seconds: float = 0.0
    policy_resolution_seconds: float = 0.0
    formula_policy_evaluation_seconds: float = 0.0
    result_construction_seconds: float = 0.0
    evidence_serialization_seconds: float = 0.0
    deterministic_hash_seconds: float = 0.0
    serialized_result_size_bytes: int = 0
    input_reference_count: int = 0
    missing_reference_count: int = 0

    def to_business_engine_metrics(self) -> BusinessEngineMetrics:
        return BusinessEngineMetrics(
            processing_duration_seconds=(
                self.validation_seconds
                + self.policy_resolution_seconds
                + self.formula_policy_evaluation_seconds
                + self.result_construction_seconds
                + self.evidence_serialization_seconds
                + self.deterministic_hash_seconds
            ),
            input_record_count=self.input_reference_count,
            output_record_count=1,
            cache_hit=False,
            dependency_versions=MappingProxyType({"entry_contract": "phase3d.milestone2.v1"}),
        )


@dataclass(frozen=True, slots=True)
class EntryEngineInput:
    evaluation_identity: StrategyEvaluationIdentity
    position_cycle_identity: PositionCycleIdentity
    resolved_configuration_hash: str
    product: TFISProductType
    resolved_branch: EntryResolvedBranch
    resolved_instrument: TFISContractIdentity | None
    entry_policy_key: str
    formula_descriptor: EntryFormulaDescriptor | None
    references: tuple[EntryReference, ...]
    strategy_parameters: Mapping[str, Any]
    evaluation_timestamp: datetime
    gap_missed_entry_result: GapMissedEntryEngineResult | None = None
    gap_missed_entry_required: bool = False
    unresolved_semantics: tuple[EntryUnresolvedSemantics, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "references", tuple(self.references))
        object.__setattr__(self, "strategy_parameters", _freeze_mapping(self.strategy_parameters))
        object.__setattr__(self, "unresolved_semantics", tuple(self.unresolved_semantics))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class EntryEngineResult:
    engine_id: str
    status: BusinessEngineStatus
    entry_status: EntryStatus
    quality: EntryQuality
    validation: EntryValidation
    base_entry: EntryBaseCandidate | None
    effective_entry: EntryEffectiveTrigger | None
    downstream_permission: EntryDownstreamPermission
    evidence: EntryEvidence
    warnings: tuple[EntryWarning, ...]
    failures: tuple[EntryFailure, ...]
    metrics: EntryMetrics
    deterministic_hash: str
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


def entry_engine_result_json(result: EntryEngineResult) -> str:
    return result.to_json()


def entry_hash(value: Any) -> str:
    return sha256(
        json.dumps(
            _serializable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _decimal_if_numeric(value: Decimal | str | bool | int | None) -> Decimal | str | bool | int | None:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception:
            return value
    return value


def _decimal_or_none(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _freeze_value(item) for key, item in sorted(value.items())})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(sorted((_freeze_value(item) for item in value), key=str))
    return value


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _serializable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_serializable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
