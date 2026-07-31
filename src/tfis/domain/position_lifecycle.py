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


class LifecycleOpeningStatus(str, Enum):
    CONTEXT_READY = "CONTEXT_READY"
    PARTIAL_CONTEXT = "PARTIAL_CONTEXT"
    BLOCKED_LIFECYCLE_CONTEXT = "BLOCKED_LIFECYCLE_CONTEXT"
    NORMAL_OPENING_CONTINUATION = "NORMAL_OPENING_CONTINUATION"
    GAP_UP_OBSERVED = "GAP_UP_OBSERVED"
    GAP_DOWN_OBSERVED = "GAP_DOWN_OBSERVED"
    TARGET_CROSSED_AT_OPEN = "TARGET_CROSSED_AT_OPEN"
    PROTECTIVE_LEVEL_CROSSED_AT_OPEN = "PROTECTIVE_LEVEL_CROSSED_AT_OPEN"
    MULTIPLE_LEVELS_CROSSED = "MULTIPLE_LEVELS_CROSSED"
    OPENING_QUOTE_UNAVAILABLE = "OPENING_QUOTE_UNAVAILABLE"
    OPENING_QUOTE_STALE = "OPENING_QUOTE_STALE"
    RULE_AUTHORITY_UNRESOLVED = "RULE_AUTHORITY_UNRESOLVED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class LifecycleActionRequirement(str, Enum):
    CONTINUE_NORMAL_MONITORING = "CONTINUE_NORMAL_MONITORING"
    OPENING_REASSESSMENT_REQUIRED = "OPENING_REASSESSMENT_REQUIRED"
    EXIT_REQUIRED = "EXIT_REQUIRED"
    NORMAL_SL_PLACEMENT_REQUIRED = "NORMAL_SL_PLACEMENT_REQUIRED"
    REVISED_SL_PLACEMENT_REQUIRED = "REVISED_SL_PLACEMENT_REQUIRED"
    IMMEDIATE_EXIT_RULE_REQUIRED = "IMMEDIATE_EXIT_RULE_REQUIRED"
    PROTECTIVE_ORDER_RECONCILIATION_REQUIRED = "PROTECTIVE_ORDER_RECONCILIATION_REQUIRED"
    WAIT_FOR_AUTHORIZED_OBSERVATION = "WAIT_FOR_AUTHORIZED_OBSERVATION"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    BLOCKED_INSUFFICIENT_EVIDENCE = "BLOCKED_INSUFFICIENT_EVIDENCE"
    RULE_AUTHORITY_UNRESOLVED = "RULE_AUTHORITY_UNRESOLVED"


class PositionReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    MISMATCH = "MISMATCH"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


class ProtectiveOrderVisibilityStatus(str, Enum):
    MATCHED = "MATCHED"
    MISSING = "MISSING"
    STALE = "STALE"
    INCORRECT_QUANTITY = "INCORRECT_QUANTITY"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class LifecycleQuoteFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"


class LifecycleGapDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class LifecycleEconomicGapEffect(str, Enum):
    FAVORABLE = "FAVORABLE"
    ADVERSE = "ADVERSE"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class OfflineLifecycleAuthorityMode(str, Enum):
    OFFLINE_ONLY = "OFFLINE_ONLY"


