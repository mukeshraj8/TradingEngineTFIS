from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable

from tfis.persistence import canonical_hash

from .models import (
    AccountReadinessStatus,
    AuthorityGateDecision,
    AuthorityGateRecommendation,
    BrokerObservedFill,
    BrokerObservedOrder,
    BrokerObservedPosition,
    LocalExpectedFill,
    LocalExpectedOrder,
    LocalExpectedPosition,
    LocalExpectedProtection,
    ReconciliationClassification,
    ReconciliationInput,
    ReconciliationItem,
    ReconciliationResult,
    ReconciliationScope,
    RepairRecommendation,
    RepairRecommendationCode,
)


_BLOCKING = {
    ReconciliationClassification.BROKER_STATE_UNAVAILABLE,
    ReconciliationClassification.MANUAL_REVIEW_REQUIRED,
    ReconciliationClassification.BROKER_ONLY_ORDER,
    ReconciliationClassification.LOCAL_ONLY_ORDER,
    ReconciliationClassification.ORDER_IDENTITY_MISMATCH,
    ReconciliationClassification.ORDER_QUANTITY_MISMATCH,
    ReconciliationClassification.UNKNOWN_BROKER_ORDER,
    ReconciliationClassification.DUPLICATE_BROKER_ORDER,
    ReconciliationClassification.BROKER_ONLY_FILL,
    ReconciliationClassification.LOCAL_ONLY_FILL,
    ReconciliationClassification.DUPLICATE_FILL,
    ReconciliationClassification.BROKER_ONLY_POSITION,
    ReconciliationClassification.LOCAL_ONLY_POSITION,
    ReconciliationClassification.POSITION_QUANTITY_MISMATCH,
    ReconciliationClassification.POSITION_DIRECTION_MISMATCH,
    ReconciliationClassification.POSITION_CONTRACT_MISMATCH,
    ReconciliationClassification.LOCAL_CLOSED_BROKER_OPEN,
    ReconciliationClassification.BROKER_CLOSED_LOCAL_OPEN,
    ReconciliationClassification.PROTECTION_MISSING,
    ReconciliationClassification.DUPLICATE_PROTECTION,
    ReconciliationClassification.STALE_PROTECTION,
    ReconciliationClassification.PROTECTION_QUANTITY_MISMATCH,
    ReconciliationClassification.PROTECTION_PRICE_MISMATCH,
    ReconciliationClassification.PROTECTION_GENERATION_MISMATCH,
    ReconciliationClassification.UNKNOWN_PROTECTION_LINKAGE,
    ReconciliationClassification.UNKNOWN_LINKAGE,
}


class ReconciliationEngine:
    def reconcile(self, reconciliation_input: ReconciliationInput) -> ReconciliationResult:
        items: list[ReconciliationItem] = []
        items.extend(_account_items(reconciliation_input))
        items.extend(_order_items(reconciliation_input))
        items.extend(_fill_items(reconciliation_input))
        items.extend(_position_items(reconciliation_input))
        items.extend(_protection_items(reconciliation_input))
        recommendations = tuple(item for rec_item in items for item in rec_item.recommendations)
        account_status = _account_status(items, reconciliation_input)
        gate = _authority_gate(items, account_status, reconciliation_input)
        return ReconciliationResult(
            reconciliation_id=reconciliation_input.reconciliation_id,
            broker_account_id=reconciliation_input.broker_account_id,
            trading_session_id=reconciliation_input.trading_session_id,
            scope=reconciliation_input.scope,
            as_of=reconciliation_input.as_of,
            local_state_version=reconciliation_input.local_state_version,
            broker_snapshot_hash=reconciliation_input.broker_snapshot_hash,
            reconciliation_policy_version=reconciliation_input.reconciliation_policy_version,
            account_status=account_status,
            order_status=_summary_status(items, "ORDER"),
            fill_status=_summary_status(items, "FILL"),
            position_status=_summary_status(items, "POSITION"),
            protection_status=_summary_status(items, "PROTECTION"),
            carried_position_status=_carried_status(items, reconciliation_input),
            authority_gate=gate,
            items=tuple(items),
            repair_recommendations=recommendations,
            manual_review_required=any(item.manual_review_required for item in items),
        )


