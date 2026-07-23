from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LiveMarketEventIngressMode(str, Enum):
    POLLING = "POLLING"
    WEBSOCKET = "WEBSOCKET"
    BROKER_EVENT = "BROKER_EVENT"


class LiveMarketEventType(str, Enum):
    QUOTE = "QUOTE"
    TRADE = "TRADE"
    ORDER_UPDATE = "ORDER_UPDATE"
    POSITION_UPDATE = "POSITION_UPDATE"
    HEARTBEAT = "HEARTBEAT"


@dataclass(frozen=True, slots=True)
class LiveMarketEventEnvelope:
    provider: str
    symbol: str
    event_type: LiveMarketEventType
    effective_timestamp: datetime
    received_at: datetime
    source_id: str
    sequence_id: int


@dataclass(frozen=True, slots=True)
class LiveMarketEventIngressSnapshot:
    provider: str
    mode: LiveMarketEventIngressMode
    connected: bool
    subscribed_symbols: tuple[str, ...]
    heartbeat_at: datetime | None
    events: tuple[LiveMarketEventEnvelope, ...]
    reconnect_attempts: int = 0


@dataclass(frozen=True, slots=True)
class LiveMarketEventIngressIssue:
    code: str
    symbol: str | None
    message: str


@dataclass(frozen=True, slots=True)
class LiveMarketEventIngressValidation:
    status: str
    issue_count: int
    issues: tuple[LiveMarketEventIngressIssue, ...]
    message: str


def validate_live_market_event_ingress(
    snapshot: LiveMarketEventIngressSnapshot,
    *,
    required_symbols: tuple[str, ...],
    now: datetime,
    max_heartbeat_age_seconds: float = 10.0,
) -> LiveMarketEventIngressValidation:
    issues: list[LiveMarketEventIngressIssue] = []
    if snapshot.mode is LiveMarketEventIngressMode.POLLING:
        issues.append(
            LiveMarketEventIngressIssue(
                code="LIVE_MARKET_INGRESS_POLLING_MODE",
                symbol=None,
                message="Live execution requires websocket or broker-event ingress; polling mode is not sufficient.",
            )
        )
    if not snapshot.connected:
        issues.append(
            LiveMarketEventIngressIssue(
                code="LIVE_MARKET_INGRESS_DISCONNECTED",
                symbol=None,
                message="Live market-event ingress is not connected.",
            )
        )
    if snapshot.heartbeat_at is None:
        issues.append(
            LiveMarketEventIngressIssue(
                code="LIVE_MARKET_INGRESS_HEARTBEAT_MISSING",
                symbol=None,
                message="Live market-event ingress heartbeat is missing.",
            )
        )
    elif (now - snapshot.heartbeat_at).total_seconds() > max_heartbeat_age_seconds:
        issues.append(
            LiveMarketEventIngressIssue(
                code="LIVE_MARKET_INGRESS_HEARTBEAT_STALE",
                symbol=None,
                message="Live market-event ingress heartbeat is stale.",
            )
        )
    subscribed = {_normalize(symbol) for symbol in snapshot.subscribed_symbols}
    event_symbols = {_normalize(event.symbol) for event in snapshot.events}
    for symbol in required_symbols:
        normalized = _normalize(symbol)
        if normalized not in subscribed:
            issues.append(
                LiveMarketEventIngressIssue(
                    code="LIVE_MARKET_INGRESS_SYMBOL_NOT_SUBSCRIBED",
                    symbol=symbol,
                    message=f"Required live symbol is not subscribed: {symbol}.",
                )
            )
        if normalized not in event_symbols:
            issues.append(
                LiveMarketEventIngressIssue(
                    code="LIVE_MARKET_INGRESS_SYMBOL_EVENT_MISSING",
                    symbol=symbol,
                    message=f"Required live symbol has no broker-event evidence: {symbol}.",
                )
            )
    _validate_event_order(snapshot.events, issues)
    status = "FAIL" if issues else "PASS"
    return LiveMarketEventIngressValidation(
        status=status,
        issue_count=len(issues),
        issues=tuple(issues),
        message=(
            f"{len(issues)} live market-event ingress issue(s) detected."
            if issues
            else "Live market-event ingress evidence is connected, fresh, subscribed, and monotonic."
        ),
    )


def _validate_event_order(
    events: tuple[LiveMarketEventEnvelope, ...],
    issues: list[LiveMarketEventIngressIssue],
) -> None:
    latest_by_symbol: dict[str, tuple[int, datetime]] = {}
    seen: set[tuple[str, int]] = set()
    for event in events:
        key = (_normalize(event.symbol), event.sequence_id)
        if key in seen:
            issues.append(
                LiveMarketEventIngressIssue(
                    code="LIVE_MARKET_INGRESS_DUPLICATE_SEQUENCE",
                    symbol=event.symbol,
                    message=f"Duplicate live event sequence for {event.symbol}: {event.sequence_id}.",
                )
            )
        seen.add(key)
        latest = latest_by_symbol.get(_normalize(event.symbol))
        if latest is not None:
            latest_sequence, latest_timestamp = latest
            if event.sequence_id < latest_sequence or event.effective_timestamp < latest_timestamp:
                issues.append(
                    LiveMarketEventIngressIssue(
                        code="LIVE_MARKET_INGRESS_NON_MONOTONIC_EVENT",
                        symbol=event.symbol,
                        message=f"Live event sequence is not monotonic for {event.symbol}.",
                    )
                )
        latest_by_symbol[_normalize(event.symbol)] = (
            event.sequence_id,
            event.effective_timestamp,
        )


def _normalize(symbol: str) -> str:
    return symbol.strip().upper()


__all__ = [
    "LiveMarketEventEnvelope",
    "LiveMarketEventIngressIssue",
    "LiveMarketEventIngressMode",
    "LiveMarketEventIngressSnapshot",
    "LiveMarketEventIngressValidation",
    "LiveMarketEventType",
    "validate_live_market_event_ingress",
]
