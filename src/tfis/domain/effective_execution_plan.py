from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

from .runtime_contracts import TFISContractIdentity, TFISExecutionSide, TFISProductType


class EffectiveExecutionPlanStatus(str, Enum):
    READY_OFFLINE = "READY_OFFLINE"
    BLOCKED = "BLOCKED"
    NO_TRADE = "NO_TRADE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    SUPERSEDED = "SUPERSEDED"


class EffectiveExecutionPath(str, Enum):
    NORMAL_RETAINED = "NORMAL_RETAINED"
    GAP_RETAINED = "GAP_RETAINED"
    GAP_RECALCULATED = "GAP_RECALCULATED"
    ABNORMAL_RECALCULATED = "ABNORMAL_RECALCULATED"
    BLOCKED_OPENING_VALIDATION = "BLOCKED_OPENING_VALIDATION"
    BLOCKED_GAP_EVALUATION = "BLOCKED_GAP_EVALUATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EffectiveRiskValueStatus(str, Enum):
    RETAINED_FROM_PREMARKET = "RETAINED_FROM_PREMARKET"
    RECALCULATED = "RECALCULATED"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    RULE_AUTHORITY_UNRESOLVED = "RULE_AUTHORITY_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class EffectiveExecutionFailure:
    stage: str
    code: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class EffectiveExecutionValues:
    base_entry: float | None
    effective_entry: float | None
    preliminary_target: float | None
    effective_target: float | None
    preliminary_msl: float | None
    effective_msl: float | None
    normal_orpt: time | None
    revised_authorized_time: time | None
    order_type: str | None
    target_status: EffectiveRiskValueStatus
    msl_status: EffectiveRiskValueStatus

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class EffectiveExecutionPlan:
    execution_plan_id: str
    schema_version: str
    trading_date: date
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance_id: str
    source_premarket_plan_id: str
    source_premarket_plan_hash: str
    source_opening_context_id: str
    source_opening_context_hash: str
    plan_revision: int
    supersedes_plan_id: str | None
    plan_status: EffectiveExecutionPlanStatus
    path_classification: EffectiveExecutionPath
    final_eligibility: str
    block_code: str | None
    block_reason: str | None
    downstream_execution_permission: str
    offline_execution_candidate: bool
    product: TFISProductType | None
    underlying: str | None
    selected_expiry: date | None
    selected_strike: float | None
    selected_contract: TFISContractIdentity | None
    order_side: TFISExecutionSide | None
    position_intent: str | None
    quantity: int | None
    lots: int | None
    values: EffectiveExecutionValues
    opening_gap_classification: str | None
    gap_missed_entry_applicability: str
    gap_missed_entry_status: str | None
    recalculation_required: bool
    recalculation_inputs: Mapping[str, Any] = MappingProxyType({})
    recalculation_output: Mapping[str, Any] = MappingProxyType({})
    retain_recalculate_block_reason: str | None = None
    policy_identities: Mapping[str, str] = MappingProxyType({})
    stage_evidence: Mapping[str, Any] = MappingProxyType({})
    missing_fields: tuple[str, ...] = ()
    derived_fields: tuple[str, ...] = ()
    supplemented_fields: tuple[str, ...] = ()
    failures: tuple[EffectiveExecutionFailure, ...] = ()
    performance: Mapping[str, float | int] = MappingProxyType({})
    execution_plan_hash: str = ""

    def __post_init__(self) -> None:
        if not self.execution_plan_id.strip():
            raise ValueError("execution_plan_id must be non-empty")
        object.__setattr__(self, "recalculation_inputs", _freeze(self.recalculation_inputs))
        object.__setattr__(self, "recalculation_output", _freeze(self.recalculation_output))
        object.__setattr__(self, "policy_identities", _freeze(self.policy_identities))
        object.__setattr__(self, "stage_evidence", _freeze(self.stage_evidence))
        object.__setattr__(self, "missing_fields", tuple(self.missing_fields))
        object.__setattr__(self, "derived_fields", tuple(self.derived_fields))
        object.__setattr__(self, "supplemented_fields", tuple(self.supplemented_fields))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "performance", _freeze(self.performance))
        object.__setattr__(self, "execution_plan_hash", self.execution_plan_hash or effective_execution_plan_hash(self._business_payload()))

    @property
    def runtime_authority(self) -> str:
        return "NONE"

    @property
    def lifecycle_action(self) -> str:
        return "NONE"

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("execution_plan_hash", None)
        data.pop("performance", None)
        return data


def effective_execution_plan_hash(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


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
    if isinstance(value, Decimal):
        return str(value)
    return value
