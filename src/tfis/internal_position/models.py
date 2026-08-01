from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from tfis.persistence import canonical_hash


class InternalPaperPositionState(str, Enum):
    PLANNED = "PLANNED"
    ENTRY_PARTIALLY_FILLED = "ENTRY_PARTIALLY_FILLED"
    OPEN_UNPROTECTED = "OPEN_UNPROTECTED"
    OPEN_PROTECTION_PENDING = "OPEN_PROTECTION_PENDING"
    OPEN_PROTECTED = "OPEN_PROTECTED"
    PARTIALLY_EXITED = "PARTIALLY_EXITED"
    EXIT_PENDING = "EXIT_PENDING"
    CARRIED_FORWARD = "CARRIED_FORWARD"
    CLOSED = "CLOSED"
    CANCELLED_BEFORE_ENTRY = "CANCELLED_BEFORE_ENTRY"
    INTERNAL_REVIEW_REQUIRED = "INTERNAL_REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    TERMINAL_ERROR = "TERMINAL_ERROR"


class InternalPaperPositionEventType(str, Enum):
    POSITION_CYCLE_RESERVED = "POSITION_CYCLE_RESERVED"
    POSITION_OPENED = "POSITION_OPENED"
    ENTRY_PARTIAL_FILL_APPLIED = "ENTRY_PARTIAL_FILL_APPLIED"
    ENTRY_FULL_FILL_APPLIED = "ENTRY_FULL_FILL_APPLIED"
    PROTECTION_REQUIRED = "PROTECTION_REQUIRED"
    PROTECTION_ORDER_LINKED = "PROTECTION_ORDER_LINKED"
    PROTECTION_RESIZE_REQUIRED = "PROTECTION_RESIZE_REQUIRED"
    PROTECTION_SUPERSEDED = "PROTECTION_SUPERSEDED"
    PARTIAL_EXIT_APPLIED = "PARTIAL_EXIT_APPLIED"
    TARGET_EXIT_APPLIED = "TARGET_EXIT_APPLIED"
    SL_EXIT_APPLIED = "SL_EXIT_APPLIED"
    EOD_EXIT_APPLIED = "EOD_EXIT_APPLIED"
    CARRY_FORWARD_RECORDED = "CARRY_FORWARD_RECORDED"
    POSITION_CLOSED = "POSITION_CLOSED"
    INTERNAL_REVIEW_REQUIRED = "INTERNAL_REVIEW_REQUIRED"


class LifecycleRequirementType(str, Enum):
    TARGET_EXIT_REQUIRED = "TARGET_EXIT_REQUIRED"
    NORMAL_SL_PLACEMENT_REQUIRED = "NORMAL_SL_PLACEMENT_REQUIRED"
    REVISED_SL_PLACEMENT_REQUIRED = "REVISED_SL_PLACEMENT_REQUIRED"
    EOD_SQUARE_OFF_REQUIRED = "EOD_SQUARE_OFF_REQUIRED"
    EOD_CARRY_FORWARD_REQUIRED = "EOD_CARRY_FORWARD_REQUIRED"


class ProtectionModel(str, Enum):
    APPLICATION_MANAGED_LINKED_PROTECTION = "APPLICATION_MANAGED_LINKED_PROTECTION"


class CarriedPositionRecoveryStatus(str, Enum):
    CARRIED_POSITION_RECOVERABLE = "CARRIED_POSITION_RECOVERABLE"
    CARRIED_POSITION_PARTIAL = "CARRIED_POSITION_PARTIAL"
    CARRIED_POSITION_REVIEW_REQUIRED = "CARRIED_POSITION_REVIEW_REQUIRED"
    CARRIED_POSITION_BLOCKED = "CARRIED_POSITION_BLOCKED"


