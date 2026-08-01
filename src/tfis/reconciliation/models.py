from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from tfis.persistence import canonical_hash


class TruthCategory(str, Enum):
    LOCAL_EXPECTED_STATE = "LOCAL_EXPECTED_STATE"
    BROKER_OBSERVED_STATE = "BROKER_OBSERVED_STATE"
    RECONCILED_STATE = "RECONCILED_STATE"


class ReconciliationScope(str, Enum):
    STARTUP_ACCOUNT = "STARTUP_ACCOUNT"
    PROCESS_RESTART = "PROCESS_RESTART"
    PRE_ENTRY_SAFETY = "PRE_ENTRY_SAFETY"
    PERIODIC_INTRADAY = "PERIODIC_INTRADAY"
    POST_ORDER_TIMEOUT = "POST_ORDER_TIMEOUT"
    POST_RECONNECT = "POST_RECONNECT"
    POST_PARTIAL_FILL = "POST_PARTIAL_FILL"
    POST_CANCEL_REPLACE = "POST_CANCEL_REPLACE"
    CARRIED_POSITION_STARTUP = "CARRIED_POSITION_STARTUP"
    PRE_EOD = "PRE_EOD"
    EOD_FINAL = "EOD_FINAL"


class ReconciliationClassification(str, Enum):
    MATCHED = "MATCHED"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    BROKER_STATE_UNAVAILABLE = "BROKER_STATE_UNAVAILABLE"
    LOCAL_STATE_UNAVAILABLE = "LOCAL_STATE_UNAVAILABLE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    BROKER_ONLY_ORDER = "BROKER_ONLY_ORDER"
    LOCAL_ONLY_ORDER = "LOCAL_ONLY_ORDER"
    ORDER_IDENTITY_MISMATCH = "ORDER_IDENTITY_MISMATCH"
    ORDER_STATUS_MISMATCH = "ORDER_STATUS_MISMATCH"
    ORDER_QUANTITY_MISMATCH = "ORDER_QUANTITY_MISMATCH"
    ORDER_PRICE_MISMATCH = "ORDER_PRICE_MISMATCH"
    UNKNOWN_BROKER_ORDER = "UNKNOWN_BROKER_ORDER"
    DUPLICATE_BROKER_ORDER = "DUPLICATE_BROKER_ORDER"
    STALE_LOCAL_ORDER = "STALE_LOCAL_ORDER"
    STALE_BROKER_ORDER = "STALE_BROKER_ORDER"
    BROKER_ONLY_FILL = "BROKER_ONLY_FILL"
    LOCAL_ONLY_FILL = "LOCAL_ONLY_FILL"
    FILL_QUANTITY_MISMATCH = "FILL_QUANTITY_MISMATCH"
    FILL_PRICE_MISMATCH = "FILL_PRICE_MISMATCH"
    DUPLICATE_FILL = "DUPLICATE_FILL"
    PARTIAL_FILL_MISMATCH = "PARTIAL_FILL_MISMATCH"
    BROKER_ONLY_POSITION = "BROKER_ONLY_POSITION"
    LOCAL_ONLY_POSITION = "LOCAL_ONLY_POSITION"
    POSITION_QUANTITY_MISMATCH = "POSITION_QUANTITY_MISMATCH"
    POSITION_DIRECTION_MISMATCH = "POSITION_DIRECTION_MISMATCH"
    POSITION_CONTRACT_MISMATCH = "POSITION_CONTRACT_MISMATCH"
    AVERAGE_PRICE_MISMATCH = "AVERAGE_PRICE_MISMATCH"
    LOCAL_CLOSED_BROKER_OPEN = "LOCAL_CLOSED_BROKER_OPEN"
    BROKER_CLOSED_LOCAL_OPEN = "BROKER_CLOSED_LOCAL_OPEN"
    PROTECTION_MATCHED = "PROTECTION_MATCHED"
    PROTECTION_MISSING = "PROTECTION_MISSING"
    DUPLICATE_PROTECTION = "DUPLICATE_PROTECTION"
    STALE_PROTECTION = "STALE_PROTECTION"
    PROTECTION_QUANTITY_MISMATCH = "PROTECTION_QUANTITY_MISMATCH"
    PROTECTION_PRICE_MISMATCH = "PROTECTION_PRICE_MISMATCH"
    PROTECTION_GENERATION_MISMATCH = "PROTECTION_GENERATION_MISMATCH"
    UNKNOWN_PROTECTION_LINKAGE = "UNKNOWN_PROTECTION_LINKAGE"
    UNKNOWN_LINKAGE = "UNKNOWN_LINKAGE"


