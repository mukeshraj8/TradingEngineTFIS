from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml

from tfis.domain.enums import MonthlyStatus

from .decision_table import MonthlyStatusReferenceLevels
from .status_engine import MonthlyStatusEngine, MonthlyStatusResult


DEFAULT_RUNTIME_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "monthly_status_runtime.yaml"
)


@dataclass(frozen=True, slots=True)
class MonthlyStatusRuntimeConfig:
    max_monthly_status_lookback_windows: int = 6

    def __post_init__(self) -> None:
        if int(self.max_monthly_status_lookback_windows) < 0:
            raise ValueError("max_monthly_status_lookback_windows must be non-negative")


def load_monthly_status_runtime_config(
    path: Path | None = None,
) -> MonthlyStatusRuntimeConfig:
    config_path = path or DEFAULT_RUNTIME_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Monthly status runtime config must contain a mapping: {config_path}"
        )
    raw_limit = data.get("max_monthly_status_lookback_windows", 6)
    return MonthlyStatusRuntimeConfig(
        max_monthly_status_lookback_windows=int(raw_limit)
    )


@dataclass(frozen=True, slots=True)
class MonthlyStatusLookbackWindow:
    window_label: str
    reference_timestamp: datetime
    context_month_label: str
    context_week_label: str
    levels: MonthlyStatusReferenceLevels


@dataclass(frozen=True, slots=True)
class MonthlyStatusResolutionTraceEntry:
    lookback_index: int
    window_label: str
    reference_timestamp: datetime
    context_month_label: str
    context_week_label: str
    PMH: float
    PML: float
    CMH: float
    CML: float
    PWH: float
    PWL: float
    CWH: float
    CWL: float
    current_price: float
    status: MonthlyStatus
    normalized_status: MonthlyStatus | None
    trigger_name: str
    threshold_value: float | None
    notes: str
    used_for_resolution: bool


@dataclass(frozen=True, slots=True)
class MonthlyStatusResolutionResult:
    current_window_result: MonthlyStatusResult
    resolved_result: MonthlyStatusResult
    trace: tuple[MonthlyStatusResolutionTraceEntry, ...]
    lookback_used: bool
    reason: str
    checked_lookback_windows: int


