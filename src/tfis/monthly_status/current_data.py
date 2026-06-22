from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping

import yaml

from tfis.brokers.fyers import FyersBrokerAdapter
from tfis.domain.enums import MonthlyStatus
from tfis.market_data import UnderlyingHistoryBar

from .decision_table import MonthlyStatusReferenceLevels
from .lookback import (
    MonthlyStatusHistoricalBar,
    MonthlyStatusResolutionResult,
    MonthlyStatusLookbackResolver,
    build_monthly_weekly_context_lookback_windows,
)
from .status_engine import MonthlyStatusEngine, MonthlyStatusResult
from .thresholds import DEFAULT_THRESHOLDS_PATH, load_monthly_status_thresholds


DEFAULT_INSTRUMENTS_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "monthly_status_instruments.yaml"
)
VALID_PRICE_SOURCES = {"spot", "futures_continuous"}


class MonthlyStatusCurrentDataError(RuntimeError):
    """Raised when current monthly-status data cannot be fetched or derived."""


@dataclass(frozen=True, slots=True)
class MonthlyStatusInstrument:
    symbol: str
    label: str
    instrument_group: str
    spot_symbol: str
    futures_continuous_symbol: str | None
    lot_size: int | None = None

    def fyers_symbol_for(self, price_source: str) -> str:
        normalized_source = _normalize_price_source(price_source)
        if normalized_source == "spot":
            return self.spot_symbol
        if self.futures_continuous_symbol:
            return self.futures_continuous_symbol
        raise MonthlyStatusCurrentDataError(
            "Futures continuous symbol is not configured for "
            f"{self.symbol}. Add futures_continuous_symbol in "
            f"{DEFAULT_INSTRUMENTS_PATH} after confirming the FYERS symbol."
        )


@dataclass(frozen=True, slots=True)
class MonthlyStatusInstrumentRegistry:
    instruments: Mapping[str, MonthlyStatusInstrument]
    default_symbol: str
    default_price_source: str

    def get(self, symbol: str) -> MonthlyStatusInstrument:
        key = str(symbol).strip().upper()
        try:
            return self.instruments[key]
        except KeyError as exc:
            raise MonthlyStatusCurrentDataError(
                f"Monthly-status instrument is not configured: {symbol}"
            ) from exc

    def to_json(self) -> dict[str, object]:
        return {
            "default_symbol": self.default_symbol,
            "default_price_source": self.default_price_source,
            "price_sources": sorted(VALID_PRICE_SOURCES),
            "instruments": [
                {
                    "symbol": item.symbol,
                    "label": item.label,
                    "instrument_group": item.instrument_group,
                    "spot_symbol": item.spot_symbol,
                    "futures_continuous_symbol": item.futures_continuous_symbol,
                    "lot_size": item.lot_size,
                }
                for item in sorted(self.instruments.values(), key=lambda value: value.symbol)
            ],
        }


@dataclass(frozen=True, slots=True)
class MonthlyStatusReferenceSnapshot:
    instrument: MonthlyStatusInstrument
    price_source: str
    fyers_symbol: str
    as_of: date
    levels: MonthlyStatusReferenceLevels
    bar_count: int
    first_bar_date: date
    last_bar_date: date

    def to_json(self) -> dict[str, object]:
        return {
            "symbol": self.instrument.symbol,
            "label": self.instrument.label,
            "instrument_group": self.instrument.instrument_group,
            "price_source": self.price_source,
            "fyers_symbol": self.fyers_symbol,
            "as_of": self.as_of.isoformat(),
            "bar_count": self.bar_count,
            "first_bar_date": self.first_bar_date.isoformat(),
            "last_bar_date": self.last_bar_date.isoformat(),
            "levels": {
                "PMH": self.levels.PMH,
                "PML": self.levels.PML,
                "CMH": self.levels.CMH,
                "CML": self.levels.CML,
                "PWH": self.levels.PWH,
                "PWL": self.levels.PWL,
                "CWH": self.levels.CWH,
                "CWL": self.levels.CWL,
                "current_price": self.levels.current_price,
            },
        }


