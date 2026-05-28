from __future__ import annotations

import csv
import json
import calendar
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tfis.domain.enums import OptionType
from tfis.paper.models import PaperEventType, SnapshotLabel

_ARTIFACT_VERSION = 1
_IST = ZoneInfo("Asia/Kolkata")
_RAW_UNDERLYING_SYMBOL = "NSE:NIFTY50-INDEX"
_NORMALIZED_UNDERLYING_SYMBOL = "NIFTY"
_NORMALIZED_BY = "tradingengine-capture-adapter-v1"
_SOURCE_TYPE = "tradingengine_capture"
_OPTION_EXPIRY_RE = re.compile(r"^(?P<yy>\d{2})(?P<month>[1-9OND])(?P<day>\d{2})$")
_MONTHLY_EXPIRY_RE = re.compile(r"^(?P<yy>\d{2})(?P<month_text>[A-Z]{3})$")
_OPTION_SYMBOL_RE = re.compile(
    r"^NSE:NIFTY(?P<expiry>[0-9OND]{5})(?P<strike>\d+)(?P<option_type>CE|PE)$"
)
_MONTHLY_OPTION_SYMBOL_RE = re.compile(
    r"^NSE:NIFTY(?P<expiry>\d{2}[A-Z]{3})(?P<strike>\d+)(?P<option_type>CE|PE)$"
)
_SNAPSHOT_WINDOWS: dict[SnapshotLabel, tuple[time, time, time]] = {
    SnapshotLabel.AT_0915: (time(9, 14, 0), time(9, 15, 0), time(9, 15, 0)),
    SnapshotLabel.ORPT: (time(9, 23, 59), time(9, 24, 59), time(9, 24, 59)),
    SnapshotLabel.RC: (time(9, 28, 59), time(9, 29, 59), time(9, 29, 59)),
}


class TradingEngineCaptureAdapterError(RuntimeError):
    """Raised when a TradingEngine capture cannot be adapted safely."""


@dataclass(frozen=True, slots=True)
class TradingEngineCaptureAuditSummary:
    artifact_version: int
    context_session_dir: str
    ticks_context_path: str
    option_quotes_path: str | None
    session_id: str
    session_date: str
    session_status: str | None
    started_at: str | None
    ended_at: str | None
    context_columns: tuple[str, ...]
    option_quote_columns: tuple[str, ...]
    first_underlying_timestamp: str | None
    last_underlying_timestamp: str | None
    covers_0915: bool
    covers_orpt: bool
    covers_rc: bool
    capture_sequence_monotonic: bool
    context_timestamp_monotonic: bool
    underlying_timestamp_monotonic: bool
    max_underlying_gap_seconds: float | None
    underlying_row_count: int
    underlying_rows_with_selected_contract: int
    option_symbol_rows_in_context: int
    option_chain_contract_count_at_rc: int
    selected_contract_observed_at_rc: str | None
    has_option_quotes_archive: bool
    sample_raw_option_symbol: str | None
    sample_normalized_option_symbol: str | None
    recommendation: str
    warnings: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    converter_scope: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TradingEngineConvertedArtifactSet:
    audit: TradingEngineCaptureAuditSummary
    output_jsonl_path: Path
    output_event_count: int
    selected_contract_symbol: str
    normalized_selected_contract_symbol: str


@dataclass(frozen=True, slots=True)
class _ContextRow:
    capture_sequence: int
    timestamp: datetime
    raw: dict[str, str]


@dataclass(frozen=True, slots=True)
class _OptionQuoteRow:
    timestamp: datetime
    option_symbol: str
    strike: float | None
    option_type: OptionType | None
    expiry: date | None
    ltp: float | None
    bid: float | None
    ask: float | None
    volume: float | None
    oi: float | None


