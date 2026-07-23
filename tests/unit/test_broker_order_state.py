from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tfis.broker import (
    BrokerOrderEventType,
    BrokerOrderLifecycleStatus,
    BrokerOrderStateDiscovery,
    BrokerOrderStateError,
    BrokerOrderStateStore,
    broker_order_is_terminal,
    broker_order_requires_operator_attention,
)


def test_broker_order_state_store_persists_broker_truth_events(tmp_path: Path) -> None:
    store = BrokerOrderStateStore()
    created_at = datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc)

    state, state_path, events_path = store.create_intent(
        tmp_path,
        provider="fyers",
        strategy_code="S23",
        strategy_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        symbol="NIFTY_20260804_24000_CE",
        order_role="ENTRY",
        side="SELL",
        quantity=75,
        product_type="NRML",
        order_type="LIMIT",
        client_order_id="TFIS-S23-20260722-0001",
        created_at=created_at,
        limit_price=194.25,
        provenance_source_ids=("paper_order_state.json",),
    )

    assert state.status is BrokerOrderLifecycleStatus.INTENT_CREATED
    assert state.remaining_quantity == 75
    assert state_path == tmp_path / "broker_order_state.json"
    assert events_path == tmp_path / "broker_order_events.jsonl"

    submitted_at = datetime(2026, 7, 22, 9, 26, tzinfo=timezone.utc)
    state, event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.ACKNOWLEDGED,
        status=BrokerOrderLifecycleStatus.ACKNOWLEDGED,
        timestamp=submitted_at,
        message="Broker accepted the live order.",
        broker_order_id="240722000123",
        exchange_order_id="11000000000123",
        exchange_status="OPEN",
        source_id="orderbook:poll:1",
    )

    assert state.broker_order_id == "240722000123"
    assert state.exchange_order_id == "11000000000123"
    assert state.exchange_status == "OPEN"
    assert state.acknowledged_at == submitted_at
    assert event.broker_order_id == "240722000123"

    modify_at = datetime(2026, 7, 22, 9, 26, 30, tzinfo=timezone.utc)
    state, _event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.MODIFIED,
        status=BrokerOrderLifecycleStatus.MODIFIED,
        timestamp=modify_at,
        message="Broker order limit was modified.",
        limit_price=193.9,
        modify_reason="operator_reviewed_price",
        source_id="orderbook:poll:2",
    )

    assert state.modified_at == modify_at
    assert state.limit_price == 193.9
    assert state.modify_reason == "operator_reviewed_price"

    partial_at = datetime(2026, 7, 22, 9, 27, tzinfo=timezone.utc)
    state, _event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.PARTIALLY_FILLED,
        status=BrokerOrderLifecycleStatus.PARTIALLY_FILLED,
        timestamp=partial_at,
        message="Broker order partially filled.",
        filled_quantity=25,
        average_fill_price=194.0,
    )

    assert state.filled_quantity == 25
    assert state.remaining_quantity == 50
    assert state.average_fill_price == 194.0

    filled_at = datetime(2026, 7, 22, 9, 28, tzinfo=timezone.utc)
    state, _event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.FILLED,
        status=BrokerOrderLifecycleStatus.FILLED,
        timestamp=filled_at,
        message="Broker order fully filled.",
        filled_quantity=75,
        average_fill_price=193.8,
    )

    loaded = store.load_state(tmp_path)
    events = store.load_events(tmp_path)
    payload = json.loads(state_path.read_text(encoding="utf-8"))

    assert state.filled_at == filled_at
    assert loaded == state
    assert len(events) == 5
    assert events[-1].status is BrokerOrderLifecycleStatus.FILLED
    assert payload["broker_order_id"] == "240722000123"
    assert payload["exchange_status"] == "OPEN"
    assert payload["filled_at"] == filled_at.isoformat()
    assert broker_order_is_terminal(loaded.status) is True


def test_broker_order_state_discovery_filters_provider_and_strategy(tmp_path: Path) -> None:
    store = BrokerOrderStateStore()
    created_at = datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc)
    store.create_intent(
        tmp_path / "s23",
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH_A",
        symbol="NIFTY_OPT",
        order_role="ENTRY",
        side="SELL",
        quantity=75,
        product_type="NRML",
        order_type="LIMIT",
        client_order_id="S23-1",
        created_at=created_at,
    )
    store.create_intent(
        tmp_path / "s21",
        provider="fyers",
        strategy_code="S21",
        strategy_branch="BRANCH_B",
        symbol="BANKNIFTY_OPT",
        order_role="ENTRY",
        side="SELL",
        quantity=35,
        product_type="NRML",
        order_type="LIMIT",
        client_order_id="S21-1",
        created_at=created_at,
    )

    discovery = BrokerOrderStateDiscovery(store=store)

    assert len(discovery.find_orders((tmp_path,), provider="fyers")) == 2
    s23_orders = discovery.find_orders((tmp_path,), strategy_code="S23")
    assert len(s23_orders) == 1
    assert s23_orders[0].state.strategy_branch == "BRANCH_A"


