from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tfis.broker import (
    BrokerOrderBookSnapshot,
    BrokerOrderEventType,
    BrokerOrderLifecycleStatus,
    BrokerOrderStateStore,
    BrokerPositionSnapshot,
    BrokerReconciliationScope,
    BrokerReconciliationStatus,
    TfisPositionExpectation,
    reconcile_broker_truth,
)


def test_reconcile_broker_truth_passes_when_positions_and_orders_match(
    tmp_path: Path,
) -> None:
    order = _acked_order(tmp_path)

    result = reconcile_broker_truth(
        scope=BrokerReconciliationScope.PRE_STARTUP,
        expected_positions=(
            TfisPositionExpectation(
                provider="fyers",
                strategy_code="S23",
                strategy_branch="BRANCH",
                symbol="NIFTY_OPT",
                expected_quantity=-75,
                expected_average_price=194.25,
            ),
        ),
        broker_positions=(
            BrokerPositionSnapshot(
                provider="fyers",
                symbol="NIFTY_OPT",
                quantity=-75,
                average_price=194.25,
            ),
        ),
        expected_orders=(order,),
        broker_orders=(
            BrokerOrderBookSnapshot(
                provider="fyers",
                client_order_id=order.client_order_id,
                broker_order_id=order.broker_order_id,
                symbol=order.symbol,
                exchange_status="OPEN",
                filled_quantity=0,
            ),
        ),
    )

    assert result.status is BrokerReconciliationStatus.PASS
    assert result.conflict_count == 0
    assert result.scope is BrokerReconciliationScope.PRE_STARTUP


def test_reconcile_broker_truth_fails_missing_expected_position() -> None:
    result = reconcile_broker_truth(
        scope=BrokerReconciliationScope.AFTER_RESTART,
        expected_positions=(
            TfisPositionExpectation(
                provider="fyers",
                strategy_code="S21",
                strategy_branch="BRANCH",
                symbol="BANKNIFTY_OPT",
                expected_quantity=-35,
            ),
        ),
        broker_positions=(),
    )

    assert result.status is BrokerReconciliationStatus.FAIL
    assert result.conflicts[0].code == "BROKER_POSITION_MISSING"


def test_reconcile_broker_truth_fails_quantity_and_unexpected_position() -> None:
    result = reconcile_broker_truth(
        scope=BrokerReconciliationScope.DURING_SUPERVISION,
        expected_positions=(
            TfisPositionExpectation(
                provider="fyers",
                strategy_code="S23",
                strategy_branch="BRANCH",
                symbol="NIFTY_OPT",
                expected_quantity=-75,
            ),
        ),
        broker_positions=(
            BrokerPositionSnapshot(provider="fyers", symbol="NIFTY_OPT", quantity=-50),
            BrokerPositionSnapshot(provider="fyers", symbol="OTHER_OPT", quantity=-10),
        ),
    )

    assert result.status is BrokerReconciliationStatus.FAIL
    assert {conflict.code for conflict in result.conflicts} == {
        "BROKER_POSITION_QUANTITY_MISMATCH",
        "BROKER_POSITION_UNEXPECTED",
    }


def test_reconcile_broker_truth_fails_order_book_drift(tmp_path: Path) -> None:
    order = _acked_order(tmp_path)

    result = reconcile_broker_truth(
        scope=BrokerReconciliationScope.AFTER_RESTART,
        expected_positions=(),
        broker_positions=(),
        expected_orders=(order,),
        broker_orders=(
            BrokerOrderBookSnapshot(
                provider="fyers",
                client_order_id=order.client_order_id,
                broker_order_id=order.broker_order_id,
                symbol=order.symbol,
                exchange_status="REJECTED",
                filled_quantity=25,
            ),
        ),
    )

    assert result.status is BrokerReconciliationStatus.FAIL
    assert {conflict.code for conflict in result.conflicts} == {
        "BROKER_ORDER_EXCHANGE_STATUS_MISMATCH",
        "BROKER_ORDER_FILLED_QUANTITY_MISMATCH",
    }


def _acked_order(tmp_path: Path):
    store = BrokerOrderStateStore()
    created_at = datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc)
    store.create_intent(
        tmp_path,
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH",
        symbol="NIFTY_OPT",
        order_role="ENTRY",
        side="SELL",
        quantity=75,
        product_type="NRML",
        order_type="LIMIT",
        client_order_id="TFIS-S23-ENTRY-1",
        created_at=created_at,
    )
    state, _event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.ACKNOWLEDGED,
        status=BrokerOrderLifecycleStatus.ACKNOWLEDGED,
        timestamp=created_at,
        message="ack",
        broker_order_id="OID-1",
        exchange_status="OPEN",
    )
    return state