class InternalPaperPositionConsistencyStatus(str, Enum):
    MATCHED = "MATCHED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class InternalPaperPositionCycleIdentity:
    position_cycle_id: str
    trading_session_id: str
    originating_trading_date: date
    broker_account_id: str
    logical_account_reference: str
    strategy_family_id: str
    strategy_definition_id: str
    strategy_version: str
    strategy_instance_id: str
    originating_execution_plan_id: str
    originating_entry_execution_intent_id: str
    normalized_contract: str
    direction: str
    side: str
    authority_classification: str = "INTERNAL_PAPER_ONLY"
    external_broker_position: bool = False
    live_position: bool = False
    broker_reconciliation_authority: bool = False
    position_cycle_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.authority_classification != "INTERNAL_PAPER_ONLY":
            raise ValueError("Only INTERNAL_PAPER_ONLY position cycles are supported.")
        if self.external_broker_position or self.live_position or self.broker_reconciliation_authority:
            raise ValueError("Internal paper position cycles cannot carry external authority.")
        object.__setattr__(self, "position_cycle_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("position_cycle_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class LifecycleRequirement:
    requirement_id: str
    position_cycle_id: str
    requirement_type: LifecycleRequirementType
    quantity: int
    side: str
    price: Decimal | None
    source_rule_ids: tuple[str, ...]
    source_artifact_id: str
    source_artifact_hash: str
    protection_generation: int | None
    created_at: datetime
    status: str = "REQUIRED"
    protection_model: ProtectionModel = ProtectionModel.APPLICATION_MANAGED_LINKED_PROTECTION
    requirement_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Lifecycle requirement quantity must be positive.")
        object.__setattr__(self, "source_rule_ids", tuple(self.source_rule_ids))
        object.__setattr__(self, "requirement_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("requirement_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class ProtectionOrderReference:
    position_cycle_id: str
    order_purpose: str
    protection_generation: int
    client_order_id: str
    requirement_id: str
    quantity: int
    status: str = "ACTIVE"
    reference_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Protection reference quantity must be positive.")
        object.__setattr__(self, "reference_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("reference_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class InternalPaperPositionEvent:
    event_id: str
    position_cycle_id: str
    event_sequence: int
    event_type: InternalPaperPositionEventType
    prior_state: InternalPaperPositionState | None
    new_state: InternalPaperPositionState
    quantity_before: int
    quantity_after: int
    price_evidence: Mapping[str, Any]
    source_fill_id: str | None
    source_client_order_id: str | None
    source_requirement_id: str | None
    rule_ids: tuple[str, ...]
    event_timestamp: datetime
    event_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "price_evidence", _freeze(self.price_evidence))
        object.__setattr__(self, "rule_ids", tuple(self.rule_ids))
        object.__setattr__(self, "event_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("event_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class InternalPaperPositionCycleProjection:
    identity: InternalPaperPositionCycleIdentity
    lifecycle_state: InternalPaperPositionState
    confirmed_entry_quantity: int
    remaining_quantity: int
    realized_quantity: int
    average_entry_price: Decimal | None
    average_exit_price: Decimal | None
    entry_fill_ids: tuple[str, ...]
    exit_fill_ids: tuple[str, ...]
    active_target: ProtectionOrderReference | None = None
    active_original_sl: ProtectionOrderReference | None = None
    active_revised_sl: ProtectionOrderReference | None = None
    active_order_references: tuple[ProtectionOrderReference, ...] = ()
    superseded_protections: tuple[ProtectionOrderReference, ...] = ()
    cancelled_protections: tuple[ProtectionOrderReference, ...] = ()
    filled_exit_order_id: str | None = None
    protection_generation: int = 0
    carry_forward_status: str | None = None
    terminal_status: str | None = None
    multiplier: Decimal = Decimal("1")
    lot_size: int = 1
    currency: str = "INR"
    originating_trading_date: date | None = None
    next_trading_session_id: str | None = None
    projection_version: int = 1
    projection_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.confirmed_entry_quantity < 0 or self.remaining_quantity < 0 or self.realized_quantity < 0:
            raise ValueError("Position quantities cannot be negative.")
        if self.realized_quantity + self.remaining_quantity != self.confirmed_entry_quantity:
            raise ValueError("Realized plus remaining quantity must equal confirmed entry quantity.")
        if self.multiplier <= 0 or self.lot_size <= 0:
            raise ValueError("Multiplier and lot size must be positive.")
        object.__setattr__(self, "entry_fill_ids", tuple(self.entry_fill_ids))
        object.__setattr__(self, "exit_fill_ids", tuple(self.exit_fill_ids))
        object.__setattr__(self, "active_order_references", tuple(self.active_order_references))
        object.__setattr__(self, "superseded_protections", tuple(self.superseded_protections))
        object.__setattr__(self, "cancelled_protections", tuple(self.cancelled_protections))
        if self.originating_trading_date is None:
            object.__setattr__(self, "originating_trading_date", self.identity.originating_trading_date)
        object.__setattr__(self, "projection_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("projection_hash", None)
        return data

    @classmethod
    def planned(cls, identity: InternalPaperPositionCycleIdentity) -> "InternalPaperPositionCycleProjection":
        return cls(
            identity=identity,
            lifecycle_state=InternalPaperPositionState.PLANNED,
            confirmed_entry_quantity=0,
            remaining_quantity=0,
            realized_quantity=0,
            average_entry_price=None,
            average_exit_price=None,
            entry_fill_ids=(),
            exit_fill_ids=(),
        )


@dataclass(frozen=True, slots=True)
class InternalPaperPositionTransition:
    transition_id: str
    projection: InternalPaperPositionCycleProjection
    event: InternalPaperPositionEvent
    requirements: tuple[LifecycleRequirement, ...] = ()
    consistency_status: str = "MATCHED"
    transition_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirements", tuple(self.requirements))
        object.__setattr__(self, "transition_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("transition_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class InternalPaperPositionConsistencyAssessment:
    assessment_id: str
    status: InternalPaperPositionConsistencyStatus
    findings: tuple[str, ...]
    projection_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class InternalPaperCarriedRecoveryAssessment:
    assessment_id: str
    status: CarriedPositionRecoveryStatus
    position_cycle_id: str
    findings: tuple[str, ...]
    recovery_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "recovery_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("recovery_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class PnlInputFacts:
    position_cycle_id: str
    side: str
    multiplier: Decimal
    lot_size: int
    currency: str
    entry_fill_ids: tuple[str, ...]
    exit_fill_ids: tuple[str, ...]
    average_entry_price: Decimal | None
    average_exit_price: Decimal | None
    realized_quantity: int
    remaining_quantity: int
    exit_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


def with_projection_version(projection: InternalPaperPositionCycleProjection, version: int) -> InternalPaperPositionCycleProjection:
    return replace(projection, projection_version=version)


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
    if isinstance(value, datetime | date):
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
