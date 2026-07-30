from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
import json

import yaml

from .runtime_contracts import TFISProductType


class BusinessEngineCapability(str, Enum):
    MONTHLY_STATUS = "MONTHLY_STATUS"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    OPTION_CHAIN = "OPTION_CHAIN"
    STRIKE_SELECTION = "STRIKE_SELECTION"
    PREMIUM_REFERENCE = "PREMIUM_REFERENCE"
    OI_REFERENCE = "OI_REFERENCE"
    ENTRY = "ENTRY"
    BASE_ENTRY = "BASE_ENTRY"
    EFFECTIVE_ENTRY = "EFFECTIVE_ENTRY"
    ENTRY_QUALIFICATION = "ENTRY_QUALIFICATION"
    RECALCULATED_ENTRY = "RECALCULATED_ENTRY"
    TRADABLE_INSTRUMENT_RESOLVED = "TRADABLE_INSTRUMENT_RESOLVED"
    GAP = "GAP"
    MISSED_ENTRY = "MISSED_ENTRY"
    TARGET = "TARGET"
    MSL = "MSL"
    TSL = "TSL"
    APS = "APS"
    EXECUTION = "EXECUTION"
    POSITION_STATE = "POSITION_STATE"
    RISK = "RISK"
    LIFECYCLE = "LIFECYCLE"
    EXECUTION_INTENT = "EXECUTION_INTENT"


class BusinessEngineStage(str, Enum):
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    MONTHLY_STATUS = "MONTHLY_STATUS"
    GAP = "GAP"
    ENTRY = "ENTRY"
    CONTRACT_SELECTION = "CONTRACT_SELECTION"
    RISK = "RISK"
    TARGET = "TARGET"
    MSL = "MSL"
    LIFECYCLE = "LIFECYCLE"
    EXECUTION_INTENT = "EXECUTION_INTENT"


class BusinessEngineStatus(str, Enum):
    PASSED = "PASSED"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    FAILED = "FAILED"


class BusinessEngineQuality(str, Enum):
    VALID = "VALID"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BusinessEngineStateRequirement(str, Enum):
    STATELESS = "STATELESS"
    READ_ONLY_STATE = "READ_ONLY_STATE"
    MUTABLE_STATE_REQUIRED = "MUTABLE_STATE_REQUIRED"