class RepairRecommendationCode(str, Enum):
    LINK_BROKER_ORDER_ID = "LINK_BROKER_ORDER_ID"
    INGEST_MISSING_BROKER_FILL = "INGEST_MISSING_BROKER_FILL"
    UPDATE_LOCAL_ORDER_STATUS = "UPDATE_LOCAL_ORDER_STATUS"
    UPDATE_LOCAL_POSITION_QUANTITY = "UPDATE_LOCAL_POSITION_QUANTITY"
    MARK_LOCAL_POSITION_CLOSED = "MARK_LOCAL_POSITION_CLOSED"
    CREATE_UNLINKED_BROKER_POSITION_CASE = "CREATE_UNLINKED_BROKER_POSITION_CASE"
    SUPERSEDE_STALE_PROTECTION_PROJECTION = "SUPERSEDE_STALE_PROTECTION_PROJECTION"
    REBUILD_POSITION_PROJECTION = "REBUILD_POSITION_PROJECTION"
    NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
    BLOCK_NEW_ENTRY = "BLOCK_NEW_ENTRY"
    ALLOW_LIFECYCLE_ONLY = "ALLOW_LIFECYCLE_ONLY"
    REQUIRE_OPERATOR_REVIEW = "REQUIRE_OPERATOR_REVIEW"
    REQUIRE_BROKER_REFRESH = "REQUIRE_BROKER_REFRESH"
    REQUIRE_PROTECTION_REVIEW = "REQUIRE_PROTECTION_REVIEW"
    REQUIRE_ACCOUNT_HALT = "REQUIRE_ACCOUNT_HALT"
    FUTURE_CANCEL_DUPLICATE_ORDER = "FUTURE_CANCEL_DUPLICATE_ORDER"
    FUTURE_PLACE_MISSING_PROTECTION = "FUTURE_PLACE_MISSING_PROTECTION"
    FUTURE_REPLACE_STALE_PROTECTION = "FUTURE_REPLACE_STALE_PROTECTION"
    FUTURE_EXIT_UNKNOWN_POSITION = "FUTURE_EXIT_UNKNOWN_POSITION"


class AuthorityGateRecommendation(str, Enum):
    SHADOW_READY = "SHADOW_READY"
    READ_ONLY_READY = "READ_ONLY_READY"
    NEW_ENTRY_ELIGIBLE_AFTER_FUTURE_APPROVAL = "NEW_ENTRY_ELIGIBLE_AFTER_FUTURE_APPROVAL"
    LIFECYCLE_ONLY = "LIFECYCLE_ONLY"
    NEW_ENTRY_BLOCKED = "NEW_ENTRY_BLOCKED"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"


class AccountReadinessStatus(str, Enum):
    RECONCILED_READY = "RECONCILED_READY"
    RECONCILED_PARTIAL = "RECONCILED_PARTIAL"
    READ_ONLY_SAFE = "READ_ONLY_SAFE"
    NEW_ENTRY_BLOCKED = "NEW_ENTRY_BLOCKED"
    LIFECYCLE_ONLY = "LIFECYCLE_ONLY"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class LocalExpectedOrder:
    local_order_id: str
    broker_account_id: str
    normalized_contract: str
    side: str
    quantity: int
    status: str
    purpose: str
    client_order_id: str | None = None
    broker_order_id: str | None = None
    exchange_order_id: str | None = None
    correlation_id: str | None = None
    limit_price: float | None = None
    trigger_price: float | None = None
    filled_quantity: int = 0
    protection_generation: int | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BrokerObservedOrder:
    broker_order_id: str
    broker_account_id: str
    normalized_contract: str
    side: str
    quantity: int
    status: str
    purpose: str | None = None
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    correlation_id: str | None = None
    limit_price: float | None = None
    trigger_price: float | None = None
    filled_quantity: int = 0
    protection_generation: int | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LocalExpectedFill:
    fill_id: str
    local_order_id: str
    broker_account_id: str
    normalized_contract: str
    side: str
    quantity: int
    price: float
    broker_order_id: str | None = None
    exchange_fill_id: str | None = None
    filled_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BrokerObservedFill:
    fill_id: str
    broker_account_id: str
    normalized_contract: str
    side: str
    quantity: int
    price: float
    broker_order_id: str | None = None
    exchange_fill_id: str | None = None
    filled_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LocalExpectedPosition:
    position_cycle_id: str
    broker_account_id: str
    normalized_contract: str
    net_quantity: int
    side: str
    product_type: str
    status: str
    average_price: float | None = None
    carry_type: str | None = None
    strategy_instance_id: str | None = None
    previous_day_quantity: int | None = None