@dataclass(frozen=True, slots=True)
class MonthlyStatusCurrentDataResult:
    snapshot: MonthlyStatusReferenceSnapshot
    result: MonthlyStatusResult
    effective_status: MonthlyStatus
    steps: tuple[str, ...]
    resolution: MonthlyStatusResolutionResult | None = None

    def to_json(self) -> dict[str, object]:
        thresholds = load_monthly_status_thresholds()[self.snapshot.instrument.instrument_group]
        return {
            **self.snapshot.to_json(),
            "effective_status": self.effective_status.value,
            "lookback_used": self.resolution.lookback_used if self.resolution else False,
            "lookback_reason": self.resolution.reason if self.resolution else None,
            "checked_lookback_windows": (
                self.resolution.checked_lookback_windows if self.resolution else 0
            ),
            "monthly_status": {
                "status": self.result.status.value,
                "trigger": self.result.trigger_name,
                "threshold": self.result.threshold_value,
                "reversal_dominated": self.result.reversal_dominated,
                "notes": self.result.notes,
            },
            "thresholds": {
                "a_pct": thresholds.a_pct,
                "b_pct": thresholds.b_pct,
                "c_pct": thresholds.c_pct,
            },
            "steps": list(self.steps),
        }


HistoryFetcher = Callable[
    [str, str, date, int, bool],
    tuple[UnderlyingHistoryBar, ...],
]


def load_monthly_status_instrument_registry(
    path: Path | None = None,
) -> MonthlyStatusInstrumentRegistry:
    registry_path = path or DEFAULT_INSTRUMENTS_PATH
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise MonthlyStatusCurrentDataError(
            f"Monthly-status instrument registry must be a mapping: {registry_path}"
        )
    raw_instruments = data.get("instruments")
    if not isinstance(raw_instruments, dict) or not raw_instruments:
        raise MonthlyStatusCurrentDataError(
            f"Monthly-status instrument registry missing instruments: {registry_path}"
        )
    instruments: dict[str, MonthlyStatusInstrument] = {}
    for raw_symbol, raw_config in raw_instruments.items():
        if not isinstance(raw_config, dict):
            raise MonthlyStatusCurrentDataError(
                f"Instrument config must be a mapping: {raw_symbol}"
            )
        symbol = str(raw_symbol).strip().upper()
        instruments[symbol] = MonthlyStatusInstrument(
            symbol=symbol,
            label=str(raw_config.get("label") or symbol),
            instrument_group=str(raw_config["instrument_group"]).strip().lower(),
            spot_symbol=str(raw_config["spot_symbol"]).strip(),
            futures_continuous_symbol=(
                str(raw_config["futures_continuous_symbol"]).strip()
                if raw_config.get("futures_continuous_symbol")
                else None
            ),
            lot_size=(
                int(raw_config["lot_size"])
                if raw_config.get("lot_size") is not None
                else None
            ),
        )
    default_symbol = str(data.get("default_symbol") or next(iter(instruments))).strip().upper()
    default_price_source = _normalize_price_source(data.get("default_price_source") or "spot")
    if default_symbol not in instruments:
        raise MonthlyStatusCurrentDataError(
            f"default_symbol {default_symbol} is not present in monthly-status registry."
        )
    return MonthlyStatusInstrumentRegistry(
        instruments=instruments,
        default_symbol=default_symbol,
        default_price_source=default_price_source,
    )


def derive_monthly_status_reference_snapshot(
    *,
    instrument: MonthlyStatusInstrument,
    price_source: str,
    fyers_symbol: str,
    as_of: date,
    daily_bars: Iterable[UnderlyingHistoryBar],
) -> MonthlyStatusReferenceSnapshot:
    historical_bars = _to_historical_bars(daily_bars, as_of=as_of)
    levels = derive_monthly_status_reference_levels(
        historical_bars=historical_bars,
        as_of=as_of,
    )
    return MonthlyStatusReferenceSnapshot(
        instrument=instrument,
        price_source=_normalize_price_source(price_source),
        fyers_symbol=fyers_symbol,
        as_of=as_of,
        levels=levels,
        bar_count=len(historical_bars),
        first_bar_date=historical_bars[0].timestamp.date(),
        last_bar_date=historical_bars[-1].timestamp.date(),
    )


