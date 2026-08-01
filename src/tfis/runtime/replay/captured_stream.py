from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from tfis.runtime import NormalizedRuntimeEvent, RuntimeEventType, RuntimeFreshness, runtime_hash

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class ReplayClockPolicy:
    market_open_time: time = time(9, 15, 0)
    premarket_time: time = time(9, 0, 0)
    orpt_time: time = time(9, 24, 59)
    rc_time: time = time(9, 29, 59)
    eod_evaluation_time: time = time(15, 0, 0)
    session_end_time: time = time(15, 30, 0)
    max_fresh_age_seconds: int = 60


@dataclass(frozen=True, slots=True)
class CapturedReplayDiagnostics:
    raw_record_count: int
    normalized_event_count: int
    captured_event_count: int
    derived_configuration_event_count: int
    missing_timestamp_count: int
    duplicate_source_timestamp_count: int
    backward_source_timestamp_count: int
    future_source_timestamp_count: int
    dispatch_ordering_difference_count: int
    exact_duplicate_event_count: int
    conflicting_duplicate_event_count: int
    event_identity_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_record_count": self.raw_record_count,
            "normalized_event_count": self.normalized_event_count,
            "captured_event_count": self.captured_event_count,
            "derived_configuration_event_count": self.derived_configuration_event_count,
            "missing_timestamp_count": self.missing_timestamp_count,
            "duplicate_source_timestamp_count": self.duplicate_source_timestamp_count,
            "backward_source_timestamp_count": self.backward_source_timestamp_count,
            "future_source_timestamp_count": self.future_source_timestamp_count,
            "dispatch_ordering_difference_count": self.dispatch_ordering_difference_count,
            "exact_duplicate_event_count": self.exact_duplicate_event_count,
            "conflicting_duplicate_event_count": self.conflicting_duplicate_event_count,
            "event_identity_hash": self.event_identity_hash,
        }


@dataclass(frozen=True, slots=True)
class CapturedReplaySession:
    session_id: str
    trading_date: date
    source_path: str
    selected_contract: str | None
    events: tuple[NormalizedRuntimeEvent, ...]
    diagnostics: CapturedReplayDiagnostics
    field_provenance: Mapping[str, str]
    capture_classification: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "trading_date": self.trading_date.isoformat(),
            "source_path": self.source_path,
            "selected_contract": self.selected_contract,
            "events": [event.to_dict() for event in self.events],
            "diagnostics": self.diagnostics.to_dict(),
            "field_provenance": dict(self.field_provenance),
            "capture_classification": self.capture_classification,
        }


def load_captured_runtime_events(
    path: str | Path,
    *,
    session_id: str,
    strategy_instance_id: str,
    selected_contract: str | None,
    clock_policy: ReplayClockPolicy | None = None,
    include_eod_clock: bool = False,
    include_session_end_clock: bool = False,
) -> CapturedReplaySession:
    records = _load_jsonl(path)
    return normalize_captured_market_records(
        records,
        session_id=session_id,
        source_path=str(path),
        strategy_instance_id=strategy_instance_id,
        selected_contract=selected_contract,
        clock_policy=clock_policy,
        include_eod_clock=include_eod_clock,
        include_session_end_clock=include_session_end_clock,
    )


