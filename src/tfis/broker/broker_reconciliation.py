from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .broker_order_state import BrokerOrderLifecycleStatus, BrokerOrderState


class BrokerReconciliationScope(str, Enum):
    PRE_STARTUP = "PRE_STARTUP"
    DURING_SUPERVISION = "DURING_SUPERVISION"
    AFTER_RESTART = "AFTER_RESTART"


class BrokerReconciliationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class TfisPositionExpectation:
    provider: str
    strategy_code: str
    strategy_branch: str
    symbol: str
    expected_quantity: int
    expected_average_price: float | None = None
    source_path: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerPositionSnapshot:
    provider: str
    symbol: str
    quantity: int
    average_price: float | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerOrderBookSnapshot:
    provider: str
    client_order_id: str | None
    broker_order_id: str | None
    symbol: str
    exchange_status: str | None
    filled_quantity: int | None = None
    remaining_quantity: int | None = None
    average_fill_price: float | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerReconciliationConflict:
    code: str
    provider: str
    symbol: str | None
    client_order_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class BrokerReconciliationResult:
    scope: BrokerReconciliationScope
    status: BrokerReconciliationStatus
    expected_position_count: int
    broker_position_count: int
    expected_order_count: int
    broker_order_count: int
    conflict_count: int
    conflicts: tuple[BrokerReconciliationConflict, ...]
    message: str


def reconcile_broker_truth(
    *,
    scope: BrokerReconciliationScope,
    expected_positions: tuple[TfisPositionExpectation, ...],
    broker_positions: tuple[BrokerPositionSnapshot, ...],
    expected_orders: tuple[BrokerOrderState, ...] = (),
    broker_orders: tuple[BrokerOrderBookSnapshot, ...] = (),
    price_tolerance: float = 0.01,
) -> BrokerReconciliationResult:
    conflicts: list[BrokerReconciliationConflict] = []
    _reconcile_positions(
        expected_positions=expected_positions,
        broker_positions=broker_positions,
        price_tolerance=price_tolerance,
        conflicts=conflicts,
    )
    _reconcile_orders(
        expected_orders=expected_orders,
        broker_orders=broker_orders,
        conflicts=conflicts,
    )
    status = (
        BrokerReconciliationStatus.FAIL
        if conflicts
        else BrokerReconciliationStatus.PASS
    )
    message = (
        f"{len(conflicts)} broker truth conflict(s) detected for {scope.value}"
        if conflicts
        else f"TFIS expectations agree with broker truth for {scope.value}"
    )
    return BrokerReconciliationResult(
        scope=scope,
        status=status,
        expected_position_count=len(expected_positions),
        broker_position_count=len(broker_positions),
        expected_order_count=len(expected_orders),
        broker_order_count=len(broker_orders),
        conflict_count=len(conflicts),
        conflicts=tuple(conflicts),
        message=message,
    )