def derive_monthly_status_reference_levels(
    *,
    historical_bars: Iterable[MonthlyStatusHistoricalBar],
    as_of: date,
) -> MonthlyStatusReferenceLevels:
    bars = tuple(
        sorted(
            (bar for bar in historical_bars if bar.timestamp.date() <= as_of),
            key=lambda item: item.timestamp,
        )
    )
    if not bars:
        raise MonthlyStatusCurrentDataError("No daily bars available up to the review date.")
    as_of_timestamp = max(bar.timestamp for bar in bars if bar.timestamp.date() <= as_of)
    current_month_key = (as_of_timestamp.year, as_of_timestamp.month)
    current_week_key = _iso_week_key(as_of_timestamp)
    current_month_bars = tuple(
        bar
        for bar in bars
        if (bar.timestamp.year, bar.timestamp.month) == current_month_key
    )
    current_week_bars = tuple(
        bar for bar in bars if _iso_week_key(bar.timestamp) == current_week_key
    )
    previous_month_keys = sorted(
        {
            (bar.timestamp.year, bar.timestamp.month)
            for bar in bars
            if (bar.timestamp.year, bar.timestamp.month) < current_month_key
        }
    )
    previous_week_keys = sorted(
        {_iso_week_key(bar.timestamp) for bar in bars if _iso_week_key(bar.timestamp) < current_week_key}
    )
    if not previous_month_keys:
        raise MonthlyStatusCurrentDataError("Previous month candles are missing.")
    if not previous_week_keys:
        raise MonthlyStatusCurrentDataError("Previous week candles are missing.")
    previous_month_key = previous_month_keys[-1]
    previous_week_key = previous_week_keys[-1]
    previous_month_bars = tuple(
        bar
        for bar in bars
        if (bar.timestamp.year, bar.timestamp.month) == previous_month_key
    )
    previous_week_bars = tuple(
        bar for bar in bars if _iso_week_key(bar.timestamp) == previous_week_key
    )
    if not current_month_bars or not current_week_bars:
        raise MonthlyStatusCurrentDataError("Current month/week candles are missing.")
    return MonthlyStatusReferenceLevels(
        PMH=max(bar.high for bar in previous_month_bars),
        PML=min(bar.low for bar in previous_month_bars),
        CMH=max(bar.high for bar in current_month_bars),
        CML=min(bar.low for bar in current_month_bars),
        PWH=max(bar.high for bar in previous_week_bars),
        PWL=min(bar.low for bar in previous_week_bars),
        CWH=max(bar.high for bar in current_week_bars),
        CWL=min(bar.low for bar in current_week_bars),
        current_price=bars[-1].close,
    )


