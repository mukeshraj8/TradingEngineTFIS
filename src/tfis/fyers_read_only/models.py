from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from enum import Enum
from io import StringIO
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


_IST = ZoneInfo("Asia/Kolkata")


class OIQuality(str, Enum):
    AVAILABLE = "AVAILABLE"
    ZERO = "ZERO"
    MISSING = "MISSING"
    MALFORMED = "MALFORMED"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class InstrumentMasterRecord:
    source_symbol: str
    instrument_id: str
    exchange: str
    segment: str
    instrument_type: str
    underlying: str | None
    expiry: date | None
    strike: Decimal | None
    option_type: str | None
    lot_size: int | None
    tick_size: Decimal | None
    instrument_token: str | None
    status: str
    source_row: Mapping[str, Any]
    source_version: str
    downloaded_at: datetime
    source_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class FyersCandle:
    symbol: str
    bar_start: datetime
    bar_end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    source_id: str
    complete: bool

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class CompletedCandleSet:
    symbol: str
    candles: tuple[FyersCandle, ...]
    excluded_incomplete: tuple[FyersCandle, ...]
    duplicate_count: int
    source_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class FyersQuote:
    symbol: str
    ltp: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    volume: Decimal | None
    oi: Decimal | None
    timestamp: datetime | None
    source_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class FyersMarketDepth:
    symbol: str
    bid_levels: tuple[Mapping[str, Any], ...]
    ask_levels: tuple[Mapping[str, Any], ...]
    oi: Decimal | None
    oi_quality: OIQuality
    timestamp: datetime | None
    source_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class FyersOptionContractQuote:
    symbol: str
    underlying: str
    expiry: date
    strike: Decimal
    option_type: str
    ltp: Decimal | None
    bid: Decimal | None
    ask: Decimal | None
    quote_timestamp: datetime | None
    oi: Decimal | None
    oi_quality: OIQuality
    oi_unit: str
    volume: Decimal | None
    lot_size: int | None
    tick_size: Decimal | None
    source_quality: str

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class FyersOptionChainSnapshot:
    underlying: str
    expiry: date | None
    captured_at: datetime
    contracts: tuple[FyersOptionContractQuote, ...]
    source_hash: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class MonthlyExpiryClassification:
    underlying: str
    near_monthly_expiry: date | None
    next_monthly_expiry: date | None
    all_expiries: tuple[date, ...]
    rule: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class ReferenceDataSnapshot:
    snapshot_id: str
    provider: str
    capture_date: date
    captured_at: datetime
    symbol_master_hash: str
    instruments: tuple[InstrumentMasterRecord, ...]
    candles: CompletedCandleSet | None
    option_chain: FyersOptionChainSnapshot | None
    validation_status: str
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


def canonical_hash(value: Any) -> str:
    rendered = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def normalize_symbol_master_rows(
    rows: Iterable[Mapping[str, Any]] | str,
    *,
    exchange: str,
    source_version: str,
    downloaded_at: datetime,
) -> tuple[InstrumentMasterRecord, ...]:
    source_rows = _rows_from_csv_or_iterable(rows)
    records: list[InstrumentMasterRecord] = []
    for row in source_rows:
        source_symbol = _first_text(row, "symbol", "Symbol", "fyers_symbol", "FYERS Symbol", "source_symbol")
        if not source_symbol:
            continue
        expiry = _parse_date(_first(row, "expiry", "expiryDate", "Expiry", "expiry_date"))
        strike = _decimal_or_none(_first(row, "strike", "strikePrice", "Strike", "strike_price"))
        option_type = _normalize_option_type(_first_text(row, "option_type", "optionType", "Option Type", "optType"))
        instrument_type = _first_text(row, "instrument_type", "instrumentType", "instrument", "Instrument", "type") or (
            "OPTION" if option_type else "EQUITY"
        )
        underlying = _first_text(row, "underlying", "underlying_symbol", "Underlying", "exSymbol", "ex_symbol")
        if not underlying:
            underlying = _infer_underlying(source_symbol)
        lot_size = _int_or_none(_first(row, "lot_size", "lotSize", "minLotSize", "Lot Size"))
        tick_size = _decimal_or_none(_first(row, "tick_size", "tickSize", "Tick Size"))
        token = _first_text(row, "instrument_token", "token", "fyToken", "fytoken", "instrumentToken")
        segment = _first_text(row, "segment", "Segment") or ("NSEFO" if option_type else "NSE")
        record_hash = canonical_hash({"row": dict(row), "source_version": source_version})
        records.append(
            InstrumentMasterRecord(
                source_symbol=source_symbol,
                instrument_id=_first_text(row, "instrument_id", "id", "fyToken", "token") or source_symbol,
                exchange=exchange,
                segment=segment,
                instrument_type=str(instrument_type).upper(),
                underlying=underlying.upper() if underlying else None,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=lot_size,
                tick_size=tick_size,
                instrument_token=token,
                status=_first_text(row, "status", "Status") or "ACTIVE",
                source_row=dict(row),
                source_version=source_version,
                downloaded_at=downloaded_at,
                source_hash=record_hash,
            )
        )
    return tuple(records)