def normalize_captured_market_records(
    records: Iterable[Mapping[str, Any]],
    *,
    session_id: str,
    source_path: str,
    strategy_instance_id: str,
    selected_contract: str | None,
    clock_policy: ReplayClockPolicy | None = None,
    include_eod_clock: bool = False,
    include_session_end_clock: bool = False,
) -> CapturedReplaySession:
    policy = clock_policy or ReplayClockPolicy()
    raw_records = tuple(records)
    if not raw_records:
        raise ValueError("captured replay records must be non-empty")
    trading_date = _session_date(raw_records)
    derived = _derived_clock_events(
        trading_date=trading_date,
        session_id=session_id,
        source_path=source_path,
        strategy_instance_id=strategy_instance_id,
        policy=policy,
        include_eod_clock=include_eod_clock,
        include_session_end_clock=include_session_end_clock,
    )
    captured = []
    sequence = len(derived) + 1
    for index, record in enumerate(raw_records, start=1):
        for event in _events_from_record(
            record,
            session_id=session_id,
            source_path=source_path,
            strategy_instance_id=strategy_instance_id,
            selected_contract=selected_contract,
            sequence_start=sequence,
            record_index=index,
            policy=policy,
        ):
            captured.append(event)
            sequence += 1
    events = tuple(sorted(derived + tuple(captured), key=lambda item: (item.effective_timestamp, item.sequence_identity, item.event_id)))
    diagnostics = _diagnostics(raw_records, events, len(captured), len(derived))
    return CapturedReplaySession(
        session_id=session_id,
        trading_date=trading_date,
        source_path=source_path,
        selected_contract=selected_contract,
        events=events,
        diagnostics=diagnostics,
        field_provenance={
            "configuration_ready": "DERIVED_FROM_VERIFIED_CONFIGURATION",
            "strategy_enabled": "DERIVED_FROM_VERIFIED_CONFIGURATION",
            "premarket_preparation_time": "DERIVED_FROM_VERIFIED_CONFIGURATION",
            "orpt_time": "DERIVED_FROM_VERIFIED_CONFIGURATION",
            "rc_time": "DERIVED_FROM_VERIFIED_CONFIGURATION",
            "market_observations": "CAPTURED",
            "option_contract_quote": "CAPTURED where present",
            "eod_evaluation_time": "MISSING unless explicitly included from verified configuration",
        },
        capture_classification="CAPTURED_WITH_DERIVED_CONFIGURATION_EVENTS",
    )


def _load_jsonl(path: str | Path) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return tuple(rows)


def _events_from_record(
    record: Mapping[str, Any],
    *,
    session_id: str,
    source_path: str,
    strategy_instance_id: str,
    selected_contract: str | None,
    sequence_start: int,
    record_index: int,
    policy: ReplayClockPolicy,
) -> tuple[NormalizedRuntimeEvent, ...]:
    event_type = str(record.get("event_type", ""))
    payload = dict(record.get("payload") or {})
    effective = _parse_dt(record.get("effective_timestamp"))
    captured_at = _parse_dt(record.get("captured_at")) or effective
    session_date = date.fromisoformat(str(record.get("session_date")))
    provenance = _captured_provenance(record, source_path, record_index)
    exchange = "NSE"
    session = "regular"
    if event_type == "UNDERLYING_SNAPSHOT":
        label = str(payload.get("snapshot_label", ""))
        runtime_type = RuntimeEventType.SESSION_OPEN_OBSERVATION if label == "0915" else RuntimeEventType.OPENING_BAR_AVAILABLE
        return (
            _event(
                session_id,
                runtime_type,
                session_date,
                exchange,
                session,
                effective,
                captured_at,
                sequence_start,
                "NSE:NIFTY",
                None,
                strategy_instance_id,
                provenance,
                _freshness(effective, captured_at, policy),
                {
                    "snapshot_label": label,
                    "open": payload.get("open"),
                    "high": payload.get("high"),
                    "low": payload.get("low"),
                    "close": payload.get("close"),
                    "opening_value": payload.get("open") if label == "0915" else None,
                    "source_market_timestamp": effective.isoformat(),
                    "captured_timestamp": captured_at.isoformat(),
                },
            ),
        )
    if event_type == "UNDERLYING_QUOTE":
        return (
            _event(
                session_id,
                RuntimeEventType.UNDERLYING_QUOTE,
                session_date,
                exchange,
                session,
                effective,
                captured_at,
                sequence_start,
                "NSE:NIFTY",
                None,
                strategy_instance_id,
                provenance,
                _freshness(effective, captured_at, policy),
                {
                    "ltp": payload.get("ltp"),
                    "bid": payload.get("bid"),
                    "ask": payload.get("ask"),
                    "volume": payload.get("volume"),
                    "source_market_timestamp": effective.isoformat(),
                    "captured_timestamp": captured_at.isoformat(),
                },
            ),
        )
    if event_type == "SELECTED_CONTRACT_QUOTE":
        contract = str(payload.get("symbol") or selected_contract or "")
        return (
            _event(
                session_id,
                RuntimeEventType.OPTION_CONTRACT_QUOTE,
                session_date,
                exchange,
                session,
                effective,
                captured_at,
                sequence_start,
                "NSE:NIFTY",
                contract,
                strategy_instance_id,
                provenance,
                _freshness(effective, captured_at, policy),
                {
                    "ltp": payload.get("ltp"),
                    "bid": payload.get("bid"),
                    "ask": payload.get("ask"),
                    "oi": payload.get("oi"),
                    "volume": payload.get("volume"),
                    "option_type": payload.get("option_type"),
                    "strike": payload.get("strike"),
                    "expiry": payload.get("expiry"),
                    "source_market_timestamp": effective.isoformat(),
                    "captured_timestamp": captured_at.isoformat(),
                },
            ),
        )
    if event_type == "OPTION_CHAIN_SNAPSHOT":
        events = []
        for offset, contract_payload in enumerate(payload.get("contracts") or ()):
            contract = str(contract_payload.get("symbol") or "")
            runtime_type = RuntimeEventType.OPTION_CONTRACT_QUOTE if contract == selected_contract else RuntimeEventType.OI_UPDATE
            events.append(
                _event(
                    session_id,
                    runtime_type,
                    session_date,
                    exchange,
                    session,
                    effective,
                    captured_at,
                    sequence_start + offset,
                    "NSE:NIFTY",
                    contract,
                    strategy_instance_id if contract == selected_contract else None,
                    provenance | {"option_chain_contract": contract},
                    _freshness(effective, captured_at, policy),
                    {
                        "ltp": contract_payload.get("ltp"),
                        "bid": contract_payload.get("bid"),
                        "ask": contract_payload.get("ask"),
                        "oi": contract_payload.get("oi"),
                        "volume": contract_payload.get("volume"),
                        "option_type": contract_payload.get("option_type"),
                        "strike": contract_payload.get("strike"),
                        "expiry": contract_payload.get("expiry"),
                        "source_market_timestamp": effective.isoformat(),
                        "captured_timestamp": captured_at.isoformat(),
                    },
                )
            )
        return tuple(events)
    return ()