def _reconcile_positions(
    *,
    expected_positions: tuple[TfisPositionExpectation, ...],
    broker_positions: tuple[BrokerPositionSnapshot, ...],
    price_tolerance: float,
    conflicts: list[BrokerReconciliationConflict],
) -> None:
    expected_by_key = {
        (_normalize(item.provider), _normalize(item.symbol)): item
        for item in expected_positions
        if item.expected_quantity != 0
    }
    broker_by_key = {
        (_normalize(item.provider), _normalize(item.symbol)): item
        for item in broker_positions
        if item.quantity != 0
    }
    for key, expected in expected_by_key.items():
        broker = broker_by_key.get(key)
        if broker is None:
            conflicts.append(
                BrokerReconciliationConflict(
                    code="BROKER_POSITION_MISSING",
                    provider=expected.provider,
                    symbol=expected.symbol,
                    client_order_id=None,
                    message="TFIS expects an open position, but broker truth has no matching non-zero position.",
                )
            )
            continue
        if broker.quantity != expected.expected_quantity:
            conflicts.append(
                BrokerReconciliationConflict(
                    code="BROKER_POSITION_QUANTITY_MISMATCH",
                    provider=expected.provider,
                    symbol=expected.symbol,
                    client_order_id=None,
                    message=(
                        "TFIS position quantity does not match broker truth: "
                        f"expected={expected.expected_quantity} actual={broker.quantity}."
                    ),
                )
            )
        if (
            expected.expected_average_price is not None
            and broker.average_price is not None
            and abs(expected.expected_average_price - broker.average_price) > price_tolerance
        ):
            conflicts.append(
                BrokerReconciliationConflict(
                    code="BROKER_POSITION_AVERAGE_PRICE_MISMATCH",
                    provider=expected.provider,
                    symbol=expected.symbol,
                    client_order_id=None,
                    message=(
                        "TFIS position average price does not match broker truth: "
                        f"expected={expected.expected_average_price} actual={broker.average_price}."
                    ),
                )
            )
    for key, broker in broker_by_key.items():
        if key in expected_by_key:
            continue
        conflicts.append(
            BrokerReconciliationConflict(
                code="BROKER_POSITION_UNEXPECTED",
                provider=broker.provider,
                symbol=broker.symbol,
                client_order_id=None,
                message="Broker truth has a non-zero position that TFIS does not expect.",
            )
        )


def _reconcile_orders(
    *,
    expected_orders: tuple[BrokerOrderState, ...],
    broker_orders: tuple[BrokerOrderBookSnapshot, ...],
    conflicts: list[BrokerReconciliationConflict],
) -> None:
    broker_by_client_id = {
        str(item.client_order_id): item
        for item in broker_orders
        if item.client_order_id is not None
    }
    broker_by_order_id = {
        str(item.broker_order_id): item
        for item in broker_orders
        if item.broker_order_id is not None
    }
    for expected in expected_orders:
        broker = broker_by_client_id.get(expected.client_order_id)
        if broker is None and expected.broker_order_id is not None:
            broker = broker_by_order_id.get(expected.broker_order_id)
        if broker is None:
            if expected.status in {
                BrokerOrderLifecycleStatus.INTENT_CREATED,
                BrokerOrderLifecycleStatus.EXPIRED,
            }:
                continue
            conflicts.append(
                BrokerReconciliationConflict(
                    code="BROKER_ORDER_MISSING",
                    provider=expected.provider,
                    symbol=expected.symbol,
                    client_order_id=expected.client_order_id,
                    message="TFIS has broker order state, but broker order-book truth has no matching order.",
                )
            )
            continue
        if expected.exchange_status and broker.exchange_status:
            if _normalize(expected.exchange_status) != _normalize(broker.exchange_status):
                conflicts.append(
                    BrokerReconciliationConflict(
                        code="BROKER_ORDER_EXCHANGE_STATUS_MISMATCH",
                        provider=expected.provider,
                        symbol=expected.symbol,
                        client_order_id=expected.client_order_id,
                        message=(
                            "TFIS broker order exchange status does not match broker truth: "
                            f"expected={expected.exchange_status} actual={broker.exchange_status}."
                        ),
                    )
                )
        if (
            broker.filled_quantity is not None
            and broker.filled_quantity != expected.filled_quantity
        ):
            conflicts.append(
                BrokerReconciliationConflict(
                    code="BROKER_ORDER_FILLED_QUANTITY_MISMATCH",
                    provider=expected.provider,
                    symbol=expected.symbol,
                    client_order_id=expected.client_order_id,
                    message=(
                        "TFIS broker order filled quantity does not match broker truth: "
                        f"expected={expected.filled_quantity} actual={broker.filled_quantity}."
                    ),
                )
            )


def _normalize(value: str) -> str:
    return value.strip().upper()


__all__ = [
    "BrokerOrderBookSnapshot",
    "BrokerPositionSnapshot",
    "BrokerReconciliationConflict",
    "BrokerReconciliationResult",
    "BrokerReconciliationScope",
    "BrokerReconciliationStatus",
    "TfisPositionExpectation",
    "reconcile_broker_truth",
]