def classify_monthly_expiries(
    records: Iterable[InstrumentMasterRecord],
    *,
    underlying: str,
    as_of: date,
) -> MonthlyExpiryClassification:
    expiries = sorted(
        {
            record.expiry
            for record in records
            if record.underlying == underlying.upper()
            and record.expiry is not None
            and record.expiry >= as_of
            and record.option_type in {"CALL", "PUT"}
        }
    )
    month_last_expiry: dict[tuple[int, int], date] = {}
    for expiry in expiries:
        month_last_expiry[(expiry.year, expiry.month)] = max(
            expiry,
            month_last_expiry.get((expiry.year, expiry.month), expiry),
        )
    monthly = sorted(set(month_last_expiry.values()))
    warnings: list[str] = []
    if len(monthly) < 2:
        warnings.append("MONTHLY_EXPIRY_CLASSIFICATION_INCOMPLETE")
    return MonthlyExpiryClassification(
        underlying=underlying.upper(),
        near_monthly_expiry=monthly[0] if monthly else None,
        next_monthly_expiry=monthly[1] if len(monthly) > 1 else None,
        all_expiries=tuple(expiries),
        rule="latest listed option expiry within each calendar month on or after as_of",
        warnings=tuple(warnings),
    )


def normalize_history_payload(
    payload: Mapping[str, Any] | list[Any],
    *,
    symbol: str,
    interval: str,
    source_id: str,
    as_of: datetime,
    exclude_incomplete_after: datetime | None = None,
) -> CompletedCandleSet:
    raw_candles = payload.get("candles") if isinstance(payload, Mapping) else payload
    if not isinstance(raw_candles, list):
        raise ValueError("FYERS history payload must contain a candles list.")
    seen: set[datetime] = set()
    candles: list[FyersCandle] = []
    excluded: list[FyersCandle] = []
    duplicate_count = 0
    duration = _interval_duration(interval)
    for raw in raw_candles:
        if not isinstance(raw, (list, tuple)) or len(raw) < 5:
            raise ValueError("FYERS candle row must contain timestamp, open, high, low, close.")
        start = _datetime_from_epoch_or_iso(raw[0])
        end = start.replace() if interval.upper() == "D" else start + duration
        if interval.upper() == "D":
            end = datetime.combine(start.date(), time(15, 29, 59), tzinfo=start.tzinfo or _IST)
        candle = FyersCandle(
            symbol=symbol.upper(),
            bar_start=start,
            bar_end=end,
            open=_decimal(raw[1]),
            high=_decimal(raw[2]),
            low=_decimal(raw[3]),
            close=_decimal(raw[4]),
            volume=_decimal_or_none(raw[5] if len(raw) > 5 else None),
            source_id=source_id,
            complete=(exclude_incomplete_after is None or end <= exclude_incomplete_after),
        )
        if candle.bar_start in seen:
            duplicate_count += 1
            continue
        seen.add(candle.bar_start)
        if candle.complete:
            candles.append(candle)
        else:
            excluded.append(candle)
    candles.sort(key=lambda item: item.bar_start)
    excluded.sort(key=lambda item: item.bar_start)
    return CompletedCandleSet(
        symbol=symbol.upper(),
        candles=tuple(candles),
        excluded_incomplete=tuple(excluded),
        duplicate_count=duplicate_count,
        source_hash=canonical_hash({"payload": payload, "symbol": symbol, "source_id": source_id, "as_of": as_of}),
    )


def normalize_quote_payload(payload: Mapping[str, Any], *, symbol: str) -> FyersQuote:
    record = _extract_quote_record(payload, symbol=symbol)
    values = record.get("v") if isinstance(record.get("v"), Mapping) else record
    return FyersQuote(
        symbol=symbol,
        ltp=_decimal_or_none(_first(values, "ltp", "lp", "last_price")),
        bid=_decimal_or_none(_first(values, "bid", "bid_price", "bid_price1")),
        ask=_decimal_or_none(_first(values, "ask", "ask_price", "ask_price1")),
        volume=_decimal_or_none(_first(values, "volume", "vol_traded_today")),
        oi=_decimal_or_none(_first(values, "oi", "open_interest")),
        timestamp=_datetime_or_none(_first(values, "timestamp", "tt", "last_traded_time")),
        source_hash=canonical_hash(payload),
    )


