from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from tfis.persistence import canonical_hash


SCHEMA_VERSION = "phase4e.execution_intent.v1"


class ExecutionAuthorityMode(str, Enum):
    OFFLINE_ONLY = "OFFLINE_ONLY"
    SHADOW_ONLY = "SHADOW_ONLY"
    VALIDATED_NOT_SUBMITTABLE = "VALIDATED_NOT_SUBMITTABLE"


class ExecutionIntentPurpose(str, Enum):
    ENTRY = "ENTRY"
    TARGET = "TARGET"
    ORIGINAL_SL = "ORIGINAL_SL"
    REVISED_SL = "REVISED_SL"
    EOD_EXIT = "EOD_EXIT"
    RISK_EXIT = "RISK_EXIT"
    OPERATOR_EXIT = "OPERATOR_EXIT"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    TSL = "TSL"
    FSL = "FSL"
    TRP = "TRP"
    EXPIRY_EXIT = "EXPIRY_EXIT"


SUPPORTED_PHASE4E_PURPOSES = frozenset(
    {
        ExecutionIntentPurpose.ENTRY,
        ExecutionIntentPurpose.TARGET,
        ExecutionIntentPurpose.ORIGINAL_SL,
        ExecutionIntentPurpose.REVISED_SL,
        ExecutionIntentPurpose.EOD_EXIT,
        ExecutionIntentPurpose.RISK_EXIT,
        ExecutionIntentPurpose.OPERATOR_EXIT,
    }
)


class IntentValidationDecision(str, Enum):
    VALIDATED_NOT_SUBMITTABLE = "VALIDATED_NOT_SUBMITTABLE"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DUPLICATE = "DUPLICATE"
    EXPIRED = "EXPIRED"


class RiskCheckStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    REJECT = "REJECT"
    BLOCK = "BLOCK"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DUPLICATE = "DUPLICATE"
    EXPIRED = "EXPIRED"


class RiskSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class ExecutionInstrument:
    exchange: str
    segment: str
    product: str
    underlying: str
    contract: str
    expiry: date | None
    strike: Decimal | None
    option_type: str | None
    lot_size: int
    tick_size: Decimal
    multiplier: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if self.multiplier <= 0:
            raise ValueError("multiplier must be positive")

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class RequestedExecutionAction:
    purpose: ExecutionIntentPurpose
    side: str
    requested_quantity: int
    quantity_unit: str
    order_type: str
    limit_price: Decimal | None
    trigger_price: Decimal | None
    time_in_force: str
    authorized_not_before: datetime
    authorized_not_after: datetime | None = None
    maximum_allowed_slippage: Decimal | None = None
    protection_generation: int | None = None

    def __post_init__(self) -> None:
        if self.purpose not in SUPPORTED_PHASE4E_PURPOSES:
            raise ValueError(f"Phase 4E does not produce purpose: {self.purpose.value}")

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class ExecutionIntentEvidence:
    source_rule_ids: tuple[str, ...]
    configuration_hash: str
    rule_matrix_version: str
    market_snapshot_hash: str
    reconciliation_result_id: str
    reconciliation_result_hash: str
    recovery_assessment_id: str
    recovery_assessment_hash: str
    evidence_packet_hash: str
    provenance: Mapping[str, Any]
    authority_mode: ExecutionAuthorityMode

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_rule_ids", tuple(self.source_rule_ids))
        object.__setattr__(self, "provenance", _freeze(self.provenance))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class ExecutionIntent:
    execution_intent_id: str
    schema_version: str
    trading_session_id: str
    trading_date: date
    strategy_family_id: str
    strategy_definition_id: str
    strategy_version: str
    strategy_instance_id: str
    broker_account_id: str
    position_cycle_id: str | None
    source_artifact_type: str
    source_artifact_id: str
    source_artifact_hash: str
    idempotency_key: str
    instrument: ExecutionInstrument
    action: RequestedExecutionAction
    evidence: ExecutionIntentEvidence
    broker_submission_permitted: bool = False
    paper_submission_permitted: bool = False
    live_submission_permitted: bool = False
    order_creation_permitted: bool = False
    position_mutation_permitted: bool = False
    intent_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported ExecutionIntent schema_version: {self.schema_version}")
        if self.action.purpose in {
            ExecutionIntentPurpose.TARGET,
            ExecutionIntentPurpose.ORIGINAL_SL,
            ExecutionIntentPurpose.REVISED_SL,
            ExecutionIntentPurpose.EOD_EXIT,
            ExecutionIntentPurpose.RISK_EXIT,
            ExecutionIntentPurpose.OPERATOR_EXIT,
        } and not self.position_cycle_id:
            raise ValueError("Lifecycle/exit intents require position_cycle_id")
        for forbidden in (
            self.broker_submission_permitted,
            self.paper_submission_permitted,
            self.live_submission_permitted,
            self.order_creation_permitted,
            self.position_mutation_permitted,
        ):
            if forbidden:
                raise ValueError("Phase 4E ExecutionIntent cannot grant execution authority")
        object.__setattr__(self, "intent_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self)
        if not include_hash:
            data.pop("intent_hash", None)
        return data


@dataclass(frozen=True, slots=True)
class RiskEvidence:
    evidence_id: str
    evidence_hash: str
    source: str
    details: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", _freeze(self.details))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class RiskFailure:
    code: str
    reason: str
    check_id: str
    evidence_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class RiskWarning:
    code: str
    reason: str
    check_id: str
    evidence_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class RiskCheckResult:
    check_id: str
    scope: str
    input: Mapping[str, Any]
    threshold_config: Mapping[str, Any]
    observed_value: Mapping[str, Any]
    result: RiskCheckStatus
    severity: RiskSeverity
    source: str
    evidence: RiskEvidence

    def __post_init__(self) -> None:
        object.__setattr__(self, "input", _freeze(self.input))
        object.__setattr__(self, "threshold_config", _freeze(self.threshold_config))
        object.__setattr__(self, "observed_value", _freeze(self.observed_value))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class AccountControlSnapshot:
    account_enabled: bool
    environment: str
    required_environment: str
    session_available: bool
    funds_evidence_available: bool
    margin_evidence_available: bool
    account_blocked: bool
    kill_switch_active: bool
    active_orders: int
    max_active_orders: int
    active_positions: int
    max_active_positions: int
    daily_loss_gate_blocked: bool
    broker_read_age_seconds: int
    max_broker_read_age_seconds: int


@dataclass(frozen=True, slots=True)
class StrategyControlSnapshot:
    strategy_enabled: bool
    expected_strategy_version: str
    configuration_hash: str
    expected_configuration_hash: str
    rule_matrix_version: str
    expected_rule_matrix_version: str
    assigned_account_id: str
    allowed_products: tuple[str, ...]
    allowed_underlyings: tuple[str, ...]
    allowed_contract_types: tuple[str, ...]
    max_active_fresh_entry_cycles: int
    active_fresh_entry_cycles: int
    configured_quantity: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_products", tuple(self.allowed_products))
        object.__setattr__(self, "allowed_underlyings", tuple(self.allowed_underlyings))
        object.__setattr__(self, "allowed_contract_types", tuple(self.allowed_contract_types))


@dataclass(frozen=True, slots=True)
class PortfolioControlSnapshot:
    global_new_entry_enabled: bool
    global_kill_switch: bool
    max_total_active_positions: int
    total_active_positions: int
    max_total_active_orders: int
    total_active_orders: int
    global_daily_loss_blocked: bool
    data_degraded_global_block: bool
    kill_switch_action: str | None = None


@dataclass(frozen=True, slots=True)
class PositionProtectionSnapshot:
    position_cycle_id: str | None
    broker_confirmed_remaining_quantity: int | None
    position_status: str | None
    active_protection_generation: int | None
    required_next_generation: int | None
    duplicate_active_sl: bool = False
    target_and_sl_can_coexist: bool = True
    superseded_requirement_id: str | None = None


@dataclass(frozen=True, slots=True)
class MarketDataQualitySnapshot:
    context_hash: str
    trading_date: date
    contract: str
    source_age_seconds: int
    max_age_seconds: int
    timestamp_skew_seconds: int
    max_timestamp_skew_seconds: int
    has_bid: bool
    has_ask: bool
    has_ltp: bool
    oi_required: bool
    has_oi: bool
    quality: str


@dataclass(frozen=True, slots=True)
class DuplicateActionSnapshot:
    existing_intent_hash: str | None = None
    existing_payload_hash: str | None = None
    same_idempotency_payload_hash: str | None = None
    old_generation_seen: bool = False


@dataclass(frozen=True, slots=True)
class RiskValidationInput:
    validation_id: str
    intent: ExecutionIntent
    evaluated_at: datetime
    recovery_status: str
    recovery_assessment_hash: str
    reconciliation_gate: str
    reconciliation_blocking_classifications: tuple[str, ...]
    account: AccountControlSnapshot
    strategy: StrategyControlSnapshot
    portfolio: PortfolioControlSnapshot
    market_data: MarketDataQualitySnapshot
    position: PositionProtectionSnapshot
    duplicate: DuplicateActionSnapshot = DuplicateActionSnapshot()
    source_artifact_available: bool = True
    source_hash_matches: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "reconciliation_blocking_classifications", tuple(self.reconciliation_blocking_classifications))

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class RiskValidationResult:
    validation_id: str
    execution_intent_id: str
    intent_hash: str
    decision: IntentValidationDecision
    checks: tuple[RiskCheckResult, ...]
    failures: tuple[RiskFailure, ...]
    warnings: tuple[RiskWarning, ...]
    authority_mode: ExecutionAuthorityMode
    broker_submission_permitted: bool = False
    paper_submission_permitted: bool = False
    live_submission_permitted: bool = False
    order_creation_permitted: bool = False
    position_mutation_permitted: bool = False
    result_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "failures", tuple(self.failures))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        for forbidden in (
            self.broker_submission_permitted,
            self.paper_submission_permitted,
            self.live_submission_permitted,
            self.order_creation_permitted,
            self.position_mutation_permitted,
        ):
            if forbidden:
                raise ValueError("Phase 4E validation cannot grant execution authority")
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