def discover_context_session_dir(
    *,
    tradingdata_root: str | Path,
    session_date: str | date,
) -> Path:
    target_date = (
        date.fromisoformat(session_date) if isinstance(session_date, str) else session_date
    )
    date_dir = (
        Path(tradingdata_root)
        / "captures"
        / "context_sessions"
        / target_date.isoformat()
    )
    if not date_dir.exists():
        raise TradingEngineCaptureAdapterError(
            f"No context_sessions directory exists for {target_date.isoformat()} under {tradingdata_root}."
        )
    candidates: list[tuple[int, int, float, Path]] = []
    rc_deadline = datetime.combine(target_date, time(9, 29, 59))
    decision_start = datetime.combine(target_date, time(9, 15, 0))
    for session_dir in sorted(path for path in date_dir.iterdir() if path.is_dir()):
        manifest_path = session_dir / "session_manifest.json"
        ticks_path = session_dir / "ticks_context.csv"
        if not manifest_path.exists() or not ticks_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        started_at = _parse_manifest_datetime(manifest.get("started_at"))
        ended_at = _parse_manifest_datetime(manifest.get("ended_at"))
        status = str(manifest.get("status", "")).lower()
        status_score = 2 if status == "completed" else 1 if status == "interrupted" else 0
        coverage_score = 0
        if started_at is not None and ended_at is not None:
            if started_at <= decision_start and ended_at >= rc_deadline:
                coverage_score = 2
            elif ended_at >= rc_deadline:
                coverage_score = 1
        duration_seconds = (
            (ended_at - started_at).total_seconds()
            if started_at is not None and ended_at is not None
            else 0.0
        )
        candidates.append((coverage_score, status_score, duration_seconds, session_dir))
    if not candidates:
        raise TradingEngineCaptureAdapterError(
            f"No usable context session folders were discovered under {date_dir}."
        )
    return max(candidates)[3]


def infer_option_quotes_path(
    *,
    tradingdata_root: str | Path,
    session_date: str | date,
) -> Path:
    target_date = (
        date.fromisoformat(session_date) if isinstance(session_date, str) else session_date
    )
    compact = target_date.strftime("%Y%m%d")
    option_quotes_path = (
        Path(tradingdata_root)
        / "data"
        / "nifty"
        / compact
        / "options"
        / "index"
        / f"NIFTY50_option_quotes_{compact}.csv"
    )
    if not option_quotes_path.exists():
        raise TradingEngineCaptureAdapterError(
            f"Matching NIFTY option quote archive was not found: {option_quotes_path}"
        )
    return option_quotes_path