def test_broker_order_state_records_pending_stale_and_failure_states(tmp_path: Path) -> None:
    store = BrokerOrderStateStore()
    created_at = datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc)
    store.create_intent(
        tmp_path,
        provider="fyers",
        strategy_code="S23",
        strategy_branch="BRANCH_A",
        symbol="NIFTY_OPT",
        order_role="ENTRY",
        side="SELL",
        quantity=75,
        product_type="NRML",
        order_type="LIMIT",
        client_order_id="S23-1",
        created_at=created_at,
    )

    pending, _event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.PENDING,
        status=BrokerOrderLifecycleStatus.PENDING,
        timestamp=datetime(2026, 7, 22, 9, 26, tzinfo=timezone.utc),
        message="Broker order is pending exchange acknowledgement.",
        exchange_status="PENDING",
    )
    stale, _event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.STALE,
        status=BrokerOrderLifecycleStatus.STALE,
        timestamp=datetime(2026, 7, 22, 9, 27, tzinfo=timezone.utc),
        message="Broker order remained pending beyond the allowed window.",
        exchange_status="PENDING",
    )
    cancel_failed, _event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.CANCEL_FAILED,
        status=BrokerOrderLifecycleStatus.CANCEL_FAILED,
        timestamp=datetime(2026, 7, 22, 9, 28, tzinfo=timezone.utc),
        message="Broker cancellation failed.",
        cancel_reason="broker_rejected_cancel",
    )
    modify_failed, _event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.MODIFY_FAILED,
        status=BrokerOrderLifecycleStatus.MODIFY_FAILED,
        timestamp=datetime(2026, 7, 22, 9, 29, tzinfo=timezone.utc),
        message="Broker modification failed.",
        modify_reason="exchange_rejected_modify",
    )

    assert pending.exchange_status == "PENDING"
    assert broker_order_requires_operator_attention(pending.status) is False
    assert broker_order_requires_operator_attention(stale.status) is True
    assert broker_order_requires_operator_attention(cancel_failed.status) is True
    assert cancel_failed.cancel_reason == "broker_rejected_cancel"
    assert broker_order_requires_operator_attention(modify_failed.status) is True
    assert modify_failed.modify_reason == "exchange_rejected_modify"
    assert len(store.load_events(tmp_path)) == 5


def test_broker_order_state_records_rejected_order_with_reason(tmp_path: Path) -> None:
    store = BrokerOrderStateStore()
    created_at = datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc)
    store.create_intent(
        tmp_path,
        provider="fyers",
        strategy_code="S21",
        strategy_branch="BRANCH_B",
        symbol="BANKNIFTY_OPT",
        order_role="ENTRY",
        side="SELL",
        quantity=35,
        product_type="NRML",
        order_type="LIMIT",
        client_order_id="S21-1",
        created_at=created_at,
    )

    rejected, event, _state_path, _events_path = store.record_event(
        tmp_path,
        event_type=BrokerOrderEventType.REJECTED,
        status=BrokerOrderLifecycleStatus.REJECTED,
        timestamp=datetime(2026, 7, 22, 9, 26, tzinfo=timezone.utc),
        message="Broker rejected the order.",
        exchange_status="REJECTED",
        rejection_code="INSUFFICIENT_MARGIN",
        rejection_message="Insufficient margin.",
    )

    assert rejected.rejected_at is not None
    assert rejected.rejection_code == "INSUFFICIENT_MARGIN"
    assert event.rejection_message == "Insufficient margin."
    assert broker_order_is_terminal(rejected.status) is True
    assert broker_order_requires_operator_attention(rejected.status) is True


def test_broker_order_state_rejects_missing_identity(tmp_path: Path) -> None:
    with pytest.raises(BrokerOrderStateError, match="client_order_id is required"):
        BrokerOrderStateStore().create_intent(
            tmp_path,
            provider="fyers",
            strategy_code="S23",
            strategy_branch="BRANCH_A",
            symbol="NIFTY_OPT",
            order_role="ENTRY",
            side="SELL",
            quantity=75,
            product_type="NRML",
            order_type="LIMIT",
            client_order_id="",
            created_at=datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc),
        )
