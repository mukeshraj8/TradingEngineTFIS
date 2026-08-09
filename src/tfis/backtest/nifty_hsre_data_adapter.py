from __future__ import annotations

import csv
import re
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from tfis.domain.enums import OptionType


class HsreDataError(ValueError):
    """Raised when historical market data is missing, malformed, or unsafe."""


@dataclass(frozen=True, slots=True)
class HistoricalOptionIdentity:
    underlying: str
    expiry: date
    strike: int
    option_type: OptionType
    raw_symbol: str


@dataclass(frozen=True, slots=True)
class HistoricalSpotMinuteBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    source_file: Path
    source_session: date


@dataclass(frozen=True, slots=True)
class HistoricalOptionMinuteBar:
    timestamp: datetime
    identity: HistoricalOptionIdentity
    open: float
    high: float
    low: float
    close: float
    oi: int
    volume: int
    source_file: Path
    source_session: date


@dataclass(frozen=True, slots=True)
class HistoricalOptionChainObservation:
    timestamp: datetime
    identity: HistoricalOptionIdentity
    ltp: float
    open: float
    high: float
    low: float
    close: float
    oi: int
    volume: int
    bid: None = None
    ask: None = None
    bid_ask_source: None = None
    source_file: Path | None = None
    source_session: date | None = None


@dataclass(frozen=True, slots=True)
class HistoricalDailyCompleteness:
    observed_minutes: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    expected_minutes_required: bool
    missing_minutes_synthesized: bool


@dataclass(frozen=True, slots=True)
class HistoricalDailyOhlc:
    session_date: date
    open: float
    high: float
    low: float
    close: float
    source_files: tuple[Path, ...]
    completeness: HistoricalDailyCompleteness
    identity: HistoricalOptionIdentity | None = None


@dataclass(frozen=True, slots=True)
class HistoricalOptionSessionAudit:
    session_date: date
    option_row_count: int
    contract_count: int
    ce_count: int
    pe_count: int
    strike_min: int | None
    strike_max: int | None
    oi_min: int | None
    oi_max: int | None
    negative_oi_count: int
    zero_oi_count: int
    chain_contract_count: int
    available_expiries: tuple[date, ...]
    source_file: Path


