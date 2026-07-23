from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tfis.broker import (
    LiveMarketEventEnvelope,
    LiveMarketEventIngressMode,
    LiveMarketEventIngressSnapshot,
    LiveMarketEventType,
    validate_live_market_event_ingress,
)


NOW = datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)


def test_live_market_event_ingress_passes_for_fresh_websocket_events() -> None:
    validation = validate_live_market_event_ingress(
        LiveMarketEventIngressSnapshot(
            provider="fyers",
            mode=LiveMarketEventIngressMode.WEBSOCKET,
            connected=True,
            subscribed_symbols=("NIFTY_OPT",),
            heartbeat_at=NOW,
            events=(
                _event("NIFTY_OPT", sequence_id=1),
                _event("NIFTY_OPT", sequence_id=2, seconds=1),
            ),
        ),
        required_symbols=("NIFTY_OPT",),
        now=NOW,
    )

    assert validation.status == "PASS"
    assert validation.issue_count == 0
    assert "connected, fresh, subscribed, and monotonic" in validation.message


def test_live_market_event_ingress_fails_polling_mode_and_stale_heartbeat() -> None:
    validation = validate_live_market_event_ingress(
        LiveMarketEventIngressSnapshot(
            provider="fyers",
            mode=LiveMarketEventIngressMode.POLLING,
            connected=True,
            subscribed_symbols=("NIFTY_OPT",),
            heartbeat_at=NOW - timedelta(seconds=30),
            events=(_event("NIFTY_OPT", sequence_id=1),),
        ),
        required_symbols=("NIFTY_OPT",),
        now=NOW,
        max_heartbeat_age_seconds=10,
    )

    assert validation.status == "FAIL"
    assert {issue.code for issue in validation.issues} >= {
        "LIVE_MARKET_INGRESS_POLLING_MODE",
        "LIVE_MARKET_INGRESS_HEARTBEAT_STALE",
    }


def test_live_market_event_ingress_fails_missing_required_symbol() -> None:
    validation = validate_live_market_event_ingress(
        LiveMarketEventIngressSnapshot(
            provider="fyers",
            mode=LiveMarketEventIngressMode.BROKER_EVENT,
            connected=True,
            subscribed_symbols=("NIFTY_OPT",),
            heartbeat_at=NOW,
            events=(_event("NIFTY_OPT", sequence_id=1),),
        ),
        required_symbols=("BANKNIFTY_OPT",),
        now=NOW,
    )

    assert validation.status == "FAIL"
    assert {issue.code for issue in validation.issues} >= {
        "LIVE_MARKET_INGRESS_SYMBOL_NOT_SUBSCRIBED",
        "LIVE_MARKET_INGRESS_SYMBOL_EVENT_MISSING",
    }


def test_live_market_event_ingress_fails_duplicate_and_non_monotonic_events() -> None:
    validation = validate_live_market_event_ingress(
        LiveMarketEventIngressSnapshot(
            provider="fyers",
            mode=LiveMarketEventIngressMode.WEBSOCKET,
            connected=True,
            subscribed_symbols=("NIFTY_OPT",),
            heartbeat_at=NOW,
            events=(
                _event("NIFTY_OPT", sequence_id=2, seconds=2),
                _event("NIFTY_OPT", sequence_id=2, seconds=3),
                _event("NIFTY_OPT", sequence_id=1, seconds=1),
            ),
        ),
        required_symbols=("NIFTY_OPT",),
        now=NOW,
    )

    assert validation.status == "FAIL"
    assert {issue.code for issue in validation.issues} >= {
        "LIVE_MARKET_INGRESS_DUPLICATE_SEQUENCE",
        "LIVE_MARKET_INGRESS_NON_MONOTONIC_EVENT",
    }


def _event(symbol: str, *, sequence_id: int, seconds: int = 0) -> LiveMarketEventEnvelope:
    return LiveMarketEventEnvelope(
        provider="fyers",
        symbol=symbol,
        event_type=LiveMarketEventType.QUOTE,
        effective_timestamp=NOW + timedelta(seconds=seconds),
        received_at=NOW + timedelta(seconds=seconds),
        source_id=f"stream:{sequence_id}",
        sequence_id=sequence_id,
    )
