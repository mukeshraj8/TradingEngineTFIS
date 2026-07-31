from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

from .position_lifecycle import OfflineLifecycleHandoff, PositionLifecycleContext


class CarriedPositionDayStage(str, Enum):
    POSITION_RECONCILED = "POSITION_RECONCILED"
    TARGET_PROTECTION_ASSESSED = "TARGET_PROTECTION_ASSESSED"
    ORPT_ORIGINAL_SL_ASSESSED = "ORPT_ORIGINAL_SL_ASSESSED"
    RC_REVISED_FSL_ASSESSED = "RC_REVISED_FSL_ASSESSED"
    INTRADAY_LIFECYCLE_READY = "INTRADAY_LIFECYCLE_READY"
    EOD_DECISION_READY = "EOD_DECISION_READY"
    OFFLINE_HANDOFF_READY = "OFFLINE_HANDOFF_READY"
    COMPLETED_OFFLINE = "COMPLETED_OFFLINE"
    BLOCKED = "BLOCKED"


class CarriedPositionIntradayState(str, Enum):
    EXIT_REQUIRED_FROM_OPEN = "EXIT_REQUIRED_FROM_OPEN"
    NORMAL_SL_REQUIRED = "NORMAL_SL_REQUIRED"
    REVISED_FSL_REQUIRED = "REVISED_FSL_REQUIRED"
    WAITING_FOR_AUTHORIZED_OBSERVATION = "WAITING_FOR_AUTHORIZED_OBSERVATION"
    BLOCKED = "BLOCKED"


class CarriedPositionEodOutcome(str, Enum):
    NOT_REACHED_EXIT_REQUIRED_FROM_OPEN = "NOT_REACHED_EXIT_REQUIRED_FROM_OPEN"
    SQUARE_OFF_AT_CMP_REQUIRED = "SQUARE_OFF_AT_CMP_REQUIRED"
    CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL = "CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL"
    RULE_AUTHORITY_UNRESOLVED = "RULE_AUTHORITY_UNRESOLVED"
    NOT_APPLICABLE_BLOCKED = "NOT_APPLICABLE_BLOCKED"


@dataclass(frozen=True, slots=True)
class CarriedPositionDayTransition:
    stage: CarriedPositionDayStage
    timestamp: datetime | None
    reason: str
    artifact_hashes: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_hashes", _freeze(self.artifact_hashes))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class OfflineCarriedPositionEodDecision:
    decision_id: str
    trading_date: date
    strategy_instance_id: str
    position_cycle_id: str | None
    observed_price: float | None
    original_sl: float | None
    option_side: str
    comparison_time: str
    source_rule_id: str
    source_cells: tuple[str, ...]
    workbook_square_off_operator: str
    workbook_carry_forward_operator: str
    effective_carry_forward_operator: str
    equality_outcome: CarriedPositionEodOutcome
    square_off_outcome: CarriedPositionEodOutcome
    carry_forward_outcome: CarriedPositionEodOutcome
    outcome: CarriedPositionEodOutcome
    evidence: Mapping[str, Any] = MappingProxyType({})
    broker_mutation_permitted: bool = False
    paper_mutation_permitted: bool = False
    live_mutation_permitted: bool = False
    decision_hash: str = ""

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("decision_id must be non-empty")
        object.__setattr__(self, "source_cells", tuple(self.source_cells))
        object.__setattr__(self, "evidence", _freeze(self.evidence))
        object.__setattr__(self, "decision_hash", self.decision_hash or carried_position_day_hash(self._business_payload()))

    @property
    def broker_authority(self) -> str:
        return "NONE"

    @property
    def paper_authority(self) -> str:
        return "NONE"

    @property
    def live_authority(self) -> str:
        return "NONE"

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("decision_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class OfflineCarriedPositionTradingDay:
    day_id: str
    trading_date: date
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance_id: str
    configuration_hash: str
    position_cycle_id: str | None
    lifecycle_context: PositionLifecycleContext
    lifecycle_handoff: OfflineLifecycleHandoff
    intraday_state: CarriedPositionIntradayState
    eod_decision: OfflineCarriedPositionEodDecision | None
    terminal_stage: CarriedPositionDayStage
    transition_evidence: tuple[CarriedPositionDayTransition, ...]
    block_code: str | None = None
    block_reason: str | None = None
    policy_identities: Mapping[str, str] = MappingProxyType({})
    broker_mutation_permitted: bool = False
    paper_mutation_permitted: bool = False
    live_mutation_permitted: bool = False
    order_modification_permitted: bool = False
    order_cancellation_permitted: bool = False
    square_off_permitted: bool = False
    position_mutation_permitted: bool = False
    performance: Mapping[str, float | int] = MappingProxyType({})
    day_hash: str = ""

    def __post_init__(self) -> None:
        if not self.day_id.strip():
            raise ValueError("day_id must be non-empty")
        object.__setattr__(self, "transition_evidence", tuple(self.transition_evidence))
        object.__setattr__(self, "policy_identities", _freeze(self.policy_identities))
        object.__setattr__(self, "performance", _freeze(self.performance))
        object.__setattr__(self, "day_hash", self.day_hash or carried_position_day_hash(self._business_payload()))

    @property
    def runtime_authority(self) -> str:
        return "NONE"

    @property
    def broker_authority(self) -> str:
        return "NONE"

    @property
    def paper_authority(self) -> str:
        return "NONE"

    @property
    def live_authority(self) -> str:
        return "NONE"

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("day_hash", None)
        data.pop("performance", None)
        return data


def carried_position_day_hash(value: Mapping[str, Any]) -> str:
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