class MonthlyStatusLookbackResolver:
    """Resolve UNKNOWN monthly status from prior historical windows.

    The base threshold-only engine remains unchanged. This resolver simply
    replays the same engine on prior completed windows until a directional
    answer is found or the safe lookback limit is exhausted.
    """

    def __init__(
        self,
        *,
        monthly_status_engine: MonthlyStatusEngine | None = None,
        runtime_config: MonthlyStatusRuntimeConfig | None = None,
    ) -> None:
        self._monthly_status_engine = monthly_status_engine or MonthlyStatusEngine()
        self._runtime_config = runtime_config or load_monthly_status_runtime_config()

    def resolve(
        self,
        instrument_group: str,
        current_levels: MonthlyStatusReferenceLevels,
        *,
        current_reference_timestamp: datetime,
        lookback_windows: Iterable[MonthlyStatusLookbackWindow] = (),
        max_lookback_windows: int | None = None,
    ) -> MonthlyStatusResolutionResult:
        current_result = self._monthly_status_engine.classify(
            instrument_group,
            current_levels,
        )
        trace_entries = [
            MonthlyStatusResolutionTraceEntry(
                lookback_index=0,
                window_label="current",
                reference_timestamp=current_reference_timestamp,
                context_month_label=_context_month_label(current_reference_timestamp),
                context_week_label=_context_week_label(current_reference_timestamp),
                PMH=current_levels.PMH,
                PML=current_levels.PML,
                CMH=current_levels.CMH,
                CML=current_levels.CML,
                PWH=current_levels.PWH,
                PWL=current_levels.PWL,
                CWH=current_levels.CWH,
                CWL=current_levels.CWL,
                current_price=current_levels.current_price,
                status=current_result.status,
                normalized_status=self._normalize_lookback_status(current_result.status),
                trigger_name=current_result.trigger_name,
                threshold_value=current_result.threshold_value,
                notes=current_result.notes,
                used_for_resolution=current_result.status is not MonthlyStatus.UNKNOWN,
            )
        ]
        if current_result.status is not MonthlyStatus.UNKNOWN:
            return MonthlyStatusResolutionResult(
                current_window_result=current_result,
                resolved_result=current_result,
                trace=tuple(trace_entries),
                lookback_used=False,
                reason="Current window resolved directly from threshold rules.",
                checked_lookback_windows=0,
            )

        allowed = (
            self._runtime_config.max_monthly_status_lookback_windows
            if max_lookback_windows is None
            else max(0, int(max_lookback_windows))
        )
        checked = 0
        for checked, window in enumerate(list(lookback_windows)[:allowed], start=1):
            lookback_result = self._monthly_status_engine.classify(
                instrument_group,
                window.levels,
            )
            normalized = self._normalize_lookback_status(lookback_result.status)
            trace_entries.append(
                MonthlyStatusResolutionTraceEntry(
                    lookback_index=checked,
                    window_label=window.window_label,
                    reference_timestamp=window.reference_timestamp,
                    context_month_label=window.context_month_label,
                    context_week_label=window.context_week_label,
                    PMH=window.levels.PMH,
                    PML=window.levels.PML,
                    CMH=window.levels.CMH,
                    CML=window.levels.CML,
                    PWH=window.levels.PWH,
                    PWL=window.levels.PWL,
                    CWH=window.levels.CWH,
                    CWL=window.levels.CWL,
                    current_price=window.levels.current_price,
                    status=lookback_result.status,
                    normalized_status=normalized,
                    trigger_name=lookback_result.trigger_name,
                    threshold_value=lookback_result.threshold_value,
                    notes=lookback_result.notes,
                    used_for_resolution=normalized is not None,
                )
            )
            if normalized is None:
                continue
            resolved_result = MonthlyStatusResult(
                status=normalized,
                trigger_name=f"LOOKBACK::{lookback_result.trigger_name}",
                threshold_value=lookback_result.threshold_value,
                reversal_dominated=lookback_result.reversal_dominated,
                candidates=list(current_result.candidates),
                notes=(
                    "Current window remained UNKNOWN; resolved from "
                    f"{window.window_label} "
                    f"({window.context_month_label} / {window.context_week_label}) at "
                    f"{window.reference_timestamp.isoformat()} "
                    f"where the historical window classified as "
                    f"{lookback_result.status.value}."
                ),
            )
            return MonthlyStatusResolutionResult(
                current_window_result=current_result,
                resolved_result=resolved_result,
                trace=tuple(trace_entries),
                lookback_used=True,
                reason=(
                    "Resolved from prior window because the current threshold-only "
                    "monthly/weekly context was UNKNOWN."
                ),
                checked_lookback_windows=checked,
            )

        return MonthlyStatusResolutionResult(
            current_window_result=current_result,
            resolved_result=current_result,
            trace=tuple(trace_entries),
            lookback_used=False,
            reason=(
                "Current monthly/weekly context remained UNKNOWN and no directional "
                "historical monthly/weekly context resolved within the safe "
                "lookback limit."
            ),
            checked_lookback_windows=checked,
        )

    @staticmethod
    def _normalize_lookback_status(
        status: MonthlyStatus,
    ) -> MonthlyStatus | None:
        if status in {MonthlyStatus.BULL, MonthlyStatus.BULL_CF}:
            return MonthlyStatus.BULL
        if status in {MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF}:
            return MonthlyStatus.BEAR
        return None


@dataclass(frozen=True, slots=True)
class MonthlyStatusHistoricalBar:
    timestamp: datetime
    high: float
    low: float
    close: float


def build_monthly_weekly_context_lookback_windows(
    *,
    historical_bars: Iterable[MonthlyStatusHistoricalBar],
    current_reference_timestamp: datetime,
) -> tuple[MonthlyStatusLookbackWindow, ...]:
    bars = tuple(sorted(historical_bars, key=lambda item: item.timestamp))
    if not bars:
        return ()
    current_context_key = _context_key(current_reference_timestamp)
    candidate_contexts = {
        _context_key(bar.timestamp)
        for bar in bars
        if bar.timestamp < current_reference_timestamp
        and _context_key(bar.timestamp) != current_context_key
    }
    ordered_contexts = sorted(
        candidate_contexts,
        key=lambda key: _context_anchor_timestamp(bars, key),
        reverse=True,
    )
    windows: list[MonthlyStatusLookbackWindow] = []
    for index, context_key in enumerate(ordered_contexts, start=1):
        anchor_timestamp = _context_anchor_timestamp(bars, context_key)
        levels = _build_levels_for_context_anchor(
            historical_bars=bars,
            anchor_timestamp=anchor_timestamp,
        )
        if levels is None:
            continue
        windows.append(
            MonthlyStatusLookbackWindow(
                window_label=f"lookback_{index}",
                reference_timestamp=anchor_timestamp,
                context_month_label=_context_month_label(anchor_timestamp),
                context_week_label=_context_week_label(anchor_timestamp),
                levels=levels,
            )
        )
    return tuple(windows)