def fetch_current_monthly_status(
    *,
    symbol: str,
    price_source: str,
    as_of: date,
    effective_status: MonthlyStatus | str = MonthlyStatus.UNKNOWN,
    registry_path: Path | None = None,
    lookback_days: int = 180,
    history_fetcher: HistoryFetcher | None = None,
) -> MonthlyStatusCurrentDataResult:
    registry = load_monthly_status_instrument_registry(registry_path)
    instrument = registry.get(symbol)
    normalized_price_source = _normalize_price_source(price_source)
    fyers_symbol = instrument.fyers_symbol_for(normalized_price_source)
    continuous = normalized_price_source == "futures_continuous"
    fetcher = history_fetcher or _default_history_fetcher
    daily_bars = fetcher(
        fyers_symbol,
        instrument.symbol,
        as_of,
        lookback_days,
        continuous,
    )
    historical_bars = _to_historical_bars(daily_bars, as_of=as_of)
    levels = derive_monthly_status_reference_levels(
        historical_bars=historical_bars,
        as_of=as_of,
    )
    snapshot = MonthlyStatusReferenceSnapshot(
        instrument=instrument,
        price_source=normalized_price_source,
        fyers_symbol=fyers_symbol,
        as_of=as_of,
        levels=levels,
        bar_count=len(historical_bars),
        first_bar_date=historical_bars[0].timestamp.date(),
        last_bar_date=historical_bars[-1].timestamp.date(),
    )
    status = _normalize_monthly_status(effective_status)
    engine = MonthlyStatusEngine()
    resolution: MonthlyStatusResolutionResult | None = None
    if status is MonthlyStatus.UNKNOWN:
        current_reference_timestamp = historical_bars[-1].timestamp
        resolution = MonthlyStatusLookbackResolver(monthly_status_engine=engine).resolve(
            instrument.instrument_group,
            snapshot.levels,
            current_reference_timestamp=current_reference_timestamp,
            lookback_windows=build_monthly_weekly_context_lookback_windows(
                historical_bars=historical_bars,
                current_reference_timestamp=current_reference_timestamp,
            ),
        )
        result = resolution.resolved_result
    else:
        result = engine.apply_current_price_transitions(
            instrument.instrument_group,
            snapshot.levels,
            effective_status=status,
        )
    return MonthlyStatusCurrentDataResult(
        snapshot=snapshot,
        result=result,
        effective_status=status,
        steps=_build_steps(
            snapshot=snapshot,
            result=result,
            effective_status=status,
            resolution=resolution,
        ),
        resolution=resolution,
    )


def calculate_monthly_status_from_levels(
    *,
    instrument_group: str,
    levels: MonthlyStatusReferenceLevels,
    effective_status: MonthlyStatus | str = MonthlyStatus.UNKNOWN,
) -> MonthlyStatusResult:
    engine = MonthlyStatusEngine()
    status = _normalize_monthly_status(effective_status)
    if status is MonthlyStatus.UNKNOWN:
        return engine.classify_monthly_structure(instrument_group, levels)
    return engine.apply_current_price_transitions(
        instrument_group,
        levels,
        effective_status=status,
    )


def _default_history_fetcher(
    raw_symbol: str,
    normalized_symbol: str,
    as_of: date,
    lookback_days: int,
    continuous: bool,
) -> tuple[UnderlyingHistoryBar, ...]:
    adapter = FyersBrokerAdapter()
    adapter.connect()
    return adapter.get_daily_bars_for_symbol(
        raw_symbol=raw_symbol,
        normalized_symbol=normalized_symbol,
        session_date=as_of,
        lookback_days=lookback_days,
        continuous=continuous,
    )


def _to_historical_bars(
    daily_bars: Iterable[UnderlyingHistoryBar],
    *,
    as_of: date,
) -> tuple[MonthlyStatusHistoricalBar, ...]:
    converted: list[MonthlyStatusHistoricalBar] = []
    for bar in daily_bars:
        if bar.bar_start.date() > as_of:
            continue
        if bar.high is None or bar.low is None or bar.close is None:
            continue
        converted.append(
            MonthlyStatusHistoricalBar(
                timestamp=bar.bar_start,
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
            )
        )
    converted.sort(key=lambda item: item.timestamp)
    if not converted:
        raise MonthlyStatusCurrentDataError("No complete high/low/close daily bars found.")
    return tuple(converted)