@dataclass(frozen=True, slots=True)
class ReconciledPositionSnapshot:
    reconciliation_id: str
    trading_date: date
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance_id: str
    configuration_hash: str
    position_cycle_id: str
    account_reference: str
    contract: TFISContractIdentity
    product: TFISProductType
    side: TFISExecutionSide
    opened_at: datetime | None
    entry_price: float | None
    local_quantity: int
    external_quantity: int
    reconciled_quantity: int
    reconciliation_status: PositionReconciliationStatus
    partial_exit_state: str = "NONE"
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.reconciliation_id.strip():
            raise ValueError("reconciliation_id must be non-empty")
        if not self.position_cycle_id.strip():
            raise ValueError("position_cycle_id must be non-empty")
        if self.local_quantity < 0 or self.external_quantity < 0 or self.reconciled_quantity < 0:
            raise ValueError("position quantities must be non-negative")
        object.__setattr__(self, "evidence", _freeze(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class LifecycleProtectionState:
    target_levels: Mapping[str, float]
    protective_levels: Mapping[str, float]
    protective_order_status: ProtectiveOrderVisibilityStatus
    lifecycle_recalculation_time: time | None = None
    revised_protective_formula_policy_id: str | None = None
    protective_order_identities: Mapping[str, str] = MappingProxyType({})
    provenance: Mapping[str, Any] = MappingProxyType({})
    unresolved_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_levels", _freeze(self.target_levels))
        object.__setattr__(self, "protective_levels", _freeze(self.protective_levels))
        object.__setattr__(self, "protective_order_identities", _freeze(self.protective_order_identities))
        object.__setattr__(self, "provenance", _freeze(self.provenance))
        object.__setattr__(self, "unresolved_fields", tuple(sorted(self.unresolved_fields)))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class CarriedContractOpeningQuote:
    contract: TFISContractIdentity
    source_timestamp: datetime | None
    ltp: float | None
    high: float | None = None
    low: float | None = None
    bid: float | None = None
    ask: float | None = None
    oi: float | None = None
    prior_reference_price: float | None = None
    freshness: LifecycleQuoteFreshness = LifecycleQuoteFreshness.MISSING
    provenance: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _freeze(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class LifecycleOpeningEvidence:
    evidence_id: str
    trading_date: date
    underlying_opening_snapshot: Mapping[str, Any]
    carried_contract_quote: CarriedContractOpeningQuote | None
    observation_timestamp: datetime | None
    max_quote_age_seconds: int
    orpt_contract_observation: CarriedContractOpeningQuote | None = None
    rc_contract_observation: CarriedContractOpeningQuote | None = None
    shared_underlying_snapshot_permitted: bool = True
    provenance: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must be non-empty")
        if self.max_quote_age_seconds < 0:
            raise ValueError("max_quote_age_seconds must be non-negative")
        object.__setattr__(self, "underlying_opening_snapshot", _freeze(self.underlying_opening_snapshot))
        object.__setattr__(self, "provenance", _freeze(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class LifecycleGapObservation:
    direction: LifecycleGapDirection
    economic_effect: LifecycleEconomicGapEffect
    amount: float | None
    percentage: float | None
    reference_price: float | None
    observed_price: float | None
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", _freeze(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class LifecycleLevelObservation:
    target_crossed: bool
    protective_level_crossed: bool
    crossed_targets: tuple[str, ...] = ()
    crossed_protective_levels: tuple[str, ...] = ()
    comparison_price: float | None = None
    comparison_basis: str | None = None
    rule_authority: str = "OBSERVATION_ONLY"
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "crossed_targets", tuple(sorted(self.crossed_targets)))
        object.__setattr__(self, "crossed_protective_levels", tuple(sorted(self.crossed_protective_levels)))
        object.__setattr__(self, "evidence", _freeze(self.evidence))

    @property
    def any_level_crossed(self) -> bool:
        return self.target_crossed or self.protective_level_crossed

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class LifecycleContextFailure:
    code: str
    field: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class PositionLifecycleContext:
    context_id: str
    schema_version: str
    trading_date: date
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance_id: str
    configuration_hash: str
    position_snapshot: ReconciledPositionSnapshot | None
    protection_state: LifecycleProtectionState | None
    opening_evidence: LifecycleOpeningEvidence | None
    opening_status: LifecycleOpeningStatus
    action_requirement: LifecycleActionRequirement
    gap_observation: LifecycleGapObservation
    level_observation: LifecycleLevelObservation
    missing_fields: tuple[str, ...] = ()
    stale_fields: tuple[str, ...] = ()
    unresolved_rule_authorities: tuple[str, ...] = ()
    failures: tuple[LifecycleContextFailure, ...] = ()
    policy_identities: Mapping[str, str] = MappingProxyType({})
    evidence: Mapping[str, Any] = MappingProxyType({})
    performance: Mapping[str, float | int] = MappingProxyType({})
    context_hash: str = ""

    def __post_init__(self) -> None:
        if not self.context_id.strip():
            raise ValueError("context_id must be non-empty")
        object.__setattr__(self, "missing_fields", tuple(sorted(self.missing_fields)))
        object.__setattr__(self, "stale_fields", tuple(sorted(self.stale_fields)))
        object.__setattr__(self, "unresolved_rule_authorities", tuple(sorted(self.unresolved_rule_authorities)))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "policy_identities", _freeze(self.policy_identities))
        object.__setattr__(self, "evidence", _freeze(self.evidence))
        object.__setattr__(self, "performance", _freeze(self.performance))
        object.__setattr__(self, "context_hash", self.context_hash or position_lifecycle_hash(self._business_payload()))

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
        data.pop("context_hash", None)
        data.pop("performance", None)
        return data


@dataclass(frozen=True, slots=True)
class OfflineLifecycleHandoff:
    handoff_id: str
    trading_date: date
    strategy_instance_id: str
    position_cycle_id: str | None
    lifecycle_context_id: str
    lifecycle_context_hash: str
    opening_status: LifecycleOpeningStatus
    action_requirement: LifecycleActionRequirement
    authority_mode: OfflineLifecycleAuthorityMode
    broker_mutation_permitted: bool = False
    paper_mutation_permitted: bool = False
    live_mutation_permitted: bool = False
    order_modification_permitted: bool = False
    order_cancellation_permitted: bool = False
    square_off_permitted: bool = False
    position_mutation_permitted: bool = False
    evidence_hash: str = ""

    def __post_init__(self) -> None:
        if not self.handoff_id.strip():
            raise ValueError("handoff_id must be non-empty")
        object.__setattr__(self, "evidence_hash", self.evidence_hash or position_lifecycle_hash(self._business_payload()))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)

    def to_json(self) -> str:
        return _canonical_json(self)

    def _business_payload(self) -> dict[str, Any]:
        data = self.to_dict()
        data.pop("evidence_hash", None)
        return data


def build_offline_lifecycle_handoff(context: PositionLifecycleContext, handoff_id: str | None = None) -> OfflineLifecycleHandoff:
    return OfflineLifecycleHandoff(
        handoff_id=handoff_id or f"{context.context_id}:offline-lifecycle-handoff",
        trading_date=context.trading_date,
        strategy_instance_id=context.strategy_instance_id,
        position_cycle_id=context.position_snapshot.position_cycle_id if context.position_snapshot else None,
        lifecycle_context_id=context.context_id,
        lifecycle_context_hash=context.context_hash,
        opening_status=context.opening_status,
        action_requirement=context.action_requirement,
        authority_mode=OfflineLifecycleAuthorityMode.OFFLINE_ONLY,
    )


def position_lifecycle_hash(value: Mapping[str, Any]) -> str:
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
