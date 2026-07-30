from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

from .enums import MonthlyStatus
from .runtime_contracts import (
    TFISContractIdentity,
    TFISDirection,
    TFISExecutionSide,
    TFISProductType,
)


class PreMarketPlanStatus(str, Enum):
    PREPARING = "PREPARING"
    PREPARED = "PREPARED"
    BLOCKED_PREMARKET = "BLOCKED_PREMARKET"
    NO_ACTION_TODAY = "NO_ACTION_TODAY"


class PreMarketFieldProvenance(str, Enum):
    LEGACY_CONFIG = "LEGACY_CONFIG"
    WORKBOOK_NORMALIZED = "WORKBOOK_NORMALIZED"
    LEGACY_FIXTURE = "LEGACY_FIXTURE"
    SYNTHETIC_SUPPLEMENT = "SYNTHETIC_SUPPLEMENT"
    DERIVED = "DERIVED"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class PreMarketPlanFailure:
    stage: str
    code: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class PreMarketReferenceSet:
    underlying: Mapping[str, Any] = MappingProxyType({})
    selected_contract: Mapping[str, Any] = MappingProxyType({})
    provenance: Mapping[str, str] = MappingProxyType({})
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "underlying", _freeze(self.underlying))
        object.__setattr__(self, "selected_contract", _freeze(self.selected_contract))
        object.__setattr__(self, "provenance", _freeze(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class PreMarketContractResolution:
    expiry_candidates: tuple[date, ...] = ()
    strike_candidates: tuple[float, ...] = ()
    selected_expiry: date | None = None
    selected_strike: float | None = None
    selected_contract: TFISContractIdentity | None = None
    premium: float | None = None
    oi: float | None = None
    oi_unit: str | None = None
    qualification_evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "expiry_candidates", tuple(self.expiry_candidates))
        object.__setattr__(self, "strike_candidates", tuple(self.strike_candidates))
        object.__setattr__(self, "qualification_evidence", _freeze(self.qualification_evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class PreMarketPlannedValues:
    base_entry: float | None = None
    preliminary_target: float | None = None
    preliminary_msl: float | None = None
    order_side: TFISExecutionSide | None = None
    position_intent: str | None = None
    direction: TFISDirection | None = None
    quantity: int | None = None
    lots: int | None = None
    normal_orpt: time | None = None
    rc_time: time | None = None
    policy_identities: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_identities", _freeze(self.policy_identities))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class PreMarketStrategyPlan:
    plan_id: str
    plan_version: str
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance_id: str
    resolved_configuration_hash: str
    trading_date: date
    enabled: bool
    fresh_entry_eligible: bool
    plan_status: PreMarketPlanStatus
    block_code: str | None
    block_reason: str | None
    monthly_status: MonthlyStatus | None
    resolved_branch: str | None
    product: TFISProductType | None
    underlying_instrument: str | None
    references: PreMarketReferenceSet
    contract_resolution: PreMarketContractResolution
    planned_values: PreMarketPlannedValues
    stage_evidence: Mapping[str, Any] = MappingProxyType({})
    missing_fields: tuple[str, ...] = ()
    derived_fields: tuple[str, ...] = ()
    supplemented_fields: tuple[str, ...] = ()
    field_provenance: Mapping[str, str] = MappingProxyType({})
    failures: tuple[PreMarketPlanFailure, ...] = ()
    business_hash: str = ""
    plan_hash: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must be a non-empty string")
        if not self.strategy_family.strip():
            raise ValueError("strategy_family must be a non-empty string")
        if not self.strategy_definition.strip():
            raise ValueError("strategy_definition must be a non-empty string")
        if not self.strategy_instance_id.strip():
            raise ValueError("strategy_instance_id must be a non-empty string")
        object.__setattr__(self, "stage_evidence", _freeze(self.stage_evidence))
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        object.__setattr__(self, "derived_fields", tuple(self.derived_fields))
        object.__setattr__(self, "supplemented_fields", tuple(self.supplemented_fields))
        object.__setattr__(self, "field_provenance", _freeze(self.field_provenance))
        object.__setattr__(self, "failures", tuple(self.failures))
        business_hash = self.business_hash or _hash(self._business_payload())
        object.__setattr__(self, "business_hash", business_hash)
        object.__setattr__(self, "plan_hash", self.plan_hash or business_hash)

    @property
    def execution_permission(self) -> str:
        return "NONE"

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def comparison_key(self) -> str:
        return self.to_json()

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("business_hash", None)
        data.pop("plan_hash", None)
        return data


def premarket_plan_hash(payload: Mapping[str, Any]) -> str:
    return _hash(payload)


def _hash(payload: Any) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(_serializable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _freeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze(item) for item in sorted(value, key=str))
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
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value
