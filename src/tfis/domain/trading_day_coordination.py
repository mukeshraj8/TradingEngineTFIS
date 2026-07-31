from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

from .runtime_contracts import TFISContractIdentity, TFISExecutionSide


class TradingDayCoordinationState(str, Enum):
    DISABLED = "DISABLED"
    BLOCKED_CONFIGURATION = "BLOCKED_CONFIGURATION"
    PREPARING_PREMARKET_PLAN = "PREPARING_PREMARKET_PLAN"
    PREMARKET_PLAN_PREPARED = "PREMARKET_PLAN_PREPARED"
    AWAITING_MARKET_OPEN = "AWAITING_MARKET_OPEN"
    OPENING_CONTEXT_BUILDING = "OPENING_CONTEXT_BUILDING"
    OPENING_CONTEXT_READY = "OPENING_CONTEXT_READY"
    AWAITING_NORMAL_ORPT = "AWAITING_NORMAL_ORPT"
    AWAITING_RECALCULATION = "AWAITING_RECALCULATION"
    EFFECTIVE_PLAN_READY = "EFFECTIVE_PLAN_READY"
    OFFLINE_HANDOFF_READY = "OFFLINE_HANDOFF_READY"
    BLOCKED = "BLOCKED"
    NO_ACTION_TODAY = "NO_ACTION_TODAY"
    CARRIED_POSITION_HANDOFF_REQUIRED = "CARRIED_POSITION_HANDOFF_REQUIRED"
    COMPLETED_OFFLINE = "COMPLETED_OFFLINE"


class TradingDayPath(str, Enum):
    NORMAL_FRESH_ENTRY = "NORMAL_FRESH_ENTRY"
    GAP_RECALCULATION = "GAP_RECALCULATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CARRIED_POSITION = "CARRIED_POSITION"
    BLOCKED = "BLOCKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CoordinationEventType(str, Enum):
    STARTUP_COMPLETED = "STARTUP_COMPLETED"
    PREMARKET_DATA_READY = "PREMARKET_DATA_READY"
    MARKET_OPEN_OBSERVED = "MARKET_OPEN_OBSERVED"
    ORPT_REACHED = "ORPT_REACHED"
    RC_REACHED = "RC_REACHED"
    OFFLINE_HANDOFF_REQUESTED = "OFFLINE_HANDOFF_REQUESTED"
    OPERATOR_CANCELLED = "OPERATOR_CANCELLED"
    RISK_CANCELLED = "RISK_CANCELLED"
    SESSION_ENDED = "SESSION_ENDED"
    POSITION_RECONCILIATION_RESULT = "POSITION_RECONCILIATION_RESULT"


class OfflineHandoffAuthorityMode(str, Enum):
    OFFLINE_ONLY = "OFFLINE_ONLY"


@dataclass(frozen=True, slots=True)
class OfflineCoordinationEvent:
    event_id: str
    strategy_instance_id: str
    trading_date: date
    event_type: CoordinationEventType
    effective_timestamp: datetime
    source_timestamp: datetime
    source_classification: str
    provenance: Mapping[str, str]
    sequence_identity: int
    instrument: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        object.__setattr__(self, "provenance", _freeze(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class CoordinationTransitionEvidence:
    from_state: TradingDayCoordinationState
    event_type: CoordinationEventType | None
    to_state: TradingDayCoordinationState
    reason: str
    artifact_hashes: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_hashes", _freeze(self.artifact_hashes))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class CoordinationFailure:
    state: TradingDayCoordinationState
    event_id: str | None
    code: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class OfflineExecutionHandoff:
    handoff_id: str
    trading_date: date
    strategy_instance_id: str
    effective_execution_plan_id: str
    effective_execution_plan_hash: str
    selected_contract: TFISContractIdentity | None
    order_side: TFISExecutionSide | None
    quantity: int | None
    lots: int | None
    effective_entry: float | None
    effective_target: float | None
    effective_msl: float | None
    authorized_placement_time: time | None
    order_type: str | None
    authority_mode: OfflineHandoffAuthorityMode
    broker_submission_permitted: bool = False
    paper_submission_permitted: bool = False
    live_submission_permitted: bool = False
    position_mutation_permitted: bool = False
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        if not self.handoff_id.strip():
            raise ValueError("handoff_id must be non-empty")
        object.__setattr__(self, "evidence_hash", self.evidence_hash or trading_day_coordination_hash(self._business_payload()))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("evidence_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class TradingDayCoordinationResult:
    coordination_id: str
    schema_version: str
    trading_date: date
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance_id: str
    configuration_hash: str
    daily_path: TradingDayPath
    current_state: TradingDayCoordinationState
    terminal_state: TradingDayCoordinationState | None
    fresh_entry_eligible: bool
    carried_position_status: str
    block_code: str | None
    block_reason: str | None
    premarket_plan_id: str | None
    premarket_plan_hash: str | None
    opening_context_id: str | None
    opening_context_hash: str | None
    effective_execution_plan_id: str | None
    effective_execution_plan_hash: str | None
    execution_handoff_id: str | None
    startup_event_id: str | None
    premarket_completion_event_id: str | None
    market_open_event_id: str | None
    orpt_event_id: str | None
    rc_event_id: str | None
    effective_plan_ready_event_id: str | None
    offline_handoff_event_id: str | None
    transition_evidence: tuple[CoordinationTransitionEvidence, ...] = ()
    missing_events: tuple[str, ...] = ()
    derived_fields: tuple[str, ...] = ()
    supplemented_fields: tuple[str, ...] = ()
    policy_identities: Mapping[str, str] = MappingProxyType({})
    failures: tuple[CoordinationFailure, ...] = ()
    offline_handoff: OfflineExecutionHandoff | None = None
    performance: Mapping[str, float | int] = MappingProxyType({})
    coordination_hash: str = ""

    def __post_init__(self) -> None:
        if not self.coordination_id.strip():
            raise ValueError("coordination_id must be non-empty")
        object.__setattr__(self, "transition_evidence", tuple(self.transition_evidence))
        object.__setattr__(self, "missing_events", tuple(self.missing_events))
        object.__setattr__(self, "derived_fields", tuple(self.derived_fields))
        object.__setattr__(self, "supplemented_fields", tuple(self.supplemented_fields))
        object.__setattr__(self, "policy_identities", _freeze(self.policy_identities))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "performance", _freeze(self.performance))
        object.__setattr__(self, "coordination_hash", self.coordination_hash or trading_day_coordination_hash(self._business_payload()))

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
        data.pop("coordination_hash", None)
        data.pop("performance", None)
        return data


def trading_day_coordination_hash(value: Mapping[str, Any]) -> str:
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