def _derived_clock_events(
    *,
    trading_date: date,
    session_id: str,
    source_path: str,
    strategy_instance_id: str,
    policy: ReplayClockPolicy,
    include_eod_clock: bool,
    include_session_end_clock: bool,
) -> tuple[NormalizedRuntimeEvent, ...]:
    items = [
        ("configuration", RuntimeEventType.CONFIGURATION_READY, policy.premarket_time, {"configuration_state": "ready"}),
        ("strategy-enabled", RuntimeEventType.STRATEGY_ENABLED, policy.premarket_time, {"strategy_state": "enabled"}),
        ("premarket", RuntimeEventType.PREMARKET_PREPARATION_TIME, policy.premarket_time, {"preparation": "ready"}),
        ("orpt", RuntimeEventType.ORPT_TIME, policy.orpt_time, {"configured_time": policy.orpt_time.isoformat()}),
        ("rc", RuntimeEventType.RC_TIME, policy.rc_time, {"configured_time": policy.rc_time.isoformat()}),
    ]
    if include_eod_clock:
        items.append(("eod", RuntimeEventType.EOD_EVALUATION_TIME, policy.eod_evaluation_time, {"configured_time": policy.eod_evaluation_time.isoformat()}))
    if include_session_end_clock:
        items.append(("session-end", RuntimeEventType.SESSION_END_TIME, policy.session_end_time, {"configured_time": policy.session_end_time.isoformat()}))
    events = []
    for index, (label, runtime_type, clock_time, payload) in enumerate(items, start=1):
        ts = datetime.combine(trading_date, clock_time, tzinfo=IST)
        events.append(
            _event(
                session_id,
                runtime_type,
                trading_date,
                "NSE",
                "regular",
                ts,
                ts,
                index,
                "NSE:NIFTY",
                None,
                strategy_instance_id,
                {
                    "source_classification": "DERIVED_FROM_VERIFIED_CONFIGURATION",
                    "source_path": source_path,
                    "derived_event": label,
                },
                RuntimeFreshness.FRESH,
                payload | {"source_market_timestamp": None, "captured_timestamp": None},
            )
        )
    return tuple(events)