def _build_steps(
    *,
    snapshot: MonthlyStatusReferenceSnapshot,
    result: MonthlyStatusResult,
    effective_status: MonthlyStatus,
    resolution: MonthlyStatusResolutionResult | None = None,
) -> tuple[str, ...]:
    thresholds = load_monthly_status_thresholds(DEFAULT_THRESHOLDS_PATH)[
        snapshot.instrument.instrument_group
    ]
    levels = snapshot.levels
    bull = levels.PMH * (1 + thresholds.a_pct / 100)
    bear = levels.PML * (1 - thresholds.a_pct / 100)
    bull_cf = bull * (1 + thresholds.b_pct / 100)
    bear_cf = bear * (1 - thresholds.b_pct / 100)
    reversal_bull = max(levels.PWH, levels.CWH) * (1 + thresholds.c_pct / 100)
    reversal_bear = min(levels.PWL, levels.CWL) * (1 - thresholds.c_pct / 100)
    direct_result = (
        resolution.current_window_result
        if resolution is not None
        else MonthlyStatusEngine().classify_monthly_structure(
            snapshot.instrument.instrument_group,
            levels,
        )
    )
    steps = [
        (
            f"Data source: FYERS {snapshot.price_source} daily candles for "
            f"{snapshot.instrument.symbol} ({snapshot.fyers_symbol}). "
            f"Fetched {snapshot.bar_count} trading-day candles from "
            f"{snapshot.first_bar_date.isoformat()} to {snapshot.last_bar_date.isoformat()} "
            "so current, previous, weekly, and lookback ranges can be derived."
        ),
        (
            f"Reference levels for {snapshot.as_of.isoformat()}: "
            f"PMH={levels.PMH:.2f}, PML={levels.PML:.2f}, "
            f"CMH={levels.CMH:.2f}, CML={levels.CML:.2f}, "
            f"PWH={levels.PWH:.2f}, PWL={levels.PWL:.2f}, "
            f"CWH={levels.CWH:.2f}, CWL={levels.CWL:.2f}, "
            f"current price={levels.current_price:.2f}."
        ),
        (
            f"{snapshot.instrument.instrument_group.title()} thresholds are "
            f"a={thresholds.a_pct}%, b={thresholds.b_pct}%, "
            f"c={thresholds.c_pct}%. Bull trigger = PMH {levels.PMH:.2f} + "
            f"{thresholds.a_pct}% = {bull:.2f}; Bull CF = {bull:.2f} + "
            f"{thresholds.b_pct}% = {bull_cf:.2f}."
        ),
        (
            f"Bear trigger = PML {levels.PML:.2f} - {thresholds.a_pct}% = "
            f"{bear:.2f}; Bear CF = {bear:.2f} - {thresholds.b_pct}% = "
            f"{bear_cf:.2f}."
        ),
        (
            f"Direct current-month test: CMH {levels.CMH:.2f} "
            f"{_comparison_word(levels.CMH, bull, '>=')} Bull {bull:.2f}; "
            f"CML {levels.CML:.2f} {_comparison_word(levels.CML, bear, '<=')} "
            f"Bear {bear:.2f}. Direct monthly status = {direct_result.status.value} "
            f"({direct_result.trigger_name})."
        ),
        (
            f"Current-price transition levels: reversal bull = "
            f"MAX(PWH {levels.PWH:.2f}, CWH {levels.CWH:.2f}) + "
            f"{thresholds.c_pct}% = {reversal_bull:.2f}; reversal bear = "
            f"MIN(PWL {levels.PWL:.2f}, CWL {levels.CWL:.2f}) - "
            f"{thresholds.c_pct}% = {reversal_bear:.2f}."
        ),
    ]
    if resolution is not None:
        steps.append(
            _format_resolution_step(
                resolution=resolution,
                current_price=levels.current_price,
                bull_cf=bull_cf,
                bear_cf=bear_cf,
                reversal_bull=reversal_bull,
                reversal_bear=reversal_bear,
            )
        )
        if resolution.borrowed_window_result is not None:
            steps.extend(
                _format_lookback_trace_steps(
                    resolution=resolution,
                    a_pct=thresholds.a_pct,
                    b_pct=thresholds.b_pct,
                )
            )
    elif effective_status is not MonthlyStatus.UNKNOWN:
        steps.append(
            (
                f"Effective status was manually supplied as {effective_status.value}, "
                "so TFIS skipped lookback borrowing and applied current-price transition rules directly."
            )
        )
    steps.append(
        f"Final result: {result.status.value}. Trigger {result.trigger_name}. {result.notes}"
    )
    return tuple(steps)