class BusinessEngineCriticality(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    SAFETY_CRITICAL = "SAFETY_CRITICAL"


class BusinessEngineFailure(str, Enum):
    MISSING_REQUIRED_INPUT = "MISSING_REQUIRED_INPUT"
    INCONSISTENT_INPUT = "INCONSISTENT_INPUT"
    UNSUPPORTED_PRODUCT = "UNSUPPORTED_PRODUCT"
    UNSUPPORTED_STRATEGY_FAMILY = "UNSUPPORTED_STRATEGY_FAMILY"
    MISSING_CAPABILITY = "MISSING_CAPABILITY"
    INCOMPATIBLE_CONFIGURATION = "INCOMPATIBLE_CONFIGURATION"
    MISSING_STATE = "MISSING_STATE"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    TIMESTAMP_INCONSISTENCY = "TIMESTAMP_INCONSISTENCY"


class BusinessEngineValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class BusinessEngineValidationIssue:
    code: str
    engine_id: str
    field: str
    message: str
    severity: BusinessEngineValidationSeverity = BusinessEngineValidationSeverity.ERROR


@dataclass(frozen=True, slots=True)
class BusinessEngineValidation:
    issues: tuple[BusinessEngineValidationIssue, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(
            issue.severity is BusinessEngineValidationSeverity.ERROR
            for issue in self.issues
        )


@dataclass(frozen=True, slots=True)
class BusinessEngineEvidence:
    raw_evidence_refs: tuple[str, ...] = ()
    derived_evidence_refs: tuple[str, ...] = ()
    formula_references: tuple[str, ...] = ()
    requirement_references: tuple[str, ...] = ()
    intermediate_values: Mapping[str, Any] = MappingProxyType({})
    quality_notes: tuple[str, ...] = ()
    data_warnings: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_evidence_refs", tuple(self.raw_evidence_refs))
        object.__setattr__(self, "derived_evidence_refs", tuple(self.derived_evidence_refs))
        object.__setattr__(self, "formula_references", tuple(self.formula_references))
        object.__setattr__(self, "requirement_references", tuple(self.requirement_references))
        object.__setattr__(self, "intermediate_values", _freeze_mapping(self.intermediate_values))
        object.__setattr__(self, "quality_notes", tuple(self.quality_notes))
        object.__setattr__(self, "data_warnings", tuple(self.data_warnings))
        object.__setattr__(self, "missing_inputs", tuple(self.missing_inputs))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_decision_evidence_fragment(self, engine_id: str) -> dict[str, Any]:
        return {"engine_id": engine_id, "evidence": _serializable(self)}


@dataclass(frozen=True, slots=True)
class BusinessEngineMetrics:
    processing_duration_seconds: float | None = None
    input_record_count: int | None = None
    output_record_count: int | None = None
    cache_hit: bool | None = None
    dependency_versions: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "dependency_versions", _freeze_mapping(self.dependency_versions))


@dataclass(frozen=True, slots=True)
class BusinessEnginePerformanceContract:
    expected_execution_frequency: str
    expected_input_size: str
    cacheable: bool
    deterministic: bool
    parallel_safe: bool
    state_requirement: BusinessEngineStateRequirement
    criticality: BusinessEngineCriticality


@dataclass(frozen=True, slots=True)
class BusinessEngineDefinition:
    engine_id: str
    display_name: str
    purpose: str
    stage: BusinessEngineStage
    schema_version: str
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    produced_outputs: tuple[str, ...]
    evidence_outputs: tuple[str, ...]
    validation_rules: tuple[str, ...]
    failure_modes: tuple[str, ...]
    quality_metrics: tuple[str, ...]
    state_requirements: BusinessEngineStateRequirement
    dependencies: tuple[str, ...]
    required_capabilities: tuple[BusinessEngineCapability, ...]
    provided_capabilities: tuple[BusinessEngineCapability, ...]
    supported_products: tuple[TFISProductType, ...]
    supported_strategy_families: tuple[str, ...]
    performance: BusinessEnginePerformanceContract

    def __post_init__(self) -> None:
        if not self.engine_id.strip():
            raise ValueError("engine_id must be non-empty")
        for name in (
            "required_inputs",
            "optional_inputs",
            "produced_outputs",
            "evidence_outputs",
            "validation_rules",
            "failure_modes",
            "quality_metrics",
            "dependencies",
            "supported_strategy_families",
        ):
            object.__setattr__(self, name, _ordered_unique(getattr(self, name)))
        object.__setattr__(self, "required_capabilities", tuple(dict.fromkeys(self.required_capabilities)))
        object.__setattr__(self, "provided_capabilities", tuple(dict.fromkeys(self.provided_capabilities)))
        object.__setattr__(self, "supported_products", tuple(dict.fromkeys(self.supported_products)))


@dataclass(frozen=True, slots=True)
class BusinessEngineContext:
    evaluation_id: str
    strategy_family_id: str
    strategy_definition_id: str
    strategy_version: str
    strategy_instance_id: str
    product_type: TFISProductType
    evaluation_timestamp: datetime
    configuration_hash: str
    available_capabilities: tuple[BusinessEngineCapability, ...]
    state_refs: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_capabilities", tuple(dict.fromkeys(self.available_capabilities)))
        object.__setattr__(self, "state_refs", _freeze_mapping(self.state_refs))


@dataclass(frozen=True, slots=True)
class BusinessEngineInput:
    engine_id: str
    payload: Mapping[str, Any]
    input_completeness: BusinessEngineQuality
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


@dataclass(frozen=True, slots=True)
class BusinessEngineResult:
    engine_id: str
    status: BusinessEngineStatus
    quality: BusinessEngineQuality
    confidence: float | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    evidence: BusinessEngineEvidence
    intermediate_values: Mapping[str, Any]
    metrics: BusinessEngineMetrics
    validation: BusinessEngineValidation
    input_completeness: BusinessEngineQuality
    capability_usage: tuple[BusinessEngineCapability, ...]
    provenance: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1 when provided")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "errors", tuple(self.errors))
        object.__setattr__(self, "intermediate_values", _freeze_mapping(self.intermediate_values))
        object.__setattr__(self, "capability_usage", tuple(dict.fromkeys(self.capability_usage)))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))


class BusinessEngine:
    definition: BusinessEngineDefinition

    def validate(
        self,
        context: BusinessEngineContext,
        engine_input: BusinessEngineInput,
    ) -> BusinessEngineValidation:
        return validate_business_engine_invocation(self.definition, context, engine_input)

    def execute(
        self,
        context: BusinessEngineContext,
        engine_input: BusinessEngineInput,
    ) -> BusinessEngineResult:
        raise NotImplementedError