def _account_items(reconciliation_input: ReconciliationInput) -> tuple[ReconciliationItem, ...]:
    payload = reconciliation_input.account_payload
    items: list[ReconciliationItem] = []
    if reconciliation_input.recovery_status not in {"RECOVERABLE_OFFLINE", "RECONCILIATION_REQUIRED"}:
        items.append(_item("account:recovery", "ACCOUNT", ReconciliationClassification.BROKER_STATE_UNAVAILABLE, "Recovery status blocks reconciliation.", None, payload, RepairRecommendationCode.REQUIRE_ACCOUNT_HALT))
    if payload.get("broker_account_id") not in {None, reconciliation_input.broker_account_id}:
        items.append(_item("account:identity", "ACCOUNT", ReconciliationClassification.MANUAL_REVIEW_REQUIRED, "Broker account identity mismatch.", {"broker_account_id": reconciliation_input.broker_account_id}, payload, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
    if payload.get("session_status") in {"UNAUTHORIZED", "EXPIRED"}:
        items.append(_item("account:session", "ACCOUNT", ReconciliationClassification.BROKER_STATE_UNAVAILABLE, "Broker read session unavailable.", None, payload, RepairRecommendationCode.REQUIRE_BROKER_REFRESH))
    if payload.get("completeness") in {"PARTIAL", "UNAVAILABLE"}:
        items.append(_item("account:partial", "ACCOUNT", ReconciliationClassification.INSUFFICIENT_EVIDENCE, "Broker snapshot is incomplete.", None, payload, RepairRecommendationCode.REQUIRE_BROKER_REFRESH))
    captured_at = payload.get("captured_at")
    if isinstance(captured_at, datetime) and reconciliation_input.as_of - captured_at > timedelta(minutes=5):
        items.append(_item("account:stale", "ACCOUNT", ReconciliationClassification.STALE_BROKER_ORDER, "Broker snapshot is stale for readiness.", None, payload, RepairRecommendationCode.REQUIRE_BROKER_REFRESH))
    if not items:
        items.append(_item("account:matched", "ACCOUNT", ReconciliationClassification.MATCHED, "Account identity and snapshot availability matched.", payload, payload, RepairRecommendationCode.NO_ACTION_REQUIRED))
    return tuple(items)


def _order_items(reconciliation_input: ReconciliationInput) -> tuple[ReconciliationItem, ...]:
    items: list[ReconciliationItem] = []
    local_by_key = _index_orders(reconciliation_input.local_orders)
    broker_by_key = _index_orders(reconciliation_input.broker_orders)
    broker_id_counts = Counter(order.broker_order_id for order in reconciliation_input.broker_orders if order.broker_order_id)
    for broker_id, count in broker_id_counts.items():
        if count > 1:
            items.append(_item(f"order:duplicate:{broker_id}", "ORDER", ReconciliationClassification.DUPLICATE_BROKER_ORDER, "Duplicate broker order id observed.", None, {"broker_order_id": broker_id}, RepairRecommendationCode.FUTURE_CANCEL_DUPLICATE_ORDER))
    matched_local: set[str] = set()
    matched_broker: set[str] = set()
    for local in reconciliation_input.local_orders:
        broker = _find_order_match(local, reconciliation_input.broker_orders, broker_by_key)
        if broker is None:
            if local.status == "INTENT_RESERVED":
                items.append(_item(f"order:{local.local_order_id}:reserved", "ORDER", ReconciliationClassification.MATCHED, "Local intent reserved; no broker order expected yet.", local, None, RepairRecommendationCode.NO_ACTION_REQUIRED))
            else:
                items.append(_item(f"order:{local.local_order_id}:local_only", "ORDER", ReconciliationClassification.LOCAL_ONLY_ORDER, "Local submitted/active order has no broker observation.", local, None, RepairRecommendationCode.BLOCK_NEW_ENTRY))
            continue
        matched_local.add(local.local_order_id)
        matched_broker.add(broker.broker_order_id)
        items.extend(_compare_order(local, broker))
    for broker in reconciliation_input.broker_orders:
        if broker.broker_order_id in matched_broker:
            continue
        if not _has_strong_order_linkage(broker):
            items.append(_item(f"order:{broker.broker_order_id}:unknown_linkage", "ORDER", ReconciliationClassification.UNKNOWN_LINKAGE, "Broker order has no deterministic client/exchange/correlation linkage.", None, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
        else:
            items.append(_item(f"order:{broker.broker_order_id}:broker_only", "ORDER", ReconciliationClassification.BROKER_ONLY_ORDER, "Broker order is unknown locally.", None, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
    return tuple(items)


def _fill_items(reconciliation_input: ReconciliationInput) -> tuple[ReconciliationItem, ...]:
    items: list[ReconciliationItem] = []
    seen = Counter(fill.fill_id or fill.exchange_fill_id for fill in reconciliation_input.broker_fills)
    for fill_id, count in seen.items():
        if fill_id and count > 1:
            items.append(_item(f"fill:duplicate:{fill_id}", "FILL", ReconciliationClassification.DUPLICATE_FILL, "Duplicate broker fill identity observed.", None, {"fill_id": fill_id}, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
    matched_broker: set[str] = set()
    for local in reconciliation_input.local_fills:
        broker = _find_fill_match(local, reconciliation_input.broker_fills)
        if broker is None:
            items.append(_item(f"fill:{local.fill_id}:local_only", "FILL", ReconciliationClassification.LOCAL_ONLY_FILL, "Local fill has no broker fill observation.", local, None, RepairRecommendationCode.REQUIRE_BROKER_REFRESH))
            continue
        matched_broker.add(broker.fill_id)
        if local.quantity != broker.quantity:
            items.append(_item(f"fill:{local.fill_id}:quantity", "FILL", ReconciliationClassification.FILL_QUANTITY_MISMATCH, "Fill quantities differ.", local, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
        elif abs(local.price - broker.price) > 0.05:
            items.append(_item(f"fill:{local.fill_id}:price", "FILL", ReconciliationClassification.FILL_PRICE_MISMATCH, "Fill prices differ.", local, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
        else:
            items.append(_item(f"fill:{local.fill_id}:matched", "FILL", ReconciliationClassification.MATCHED, "Fill identity, quantity and price matched.", local, broker, RepairRecommendationCode.NO_ACTION_REQUIRED))
    for broker in reconciliation_input.broker_fills:
        if broker.fill_id not in matched_broker:
            items.append(_item(f"fill:{broker.fill_id}:broker_only", "FILL", ReconciliationClassification.BROKER_ONLY_FILL, "Broker fill is missing locally.", None, broker, RepairRecommendationCode.INGEST_MISSING_BROKER_FILL))
    if not reconciliation_input.local_fills and not reconciliation_input.broker_fills:
        items.append(_item("fill:empty", "FILL", ReconciliationClassification.MATCHED, "No local or broker fills expected.", None, None, RepairRecommendationCode.NO_ACTION_REQUIRED))
    return tuple(items)


def _position_items(reconciliation_input: ReconciliationInput) -> tuple[ReconciliationItem, ...]:
    items: list[ReconciliationItem] = []
    broker_by_key = {(item.broker_account_id, item.normalized_contract, item.product_type): item for item in reconciliation_input.broker_positions}
    matched_broker: set[tuple[str, str, str]] = set()
    for local in reconciliation_input.local_positions:
        key = (local.broker_account_id, local.normalized_contract, local.product_type)
        broker = broker_by_key.get(key)
        if broker is None:
            items.append(_item(f"position:{local.position_cycle_id}:local_only", "POSITION", ReconciliationClassification.LOCAL_ONLY_POSITION, "Local PositionCycle has no broker position.", local, None, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
            continue
        matched_broker.add(key)
        if _direction(local.net_quantity) != _direction(broker.net_quantity):
            items.append(_item(f"position:{local.position_cycle_id}:direction", "POSITION", ReconciliationClassification.POSITION_DIRECTION_MISMATCH, "Broker and local directions differ.", local, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
        elif local.net_quantity != broker.net_quantity:
            items.append(_item(f"position:{local.position_cycle_id}:quantity", "POSITION", ReconciliationClassification.POSITION_QUANTITY_MISMATCH, "Broker and local quantities differ.", local, broker, RepairRecommendationCode.UPDATE_LOCAL_POSITION_QUANTITY))
        elif local.status == "CLOSED" and broker.net_quantity != 0:
            items.append(_item(f"position:{local.position_cycle_id}:closed_open", "POSITION", ReconciliationClassification.LOCAL_CLOSED_BROKER_OPEN, "Local closed position is open at broker.", local, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW))
        else:
            items.append(_item(f"position:{local.position_cycle_id}:matched", "POSITION", ReconciliationClassification.MATCHED, "Position contract, direction and quantity matched.", local, broker, RepairRecommendationCode.NO_ACTION_REQUIRED))
    for broker in reconciliation_input.broker_positions:
        key = (broker.broker_account_id, broker.normalized_contract, broker.product_type)
        if key in matched_broker:
            continue
        items.append(_item(f"position:{broker.normalized_contract}:broker_only", "POSITION", ReconciliationClassification.BROKER_ONLY_POSITION, "Broker position has no deterministic local PositionCycle linkage.", None, broker, RepairRecommendationCode.CREATE_UNLINKED_BROKER_POSITION_CASE))
    if not reconciliation_input.local_positions and not reconciliation_input.broker_positions:
        items.append(_item("position:empty", "POSITION", ReconciliationClassification.MATCHED, "No local or broker positions expected.", None, None, RepairRecommendationCode.NO_ACTION_REQUIRED))
    return tuple(items)


def _protection_items(reconciliation_input: ReconciliationInput) -> tuple[ReconciliationItem, ...]:
    items: list[ReconciliationItem] = []
    broker_working = [order for order in reconciliation_input.broker_orders if order.purpose in {"TARGET", "ORIGINAL_SL", "REVISED_SL"} and order.status in {"OPEN", "TRIGGER_PENDING"}]
    used: set[str] = set()
    for expected in reconciliation_input.local_protections:
        candidates = [
            order for order in broker_working
            if order.broker_account_id == expected.broker_account_id
            and order.normalized_contract == expected.normalized_contract
            and order.purpose == expected.protection_type
        ]
        if not candidates:
            items.append(_item(f"protection:{expected.protection_id}:missing", "PROTECTION", ReconciliationClassification.PROTECTION_MISSING, "Required protection is missing at broker.", expected, None, RepairRecommendationCode.FUTURE_PLACE_MISSING_PROTECTION))
            continue
        if len(candidates) > 1:
            items.append(_item(f"protection:{expected.protection_id}:duplicate", "PROTECTION", ReconciliationClassification.DUPLICATE_PROTECTION, "Duplicate active protection observed.", expected, [item.broker_order_id for item in candidates], RepairRecommendationCode.FUTURE_CANCEL_DUPLICATE_ORDER))
            continue
        broker = candidates[0]
        used.add(broker.broker_order_id)
        if broker.quantity != expected.quantity:
            items.append(_item(f"protection:{expected.protection_id}:quantity", "PROTECTION", ReconciliationClassification.PROTECTION_QUANTITY_MISMATCH, "Protection quantity differs.", expected, broker, RepairRecommendationCode.REQUIRE_PROTECTION_REVIEW))
        elif (broker.limit_price or broker.trigger_price) not in {expected.price, None}:
            items.append(_item(f"protection:{expected.protection_id}:price", "PROTECTION", ReconciliationClassification.PROTECTION_PRICE_MISMATCH, "Protection price differs.", expected, broker, RepairRecommendationCode.FUTURE_REPLACE_STALE_PROTECTION))
        elif broker.protection_generation is not None and broker.protection_generation != expected.generation:
            items.append(_item(f"protection:{expected.protection_id}:generation", "PROTECTION", ReconciliationClassification.PROTECTION_GENERATION_MISMATCH, "Protection generation differs.", expected, broker, RepairRecommendationCode.FUTURE_REPLACE_STALE_PROTECTION))
        else:
            items.append(_item(f"protection:{expected.protection_id}:matched", "PROTECTION", ReconciliationClassification.PROTECTION_MATCHED, "Protection matched.", expected, broker, RepairRecommendationCode.NO_ACTION_REQUIRED))
    for broker in broker_working:
        if broker.broker_order_id not in used and broker.purpose in {"ORIGINAL_SL", "REVISED_SL"}:
            items.append(_item(f"protection:{broker.broker_order_id}:stale", "PROTECTION", ReconciliationClassification.STALE_PROTECTION, "Unexpected active protection remains at broker.", None, broker, RepairRecommendationCode.SUPERSEDE_STALE_PROTECTION_PROJECTION))
    if not reconciliation_input.local_protections and not broker_working:
        items.append(_item("protection:empty", "PROTECTION", ReconciliationClassification.MATCHED, "No protection expected or observed.", None, None, RepairRecommendationCode.NO_ACTION_REQUIRED))
    return tuple(items)


def _compare_order(local: LocalExpectedOrder, broker: BrokerObservedOrder) -> tuple[ReconciliationItem, ...]:
    if local.broker_account_id != broker.broker_account_id:
        return (_item(f"order:{local.local_order_id}:account", "ORDER", ReconciliationClassification.ORDER_IDENTITY_MISMATCH, "Order accounts differ.", local, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW),)
    if local.normalized_contract != broker.normalized_contract:
        return (_item(f"order:{local.local_order_id}:contract", "ORDER", ReconciliationClassification.ORDER_IDENTITY_MISMATCH, "Order contracts differ.", local, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW),)
    if local.status != broker.status:
        return (_item(f"order:{local.local_order_id}:status", "ORDER", ReconciliationClassification.ORDER_STATUS_MISMATCH, "Order statuses differ.", local, broker, RepairRecommendationCode.UPDATE_LOCAL_ORDER_STATUS),)
    if local.quantity != broker.quantity or local.filled_quantity != broker.filled_quantity:
        return (_item(f"order:{local.local_order_id}:quantity", "ORDER", ReconciliationClassification.ORDER_QUANTITY_MISMATCH, "Order quantity or fill quantity differs.", local, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW),)
    if _price_diff(local.limit_price, broker.limit_price) or _price_diff(local.trigger_price, broker.trigger_price):
        return (_item(f"order:{local.local_order_id}:price", "ORDER", ReconciliationClassification.ORDER_PRICE_MISMATCH, "Order price differs.", local, broker, RepairRecommendationCode.REQUIRE_OPERATOR_REVIEW),)
    return (_item(f"order:{local.local_order_id}:matched", "ORDER", ReconciliationClassification.MATCHED, "Order identity, status, quantity and price matched.", local, broker, RepairRecommendationCode.NO_ACTION_REQUIRED),)


def _index_orders(orders: Iterable[LocalExpectedOrder | BrokerObservedOrder]) -> dict[tuple[str, str], LocalExpectedOrder | BrokerObservedOrder]:
    index = {}
    for order in orders:
        for key_name in ("broker_order_id", "exchange_order_id", "client_order_id", "correlation_id"):
            value = getattr(order, key_name, None)
            if value:
                index[(key_name, str(value))] = order
    return index


def _find_order_match(local: LocalExpectedOrder, broker_orders: tuple[BrokerObservedOrder, ...], broker_by_key: dict[tuple[str, str], LocalExpectedOrder | BrokerObservedOrder]) -> BrokerObservedOrder | None:
    for key_name in ("broker_order_id", "exchange_order_id", "client_order_id", "correlation_id"):
        value = getattr(local, key_name)
        if not value:
            continue
        candidate = broker_by_key.get((key_name, str(value)))
        if isinstance(candidate, BrokerObservedOrder) and candidate.broker_account_id == local.broker_account_id:
            return candidate
    return None


def _has_strong_order_linkage(broker: BrokerObservedOrder) -> bool:
    return bool(broker.broker_order_id or broker.exchange_order_id or broker.client_order_id or broker.correlation_id)


def _find_fill_match(local: LocalExpectedFill, broker_fills: tuple[BrokerObservedFill, ...]) -> BrokerObservedFill | None:
    for broker in broker_fills:
        if local.exchange_fill_id and broker.exchange_fill_id == local.exchange_fill_id:
            return broker
        if broker.fill_id == local.fill_id:
            return broker
    return None


def _summary_status(items: list[ReconciliationItem], item_type: str) -> ReconciliationClassification:
    relevant = [item.classification for item in items if item.item_type == item_type]
    if not relevant:
        return ReconciliationClassification.INSUFFICIENT_EVIDENCE
    if all(item in {ReconciliationClassification.MATCHED, ReconciliationClassification.PROTECTION_MATCHED} for item in relevant):
        return ReconciliationClassification.MATCHED
    if any(item in _BLOCKING for item in relevant):
        return next(item for item in relevant if item in _BLOCKING)
    return ReconciliationClassification.PARTIAL_MATCH


def _carried_status(items: list[ReconciliationItem], reconciliation_input: ReconciliationInput) -> ReconciliationClassification:
    if reconciliation_input.scope is not ReconciliationScope.CARRIED_POSITION_STARTUP:
        return ReconciliationClassification.MATCHED
    position_status = _summary_status(items, "POSITION")
    protection_status = _summary_status(items, "PROTECTION")
    if position_status is ReconciliationClassification.MATCHED and protection_status in {ReconciliationClassification.MATCHED, ReconciliationClassification.PROTECTION_MATCHED}:
        return ReconciliationClassification.MATCHED
    return position_status if position_status is not ReconciliationClassification.MATCHED else protection_status


def _account_status(items: list[ReconciliationItem], reconciliation_input: ReconciliationInput) -> AccountReadinessStatus:
    classifications = {item.classification for item in items}
    if ReconciliationClassification.BROKER_STATE_UNAVAILABLE in classifications:
        return AccountReadinessStatus.BROKER_UNAVAILABLE
    if ReconciliationClassification.MANUAL_REVIEW_REQUIRED in classifications or any(item.manual_review_required for item in items):
        return AccountReadinessStatus.MANUAL_REVIEW_REQUIRED
    if any(item in _BLOCKING for item in classifications):
        if reconciliation_input.scope is ReconciliationScope.CARRIED_POSITION_STARTUP:
            return AccountReadinessStatus.LIFECYCLE_ONLY
        return AccountReadinessStatus.NEW_ENTRY_BLOCKED
    if ReconciliationClassification.INSUFFICIENT_EVIDENCE in classifications:
        return AccountReadinessStatus.RECONCILED_PARTIAL
    return AccountReadinessStatus.RECONCILED_READY


def _authority_gate(items: list[ReconciliationItem], account_status: AccountReadinessStatus, reconciliation_input: ReconciliationInput) -> AuthorityGateDecision:
    blocking = tuple(item.classification.value for item in items if item.classification in _BLOCKING)
    manual = any(item.manual_review_required for item in items)
    if reconciliation_input.recovery_status not in {"RECOVERABLE_OFFLINE", "RECONCILIATION_REQUIRED"}:
        recommendation = AuthorityGateRecommendation.RECOVERY_BLOCKED
    elif account_status is AccountReadinessStatus.RECONCILED_READY:
        recommendation = AuthorityGateRecommendation.SHADOW_READY
    elif account_status is AccountReadinessStatus.RECONCILED_PARTIAL:
        recommendation = AuthorityGateRecommendation.READ_ONLY_READY
    elif account_status is AccountReadinessStatus.LIFECYCLE_ONLY:
        recommendation = AuthorityGateRecommendation.LIFECYCLE_ONLY
    elif manual:
        recommendation = AuthorityGateRecommendation.MANUAL_REVIEW_REQUIRED
    elif account_status in {AccountReadinessStatus.BROKER_UNAVAILABLE, AccountReadinessStatus.ACCOUNT_BLOCKED}:
        recommendation = AuthorityGateRecommendation.ACCOUNT_BLOCKED
    else:
        recommendation = AuthorityGateRecommendation.NEW_ENTRY_BLOCKED
    return AuthorityGateDecision(
        recommendation=recommendation,
        blocking_reasons=blocking,
        manual_review_required=manual,
        evidence_hashes={"item_hash": canonical_hash(tuple(item.to_dict() for item in items))},
        grants_authority=False,
    )


def _item(item_id: str, item_type: str, classification: ReconciliationClassification, risk: str, local: object | None, broker: object | None, recommendation: RepairRecommendationCode) -> ReconciliationItem:
    manual = classification in {
        ReconciliationClassification.MANUAL_REVIEW_REQUIRED,
        ReconciliationClassification.UNKNOWN_LINKAGE,
        ReconciliationClassification.BROKER_ONLY_POSITION,
        ReconciliationClassification.DUPLICATE_BROKER_ORDER,
        ReconciliationClassification.DUPLICATE_FILL,
        ReconciliationClassification.DUPLICATE_PROTECTION,
    }
    return ReconciliationItem(
        item_id=item_id,
        item_type=item_type,
        classification=classification,
        financial_risk=risk,
        local_reference=_ref(local),
        broker_reference=_ref(broker),
        manual_review_required=manual,
        blocks_new_entry=classification in _BLOCKING,
        allows_lifecycle_only=classification in {ReconciliationClassification.PROTECTION_MISSING, ReconciliationClassification.ORDER_STATUS_MISMATCH, ReconciliationClassification.PARTIAL_MATCH},
        recommendations=(RepairRecommendation(recommendation, item_id, risk),),
    )


def _ref(value: object | None) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return {"values": list(value)}
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(value)
    return {"value": str(value)}


def _direction(quantity: int) -> int:
    if quantity > 0:
        return 1
    if quantity < 0:
        return -1
    return 0


def _price_diff(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) > 0.05


def build_s23_first_slice_reconciliation_input(*, mismatch: bool = False) -> ReconciliationInput:
    ts = datetime.fromisoformat("2026-06-05T09:16:00+05:30")
    local_order = LocalExpectedOrder(
        local_order_id="s23-entry-local",
        broker_account_id="acct-a",
        normalized_contract="NIFTY_20260609_22650_CE",
        side="SELL",
        quantity=75,
        status="OPEN",
        purpose="ENTRY",
        client_order_id="client-s23-entry",
        broker_order_id="broker-s23-entry",
        limit_price=100.0,
        filled_quantity=75,
    )
    broker_order = BrokerObservedOrder(
        broker_order_id="broker-s23-entry",
        broker_account_id="acct-a",
        normalized_contract="NIFTY_20260609_22650_CE",
        side="SELL",
        quantity=75,
        status="OPEN",
        purpose="ENTRY",
        client_order_id="client-s23-entry",
        limit_price=100.0,
        filled_quantity=75,
    )
    target = LocalExpectedProtection("target-1", "pc-s23-1", "acct-a", "NIFTY_20260609_22650_CE", "TARGET", "BUY", 75, 60.0, 1)
    revised_sl = LocalExpectedProtection("rsl-1", "pc-s23-1", "acct-a", "NIFTY_20260609_22650_CE", "REVISED_SL", "BUY", 75, 130.0, 2)
    broker_protections = (
        BrokerObservedOrder("broker-target", "acct-a", "NIFTY_20260609_22650_CE", "BUY", 75, "OPEN", "TARGET", limit_price=60.0, protection_generation=1),
        BrokerObservedOrder("broker-rsl", "acct-a", "NIFTY_20260609_22650_CE", "BUY", 75, "OPEN", "REVISED_SL", trigger_price=130.0, protection_generation=2),
    )
    local_qty = -75
    broker_qty = -50 if mismatch else -75
    return ReconciliationInput(
        reconciliation_id="s23-first-slice-reconciliation",
        broker_account_id="acct-a",
        trading_session_id="session-2026-06-05",
        scope=ReconciliationScope.CARRIED_POSITION_STARTUP,
        as_of=ts,
        local_state_version=1,
        broker_snapshot_hash="broker-snapshot-s23",
        reconciliation_policy_version="phase4d.v1",
        account_payload={"broker_account_id": "acct-a", "session_status": "AUTHENTICATED", "completeness": "COMPLETE"},
        local_orders=(local_order,),
        broker_orders=(broker_order, *broker_protections),
        local_fills=(LocalExpectedFill("fill-s23", "s23-entry-local", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, 100.0, "broker-s23-entry"),),
        broker_fills=(BrokerObservedFill("fill-s23", "acct-a", "NIFTY_20260609_22650_CE", "SELL", 75, 100.0, "broker-s23-entry"),),
        local_positions=(LocalExpectedPosition("pc-s23-1", "acct-a", "NIFTY_20260609_22650_CE", local_qty, "SHORT", "NRML", "OPEN", 100.0, "CARRIED_OVERNIGHT", "S23_NIFTY_ACCOUNT_A_PAPER"),),
        broker_positions=(BrokerObservedPosition("acct-a", "NIFTY_20260609_22650_CE", broker_qty, "SHORT", "NRML", 100.0, "CARRIED_OVERNIGHT"),),
        local_protections=(target, revised_sl),
    )