def _comparison_word(value: float, threshold: float, operator: str) -> str:
    if operator == ">=":
        return "is above/equal to" if value >= threshold else "is below"
    if operator == "<=":
        return "is below/equal to" if value <= threshold else "is above"
    raise ValueError(f"Unsupported comparison operator: {operator}")


def _format_resolution_step(
    *,
    resolution: MonthlyStatusResolutionResult,
    current_price: float,
    bull_cf: float,
    bear_cf: float,
    reversal_bull: float,
    reversal_bear: float,
) -> str:
    if not resolution.lookback_used:
        return (
            "Lookback was not needed because the current month produced a direct "
            f"monthly status. TFIS still applied current price {current_price:.2f} "
            "to the transition rules."
        )
    borrowed_status = (
        resolution.borrowed_window_result.status.value
        if resolution.borrowed_window_result is not None
        else "UNKNOWN"
    )
    return (
        "Current month was not decisive, so TFIS checked prior monthly contexts. "
        f"It checked {resolution.checked_lookback_windows} window(s), borrowed "
        f"{borrowed_status}, then tested today's price {current_price:.2f}: "
        f"Bull CF threshold {bull_cf:.2f}, Bear CF threshold {bear_cf:.2f}, "
        f"reversal bull {reversal_bull:.2f}, reversal bear {reversal_bear:.2f}."
    )


def _format_lookback_trace_steps(
    *,
    resolution: MonthlyStatusResolutionResult,
    a_pct: float,
    b_pct: float,
) -> tuple[str, ...]:
    steps: list[str] = []
    for item in resolution.trace:
        if item.lookback_index <= 0:
            continue
        bull = item.PMH * (1 + a_pct / 100)
        bear = item.PML * (1 - a_pct / 100)
        bull_cf = bull * (1 + b_pct / 100)
        bear_cf = bear * (1 - b_pct / 100)
        if item.normalized_status is None:
            conclusion = (
                "not borrowed because it stayed UNKNOWN: "
                f"CMH {item.CMH:.2f} was below Bull {bull:.2f}, "
                f"and CML {item.CML:.2f} was above Bear {bear:.2f}."
            )
        else:
            conclusion = (
                f"borrowed as {item.normalized_status.value}: "
                f"CMH {item.CMH:.2f} vs Bull {bull:.2f} / Bull CF {bull_cf:.2f}; "
                f"CML {item.CML:.2f} vs Bear {bear:.2f} / Bear CF {bear_cf:.2f}."
            )
        steps.append(
            (
                f"Lookback {item.lookback_index}: {item.window_label} "
                f"({item.context_month_label}, {item.context_week_label}) used "
                f"PMH={item.PMH:.2f}, PML={item.PML:.2f}, CMH={item.CMH:.2f}, "
                f"CML={item.CML:.2f}. It classified as {item.status.value} "
                f"via {item.trigger_name}; {conclusion}"
            )
        )
        if item.used_for_resolution:
            break
    return tuple(steps)


def _normalize_monthly_status(value: MonthlyStatus | str) -> MonthlyStatus:
    if isinstance(value, MonthlyStatus):
        return value
    text = str(value or MonthlyStatus.UNKNOWN.value).strip().upper()
    try:
        return MonthlyStatus(text)
    except ValueError as exc:
        raise MonthlyStatusCurrentDataError(f"Unsupported monthly status: {value}") from exc


def _normalize_price_source(value: object) -> str:
    normalized = str(value or "spot").strip().lower()
    if normalized not in VALID_PRICE_SOURCES:
        raise MonthlyStatusCurrentDataError(
            f"Unsupported monthly-status price source: {value}"
        )
    return normalized


def _iso_week_key(timestamp: datetime) -> tuple[int, int]:
    iso = timestamp.isocalendar()
    return iso.year, iso.week