def _build_levels_for_context_anchor(
    *,
    historical_bars: tuple[MonthlyStatusHistoricalBar, ...],
    anchor_timestamp: datetime,
) -> MonthlyStatusReferenceLevels | None:
    eligible = tuple(
        bar for bar in historical_bars if bar.timestamp <= anchor_timestamp
    )
    if not eligible:
        return None
    anchor_context = _context_key(anchor_timestamp)
    current_month_bars = tuple(
        bar
        for bar in eligible
        if (bar.timestamp.year, bar.timestamp.month)
        == (anchor_timestamp.year, anchor_timestamp.month)
    )
    previous_month_keys = sorted(
        {
            (bar.timestamp.year, bar.timestamp.month)
            for bar in eligible
            if (bar.timestamp.year, bar.timestamp.month)
            < (anchor_timestamp.year, anchor_timestamp.month)
        }
    )
    current_week_bars = tuple(
        bar
        for bar in eligible
        if _iso_week_key(bar.timestamp) == _iso_week_key(anchor_timestamp)
    )
    previous_week_keys = sorted(
        {
            _iso_week_key(bar.timestamp)
            for bar in eligible
            if _iso_week_key(bar.timestamp) < _iso_week_key(anchor_timestamp)
        }
    )
    if not previous_month_keys or not current_month_bars:
        return None
    if not previous_week_keys or not current_week_bars:
        return None
    previous_month_key = previous_month_keys[-1]
    previous_week_key = previous_week_keys[-1]
    previous_month_bars = tuple(
        bar
        for bar in eligible
        if (bar.timestamp.year, bar.timestamp.month) == previous_month_key
    )
    previous_week_bars = tuple(
        bar for bar in eligible if _iso_week_key(bar.timestamp) == previous_week_key
    )
    anchor_bars = tuple(
        bar for bar in eligible if _context_key(bar.timestamp) == anchor_context
    )
    if not previous_month_bars or not previous_week_bars or not anchor_bars:
        return None
    anchor_bar = max(anchor_bars, key=lambda item: item.timestamp)
    return MonthlyStatusReferenceLevels(
        PMH=max(bar.high for bar in previous_month_bars),
        PML=min(bar.low for bar in previous_month_bars),
        CMH=max(bar.high for bar in current_month_bars),
        CML=min(bar.low for bar in current_month_bars),
        PWH=max(bar.high for bar in previous_week_bars),
        PWL=min(bar.low for bar in previous_week_bars),
        CWH=max(bar.high for bar in current_week_bars),
        CWL=min(bar.low for bar in current_week_bars),
        current_price=anchor_bar.close,
    )


def _context_anchor_timestamp(
    historical_bars: tuple[MonthlyStatusHistoricalBar, ...],
    context_key: tuple[tuple[int, int], tuple[int, int]],
) -> datetime:
    return max(
        bar.timestamp
        for bar in historical_bars
        if _context_key(bar.timestamp) == context_key
    )


def _context_key(timestamp: datetime) -> tuple[tuple[int, int], tuple[int, int]]:
    return (
        (timestamp.year, timestamp.month),
        _iso_week_key(timestamp),
    )


def _iso_week_key(timestamp: datetime) -> tuple[int, int]:
    iso = timestamp.isocalendar()
    return iso.year, iso.week


def _context_month_label(timestamp: datetime) -> str:
    return f"{timestamp.year:04d}-{timestamp.month:02d}"


def _context_week_label(timestamp: datetime) -> str:
    iso_year, iso_week = _iso_week_key(timestamp)
    return f"{iso_year:04d}-W{iso_week:02d}"
