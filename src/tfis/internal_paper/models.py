from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from tfis.persistence import canonical_hash


class AccountCoordinatorEnvironment(str, Enum):
    INTERNAL_PAPER_ONLY = "INTERNAL_PAPER_ONLY"
    LIVE = "LIVE"
    BROKER_SANDBOX = "BROKER_SANDBOX"
    BROKER_PAPER = "BROKER_PAPER"


class InternalPaperAuthority(str, Enum):
    INTERNAL_PAPER_ORDER_SIMULATION_ONLY = "INTERNAL_PAPER_ORDER_SIMULATION_ONLY"


class ClientOrderAuthority(str, Enum):
    INTERNAL_PAPER_ONLY = "INTERNAL_PAPER_ONLY"


class InternalPaperOrderState(str, Enum):
    CREATED = "CREATED"
    VALIDATION_PENDING = "VALIDATION_PENDING"
    READY_FOR_INTERNAL_PAPER = "READY_FOR_INTERNAL_PAPER"
    SUBMISSION_PENDING_INTERNAL = "SUBMISSION_PENDING_INTERNAL"
    ACKNOWLEDGED_INTERNAL = "ACKNOWLEDGED_INTERNAL"
    PARTIALLY_FILLED_INTERNAL = "PARTIALLY_FILLED_INTERNAL"
    FILLED_INTERNAL = "FILLED_INTERNAL"
    REJECTED_INTERNAL = "REJECTED_INTERNAL"
    CANCEL_PENDING_INTERNAL = "CANCEL_PENDING_INTERNAL"
    CANCELLED_INTERNAL = "CANCELLED_INTERNAL"
    EXPIRED_INTERNAL = "EXPIRED_INTERNAL"
    UNKNOWN_INTERNAL_REVIEW_REQUIRED = "UNKNOWN_INTERNAL_REVIEW_REQUIRED"
    TERMINAL_ERROR = "TERMINAL_ERROR"


class InternalPaperOrderEventType(str, Enum):
    CLIENT_ORDER_CREATED = "CLIENT_ORDER_CREATED"
    INTERNAL_SUBMISSION_ACCEPTED = "INTERNAL_SUBMISSION_ACCEPTED"
    INTERNAL_SUBMISSION_REJECTED = "INTERNAL_SUBMISSION_REJECTED"
    INTERNAL_PARTIAL_FILL = "INTERNAL_PARTIAL_FILL"
    INTERNAL_FULL_FILL = "INTERNAL_FULL_FILL"
    INTERNAL_CANCEL_REQUESTED = "INTERNAL_CANCEL_REQUESTED"
    INTERNAL_CANCELLED = "INTERNAL_CANCELLED"
    INTERNAL_EXPIRED = "INTERNAL_EXPIRED"


class InternalPaperExecutionScenario(str, Enum):
    IMMEDIATE_FULL_FILL = "IMMEDIATE_FULL_FILL"
    ACK_THEN_FULL_FILL = "ACK_THEN_FULL_FILL"
    PARTIAL_THEN_FULL_FILL = "PARTIAL_THEN_FULL_FILL"
    PARTIAL_REMAINS_OPEN = "PARTIAL_REMAINS_OPEN"
    REJECTED_INSUFFICIENT_PAPER_MARGIN = "REJECTED_INSUFFICIENT_PAPER_MARGIN"
    REJECTED_INVALID_PRICE = "REJECTED_INVALID_PRICE"
    NO_FILL_BEFORE_EXPIRY = "NO_FILL_BEFORE_EXPIRY"
    CANCEL_BEFORE_FILL = "CANCEL_BEFORE_FILL"
    FILL_BEFORE_CANCEL_CONFIRMATION = "FILL_BEFORE_CANCEL_CONFIRMATION"
    DUPLICATE_EVENT_REPLAY = "DUPLICATE_EVENT_REPLAY"


class InternalPaperRecoveryStatus(str, Enum):
    INTERNAL_PAPER_RECOVERABLE = "INTERNAL_PAPER_RECOVERABLE"
    INTERNAL_PAPER_PARTIAL = "INTERNAL_PAPER_PARTIAL"
    INTERNAL_PAPER_REVIEW_REQUIRED = "INTERNAL_PAPER_REVIEW_REQUIRED"
    INTERNAL_PAPER_BLOCKED = "INTERNAL_PAPER_BLOCKED"


