from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from .enums import MonthlyStatus, Segment
from .runtime_contracts import TFISProductType, product_type_from_segment


class StrategyLifecycleStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    RETIRED = "RETIRED"


class StrategyVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    RETIRED = "RETIRED"


class StrategyExecutionMode(str, Enum):
    PAPER = "PAPER"
    REPLAY = "REPLAY"
    BACKTEST = "BACKTEST"
    LIVE = "LIVE"


class StrategyValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class StrategyValidationError:
    code: str
    location: str
    identity: str
    field: str
    message: str
    severity: StrategyValidationSeverity = StrategyValidationSeverity.ERROR


class StrategyConfigurationError(ValueError):
    def __init__(self, errors: tuple[StrategyValidationError, ...]) -> None:
        self.errors = errors
        super().__init__("; ".join(error.message for error in errors))


@dataclass(frozen=True, slots=True)
class StrategyPolicyComposition:
    product_policy: str
    entry_policy: str
    gap_policy: str
    missed_entry_policy: str
    contract_selection_policy: str
    target_policy: str
    msl_policy: str
    optional_policy_stages: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        for name in (
            "product_policy",
            "entry_policy",
            "gap_policy",
            "missed_entry_policy",
            "contract_selection_policy",
            "target_policy",
            "msl_policy",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        object.__setattr__(
            self,
            "optional_policy_stages",
            _freeze_mapping(self.optional_policy_stages),
        )

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class StrategyFamilyDefinition:
    family_id: str
    display_name: str
    product_type: TFISProductType
    required_capabilities: tuple[str, ...]
    optional_capabilities: tuple[str, ...]
    allowed_policy_stages: tuple[str, ...]
    family_defaults: Mapping[str, Any]
    supported_segments: tuple[Segment, ...]
    supported_instruments: tuple[str, ...]
    schema_version: str

    def __post_init__(self) -> None:
        _require_text(self.family_id, "family_id")
        object.__setattr__(self, "required_capabilities", _ordered_unique(self.required_capabilities))
        object.__setattr__(self, "optional_capabilities", _ordered_unique(self.optional_capabilities))
        object.__setattr__(self, "allowed_policy_stages", _ordered_unique(self.allowed_policy_stages))
        object.__setattr__(self, "family_defaults", _freeze_mapping(self.family_defaults))
        object.__setattr__(self, "supported_segments", tuple(self.supported_segments))
        object.__setattr__(self, "supported_instruments", _ordered_unique(self.supported_instruments))


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    strategy_definition_id: str
    family_id: str
    unique_strategy_code: str
    display_name: str
    description: str
    product_type: TFISProductType
    supported_underlyings: tuple[str, ...]
    policy_composition_ref: str
    formula_config_ref: str
    required_input_capabilities: tuple[str, ...]
    supported_monthly_status_branches: tuple[MonthlyStatus, ...]
    lifecycle_status: StrategyLifecycleStatus
    provenance: str
    source_references: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_text(self.strategy_definition_id, "strategy_definition_id")
        object.__setattr__(self, "supported_underlyings", _ordered_unique(self.supported_underlyings))
        object.__setattr__(self, "required_input_capabilities", _ordered_unique(self.required_input_capabilities))
        object.__setattr__(self, "supported_monthly_status_branches", tuple(self.supported_monthly_status_branches))
        object.__setattr__(self, "source_references", tuple(self.source_references))


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    strategy_definition_id: str
    strategy_version: str
    effective_from: datetime
    retired_at: datetime | None
    configuration_hash: str
    formula_hash: str
    policy_composition_hash: str
    source_references: tuple[str, ...]
    change_description: str
    status: StrategyVersionStatus
    version_values: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_text(self.strategy_version, "strategy_version")
        if self.retired_at is not None and self.retired_at <= self.effective_from:
            raise ValueError("retired_at must be after effective_from")
        object.__setattr__(self, "source_references", tuple(self.source_references))
        object.__setattr__(self, "version_values", _freeze_mapping(self.version_values))


@dataclass(frozen=True, slots=True)
class StrategyInstanceDefinition:
    strategy_instance_id: str
    strategy_definition_id: str
    strategy_version: str
    underlying: str
    exchange: str
    segment: Segment
    account_ref: str
    execution_mode: StrategyExecutionMode
    enabled: bool
    lot_quantity: int
    capital_allocation_ref: str
    risk_profile_ref: str
    schedule_ref: str
    start_date: date
    end_date: date | None
    allowed_overrides: tuple[str, ...]
    instance_overrides: Mapping[str, Any]
    instance_configuration_hash: str

    def __post_init__(self) -> None:
        _require_text(self.strategy_instance_id, "strategy_instance_id")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        object.__setattr__(self, "allowed_overrides", _ordered_unique(self.allowed_overrides))
        object.__setattr__(self, "instance_overrides", _freeze_mapping(self.instance_overrides))


@dataclass(frozen=True, slots=True)
class ResolvedStrategyConfiguration:
    family: StrategyFamilyDefinition
    definition: StrategyDefinition
    version: StrategyVersion
    instance: StrategyInstanceDefinition
    resolved_policy_keys: StrategyPolicyComposition
    resolved_formula_config_ref: str
    resolved_parameters: Mapping[str, Any]
    resolved_capabilities: tuple[str, ...]
    resolved_instrument: Mapping[str, Any]
    resolved_session: Mapping[str, Any]
    effective_configuration_hash: str
    provenance: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "resolved_parameters", _freeze_mapping(self.resolved_parameters))
        object.__setattr__(self, "resolved_capabilities", _ordered_unique(self.resolved_capabilities))
        object.__setattr__(self, "resolved_instrument", _freeze_mapping(self.resolved_instrument))
        object.__setattr__(self, "resolved_session", _freeze_mapping(self.resolved_session))
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class StrategyEvaluationIdentity:
    evaluation_id: str
    strategy_instance_id: str
    strategy_definition_id: str
    strategy_version: str
    trading_date: date
    evaluation_timestamp: datetime
    evaluation_sequence: int
    trigger_type: str
    configuration_hash: str
    correlation_id: str | None = None
    causation_id: str | None = None

    @classmethod
    def deterministic(
        cls,
        *,
        strategy_instance_id: str,
        strategy_definition_id: str,
        strategy_version: str,
        trading_date: date,
        evaluation_timestamp: datetime,
        evaluation_sequence: int,
        trigger_type: str,
        configuration_hash: str,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> "StrategyEvaluationIdentity":
        material = {
            "strategy_instance_id": strategy_instance_id,
            "strategy_definition_id": strategy_definition_id,
            "strategy_version": strategy_version,
            "trading_date": trading_date.isoformat(),
            "evaluation_timestamp": evaluation_timestamp.isoformat(),
            "evaluation_sequence": evaluation_sequence,
            "trigger_type": trigger_type,
            "configuration_hash": configuration_hash,
            "correlation_id": correlation_id,
            "causation_id": causation_id,
        }
        digest = sha256(_canonical_bytes(material)).hexdigest()[:24]
        return cls(
            evaluation_id=f"eval-{digest}",
            strategy_instance_id=strategy_instance_id,
            strategy_definition_id=strategy_definition_id,
            strategy_version=strategy_version,
            trading_date=trading_date,
            evaluation_timestamp=evaluation_timestamp,
            evaluation_sequence=evaluation_sequence,
            trigger_type=trigger_type,
            configuration_hash=configuration_hash,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )


@dataclass(frozen=True, slots=True)
class PositionCycleIdentity:
    position_cycle_id: str
    strategy_instance_id: str
    trading_date: date
    cycle_sequence: int
    entry_evaluation_id: str
    product_instrument_identity: str
    parent_cycle_id: str | None = None
    reentry_reason: str | None = None
    lifecycle_status: str | None = None

    @classmethod
    def deterministic(
        cls,
        *,
        strategy_instance_id: str,
        trading_date: date,
        cycle_sequence: int,
        entry_evaluation_id: str,
        product_instrument_identity: str,
        parent_cycle_id: str | None = None,
        reentry_reason: str | None = None,
        lifecycle_status: str | None = None,
    ) -> "PositionCycleIdentity":
        material = {
            "strategy_instance_id": strategy_instance_id,
            "trading_date": trading_date.isoformat(),
            "cycle_sequence": cycle_sequence,
            "entry_evaluation_id": entry_evaluation_id,
            "product_instrument_identity": product_instrument_identity,
            "parent_cycle_id": parent_cycle_id,
            "reentry_reason": reentry_reason,
        }
        digest = sha256(_canonical_bytes(material)).hexdigest()[:24]
        return cls(
            position_cycle_id=f"cycle-{digest}",
            strategy_instance_id=strategy_instance_id,
            trading_date=trading_date,
            cycle_sequence=cycle_sequence,
            entry_evaluation_id=entry_evaluation_id,
            product_instrument_identity=product_instrument_identity,
            parent_cycle_id=parent_cycle_id,
            reentry_reason=reentry_reason,
            lifecycle_status=lifecycle_status,
        )

    @property
    def state_isolation_key(self) -> tuple[str, date, str]:
        return (self.strategy_instance_id, self.trading_date, self.position_cycle_id)


class StrategyConfigurationResolver:
    def __init__(
        self,
        *,
        families: Mapping[str, StrategyFamilyDefinition],
        definitions: Mapping[str, StrategyDefinition],
        versions: Mapping[tuple[str, str], StrategyVersion],
        instances: Mapping[str, StrategyInstanceDefinition],
        policy_compositions: Mapping[tuple[str, str], StrategyPolicyComposition],
    ) -> None:
        self.families = MappingProxyType(dict(sorted(families.items())))
        self.definitions = MappingProxyType(dict(sorted(definitions.items())))
        self.versions = MappingProxyType(dict(sorted(versions.items())))
        self.instances = MappingProxyType(dict(sorted(instances.items())))
        self.policy_compositions = MappingProxyType(dict(sorted(policy_compositions.items())))
        self._cache: dict[str, ResolvedStrategyConfiguration] = {}
        self._validate_all()

    def resolve(self, strategy_instance_id: str) -> ResolvedStrategyConfiguration:
        cached = self._cache.get(strategy_instance_id)
        if cached is not None:
            return cached
        instance = self._require(self.instances, strategy_instance_id, "UNKNOWN_INSTANCE")
        definition = self._require(self.definitions, instance.strategy_definition_id, "UNKNOWN_DEFINITION")
        family = self._require(self.families, definition.family_id, "UNKNOWN_FAMILY")
        version = self._require(self.versions, (definition.strategy_definition_id, instance.strategy_version), "UNKNOWN_VERSION")
        composition = self._require(self.policy_compositions, (definition.strategy_definition_id, version.strategy_version), "MISSING_POLICY_COMPOSITION")
        errors = self._resolution_errors(family, definition, version, instance, composition)
        if errors:
            raise StrategyConfigurationError(tuple(errors))
        parameters, provenance = self._resolve_parameters(family, definition, version, instance)
        resolved = ResolvedStrategyConfiguration(
            family=family,
            definition=definition,
            version=version,
            instance=instance,
            resolved_policy_keys=composition,
            resolved_formula_config_ref=str(version.version_values.get("formula_config_ref") or definition.formula_config_ref),
            resolved_parameters=parameters,
            resolved_capabilities=tuple(sorted(set(family.required_capabilities) | set(definition.required_input_capabilities))),
            resolved_instrument={
                "underlying": instance.underlying,
                "exchange": instance.exchange,
                "segment": instance.segment,
                "product_type": definition.product_type,
            },
            resolved_session={"schedule_ref": instance.schedule_ref, "execution_mode": instance.execution_mode},
            effective_configuration_hash="pending",
            provenance=provenance,
        )
        digest = sha256(_canonical_bytes({k: v for k, v in resolved.to_dict().items() if k != "effective_configuration_hash"})).hexdigest()
        resolved = ResolvedStrategyConfiguration(
            family=resolved.family,
            definition=resolved.definition,
            version=resolved.version,
            instance=resolved.instance,
            resolved_policy_keys=resolved.resolved_policy_keys,
            resolved_formula_config_ref=resolved.resolved_formula_config_ref,
            resolved_parameters=resolved.resolved_parameters,
            resolved_capabilities=resolved.resolved_capabilities,
            resolved_instrument=resolved.resolved_instrument,
            resolved_session=resolved.resolved_session,
            effective_configuration_hash=digest,
            provenance=resolved.provenance,
        )
        self._cache[strategy_instance_id] = resolved
        return resolved

    def _validate_all(self) -> None:
        errors: list[StrategyValidationError] = []
        for definition in self.definitions.values():
            if definition.family_id not in self.families:
                errors.append(_error("UNKNOWN_FAMILY", "definitions", definition.strategy_definition_id, "family_id", "definition references unknown family"))
        seen_versions: dict[tuple[str, str], str] = {}
        for key, version in self.versions.items():
            content_hash = _hash_mapping(version.version_values)
            previous = seen_versions.get(key)
            if previous is not None and previous != content_hash:
                errors.append(_error("VERSION_HASH_CONTENT_CONFLICT", "versions", "|".join(key), "version_values", "duplicate version has different content"))
            seen_versions[key] = content_hash
            if version.strategy_definition_id not in self.definitions:
                errors.append(_error("UNKNOWN_DEFINITION", "versions", "|".join(key), "strategy_definition_id", "version references unknown definition"))
        for instance in self.instances.values():
            if instance.strategy_definition_id not in self.definitions:
                errors.append(_error("UNKNOWN_DEFINITION", "instances", instance.strategy_instance_id, "strategy_definition_id", "instance references unknown definition"))
            if (instance.strategy_definition_id, instance.strategy_version) not in self.versions:
                errors.append(_error("UNKNOWN_VERSION", "instances", instance.strategy_instance_id, "strategy_version", "instance references unknown version"))
        if errors:
            raise StrategyConfigurationError(tuple(errors))

    def _resolution_errors(
        self,
        family: StrategyFamilyDefinition,
        definition: StrategyDefinition,
        version: StrategyVersion,
        instance: StrategyInstanceDefinition,
        composition: StrategyPolicyComposition,
    ) -> list[StrategyValidationError]:
        errors: list[StrategyValidationError] = []
        if family.product_type is not definition.product_type:
            errors.append(_error("UNSUPPORTED_PRODUCT_FAMILY", "resolution", definition.strategy_definition_id, "product_type", "definition product does not match family"))
        if instance.segment not in family.supported_segments:
            errors.append(_error("UNSUPPORTED_PRODUCT_FAMILY", "resolution", instance.strategy_instance_id, "segment", "instance segment not supported by family"))
        if product_type_from_segment(instance.segment) is not definition.product_type:
            errors.append(_error("UNSUPPORTED_PRODUCT_FAMILY", "resolution", instance.strategy_instance_id, "segment", "instance segment product does not match definition"))
        if definition.required_input_capabilities and not set(definition.required_input_capabilities).issubset(set(family.required_capabilities) | set(family.optional_capabilities)):
            errors.append(_error("MISSING_REQUIRED_CAPABILITY", "resolution", definition.strategy_definition_id, "required_input_capabilities", "definition requires unsupported family capability"))
        for key in instance.instance_overrides:
            if key not in instance.allowed_overrides:
                errors.append(_error("FORBIDDEN_INSTANCE_OVERRIDE", "instances", instance.strategy_instance_id, key, "instance override is not declared"))
            if key in {"entry_formula", "monthly_status_rule", "strike_formula", "target_formula", "msl_formula", "policy_key"}:
                errors.append(_error("FORBIDDEN_INSTANCE_OVERRIDE", "instances", instance.strategy_instance_id, key, "override would change strategy business identity"))
        if version.status is StrategyVersionStatus.RETIRED:
            errors.append(_error("RETIRED_VERSION_SELECTED", "instances", instance.strategy_instance_id, "strategy_version", "new instance cannot select retired version"))
        allowed_stages = set(family.allowed_policy_stages)
        for stage, policy in composition.to_dict().items():
            if stage == "optional_policy_stages":
                continue
            if stage.replace("_policy", "") not in allowed_stages and policy:
                errors.append(_error("COMPOSITION_CAPABILITY_MISMATCH", "composition", definition.strategy_definition_id, stage, "policy stage is not allowed by family"))
        return errors

    def _resolve_parameters(
        self,
        family: StrategyFamilyDefinition,
        definition: StrategyDefinition,
        version: StrategyVersion,
        instance: StrategyInstanceDefinition,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        allowed_family_keys = {"parameters", "session", "risk"}
        unknown = set(family.family_defaults) - allowed_family_keys
        if unknown:
            raise StrategyConfigurationError(tuple(_error("UNKNOWN_CONFIGURATION_KEY", "families", family.family_id, key, "unknown family default key") for key in sorted(unknown)))
        parameters = dict(family.family_defaults.get("parameters") or {})
        provenance = {f"parameters.{key}": "family" for key in parameters}
        version_parameters = dict(version.version_values.get("parameters") or {})
        for key, value in version_parameters.items():
            parameters[key] = value
            provenance[f"parameters.{key}"] = "version"
        for key, value in instance.instance_overrides.items():
            if key in {"lots", "capital_limit", "account_ref", "execution_mode", "enabled", "schedule_ref"}:
                parameters[key] = value
                provenance[f"parameters.{key}"] = "instance"
        provenance["definition"] = definition.strategy_definition_id
        provenance["version"] = version.strategy_version
        provenance["instance"] = instance.strategy_instance_id
        return parameters, provenance

    @staticmethod
    def _require(mapping: Mapping[Any, Any], key: Any, code: str) -> Any:
        if key not in mapping:
            raise StrategyConfigurationError((_error(code, "resolver", str(key), "reference", f"missing required reference {key!r}"),))
        return mapping[key]


def load_strategy_configuration_resolver(root: str | Path) -> StrategyConfigurationResolver:
    base = Path(root)
    families = _load_families(base / "config" / "strategy_families")
    definitions, versions = _load_definitions(base / "config" / "strategy_definitions")
    instances = _load_instances(base / "config" / "strategy_instances")
    compositions = _load_identity_compositions(base / "config" / "strategy_policy_composition.yaml")
    return StrategyConfigurationResolver(
        families=families,
        definitions=definitions,
        versions=versions,
        instances=instances,
        policy_compositions=compositions,
    )


def _load_families(path: Path) -> dict[str, StrategyFamilyDefinition]:
    records = {}
    for file_path in sorted(path.glob("*.yaml")):
        data = _load_yaml(file_path, _FAMILY_KEYS)
        family = StrategyFamilyDefinition(
            family_id=str(data["family_id"]),
            display_name=str(data["display_name"]),
            product_type=TFISProductType(data["product_type"]),
            required_capabilities=tuple(data.get("required_capabilities") or ()),
            optional_capabilities=tuple(data.get("optional_capabilities") or ()),
            allowed_policy_stages=tuple(data.get("allowed_policy_stages") or ()),
            family_defaults=data.get("family_defaults") or {},
            supported_segments=tuple(Segment(item) for item in data.get("supported_segments") or ()),
            supported_instruments=tuple(data.get("supported_instruments") or ()),
            schema_version=str(data["schema_version"]),
        )
        _add_unique(records, family.family_id, family, "DUPLICATE_FAMILY_ID", file_path)
    return records


def _load_definitions(path: Path) -> tuple[dict[str, StrategyDefinition], dict[tuple[str, str], StrategyVersion]]:
    definitions = {}
    versions = {}
    for strategy_path in sorted(item for item in path.iterdir() if item.is_dir()):
        data = _load_yaml(strategy_path / "strategy.yaml", _DEFINITION_KEYS)
        definition = StrategyDefinition(
            strategy_definition_id=str(data["strategy_definition_id"]),
            family_id=str(data["family_id"]),
            unique_strategy_code=str(data["unique_strategy_code"]),
            display_name=str(data["display_name"]),
            description=str(data.get("description") or ""),
            product_type=TFISProductType(data["product_type"]),
            supported_underlyings=tuple(data.get("supported_underlyings") or ()),
            policy_composition_ref=str(data["policy_composition_ref"]),
            formula_config_ref=str(data["formula_config_ref"]),
            required_input_capabilities=tuple(data.get("required_input_capabilities") or ()),
            supported_monthly_status_branches=tuple(MonthlyStatus(item) for item in data.get("supported_monthly_status_branches") or ()),
            lifecycle_status=StrategyLifecycleStatus(data["lifecycle_status"]),
            provenance=str(data.get("provenance") or ""),
            source_references=tuple(data.get("source_references") or ()),
        )
        _add_unique(definitions, definition.strategy_definition_id, definition, "DUPLICATE_DEFINITION_ID", strategy_path)
        for version_path in sorted((strategy_path / "versions").glob("*.yaml")):
            version_data = _load_yaml(version_path, _VERSION_KEYS)
            version = StrategyVersion(
                strategy_definition_id=str(version_data["strategy_definition_id"]),
                strategy_version=str(version_data["strategy_version"]),
                effective_from=datetime.fromisoformat(str(version_data["effective_from"])),
                retired_at=(datetime.fromisoformat(str(version_data["retired_at"])) if version_data.get("retired_at") else None),
                configuration_hash=str(version_data["configuration_hash"]),
                formula_hash=str(version_data["formula_hash"]),
                policy_composition_hash=str(version_data["policy_composition_hash"]),
                source_references=tuple(version_data.get("source_references") or ()),
                change_description=str(version_data.get("change_description") or ""),
                status=StrategyVersionStatus(version_data["status"]),
                version_values=version_data.get("version_values") or {},
            )
            _add_unique(versions, (version.strategy_definition_id, version.strategy_version), version, "DUPLICATE_VERSION_ID", version_path)
    return definitions, versions


def _load_instances(path: Path) -> dict[str, StrategyInstanceDefinition]:
    records = {}
    for file_path in sorted(path.glob("*.yaml")):
        data = _load_yaml(file_path, _INSTANCE_KEYS)
        instance = StrategyInstanceDefinition(
            strategy_instance_id=str(data["strategy_instance_id"]),
            strategy_definition_id=str(data["strategy_definition_id"]),
            strategy_version=str(data["strategy_version"]),
            underlying=str(data["underlying"]),
            exchange=str(data["exchange"]),
            segment=Segment(data["segment"]),
            account_ref=str(data["account_ref"]),
            execution_mode=StrategyExecutionMode(data["execution_mode"]),
            enabled=bool(data["enabled"]),
            lot_quantity=int(data["lot_quantity"]),
            capital_allocation_ref=str(data["capital_allocation_ref"]),
            risk_profile_ref=str(data["risk_profile_ref"]),
            schedule_ref=str(data["schedule_ref"]),
            start_date=date.fromisoformat(str(data["start_date"])),
            end_date=(date.fromisoformat(str(data["end_date"])) if data.get("end_date") else None),
            allowed_overrides=tuple(data.get("allowed_overrides") or ()),
            instance_overrides=data.get("instance_overrides") or {},
            instance_configuration_hash=str(data["instance_configuration_hash"]),
        )
        _add_unique(records, instance.strategy_instance_id, instance, "DUPLICATE_INSTANCE_ID", file_path)
    return records


def _load_identity_compositions(path: Path) -> dict[tuple[str, str], StrategyPolicyComposition]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    identity_records = data.get("identity_compositions") or {}
    records = {}
    for key, value in identity_records.items():
        definition_id, version = str(key).split("@", 1)
        records[(definition_id, version)] = StrategyPolicyComposition(
            product_policy=str(value["product_policy"]),
            entry_policy=str(value["entry_policy"]),
            gap_policy=str(value["gap_policy"]),
            missed_entry_policy=str(value["missed_entry_policy"]),
            contract_selection_policy=str(value["contract_selection_policy"]),
            target_policy=str(value["target_policy"]),
            msl_policy=str(value["msl_policy"]),
            optional_policy_stages=value.get("optional_policy_stages") or {},
        )
    return records


_FAMILY_KEYS = {"family_id", "display_name", "product_type", "required_capabilities", "optional_capabilities", "allowed_policy_stages", "family_defaults", "supported_segments", "supported_instruments", "schema_version"}
_DEFINITION_KEYS = {"strategy_definition_id", "family_id", "unique_strategy_code", "display_name", "description", "product_type", "supported_underlyings", "policy_composition_ref", "formula_config_ref", "required_input_capabilities", "supported_monthly_status_branches", "lifecycle_status", "provenance", "source_references"}
_VERSION_KEYS = {"strategy_definition_id", "strategy_version", "effective_from", "retired_at", "configuration_hash", "formula_hash", "policy_composition_hash", "source_references", "change_description", "status", "version_values"}
_INSTANCE_KEYS = {"strategy_instance_id", "strategy_definition_id", "strategy_version", "underlying", "exchange", "segment", "account_ref", "execution_mode", "enabled", "lot_quantity", "capital_allocation_ref", "risk_profile_ref", "schedule_ref", "start_date", "end_date", "allowed_overrides", "instance_overrides", "instance_configuration_hash"}


def _load_yaml(path: Path, allowed_keys: set[str]) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise StrategyConfigurationError((_error("INVALID_CONFIGURATION_SHAPE", path.as_posix(), path.stem, "", "YAML must contain a mapping"),))
    unknown = set(payload) - allowed_keys
    if unknown:
        raise StrategyConfigurationError(tuple(_error("UNKNOWN_CONFIGURATION_KEY", path.as_posix(), path.stem, key, "unknown configuration key") for key in sorted(unknown)))
    missing = allowed_keys - set(payload)
    if missing:
        raise StrategyConfigurationError(tuple(_error("MISSING_MANDATORY_VALUE", path.as_posix(), path.stem, key, "missing mandatory configuration key") for key in sorted(missing)))
    return payload


def _add_unique(records: dict[Any, Any], key: Any, value: Any, code: str, path: Path) -> None:
    if key in records:
        raise StrategyConfigurationError((_error(code, path.as_posix(), str(key), "id", "duplicate identity"),))
    records[key] = value


def _ordered_unique(values: tuple[Any, ...]) -> tuple[Any, ...]:
    return tuple(dict.fromkeys(str(value) for value in values))


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType({str(key): _freeze_value(item) for key, item in sorted(value.items())})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


def _require_text(value: str, field_name: str) -> None:
    if not str(value).strip():
        raise ValueError(f"{field_name} must be non-empty")


def _error(code: str, location: str, identity: str, field: str, message: str) -> StrategyValidationError:
    return StrategyValidationError(code=code, location=location, identity=identity, field=field, message=message)


def _hash_mapping(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(_serializable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


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
    if isinstance(value, date):
        return value.isoformat()
    return value