def _event(
    session_id: str,
    event_type: RuntimeEventType,
    trading_date: date,
    exchange: str,
    session: str,
    effective: datetime,
    captured_at: datetime,
    sequence: int,
    instrument: str | None,
    contract: str | None,
    strategy: str | None,
    provenance: Mapping[str, Any],
    freshness: RuntimeFreshness,
    payload: Mapping[str, Any],
) -> NormalizedRuntimeEvent:
    identity_payload = {
        "session_id": session_id,
        "event_type": event_type.value,
        "effective_timestamp": effective.isoformat(),
        "source_timestamp": captured_at.isoformat(),
        "sequence": sequence,
        "instrument": instrument,
        "contract": contract,
        "payload": payload,
    }
    event_hash = runtime_hash(identity_payload)[:20]
    return NormalizedRuntimeEvent(
        event_id=f"{session_id}:{sequence:06d}:{event_type.value}:{event_hash}",
        event_type=event_type,
        trading_date=trading_date,
        exchange=exchange,
        session=session,
        effective_timestamp=effective,
        source_timestamp=effective,
        dispatch_timestamp=captured_at,
        sequence_identity=sequence,
        instrument_identity=instrument,
        contract_identity=contract,
        strategy_instance_target=strategy,
        provenance=provenance,
        freshness=freshness,
        payload=payload,
    )


def _diagnostics(
    records: tuple[Mapping[str, Any], ...],
    events: tuple[NormalizedRuntimeEvent, ...],
    captured_count: int,
    derived_count: int,
) -> CapturedReplayDiagnostics:
    source_times = [_parse_dt(record.get("effective_timestamp")) for record in records]
    valid_times = [item for item in source_times if item is not None]
    missing = sum(1 for item in source_times if item is None)
    duplicates = len(valid_times) - len(set(valid_times))
    backward = sum(1 for prev, cur in zip(valid_times, valid_times[1:]) if cur < prev)
    future = sum(1 for item in valid_times if item.date() > _session_date(records))
    by_time = tuple(sorted(events, key=lambda item: (item.effective_timestamp, item.sequence_identity, item.event_id)))
    dispatch_ordering_difference = sum(1 for left, right in zip(events, by_time) if left.event_id != right.event_id)
    seen: dict[str, dict[str, Any]] = {}
    exact = 0
    conflict = 0
    for event in events:
        prior = seen.get(event.event_id)
        current = event.to_dict()
        if prior is None:
            seen[event.event_id] = current
        elif prior == current:
            exact += 1
        else:
            conflict += 1
    return CapturedReplayDiagnostics(
        raw_record_count=len(records),
        normalized_event_count=len(events),
        captured_event_count=captured_count,
        derived_configuration_event_count=derived_count,
        missing_timestamp_count=missing,
        duplicate_source_timestamp_count=duplicates,
        backward_source_timestamp_count=backward,
        future_source_timestamp_count=future,
        dispatch_ordering_difference_count=dispatch_ordering_difference,
        exact_duplicate_event_count=exact,
        conflicting_duplicate_event_count=conflict,
        event_identity_hash=runtime_hash([event.event_id for event in events]),
    )


def _captured_provenance(record: Mapping[str, Any], source_path: str, record_index: int) -> dict[str, Any]:
    return {
        "source_classification": "CAPTURED",
        "source_path": source_path,
        "source_type": record.get("source_type"),
        "source_id": record.get("source_id"),
        "source_sequence": record.get("source_sequence"),
        "record_index": record_index,
        "normalized_by": record.get("normalized_by"),
        "data_quality_flags": tuple(record.get("data_quality_flags") or ()),
    }


def _freshness(effective: datetime, captured_at: datetime, policy: ReplayClockPolicy) -> RuntimeFreshness:
    age = abs((captured_at - effective).total_seconds())
    if age > policy.max_fresh_age_seconds:
        return RuntimeFreshness.STALE
    return RuntimeFreshness.FRESH


def _session_date(records: Iterable[Mapping[str, Any]]) -> date:
    first = next(iter(records))
    value = first.get("session_date")
    if not value:
        raise ValueError("captured replay records must include session_date")
    return date.fromisoformat(str(value))


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=IST)
    return parsed
