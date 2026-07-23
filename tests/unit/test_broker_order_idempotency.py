from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tfis.broker import (
    BrokerOrderIdempotencyError,
    BrokerOrderIdempotencyKey,
    BrokerOrderIdempotencyStore,
    BrokerOrderReservationStatus,
    build_broker_client_order_id,
)


def _key(*, attempt: int = 1) -> BrokerOrderIdempotencyKey:
    return BrokerOrderIdempotencyKey(
        provider="fyers",
        strategy_code="S23",
        strategy_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        trade_id="S23-NIFTY-ORDER-20260722T092500",
        order_role="ENTRY",
        attempt=attempt,
    )


def test_client_order_id_is_restart_stable_and_compact() -> None:
    first = build_broker_client_order_id(_key())
    second = build_broker_client_order_id(_key())
    retry = build_broker_client_order_id(_key(attempt=2))

    assert first == second
    assert first != retry
    assert first.startswith("TFIS-S23-ENTRY-")
    assert len(first) <= 48


def test_idempotency_store_prevents_duplicate_reservation(tmp_path: Path) -> None:
    store = BrokerOrderIdempotencyStore()
    reserved_at = datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc)

    first = store.reserve(tmp_path, key=_key(), reserved_at=reserved_at)
    duplicate = store.reserve(
        tmp_path,
        key=_key(),
        reserved_at=datetime(2026, 7, 22, 9, 26, tzinfo=timezone.utc),
    )

    assert first.created is True
    assert first.duplicate_prevented is False
    assert duplicate.created is False
    assert duplicate.duplicate_prevented is True
    assert duplicate.reservation == first.reservation
    assert len(store.load_records(tmp_path)) == 1


def test_idempotency_store_allows_explicit_retry_attempt(tmp_path: Path) -> None:
    store = BrokerOrderIdempotencyStore()
    reserved_at = datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc)

    first = store.reserve(tmp_path, key=_key(), reserved_at=reserved_at)
    retry = store.reserve(tmp_path, key=_key(attempt=2), reserved_at=reserved_at)

    assert first.reservation.client_order_id != retry.reservation.client_order_id
    assert retry.created is True
    assert len(store.load_records(tmp_path)) == 2


def test_idempotency_store_marks_reservation_consumed(tmp_path: Path) -> None:
    store = BrokerOrderIdempotencyStore()
    reserved_at = datetime(2026, 7, 22, 9, 25, tzinfo=timezone.utc)
    result = store.reserve(tmp_path, key=_key(), reserved_at=reserved_at)

    consumed = store.mark_consumed(
        tmp_path,
        idempotency_key=result.reservation.idempotency_key,
        consumed_at=datetime(2026, 7, 22, 9, 26, tzinfo=timezone.utc),
        broker_order_state_path=tmp_path / "order" / "broker_order_state.json",
    )

    assert consumed.status is BrokerOrderReservationStatus.CONSUMED
    assert consumed.client_order_id == result.reservation.client_order_id
    assert consumed.broker_order_state_path.endswith("broker_order_state.json")
    assert store.load_records(tmp_path)[-1] == consumed


def test_idempotency_key_rejects_invalid_attempt() -> None:
    with pytest.raises(BrokerOrderIdempotencyError, match="attempt must be positive"):
        build_broker_client_order_id(_key(attempt=0))