_OPTION_SYMBOL_RE = re.compile(
    r"^(?P<underlying>[A-Z]+)(?P<day>\d{2})(?P<month>[A-Z]{3})(?P<year>\d{2})(?P<strike>\d+)(?P<option_type>CE|PE)$"
)
_SPOT_FILE_RE = re.compile(r"^nifty_spot(?P<day>\d{2})_(?P<month>\d{2})_(?P<year>\d{4})\.csv$", re.IGNORECASE)
_OPTION_FILE_RE = re.compile(r"^nifty_options_(?P<day>\d{2})_(?P<month>\d{2})_(?P<year>\d{4})\.csv$", re.IGNORECASE)
_MONTHS = {
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


def parse_nifty_option_symbol(symbol: str) -> HistoricalOptionIdentity:
    raw_symbol = str(symbol).strip().upper()
    match = _OPTION_SYMBOL_RE.match(raw_symbol)
    if match is None:
        raise HsreDataError(f"Malformed NIFTY option symbol: {symbol!r}")

    month_name = match.group("month")
    if month_name not in _MONTHS:
        raise HsreDataError(f"Unsupported option expiry month in symbol: {symbol!r}")

    side = match.group("option_type")
    option_type = OptionType.CALL if side == "CE" else OptionType.PUT
    return HistoricalOptionIdentity(
        underlying=match.group("underlying"),
        expiry=date(
            2000 + int(match.group("year")),
            _MONTHS[month_name],
            int(match.group("day")),
        ),
        strike=int(match.group("strike")),
        option_type=option_type,
        raw_symbol=raw_symbol,
    )


class NiftyHsreHistoricalMarketDataProvider:
    """Strategy-neutral reader for local NIFTY HSRE minute data.

    The provider exposes market facts only. It does not select a strategy,
    apply S23 thresholds, compute entries, or simulate lifecycle outcomes.
    """

    def __init__(
        self,
        root: str | Path = r"D:\HistoricalData\Nifty",
        *,
        instrument: str = "NIFTY",
        max_cached_sessions: int = 8,
    ) -> None:
        if max_cached_sessions < 1:
            raise ValueError("max_cached_sessions must be positive")
        self.root = Path(root)
        self.instrument = instrument.strip().upper()
        self.max_cached_sessions = int(max_cached_sessions)
        self._spot_cache: OrderedDict[date, tuple[HistoricalSpotMinuteBar, ...]] = OrderedDict()
        self._option_cache: OrderedDict[date, tuple[HistoricalOptionMinuteBar, ...]] = OrderedDict()

    def resolve_spot_file(self, session_date: date) -> Path:
        return self._resolve_daily_file(
            kind="spot",
            session_date=session_date,
            pattern=_SPOT_FILE_RE,
            relative=(
                "spot",
                f"{session_date.year}",
                f"{session_date.month}",
                f"nifty_spot{session_date:%d_%m_%Y}.csv",
            ),
        )

    def resolve_option_file(self, session_date: date) -> Path:
        return self._resolve_daily_file(
            kind="options",
            session_date=session_date,
            pattern=_OPTION_FILE_RE,
            relative=(
                "options",
                f"{session_date.year}",
                f"{session_date.month}",
                f"nifty_options_{session_date:%d_%m_%Y}.csv",
            ),
        )

    def available_spot_sessions(self) -> tuple[date, ...]:
        return self._discover_session_dates("spot", _SPOT_FILE_RE)

    def available_option_sessions(self) -> tuple[date, ...]:
        return self._discover_session_dates("options", _OPTION_FILE_RE)

    def get_spot_session_bars(self, session_date: date) -> tuple[HistoricalSpotMinuteBar, ...]:
        cached = self._spot_cache.get(session_date)
        if cached is not None:
            self._spot_cache.move_to_end(session_date)
            return cached
        path = self.resolve_spot_file(session_date)
        rows: list[HistoricalSpotMinuteBar] = []
        for row_number, row in self._read_csv(path, required=("date", "time", "symbol", "open", "high", "low", "close")):
            symbol = self._require_text(path, row_number, "symbol", row["symbol"]).upper()
            if symbol != self.instrument:
                raise HsreDataError(
                    f"{path}: expected symbol {self.instrument}, got {symbol!r} at row {row_number}"
                )
            timestamp = self._parse_timestamp(path, row_number, row["date"], row["time"])
            rows.append(
                HistoricalSpotMinuteBar(
                    timestamp=timestamp,
                    open=self._parse_float(path, row_number, "open", row["open"]),
                    high=self._parse_float(path, row_number, "high", row["high"]),
                    low=self._parse_float(path, row_number, "low", row["low"]),
                    close=self._parse_float(path, row_number, "close", row["close"]),
                    source_file=path,
                    source_session=session_date,
                )
            )
        result = tuple(sorted(rows, key=lambda item: item.timestamp))
        self._remember(self._spot_cache, session_date, result)
        return result

    def get_spot_bar(
        self,
        session_date: date,
        timestamp: datetime | time,
        *,
        exact: bool = True,
    ) -> HistoricalSpotMinuteBar:
        cutoff = self._coerce_session_timestamp(session_date, timestamp)
        bars = self.get_spot_session_bars(session_date)
        if exact:
            matches = [bar for bar in bars if bar.timestamp == cutoff]
            if len(matches) != 1:
                raise HsreDataError(
                    f"Expected exactly one spot bar at {cutoff.isoformat()}, got {len(matches)}"
                )
            return matches[0]
        prior = [bar for bar in bars if bar.timestamp <= cutoff]
        if not prior:
            raise HsreDataError(f"No spot bars available at or before {cutoff.isoformat()}")
        return prior[-1]

    def get_spot_bars_through(
        self,
        session_date: date,
        timestamp: datetime | time,
    ) -> tuple[HistoricalSpotMinuteBar, ...]:
        cutoff = self._coerce_session_timestamp(session_date, timestamp)
        return tuple(
            bar for bar in self.get_spot_session_bars(session_date)
            if bar.timestamp <= cutoff
        )

    def get_option_session_bars(self, session_date: date) -> tuple[HistoricalOptionMinuteBar, ...]:
        cached = self._option_cache.get(session_date)
        if cached is not None:
            self._option_cache.move_to_end(session_date)
            return cached
        path = self.resolve_option_file(session_date)
        rows: list[HistoricalOptionMinuteBar] = []
        required = ("date", "time", "symbol", "open", "high", "low", "close", "oi", "volume")
        for row_number, row in self._read_csv(path, required=required):
            identity = parse_nifty_option_symbol(row["symbol"])
            if identity.underlying != self.instrument:
                raise HsreDataError(
                    f"{path}: expected underlying {self.instrument}, got {identity.underlying!r} at row {row_number}"
                )
            timestamp = self._parse_timestamp(path, row_number, row["date"], row["time"])
            oi = self._parse_intish(path, row_number, "oi", row["oi"])
            if oi < 0:
                raise HsreDataError(f"{path}: negative OI {oi} at row {row_number}")
            rows.append(
                HistoricalOptionMinuteBar(
                    timestamp=timestamp,
                    identity=identity,
                    open=self._parse_float(path, row_number, "open", row["open"]),
                    high=self._parse_float(path, row_number, "high", row["high"]),
                    low=self._parse_float(path, row_number, "low", row["low"]),
                    close=self._parse_float(path, row_number, "close", row["close"]),
                    oi=oi,
                    volume=self._parse_intish(path, row_number, "volume", row["volume"]),
                    source_file=path,
                    source_session=session_date,
                )
            )
        result = tuple(sorted(rows, key=lambda item: (item.timestamp, item.identity.raw_symbol)))
        self._remember(self._option_cache, session_date, result)
        return result

    def get_available_expiries(self, session_date: date) -> tuple[date, ...]:
        return tuple(sorted({bar.identity.expiry for bar in self.get_option_session_bars(session_date)}))

    def get_option_chain(
        self,
        session_date: date,
        timestamp: datetime | time,
        *,
        expiry: date | None = None,
        exact: bool = True,
    ) -> tuple[HistoricalOptionChainObservation, ...]:
        cutoff = self._coerce_session_timestamp(session_date, timestamp)
        if not exact:
            raise HsreDataError("Non-exact option-chain reads are intentionally unsupported")
        rows: list[HistoricalOptionChainObservation] = []
        for bar in self.get_option_session_bars(session_date):
            if bar.timestamp != cutoff:
                continue
            if expiry is not None and bar.identity.expiry != expiry:
                continue
            rows.append(
                HistoricalOptionChainObservation(
                    timestamp=bar.timestamp,
                    identity=bar.identity,
                    ltp=bar.close,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    oi=bar.oi,
                    volume=bar.volume,
                    source_file=bar.source_file,
                    source_session=bar.source_session,
                )
            )
        return tuple(sorted(rows, key=lambda item: (item.identity.expiry, item.identity.strike, item.identity.option_type.value, item.identity.raw_symbol)))

    def get_contract_session_bars(
        self,
        session_date: date,
        identity: HistoricalOptionIdentity,
    ) -> tuple[HistoricalOptionMinuteBar, ...]:
        cached = self._option_cache.get(session_date)
        if cached is None:
            return self._read_contract_session_bars(session_date, identity)
        return tuple(
            bar for bar in cached
            if self._same_contract(bar.identity, identity)
        )

    def aggregate_spot_session(self, session_date: date) -> HistoricalDailyOhlc:
        return self._aggregate_spot_bars(session_date, self.get_spot_session_bars(session_date))

    def aggregate_option_contract_session(
        self,
        session_date: date,
        identity: HistoricalOptionIdentity,
    ) -> HistoricalDailyOhlc:
        bars = self.get_contract_session_bars(session_date, identity)
        if not bars:
            raise HsreDataError(
                f"No bars for {identity.raw_symbol} on {session_date.isoformat()}"
            )
        return self._aggregate_option_bars(session_date, identity, bars)

    def get_prior_contract_daily_bars(
        self,
        *,
        session_date: date,
        identity: HistoricalOptionIdentity,
        limit: int | None = None,
    ) -> tuple[HistoricalDailyOhlc, ...]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be positive when supplied")
        completed_sessions = [
            item for item in self.available_option_sessions() if item < session_date
        ]
        result: list[HistoricalDailyOhlc] = []
        for prior_session in reversed(completed_sessions):
            bars = self.get_contract_session_bars(prior_session, identity)
            if not bars:
                continue
            result.append(self._aggregate_option_bars(prior_session, identity, bars))
            if limit is not None and len(result) >= limit:
                break
        return tuple(reversed(result))

    def audit_option_session(
        self,
        session_date: date,
        *,
        chain_time: time = time(9, 16),
    ) -> HistoricalOptionSessionAudit:
        rows = self.get_option_session_bars(session_date)
        identities = {bar.identity.raw_symbol: bar.identity for bar in rows}
        oi_values = [bar.oi for bar in rows]
        chain = self.get_option_chain(session_date, chain_time, exact=True)
        strikes = [identity.strike for identity in identities.values()]
        return HistoricalOptionSessionAudit(
            session_date=session_date,
            option_row_count=len(rows),
            contract_count=len(identities),
            ce_count=sum(1 for item in identities.values() if item.option_type is OptionType.CALL),
            pe_count=sum(1 for item in identities.values() if item.option_type is OptionType.PUT),
            strike_min=min(strikes) if strikes else None,
            strike_max=max(strikes) if strikes else None,
            oi_min=min(oi_values) if oi_values else None,
            oi_max=max(oi_values) if oi_values else None,
            negative_oi_count=sum(1 for oi in oi_values if oi < 0),
            zero_oi_count=sum(1 for oi in oi_values if oi == 0),
            chain_contract_count=len(chain),
            available_expiries=self.get_available_expiries(session_date),
            source_file=self.resolve_option_file(session_date),
        )

    def _resolve_daily_file(
        self,
        *,
        kind: Literal["spot", "options"],
        session_date: date,
        pattern: re.Pattern[str],
        relative: tuple[str, str, str, str],
    ) -> Path:
        expected = self.root.joinpath(*relative)
        if expected.is_file():
            parsed = self._parse_file_date(expected.name, pattern)
            if parsed != session_date:
                raise HsreDataError(
                    f"Resolved {kind} file date mismatch: {expected} parsed as {parsed}"
                )
            return expected
        raise HsreDataError(
            f"Missing {kind} file for {session_date.isoformat()}: {expected}"
        )

    def _discover_session_dates(
        self,
        kind: Literal["spot", "options"],
        pattern: re.Pattern[str],
    ) -> tuple[date, ...]:
        base = self.root / kind
        if not base.is_dir():
            return ()
        dates: set[date] = set()
        for path in base.rglob("*.csv"):
            parsed = self._parse_file_date_or_none(path.name, pattern)
            if parsed is not None:
                dates.add(parsed)
        return tuple(sorted(dates))

    @staticmethod
    def _parse_file_date(name: str, pattern: re.Pattern[str]) -> date:
        parsed = NiftyHsreHistoricalMarketDataProvider._parse_file_date_or_none(name, pattern)
        if parsed is None:
            raise HsreDataError(f"Malformed historical filename: {name!r}")
        return parsed

    @staticmethod
    def _parse_file_date_or_none(name: str, pattern: re.Pattern[str]) -> date | None:
        match = pattern.match(name)
        if match is None:
            return None
        return date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )

    @staticmethod
    def _read_csv(path: Path, *, required: tuple[str, ...]) -> list[tuple[int, dict[str, str]]]:
        if not path.is_file():
            raise HsreDataError(f"CSV file not found: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            normalized = {name.strip().lower(): name for name in fieldnames if name}
            missing = [name for name in required if name not in normalized]
            if missing:
                raise HsreDataError(f"{path}: missing columns {', '.join(missing)}")
            rows: list[tuple[int, dict[str, str]]] = []
            for row_number, raw in enumerate(reader, start=2):
                row = {
                    lower: (raw.get(original, "") or "").strip()
                    for lower, original in normalized.items()
                }
                if any(value != "" for value in row.values()):
                    rows.append((row_number, row))
        if not rows:
            raise HsreDataError(f"CSV contains no data rows: {path}")
        return rows

    def _read_contract_session_bars(
        self,
        session_date: date,
        identity: HistoricalOptionIdentity,
    ) -> tuple[HistoricalOptionMinuteBar, ...]:
        path = self.resolve_option_file(session_date)
        required = ("date", "time", "symbol", "open", "high", "low", "close", "oi", "volume")
        rows: list[HistoricalOptionMinuteBar] = []
        for row_number, row in self._read_csv(path, required=required):
            raw_symbol = self._require_text(path, row_number, "symbol", row["symbol"]).upper()
            if raw_symbol != identity.raw_symbol:
                continue
            parsed_identity = parse_nifty_option_symbol(raw_symbol)
            if not self._same_contract(parsed_identity, identity):
                continue
            timestamp = self._parse_timestamp(path, row_number, row["date"], row["time"])
            oi = self._parse_intish(path, row_number, "oi", row["oi"])
            if oi < 0:
                raise HsreDataError(f"{path}: negative OI {oi} at row {row_number}")
            rows.append(
                HistoricalOptionMinuteBar(
                    timestamp=timestamp,
                    identity=parsed_identity,
                    open=self._parse_float(path, row_number, "open", row["open"]),
                    high=self._parse_float(path, row_number, "high", row["high"]),
                    low=self._parse_float(path, row_number, "low", row["low"]),
                    close=self._parse_float(path, row_number, "close", row["close"]),
                    oi=oi,
                    volume=self._parse_intish(path, row_number, "volume", row["volume"]),
                    source_file=path,
                    source_session=session_date,
                )
            )
        return tuple(sorted(rows, key=lambda item: item.timestamp))

    @staticmethod
    def _parse_timestamp(path: Path, row_number: int, raw_date: str, raw_time: str) -> datetime:
        if not raw_date or not raw_time:
            raise HsreDataError(f"{path}: missing date/time at row {row_number}")
        try:
            return datetime.fromisoformat(f"{raw_date}T{raw_time}")
        except ValueError as exc:
            raise HsreDataError(
                f"{path}: invalid date/time at row {row_number}: {raw_date!r} {raw_time!r}"
            ) from exc

    @staticmethod
    def _require_text(path: Path, row_number: int, column: str, value: str) -> str:
        if not value:
            raise HsreDataError(f"{path}: missing {column} at row {row_number}")
        return value

    @staticmethod
    def _parse_float(path: Path, row_number: int, column: str, value: str) -> float:
        if value == "":
            raise HsreDataError(f"{path}: missing {column} at row {row_number}")
        try:
            return float(value)
        except ValueError as exc:
            raise HsreDataError(
                f"{path}: invalid numeric {column} at row {row_number}: {value!r}"
            ) from exc

    @classmethod
    def _parse_intish(cls, path: Path, row_number: int, column: str, value: str) -> int:
        numeric = cls._parse_float(path, row_number, column, value)
        if int(numeric) != numeric:
            raise HsreDataError(
                f"{path}: invalid integer-like {column} at row {row_number}: {value!r}"
            )
        return int(numeric)

    @staticmethod
    def _coerce_session_timestamp(session_date: date, value: datetime | time) -> datetime:
        if isinstance(value, datetime):
            if value.date() != session_date:
                raise HsreDataError(
                    f"Timestamp {value.isoformat()} is outside session {session_date.isoformat()}"
                )
            return value
        return datetime.combine(session_date, value)

    @staticmethod
    def _same_contract(
        left: HistoricalOptionIdentity,
        right: HistoricalOptionIdentity,
    ) -> bool:
        return (
            left.underlying == right.underlying
            and left.expiry == right.expiry
            and left.strike == right.strike
            and left.option_type is right.option_type
        )

    @staticmethod
    def _aggregate_spot_bars(
        session_date: date,
        bars: tuple[HistoricalSpotMinuteBar, ...],
    ) -> HistoricalDailyOhlc:
        if not bars:
            raise HsreDataError(f"No spot bars for {session_date.isoformat()}")
        ordered = tuple(sorted(bars, key=lambda item: item.timestamp))
        return HistoricalDailyOhlc(
            session_date=session_date,
            open=ordered[0].open,
            high=max(bar.high for bar in ordered),
            low=min(bar.low for bar in ordered),
            close=ordered[-1].close,
            source_files=tuple(sorted({bar.source_file for bar in ordered})),
            completeness=HistoricalDailyCompleteness(
                observed_minutes=len(ordered),
                first_timestamp=ordered[0].timestamp,
                last_timestamp=ordered[-1].timestamp,
                expected_minutes_required=False,
                missing_minutes_synthesized=False,
            ),
        )

    @staticmethod
    def _aggregate_option_bars(
        session_date: date,
        identity: HistoricalOptionIdentity,
        bars: tuple[HistoricalOptionMinuteBar, ...],
    ) -> HistoricalDailyOhlc:
        if not bars:
            raise HsreDataError(
                f"No option bars for {identity.raw_symbol} on {session_date.isoformat()}"
            )
        ordered = tuple(sorted(bars, key=lambda item: item.timestamp))
        return HistoricalDailyOhlc(
            session_date=session_date,
            open=ordered[0].open,
            high=max(bar.high for bar in ordered),
            low=min(bar.low for bar in ordered),
            close=ordered[-1].close,
            source_files=tuple(sorted({bar.source_file for bar in ordered})),
            completeness=HistoricalDailyCompleteness(
                observed_minutes=len(ordered),
                first_timestamp=ordered[0].timestamp,
                last_timestamp=ordered[-1].timestamp,
                expected_minutes_required=False,
                missing_minutes_synthesized=False,
            ),
            identity=identity,
        )

    def _remember(
        self,
        cache: OrderedDict[date, tuple],
        session_date: date,
        value: tuple,
    ) -> None:
        cache[session_date] = value
        cache.move_to_end(session_date)
        while len(cache) > self.max_cached_sessions:
            cache.popitem(last=False)