def build_capture_audit(
    *,
    context_session_dir: str | Path,
    option_quotes_path: str | Path | None = None,
) -> TradingEngineCaptureAuditSummary:
    session_dir = Path(context_session_dir)
    ticks_context_path = session_dir / "ticks_context.csv"
    manifest_path = session_dir / "session_manifest.json"
    if not ticks_context_path.exists():
        raise TradingEngineCaptureAdapterError(
            f"ticks_context.csv was not found under {session_dir}"
        )
    if not manifest_path.exists():
        raise TradingEngineCaptureAdapterError(
            f"session_manifest.json was not found under {session_dir}"
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    session_date = _derive_session_date(session_dir, manifest)
    context_rows = _load_context_rows(ticks_context_path)
    underlying_rows = [row for row in context_rows if row.raw.get("symbol") == _RAW_UNDERLYING_SYMBOL]
    option_rows = [
        row
        for row in context_rows
        if _looks_like_raw_option_symbol(row.raw.get("symbol"))
    ]
    option_quotes_target = Path(option_quotes_path) if option_quotes_path else None
    option_quote_rows: tuple[_OptionQuoteRow, ...] = ()
    option_quote_columns: tuple[str, ...] = ()
    if option_quotes_target is not None and option_quotes_target.exists():
        option_quote_rows, option_quote_columns = _load_option_quote_rows(option_quotes_target)

    covers = {
        label: bool(_rows_in_window(underlying_rows, session_date, label))
        for label in _SNAPSHOT_WINDOWS
    }
    capture_sequence_monotonic = _is_capture_sequence_monotonic(context_rows)
    context_timestamp_monotonic = _is_timestamp_monotonic(context_rows)
    underlying_timestamp_monotonic = _is_timestamp_monotonic(underlying_rows)
    max_underlying_gap_seconds = _max_gap_seconds(underlying_rows)
    rc_rows = _rows_in_window(underlying_rows, session_date, SnapshotLabel.RC)
    selected_contract_at_rc = next(
        (
            row.raw.get("selected_option_symbol")
            for row in reversed(rc_rows)
            if (row.raw.get("selected_option_symbol") or "").strip()
        ),
        None,
    )
    sample_raw_option_symbol = None
    sample_normalized_option_symbol = None
    if option_quote_rows:
        sample_raw_option_symbol = option_quote_rows[0].option_symbol
        sample_normalized_option_symbol = normalize_tradingengine_option_symbol(
            sample_raw_option_symbol,
            expiry=_format_date(option_quote_rows[0].expiry),
            strike=option_quote_rows[0].strike,
            option_type=option_quote_rows[0].option_type,
        )
    option_chain_contract_count_at_rc = 0
    if option_quote_rows:
        rc_quotes = _latest_option_quotes_at_or_before(
            option_quote_rows,
            _snapshot_effective_datetime(session_date, SnapshotLabel.RC),
            freshness_limit=timedelta(seconds=60),
        )
        option_chain_contract_count_at_rc = len(rc_quotes)

    warnings: list[str] = []
    if not context_timestamp_monotonic:
        warnings.append(
            "ticks_context.csv is not globally timestamp ordered; normalize by "
            "capture_sequence and explicit timestamps rather than file order alone."
        )
    if not underlying_timestamp_monotonic:
        warnings.append(
            "NIFTY underlying rows are not perfectly timestamp ordered in the raw "
            "capture; minute-window aggregation should sort within each window."
        )
    if max_underlying_gap_seconds is not None and max_underlying_gap_seconds > 30:
        warnings.append(
            f"Underlying quote gaps reach {max_underlying_gap_seconds:.1f}s in this session."
        )
    if not option_quote_rows:
        warnings.append(
            "Option quote archive is missing; option-chain and selected-contract "
            "conversion cannot be emitted safely."
        )
    if not selected_contract_at_rc:
        warnings.append(
            "No selected_option_symbol is embedded on NIFTY rows during the RC window; "
            "selected contract must be supplied externally for deterministic conversion."
        )

    missing_requirements: list[str] = []
    if not covers[SnapshotLabel.AT_0915]:
        missing_requirements.append("missing_0915_window")
    if not covers[SnapshotLabel.ORPT]:
        missing_requirements.append("missing_orpt_window")
    if not covers[SnapshotLabel.RC]:
        missing_requirements.append("missing_rc_window")
    if not option_quote_rows:
        missing_requirements.append("missing_option_quote_archive")

    recommendation = "partially_usable"
    if not covers[SnapshotLabel.RC] or not option_quote_rows:
        recommendation = "not_usable"
    elif all(covers.values()):
        recommendation = "usable"

    return TradingEngineCaptureAuditSummary(
        artifact_version=_ARTIFACT_VERSION,
        context_session_dir=str(session_dir),
        ticks_context_path=str(ticks_context_path),
        option_quotes_path=str(option_quotes_target) if option_quotes_target else None,
        session_id=str(manifest.get("session_id", session_dir.name)),
        session_date=session_date.isoformat(),
        session_status=_optional_text(manifest.get("status")),
        started_at=_optional_text(manifest.get("started_at")),
        ended_at=_optional_text(manifest.get("ended_at")),
        context_columns=tuple(context_rows[0].raw.keys()) if context_rows else (),
        option_quote_columns=option_quote_columns,
        first_underlying_timestamp=underlying_rows[0].timestamp.isoformat() if underlying_rows else None,
        last_underlying_timestamp=underlying_rows[-1].timestamp.isoformat() if underlying_rows else None,
        covers_0915=covers[SnapshotLabel.AT_0915],
        covers_orpt=covers[SnapshotLabel.ORPT],
        covers_rc=covers[SnapshotLabel.RC],
        capture_sequence_monotonic=capture_sequence_monotonic,
        context_timestamp_monotonic=context_timestamp_monotonic,
        underlying_timestamp_monotonic=underlying_timestamp_monotonic,
        max_underlying_gap_seconds=max_underlying_gap_seconds,
        underlying_row_count=len(underlying_rows),
        underlying_rows_with_selected_contract=sum(
            1 for row in underlying_rows if (row.raw.get("selected_option_symbol") or "").strip()
        ),
        option_symbol_rows_in_context=len(option_rows),
        option_chain_contract_count_at_rc=option_chain_contract_count_at_rc,
        selected_contract_observed_at_rc=selected_contract_at_rc,
        has_option_quotes_archive=bool(option_quote_rows),
        sample_raw_option_symbol=sample_raw_option_symbol,
        sample_normalized_option_symbol=sample_normalized_option_symbol,
        recommendation=recommendation,
        warnings=tuple(warnings),
        missing_requirements=tuple(missing_requirements),
        converter_scope=(
            "market_events_only",
            "requires_external_prelude_for_calendar_monthly_status_trade_plan",
            "read_only_source_inputs",
        ),
    )


def convert_capture_to_normalized_market_events(
    *,
    context_session_dir: str | Path,
    option_quotes_path: str | Path,
    selected_contract_symbol: str,
    output_jsonl_path: str | Path,
) -> TradingEngineConvertedArtifactSet:
    audit = build_capture_audit(
        context_session_dir=context_session_dir,
        option_quotes_path=option_quotes_path,
    )
    if audit.recommendation == "not_usable":
        raise TradingEngineCaptureAdapterError(
            "This capture session does not safely cover the S23 RC dry-run window."
        )
    if audit.missing_requirements:
        raise TradingEngineCaptureAdapterError(
            "Cannot convert capture safely because required windows or archives are missing: "
            + ", ".join(audit.missing_requirements)
        )

    session_dir = Path(context_session_dir)
    ticks_context_path = session_dir / "ticks_context.csv"
    context_rows = _load_context_rows(ticks_context_path)
    underlying_rows = [row for row in context_rows if row.raw.get("symbol") == _RAW_UNDERLYING_SYMBOL]
    option_quote_rows, _ = _load_option_quote_rows(Path(option_quotes_path))
    session_date = date.fromisoformat(audit.session_date)
    rc_effective = _snapshot_effective_datetime(session_date, SnapshotLabel.RC)
    selected_quote = _latest_quote_for_symbol(
        option_quote_rows,
        raw_symbol=selected_contract_symbol,
        effective_time=rc_effective,
        freshness_limit=timedelta(seconds=60),
    )
    if selected_quote is None:
        raise TradingEngineCaptureAdapterError(
            f"No fresh option quote was found at RC for {selected_contract_symbol}."
        )

    contracts = _latest_option_quotes_at_or_before(
        option_quote_rows,
        rc_effective,
        freshness_limit=timedelta(seconds=60),
    )
    if selected_contract_symbol not in contracts:
        raise TradingEngineCaptureAdapterError(
            "The selected contract is missing from the RC option-chain snapshot."
        )

    output_path = Path(output_jsonl_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    quality_flags = list(audit.warnings)
    source_sequence = 1
    events: list[dict[str, Any]] = []
    for label in (SnapshotLabel.AT_0915, SnapshotLabel.ORPT, SnapshotLabel.RC):
        snapshot_rows = _rows_in_window(underlying_rows, session_date, label)
        if not snapshot_rows:
            raise TradingEngineCaptureAdapterError(
                f"Required {label.value} snapshot window is missing from the context capture."
            )
        snapshot_event = _build_underlying_snapshot_event(
            snapshot_rows=snapshot_rows,
            session_date=session_date,
            label=label,
            source_sequence=source_sequence,
            source_id=str(ticks_context_path),
            quality_flags=quality_flags,
        )
        events.append(snapshot_event)
        source_sequence += 1

    latest_underlying = _latest_underlying_at_or_before(underlying_rows, rc_effective)
    if latest_underlying is None:
        raise TradingEngineCaptureAdapterError("No NIFTY underlying quote was found at RC.")

    events.append(
        _build_underlying_quote_event(
            row=latest_underlying,
            session_date=session_date,
            source_sequence=source_sequence,
            source_id=str(ticks_context_path),
            quality_flags=quality_flags,
        )
    )
    source_sequence += 1

    option_chain_event = _build_option_chain_snapshot_event(
        contracts=tuple(contracts.values()),
        session_date=session_date,
        effective_time=rc_effective,
        source_sequence=source_sequence,
        source_id=str(option_quotes_path),
        quality_flags=quality_flags,
    )
    events.append(option_chain_event)
    source_sequence += 1

    events.append(
        _build_selected_contract_quote_event(
            quote=selected_quote,
            session_date=session_date,
            effective_time=rc_effective,
            source_sequence=source_sequence,
            source_id=str(option_quotes_path),
            quality_flags=quality_flags,
        )
    )

    output_path.write_text(
        "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
        encoding="utf-8",
    )
    return TradingEngineConvertedArtifactSet(
        audit=audit,
        output_jsonl_path=output_path,
        output_event_count=len(events),
        selected_contract_symbol=selected_contract_symbol,
        normalized_selected_contract_symbol=normalize_tradingengine_option_symbol(
            selected_contract_symbol,
            expiry=_format_date(selected_quote.expiry),
            strike=selected_quote.strike,
            option_type=selected_quote.option_type,
        ),
    )


def render_audit_json(summary: TradingEngineCaptureAuditSummary) -> str:
    return json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n"


def normalize_tradingengine_option_symbol(
    raw_symbol: str,
    *,
    expiry: str | None = None,
    strike: float | None = None,
    option_type: OptionType | None = None,
) -> str:
    if raw_symbol.startswith("NIFTY_"):
        return raw_symbol
    match = _OPTION_SYMBOL_RE.match(raw_symbol)
    monthly_match = _MONTHLY_OPTION_SYMBOL_RE.match(raw_symbol)
    if match is None and monthly_match is None and (
        expiry is None or strike is None or option_type is None
    ):
        raise TradingEngineCaptureAdapterError(
            f"Unsupported TradingEngine option symbol format: {raw_symbol}"
        )
    selected_match = match or monthly_match
    expiry_value = expiry or _decode_expiry_code(selected_match.group("expiry")).isoformat()
    strike_value = strike if strike is not None else float(selected_match.group("strike"))
    option_value = option_type or _option_type_from_raw(selected_match.group("option_type"))
    return f"NIFTY_{expiry_value.replace('-', '')}_{int(strike_value)}_{_option_suffix(option_value)}"


def _build_underlying_snapshot_event(
    *,
    snapshot_rows: list[_ContextRow],
    session_date: date,
    label: SnapshotLabel,
    source_sequence: int,
    source_id: str,
    quality_flags: list[str],
) -> dict[str, Any]:
    ordered = sorted(snapshot_rows, key=lambda row: (row.timestamp, row.capture_sequence))
    prices = [_require_float(row.raw.get("ltp"), "ltp") for row in ordered]
    window_start, window_end, effective = _SNAPSHOT_WINDOWS[label]
    effective_time = datetime.combine(session_date, effective, tzinfo=_IST)
    return {
        "event_type": PaperEventType.UNDERLYING_SNAPSHOT.value,
        "session_date": session_date.isoformat(),
        "effective_timestamp": effective_time.isoformat(),
        "captured_at": ordered[-1].timestamp.isoformat(),
        "timezone": "Asia/Kolkata",
        "source_type": _SOURCE_TYPE,
        "source_id": source_id,
        "synthetic_fixture": False,
        "normalized_by": _NORMALIZED_BY,
        "source_sequence": source_sequence,
        "data_quality_flags": quality_flags,
        "payload": {
            "snapshot_label": label.value,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "bar_start": datetime.combine(session_date, window_start, tzinfo=_IST).isoformat(),
            "bar_end": datetime.combine(session_date, window_end, tzinfo=_IST).isoformat(),
            "complete": True,
        },
    }


def _build_underlying_quote_event(
    *,
    row: _ContextRow,
    session_date: date,
    source_sequence: int,
    source_id: str,
    quality_flags: list[str],
) -> dict[str, Any]:
    return {
        "event_type": PaperEventType.UNDERLYING_QUOTE.value,
        "session_date": session_date.isoformat(),
        "effective_timestamp": row.timestamp.isoformat(),
        "captured_at": (row.timestamp + timedelta(seconds=1)).isoformat(),
        "timezone": "Asia/Kolkata",
        "source_type": _SOURCE_TYPE,
        "source_id": source_id,
        "synthetic_fixture": False,
        "normalized_by": _NORMALIZED_BY,
        "source_sequence": source_sequence,
        "data_quality_flags": quality_flags,
        "payload": {
            "symbol": _NORMALIZED_UNDERLYING_SYMBOL,
            "ltp": _optional_float(row.raw.get("ltp")),
            "bid": None,
            "ask": None,
            "volume": _optional_float(row.raw.get("volume")),
            "source_latency_ms": None,
        },
    }


def _build_option_chain_snapshot_event(
    *,
    contracts: tuple[_OptionQuoteRow, ...],
    session_date: date,
    effective_time: datetime,
    source_sequence: int,
    source_id: str,
    quality_flags: list[str],
) -> dict[str, Any]:
    if not contracts:
        raise TradingEngineCaptureAdapterError("No option-chain contracts were available at RC.")
    expiry = contracts[0].expiry
    if expiry is None:
        raise TradingEngineCaptureAdapterError("RC option-chain contracts are missing expiry metadata.")
    payload_contracts = [
        {
            "symbol": normalize_tradingengine_option_symbol(
                contract.option_symbol,
                expiry=_format_date(contract.expiry),
                strike=contract.strike,
                option_type=contract.option_type,
            ),
            "option_type": contract.option_type.value if contract.option_type is not None else None,
            "strike": contract.strike,
            "expiry": _format_date(contract.expiry),
            "bid": contract.bid,
            "ask": contract.ask,
            "ltp": contract.ltp,
            "oi": contract.oi,
            "volume": contract.volume,
        }
        for contract in sorted(
            contracts,
            key=lambda contract: (
                contract.strike if contract.strike is not None else float("inf"),
                contract.option_type.value if contract.option_type is not None else "",
            ),
        )
    ]
    return {
        "event_type": PaperEventType.OPTION_CHAIN_SNAPSHOT.value,
        "session_date": session_date.isoformat(),
        "effective_timestamp": effective_time.isoformat(),
        "captured_at": (effective_time + timedelta(seconds=2)).isoformat(),
        "timezone": "Asia/Kolkata",
        "source_type": _SOURCE_TYPE,
        "source_id": source_id,
        "synthetic_fixture": False,
        "normalized_by": _NORMALIZED_BY,
        "source_sequence": source_sequence,
        "data_quality_flags": quality_flags,
        "payload": {
            "underlying_symbol": _NORMALIZED_UNDERLYING_SYMBOL,
            "expiry": expiry.isoformat(),
            "contracts": payload_contracts,
        },
    }


def _build_selected_contract_quote_event(
    *,
    quote: _OptionQuoteRow,
    session_date: date,
    effective_time: datetime,
    source_sequence: int,
    source_id: str,
    quality_flags: list[str],
) -> dict[str, Any]:
    return {
        "event_type": PaperEventType.SELECTED_CONTRACT_QUOTE.value,
        "session_date": session_date.isoformat(),
        "effective_timestamp": effective_time.isoformat(),
        "captured_at": (effective_time + timedelta(seconds=2)).isoformat(),
        "timezone": "Asia/Kolkata",
        "source_type": _SOURCE_TYPE,
        "source_id": source_id,
        "synthetic_fixture": False,
        "normalized_by": _NORMALIZED_BY,
        "source_sequence": source_sequence,
        "data_quality_flags": quality_flags,
        "payload": {
            "symbol": normalize_tradingengine_option_symbol(
                quote.option_symbol,
                expiry=_format_date(quote.expiry),
                strike=quote.strike,
                option_type=quote.option_type,
            ),
            "option_type": quote.option_type.value if quote.option_type is not None else None,
            "strike": quote.strike,
            "expiry": _format_date(quote.expiry),
            "bid": quote.bid,
            "ask": quote.ask,
            "ltp": quote.ltp,
            "oi": quote.oi,
            "volume": quote.volume,
        },
    }


def _load_context_rows(path: Path) -> tuple[_ContextRow, ...]:
    rows: list[_ContextRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            timestamp = raw.get("timestamp")
            capture_sequence = raw.get("capture_sequence")
            if not timestamp or not capture_sequence:
                continue
            rows.append(
                _ContextRow(
                    capture_sequence=int(capture_sequence),
                    timestamp=datetime.fromisoformat(timestamp),
                    raw=raw,
                )
            )
    if not rows:
        raise TradingEngineCaptureAdapterError(f"No rows were found in {path}.")
    return tuple(rows)


def _load_option_quote_rows(path: Path) -> tuple[tuple[_OptionQuoteRow, ...], tuple[str, ...]]:
    rows: list[_OptionQuoteRow] = []
    fieldnames: tuple[str, ...] = ()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(reader.fieldnames or ())
        for raw in reader:
            option_symbol = raw.get("option_symbol")
            timestamp = raw.get("timestamp")
            if not option_symbol or not timestamp:
                continue
            expiry = _decode_expiry_code(raw.get("expiry"))
            rows.append(
                _OptionQuoteRow(
                    timestamp=datetime.fromisoformat(timestamp),
                    option_symbol=option_symbol,
                    strike=_optional_float(raw.get("strike")),
                    option_type=_option_type_from_raw(raw.get("option_type")),
                    expiry=expiry,
                    ltp=_optional_float(raw.get("ltp")),
                    bid=_optional_float(raw.get("bid")),
                    ask=_optional_float(raw.get("ask")),
                    volume=_optional_float(raw.get("volume")),
                    oi=_optional_float(raw.get("oi")),
                )
            )
    if not rows:
        raise TradingEngineCaptureAdapterError(f"No option quote rows were found in {path}.")
    return tuple(rows), fieldnames


def _rows_in_window(
    rows: list[_ContextRow] | tuple[_ContextRow, ...],
    session_date: date,
    label: SnapshotLabel,
) -> list[_ContextRow]:
    start_time, end_time, _ = _SNAPSHOT_WINDOWS[label]
    start_dt = datetime.combine(session_date, start_time, tzinfo=_IST)
    end_dt = datetime.combine(session_date, end_time, tzinfo=_IST)
    filtered = [row for row in rows if start_dt < row.timestamp <= end_dt]
    return sorted(filtered, key=lambda row: (row.timestamp, row.capture_sequence))


def _latest_underlying_at_or_before(
    rows: list[_ContextRow],
    effective_time: datetime,
) -> _ContextRow | None:
    filtered = [row for row in rows if row.timestamp <= effective_time]
    if not filtered:
        return None
    return max(filtered, key=lambda row: (row.timestamp, row.capture_sequence))


def _latest_option_quotes_at_or_before(
    rows: tuple[_OptionQuoteRow, ...],
    effective_time: datetime,
    *,
    freshness_limit: timedelta,
) -> dict[str, _OptionQuoteRow]:
    latest: dict[str, _OptionQuoteRow] = {}
    for row in rows:
        if row.timestamp > effective_time:
            continue
        if effective_time - row.timestamp > freshness_limit:
            continue
        current = latest.get(row.option_symbol)
        if current is None or row.timestamp > current.timestamp:
            latest[row.option_symbol] = row
    return latest


def _latest_quote_for_symbol(
    rows: tuple[_OptionQuoteRow, ...],
    *,
    raw_symbol: str,
    effective_time: datetime,
    freshness_limit: timedelta,
) -> _OptionQuoteRow | None:
    latest = _latest_option_quotes_at_or_before(
        rows,
        effective_time,
        freshness_limit=freshness_limit,
    )
    return latest.get(raw_symbol)


def _snapshot_effective_datetime(session_date: date, label: SnapshotLabel) -> datetime:
    _, _, effective_time = _SNAPSHOT_WINDOWS[label]
    return datetime.combine(session_date, effective_time, tzinfo=_IST)


def _is_capture_sequence_monotonic(rows: tuple[_ContextRow, ...]) -> bool:
    previous = None
    for row in rows:
        if previous is not None and row.capture_sequence <= previous:
            return False
        previous = row.capture_sequence
    return True


def _is_timestamp_monotonic(rows: list[_ContextRow] | tuple[_ContextRow, ...]) -> bool:
    previous = None
    for row in rows:
        if previous is not None and row.timestamp < previous:
            return False
        previous = row.timestamp
    return True


def _max_gap_seconds(rows: list[_ContextRow] | tuple[_ContextRow, ...]) -> float | None:
    if len(rows) < 2:
        return None
    ordered = sorted(rows, key=lambda row: (row.timestamp, row.capture_sequence))
    max_gap = 0.0
    previous = ordered[0].timestamp
    for row in ordered[1:]:
        gap = (row.timestamp - previous).total_seconds()
        if gap > max_gap:
            max_gap = gap
        previous = row.timestamp
    return max_gap


def _derive_session_date(session_dir: Path, manifest: dict[str, Any]) -> date:
    parent_name = session_dir.parent.name
    try:
        return date.fromisoformat(parent_name)
    except ValueError:
        started_at = manifest.get("started_at")
        if not started_at:
            raise TradingEngineCaptureAdapterError(
                f"Could not derive session date for {session_dir}."
            )
        return datetime.fromisoformat(started_at).date()


def _parse_manifest_datetime(value: Any) -> datetime | None:
    text = _optional_text(value)
    if text is None:
        return None
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _decode_expiry_code(raw: str | None) -> date | None:
    if not raw:
        return None
    text = str(raw).strip()
    match = _OPTION_EXPIRY_RE.match(text)
    if match is not None:
        month_code = match.group("month")
        month_map = {
            "1": 1,
            "2": 2,
            "3": 3,
            "4": 4,
            "5": 5,
            "6": 6,
            "7": 7,
            "8": 8,
            "9": 9,
            "O": 10,
            "N": 11,
            "D": 12,
        }
        return date(
            year=2000 + int(match.group("yy")),
            month=month_map[month_code],
            day=int(match.group("day")),
        )
    monthly_match = _MONTHLY_EXPIRY_RE.match(text)
    if monthly_match is None:
        return None
    month_text_map = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }
    year = 2000 + int(monthly_match.group("yy"))
    month = month_text_map[monthly_match.group("month_text")]
    last_day = calendar.monthrange(year, month)[1]
    candidate = date(year, month, last_day)
    while candidate.weekday() != 3:
        candidate = candidate.replace(day=candidate.day - 1)
    return candidate


def _option_type_from_raw(raw: str | None) -> OptionType | None:
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip().upper()
    if text == "CE":
        return OptionType.CALL
    if text == "PE":
        return OptionType.PUT
    return None


def _option_suffix(option_type: OptionType) -> str:
    return "CE" if option_type is OptionType.CALL else "PE"


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_float(value: Any, field_name: str) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise TradingEngineCaptureAdapterError(f"Required numeric field `{field_name}` is missing.")
    return parsed


def _format_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _looks_like_raw_option_symbol(value: str | None) -> bool:
    if value is None:
        return False
    text = value.strip()
    return (
        _OPTION_SYMBOL_RE.match(text) is not None
        or _MONTHLY_OPTION_SYMBOL_RE.match(text) is not None
    )