@dataclass(frozen=True, slots=True)
class BrokerObservedPosition:
    broker_account_id: str
    normalized_contract: str
    net_quantity: int
    side: str
    product_type: str
    average_price: float | None = None
    carry_type: str | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LocalExpectedProtection:
    protection_id: str
    position_cycle_id: str
    broker_account_id: str
    normalized_contract: str
    protection_type: str
    side: str
    quantity: int
    price: float
    generation: int
    status: str = "ACTIVE"


@dataclass(frozen=True, slots=True)
class RepairRecommendation:
    code: RepairRecommendationCode
    item_id: str
    reason: str
    execution_not_permitted: bool = True

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class ReconciliationItem:
    item_id: str
    item_type: str
    classification: ReconciliationClassification
    financial_risk: str
    local_reference: Mapping[str, Any] | None
    broker_reference: Mapping[str, Any] | None
    manual_review_required: bool
    blocks_new_entry: bool
    allows_lifecycle_only: bool
    recommendations: tuple[RepairRecommendation, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class AuthorityGateDecision:
    recommendation: AuthorityGateRecommendation
    blocking_reasons: tuple[str, ...]
    manual_review_required: bool
    evidence_hashes: Mapping[str, str]
    grants_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class ReconciliationInput:
    reconciliation_id: str
    broker_account_id: str
    trading_session_id: str
    scope: ReconciliationScope
    as_of: datetime
    local_state_version: int
    broker_snapshot_hash: str
    reconciliation_policy_version: str
    account_payload: Mapping[str, Any]
    local_orders: tuple[LocalExpectedOrder, ...] = ()
    broker_orders: tuple[BrokerObservedOrder, ...] = ()
    local_fills: tuple[LocalExpectedFill, ...] = ()
    broker_fills: tuple[BrokerObservedFill, ...] = ()
    local_positions: tuple[LocalExpectedPosition, ...] = ()
    broker_positions: tuple[BrokerObservedPosition, ...] = ()
    local_protections: tuple[LocalExpectedProtection, ...] = ()
    recovery_status: str = "RECOVERABLE_OFFLINE"

    def to_dict(self) -> dict[str, Any]:
        return _serializable(self)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    reconciliation_id: str
    broker_account_id: str
    trading_session_id: str
    scope: ReconciliationScope
    as_of: datetime
    local_state_version: int
    broker_snapshot_hash: str
    reconciliation_policy_version: str
    account_status: AccountReadinessStatus
    order_status: ReconciliationClassification
    fill_status: ReconciliationClassification
    position_status: ReconciliationClassification
    protection_status: ReconciliationClassification
    carried_position_status: ReconciliationClassification
    authority_gate: AuthorityGateDecision
    items: tuple[ReconciliationItem, ...]
    repair_recommendations: tuple[RepairRecommendation, ...]
    manual_review_required: bool
    result_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = _serializable(self, include_hash=include_hash)
        if not include_hash:
            data.pop("result_hash", None)
        return data


def _serializable(value: Any, *, include_hash: bool = True) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        data = {}
        for dataclass_field in fields(value):
            try:
                data[dataclass_field.name] = getattr(value, dataclass_field.name)
            except AttributeError:
                continue
        if not include_hash:
            data.pop("result_hash", None)
        return {key: _serializable(item, include_hash=include_hash) for key, item in data.items()}
    if isinstance(value, tuple | list):
        return [_serializable(item, include_hash=include_hash) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _serializable(item, include_hash=include_hash) for key, item in value.items()}
    return value