class BusinessEngineRegistry:
    def __init__(self, definitions: Mapping[str, BusinessEngineDefinition]) -> None:
        normalized: dict[str, BusinessEngineDefinition] = {}
        issues: list[BusinessEngineValidationIssue] = []
        for engine_id, definition in sorted(definitions.items()):
            if engine_id != definition.engine_id:
                issues.append(_issue("ENGINE_ID_MISMATCH", engine_id, "engine_id", "registry key must match definition id"))
            if definition.engine_id in normalized:
                issues.append(_issue("DUPLICATE_ENGINE_ID", definition.engine_id, "engine_id", "duplicate business engine id"))
            normalized[definition.engine_id] = definition
        self._definitions = MappingProxyType(normalized)
        issues.extend(self._dependency_issues())
        issues.extend(self._capability_issues())
        if issues:
            raise BusinessEngineRegistryError(tuple(issues))
        self._execution_order = self._topological_order()

    @property
    def definitions(self) -> Mapping[str, BusinessEngineDefinition]:
        return self._definitions

    @property
    def execution_order(self) -> tuple[str, ...]:
        return self._execution_order

    def get(self, engine_id: str) -> BusinessEngineDefinition:
        return self._definitions[engine_id]

    def engines_providing(self, capability: BusinessEngineCapability) -> tuple[str, ...]:
        return tuple(
            engine.engine_id
            for engine in self._definitions.values()
            if capability in engine.provided_capabilities
        )

    def _dependency_issues(self) -> list[BusinessEngineValidationIssue]:
        issues = []
        for definition in self._definitions.values():
            for dependency in definition.dependencies:
                if dependency not in self._definitions:
                    issues.append(_issue("UNKNOWN_ENGINE_DEPENDENCY", definition.engine_id, "dependencies", f"unknown dependency {dependency}"))
        return issues

    def _capability_issues(self) -> list[BusinessEngineValidationIssue]:
        issues = []
        for definition in self._definitions.values():
            dependency_provided = {
                capability
                for dependency in definition.dependencies
                if dependency in self._definitions
                for capability in self._definitions[dependency].provided_capabilities
            }
            missing = set(definition.required_capabilities) - dependency_provided
            if missing:
                issues.append(_issue("UNSATISFIED_ENGINE_CAPABILITY", definition.engine_id, "required_capabilities", f"missing dependency capabilities: {', '.join(sorted(item.value for item in missing))}"))
            for dependency in definition.dependencies:
                if dependency not in self._definitions:
                    continue
                dependency_caps = set(self._definitions[dependency].provided_capabilities)
                if not dependency_caps and definition.required_capabilities:
                    issues.append(_issue("DEPENDENCY_PROVIDES_NO_CAPABILITIES", definition.engine_id, "dependencies", f"dependency {dependency} provides no capabilities"))
        return issues

    def _topological_order(self) -> tuple[str, ...]:
        temporary: set[str] = set()
        permanent: set[str] = set()
        ordered: list[str] = []

        def visit(engine_id: str) -> None:
            if engine_id in permanent:
                return
            if engine_id in temporary:
                raise BusinessEngineRegistryError((_issue("CIRCULAR_ENGINE_DEPENDENCY", engine_id, "dependencies", "circular engine dependency detected"),))
            temporary.add(engine_id)
            for dependency in self._definitions[engine_id].dependencies:
                visit(dependency)
            temporary.remove(engine_id)
            permanent.add(engine_id)
            ordered.append(engine_id)

        for engine_id in self._definitions:
            visit(engine_id)
        return tuple(ordered)