class InternalPaperConsistencyStatus(str, Enum):
    MATCHED = "MATCHED"
    PARTIAL = "PARTIAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class AccountCoordinatorIdentity:
    account_coordinator_id: str
    broker_account_id: str
    logical_account_reference: str
    trading_session_id: str
    environment: AccountCoordinatorEnvironment
    configuration_hash: str
    coordinator_version: str
    coordinator_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.environment is not AccountCoordinatorEnvironment.INTERNAL_PAPER_ONLY:
            raise ValueError("Phase 4F only supports INTERNAL_PAPER_ONLY.")
        object.__setattr__(self, "coordinator_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("coordinator_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class InternalPaperAuthorityGrant:
    grant_id: str
    broker_account_id: str
    trading_session_id: str
    strategy_instance_id: str
    allowed_intent_purposes: tuple[str, ...]
    maximum_quantity: int
    valid_from: datetime
    valid_until: datetime
    configuration_hash: str
    rule_version: str
    issued_by: str
    reason: str
    authority: InternalPaperAuthority = InternalPaperAuthority.INTERNAL_PAPER_ORDER_SIMULATION_ONLY
    live_broker_submission_permitted: bool = False
    broker_sandbox_submission_permitted: bool = False
    external_paper_submission_permitted: bool = False
    real_position_mutation_permitted: bool = False
    real_funds_mutation_permitted: bool = False
    grant_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_intent_purposes", tuple(self.allowed_intent_purposes))
        if self.maximum_quantity <= 0:
            raise ValueError("maximum_quantity must be positive")
        if any((self.live_broker_submission_permitted, self.broker_sandbox_submission_permitted, self.external_paper_submission_permitted, self.real_position_mutation_permitted, self.real_funds_mutation_permitted)):
            raise ValueError("Internal paper grants cannot permit external authority.")
        object.__setattr__(self, "grant_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("grant_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class SimulatedPaperAccountSnapshot:
    broker_account_id: str
    opening_paper_cash: Decimal
    reserved_margin: Decimal
    released_margin: Decimal
    available_paper_margin: Decimal
    simulated_charges: Decimal
    active_order_reservation: Decimal
    margin_per_quantity: Decimal
    account_enabled: bool = True
    account_blocked: bool = False
    active_order_count: int = 0
    max_active_order_count: int = 10

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class ClientOrder:
    client_order_id: str
    execution_intent_id: str
    account_coordinator_id: str
    broker_account_id: str
    strategy_instance_id: str
    trading_session_id: str
    position_cycle_id: str | None
    idempotency_key: str
    normalized_contract: str
    side: str
    quantity: int
    order_purpose: str
    order_type: str
    limit_price: Decimal | None
    trigger_price: Decimal | None
    time_in_force: str
    authorized_time: datetime
    protection_generation: int | None
    source_intent_hash: str
    authority: ClientOrderAuthority = ClientOrderAuthority.INTERNAL_PAPER_ONLY
    broker_submission_permitted: bool = False
    live_submission_permitted: bool = False
    order_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("ClientOrder quantity must be positive.")
        if self.broker_submission_permitted or self.live_submission_permitted:
            raise ValueError("ClientOrder cannot permit broker/live submission.")
        object.__setattr__(self, "order_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("order_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class InternalPaperOrderEvent:
    event_id: str
    client_order_id: str
    broker_account_id: str
    sequence: int
    previous_state: InternalPaperOrderState | None
    new_state: InternalPaperOrderState
    event_type: InternalPaperOrderEventType
    event_timestamp: datetime
    simulated_exchange_timestamp: datetime
    quantity_delta: int
    cumulative_filled_quantity: int
    fill_price: Decimal | None
    reason: str
    scenario_id: str
    provenance: Mapping[str, Any] = MappingProxyType({})
    authority_source: str = "INTERNAL_PAPER_SIMULATION"
    event_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "event_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("event_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class InternalPaperFill:
    internal_fill_id: str
    client_order_id: str
    broker_account_id: str
    strategy_instance_id: str
    position_cycle_id: str | None
    contract: str
    side: str
    fill_quantity: int
    fill_price: Decimal
    simulated_exchange_timestamp: datetime
    recorded_timestamp: datetime
    scenario_id: str
    provenance: Mapping[str, Any] = MappingProxyType({})
    fill_classification: str = "INTERNAL_PAPER_SIMULATED_FILL"
    fill_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.fill_quantity <= 0:
            raise ValueError("fill_quantity must be positive")
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "fill_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("fill_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class DeterministicMarketEvidence:
    bid: Decimal | None
    ask: Decimal | None
    ltp: Decimal | None
    high: Decimal | None
    low: Decimal | None
    source_timestamp: datetime
    snapshot_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class DeterministicExecutionScenarioDefinition:
    scenario_id: str
    scenario: InternalPaperExecutionScenario
    market_evidence: DeterministicMarketEvidence
    event_time: datetime
    fill_quantity: int | None = None
    fill_price: Decimal | None = None
    rejection_reason: str | None = None
    cancel_reason: str | None = None
    deterministic_seed: str | None = None
    scenario_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("scenario_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class PositionCycleUpdateCandidate:
    candidate_id: str
    source_fill_id: str
    position_cycle_id: str | None
    quantity_delta: int
    fill_price: Decimal
    suggested_state_impact: str
    authority_mode: str = "INTERNAL_PAPER_ONLY"
    update_permitted: bool = False
    candidate_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.update_permitted:
            raise ValueError("Phase 4F cannot mutate PositionCycle.")
        object.__setattr__(self, "candidate_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("candidate_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class InternalPaperAdapterResult:
    client_order: ClientOrder
    final_state: InternalPaperOrderState
    events: tuple[InternalPaperOrderEvent, ...]
    fills: tuple[InternalPaperFill, ...]
    position_update_candidates: tuple[PositionCycleUpdateCandidate, ...]
    account_snapshot: SimulatedPaperAccountSnapshot
    result_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "fills", tuple(self.fills))
        object.__setattr__(self, "position_update_candidates", tuple(self.position_update_candidates))
        object.__setattr__(self, "result_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("result_hash", None)
        return data


def _freeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))})
    if isinstance(value, tuple | list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return tuple(_freeze(item) for item in sorted(value, key=str))
    return value


def _serializable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if is_dataclass(value):
        result: dict[str, Any] = {}
        for item in fields(value):
            try:
                result[item.name] = _serializable(getattr(value, item.name))
            except AttributeError:
                continue
        return result
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_serializable(item) for item in value]
    return value