def normalize_market_depth_payload(payload: Mapping[str, Any], *, symbol: str) -> FyersMarketDepth:
    data = payload.get("d") or payload.get("data") or payload
    if isinstance(data, Mapping) and symbol in data:
        data = data[symbol]
    if not isinstance(data, Mapping):
        raise ValueError("FYERS depth payload must normalize to an object.")
    oi = _decimal_or_none(_first(data, "oi", "open_interest"))
    return FyersMarketDepth(
        symbol=symbol,
        bid_levels=tuple(data.get("bids") or data.get("bid") or ()),
        ask_levels=tuple(data.get("asks") or data.get("ask") or ()),
        oi=oi,
        oi_quality=_oi_quality(_first(data, "oi", "open_interest")),
        timestamp=_datetime_or_none(_first(data, "timestamp", "last_traded_time")),
        source_hash=canonical_hash(payload),
    )


def normalize_option_chain_payload(
    payload: Mapping[str, Any],
    *,
    underlying: str,
    expiry: date | None = None,
    instrument_records: Iterable[InstrumentMasterRecord] = (),
    captured_at: datetime,
) -> FyersOptionChainSnapshot:
    chain = (
        payload.get("optionsChain")
        or (payload.get("data") or {}).get("optionsChain")
        or (payload.get("data") or {}).get("options_chain")
        or payload.get("contracts")
        or []
    )
    if not isinstance(chain, list):
        raise ValueError("FYERS option-chain payload is missing optionsChain/contracts list.")
    metadata = {
        (record.source_symbol.upper(), record.expiry, record.strike, record.option_type): record
        for record in instrument_records
    }
    metadata_by_symbol = {record.source_symbol.upper(): record for record in instrument_records}
    contracts: list[FyersOptionContractQuote] = []
    warnings: list[str] = []
    for raw in chain:
        if not isinstance(raw, Mapping):
            warnings.append("MALFORMED_CONTRACT_ROW")
            continue
        symbol = _first_text(raw, "symbol", "option_symbol", "n")
        option_type = _normalize_option_type(_first_text(raw, "option_type", "optionType") or symbol[-2:])
        if not symbol or option_type not in {"CALL", "PUT"}:
            continue
        meta_by_symbol = metadata_by_symbol.get(symbol.upper())
        contract_expiry = _parse_date(_first(raw, "expiry", "expiryDate")) or expiry or (meta_by_symbol.expiry if meta_by_symbol else None)
        strike = _decimal_or_none(_first(raw, "strike", "strike_price", "strikePrice")) or (meta_by_symbol.strike if meta_by_symbol else None)
        if contract_expiry is None or strike is None:
            warnings.append(f"INCOMPLETE_CONTRACT_IDENTITY:{symbol}")
            continue
        meta = metadata.get((symbol.upper(), contract_expiry, strike, option_type)) or meta_by_symbol
        raw_oi = _first(raw, "oi", "open_interest")
        contracts.append(
            FyersOptionContractQuote(
                symbol=symbol,
                underlying=underlying.upper(),
                expiry=contract_expiry,
                strike=strike,
                option_type=option_type,
                ltp=_decimal_or_none(_first(raw, "ltp", "lp")),
                bid=_decimal_or_none(_first(raw, "bid", "bid_price", "bid_price1")),
                ask=_decimal_or_none(_first(raw, "ask", "ask_price", "ask_price1")),
                quote_timestamp=_datetime_or_none(_first(raw, "timestamp", "last_traded_time")),
                oi=_decimal_or_none(raw_oi),
                oi_quality=_oi_quality(raw_oi),
                oi_unit=str(_first(raw, "oi_unit", "oiUnit") or "SOURCE_UNSPECIFIED"),
                volume=_decimal_or_none(_first(raw, "volume", "vol_traded_today")),
                lot_size=_int_or_none(_first(raw, "lot_size", "lotSize")) or (meta.lot_size if meta else None),
                tick_size=_decimal_or_none(_first(raw, "tick_size", "tickSize")) or (meta.tick_size if meta else None),
                source_quality=str(_first(raw, "source_quality") or "LIVE_READ_OR_FIXTURE"),
            )
        )
    return FyersOptionChainSnapshot(
        underlying=underlying.upper(),
        expiry=expiry,
        captured_at=captured_at,
        contracts=tuple(sorted(contracts, key=lambda item: (item.expiry, item.strike, item.option_type, item.symbol))),
        source_hash=canonical_hash(payload),
        warnings=tuple(warnings),
    )