class BusinessEngineRegistryError(ValueError):
    def __init__(self, issues: tuple[BusinessEngineValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


def load_business_engine_registry(path: str | Path) -> BusinessEngineRegistry:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise BusinessEngineRegistryError((_issue("INVALID_ENGINE_CATALOG", str(path), "", "catalog must be a mapping"),))
    allowed = {"schema_version", "engines"}
    unknown = set(payload) - allowed
    if unknown:
        raise BusinessEngineRegistryError(tuple(_issue("UNKNOWN_ENGINE_CATALOG_KEY", str(path), key, "unknown catalog key") for key in sorted(unknown)))
    definitions = {}
    for data in payload.get("engines") or ():
        definition = _definition_from_mapping(data)
        if definition.engine_id in definitions:
            raise BusinessEngineRegistryError((_issue("DUPLICATE_ENGINE_ID", definition.engine_id, "engine_id", "duplicate business engine id"),))
        definitions[definition.engine_id] = definition
    return BusinessEngineRegistry(definitions)


def validate_business_engine_invocation(
    definition: BusinessEngineDefinition,
    context: BusinessEngineContext,
    engine_input: BusinessEngineInput,
) -> BusinessEngineValidation:
    issues: list[BusinessEngineValidationIssue] = []
    if engine_input.engine_id != definition.engine_id:
        issues.append(_issue("ENGINE_INPUT_MISMATCH", definition.engine_id, "engine_input.engine_id", "input engine_id must match the engine definition"))
    for input_name in definition.required_inputs:
        if input_name not in engine_input.payload:
            issues.append(_issue(BusinessEngineFailure.MISSING_REQUIRED_INPUT.value, definition.engine_id, input_name, "required input is missing"))
    if context.product_type not in definition.supported_products:
        issues.append(_issue(BusinessEngineFailure.UNSUPPORTED_PRODUCT.value, definition.engine_id, "product_type", f"unsupported product {context.product_type.value}"))
    if (
        "*"
        not in definition.supported_strategy_families
        and context.strategy_family_id not in definition.supported_strategy_families
    ):
        issues.append(_issue(BusinessEngineFailure.UNSUPPORTED_STRATEGY_FAMILY.value, definition.engine_id, "strategy_family_id", f"unsupported strategy family {context.strategy_family_id}"))
    missing_capabilities = set(definition.required_capabilities) - set(context.available_capabilities)
    if missing_capabilities:
        issues.append(_issue(BusinessEngineFailure.MISSING_CAPABILITY.value, definition.engine_id, "available_capabilities", f"missing capabilities: {', '.join(sorted(item.value for item in missing_capabilities))}"))
    if not context.configuration_hash.strip():
        issues.append(_issue(BusinessEngineFailure.INCOMPATIBLE_CONFIGURATION.value, definition.engine_id, "configuration_hash", "configuration hash is required"))
    if (
        definition.state_requirements is not BusinessEngineStateRequirement.STATELESS
        and not context.state_refs
    ):
        issues.append(_issue(BusinessEngineFailure.MISSING_STATE.value, definition.engine_id, "state_refs", "engine requires state references"))
    if not isinstance(context.evaluation_timestamp, datetime):
        issues.append(_issue(BusinessEngineFailure.TIMESTAMP_INCONSISTENCY.value, definition.engine_id, "evaluation_timestamp", "evaluation timestamp must be a datetime"))
    return BusinessEngineValidation(tuple(issues))


def _definition_from_mapping(data: Mapping[str, Any]) -> BusinessEngineDefinition:
    performance = data["performance"]
    return BusinessEngineDefinition(
        engine_id=str(data["engine_id"]),
        display_name=str(data["display_name"]),
        purpose=str(data["purpose"]),
        stage=BusinessEngineStage(data["stage"]),
        schema_version=str(data["schema_version"]),
        required_inputs=tuple(data.get("required_inputs") or ()),
        optional_inputs=tuple(data.get("optional_inputs") or ()),
        produced_outputs=tuple(data.get("produced_outputs") or ()),
        evidence_outputs=tuple(data.get("evidence_outputs") or ()),
        validation_rules=tuple(data.get("validation_rules") or ()),
        failure_modes=tuple(data.get("failure_modes") or ()),
        quality_metrics=tuple(data.get("quality_metrics") or ()),
        state_requirements=BusinessEngineStateRequirement(data["state_requirements"]),
        dependencies=tuple(data.get("dependencies") or ()),
        required_capabilities=tuple(BusinessEngineCapability(item) for item in data.get("required_capabilities") or ()),
        provided_capabilities=tuple(BusinessEngineCapability(item) for item in data.get("provided_capabilities") or ()),
        supported_products=tuple(TFISProductType(item) for item in data.get("supported_products") or ()),
        supported_strategy_families=tuple(data.get("supported_strategy_families") or ()),
        performance=BusinessEnginePerformanceContract(
            expected_execution_frequency=str(performance["expected_execution_frequency"]),
            expected_input_size=str(performance["expected_input_size"]),
            cacheable=bool(performance["cacheable"]),
            deterministic=bool(performance["deterministic"]),
            parallel_safe=bool(performance["parallel_safe"]),
            state_requirement=BusinessEngineStateRequirement(performance["state_requirement"]),
            criticality=BusinessEngineCriticality(performance["criticality"]),
        ),
    )


def _issue(code: str, engine_id: str, field: str, message: str) -> BusinessEngineValidationIssue:
    return BusinessEngineValidationIssue(code=code, engine_id=engine_id, field=field, message=message)


def _ordered_unique(values: tuple[Any, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values))


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _freeze_value(item) for key, item in sorted(value.items())})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


def _serializable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _serializable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def business_engine_catalog_json(registry: BusinessEngineRegistry) -> str:
    return json.dumps(
        {engine_id: _serializable(definition) for engine_id, definition in registry.definitions.items()},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