def _rows_from_csv_or_iterable(rows: Iterable[Mapping[str, Any]] | str) -> list[Mapping[str, Any]]:
    if not isinstance(rows, str):
        return list(rows)
    sample = rows.lstrip()
    if not sample:
        return []
    dialect = csv.Sniffer().sniff(sample[:2048], delimiters=",|\t")
    parsed_rows = list(csv.reader(StringIO(rows), dialect=dialect))
    if not parsed_rows:
        return []
    first_cells = {cell.strip().lower() for cell in parsed_rows[0]}
    if {"symbol", "fyers symbol", "fytoken"} & first_cells:
        return list(csv.DictReader(StringIO(rows), dialect=dialect))
    return [_fyers_headerless_symbol_row(row) for row in parsed_rows if row]


def _fyers_headerless_symbol_row(row: list[str]) -> Mapping[str, Any]:
    def cell(index: int) -> str:
        return row[index].strip() if index < len(row) else ""

    option_type = cell(16)
    symbol = cell(9)
    instrument_code = cell(2)
    return {
        "fyToken": cell(0),
        "description": cell(1),
        "instrument_type": _fyers_instrument_type(symbol=symbol, instrument_code=instrument_code, option_type=option_type),
        "lotSize": cell(3),
        "tickSize": cell(4),
        "isin": cell(5),
        "trading_session": cell(6),
        "source_effective_date": cell(7),
        "expiry": cell(8),
        "symbol": symbol,
        "exchange_code": cell(10),
        "segment_code": cell(11),
        "token": cell(12),
        "underlying": cell(13),
        "underlying_token": cell(14),
        "strike": cell(15),
        "option_type": option_type,
        "underlying_fyToken": cell(17),
        "raw_fyers_row": tuple(row),
    }


def _fyers_instrument_type(*, symbol: str, instrument_code: str, option_type: str) -> str:
    normalized_option = _normalize_option_type(option_type)
    if normalized_option in {"CALL", "PUT"}:
        return "OPTION"
    if symbol.upper().endswith("FUT") or instrument_code in {"11", "13"}:
        return "FUTURE"
    return "EQUITY"


def _extract_quote_record(payload: Mapping[str, Any], *, symbol: str) -> Mapping[str, Any]:
    data = payload.get("d")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, Mapping) and str(item.get("n") or item.get("symbol") or "").upper() == symbol.upper():
                return item
        if data and isinstance(data[0], Mapping):
            return data[0]
    if isinstance(payload.get("data"), Mapping):
        return payload["data"]  # type: ignore[return-value]
    return payload


def _interval_duration(interval: str):
    from datetime import timedelta

    if interval.upper() == "D":
        return timedelta(days=1)
    return timedelta(minutes=max(1, int(interval)))


def _datetime_from_epoch_or_iso(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=_IST)
    if isinstance(value, (int, float)) or str(value).isdigit():
        return datetime.fromtimestamp(int(value), tz=_IST)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_IST)


def _datetime_or_none(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return _datetime_from_epoch_or_iso(value)


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value)
    if text.isdigit() and len(text) >= 10:
        return datetime.fromtimestamp(int(text), tz=_IST).date()
    return date.fromisoformat(text[:10])


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return _decimal(value)
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(Decimal(str(value)))


def _oi_quality(value: Any) -> OIQuality:
    if value in (None, ""):
        return OIQuality.MISSING
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return OIQuality.MALFORMED
    return OIQuality.ZERO if parsed == 0 else OIQuality.AVAILABLE


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def _first_text(row: Mapping[str, Any], *keys: str) -> str:
    value = _first(row, *keys)
    return "" if value in (None, "") else str(value).strip()


def _normalize_option_type(value: Any) -> str | None:
    text = str(value or "").upper()
    if text in {"CE", "CALL"} or text.endswith("CE"):
        return "CALL"
    if text in {"PE", "PUT"} or text.endswith("PE"):
        return "PUT"
    return None


def _infer_underlying(symbol: str) -> str | None:
    text = symbol.upper().split(":")[-1]
    for suffix in ("CE", "PE"):
        if text.endswith(suffix):
            text = text[:-2]
            break
    while text and text[-1].isdigit():
        text = text[:-1]
    for month in ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"):
        idx = text.find(month)
        if idx > 0:
            text = text[: max(0, idx - 2)]
            break
    return text or None


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value
