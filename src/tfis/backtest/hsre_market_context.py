from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Literal

from tfis.backtest.monthly_status_context import build_monthly_status_context
from tfis.backtest.nifty_hsre_data_adapter import (
    HistoricalDailyOhlc,
    HistoricalSpotMinuteBar,
    HsreDataError,
    NiftyHsreHistoricalMarketDataProvider,
)
from tfis.domain.market_levels import MarketLevels
from tfis.market_structure.ohlc import OhlcBar
from tfis.market_structure.structure_calculator import (
    MarketStructureCalculator,
    MarketStructureError,
)


HsreContextStatus = Literal[
    "READY",
    "INSUFFICIENT_DAILY_LOOKBACK",
    "INSUFFICIENT_WEEKLY_LOOKBACK",
    "INSUFFICIENT_MONTHLY_LOOKBACK",
    "INSUFFICIENT_MONTHLY_STATUS_LOOKBACK",
]


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_NIFTY_STRATEGY_ROOT = (
    PROJECT_ROOT / "config" / "strategies" / "options_sell" / "nifty"
)


@dataclass(frozen=True, slots=True)
class HsreDailyProvenance:
    session_date: str
    source_files: tuple[str, ...]
    first_timestamp: str | None
    last_timestamp: str | None
    observed_minutes: int
    missing_minutes_synthesized: bool


@dataclass(frozen=True, slots=True)
class HsreGroupedProvenance:
    label: str
    start_session: str
    end_session: str
    source_sessions: tuple[str, ...]
    source_files: tuple[str, ...]
    first_timestamp: str | None
    last_timestamp: str | None
    observed_minutes: int


@dataclass(frozen=True, slots=True)
class HsreMarketContextPacket:
    session_date: str
    evaluation_timestamp: str
    data_root: str
    context_status: HsreContextStatus
    status_reason: str
    completed_prior_sessions_used: tuple[str, ...]
    market_levels: MarketLevels | None
    current_day_high_through_evaluation: float | None
    current_day_low_through_evaluation: float | None
    daily_provenance: tuple[HsreDailyProvenance, ...]
    current_day_provenance: HsreDailyProvenance | None
    weekly_context_provenance: tuple[HsreGroupedProvenance, ...]
    monthly_context_provenance: tuple[HsreGroupedProvenance, ...]
    monthly_status: str | None
    monthly_status_trigger: str | None
    monthly_status_notes: str | None
    monthly_status_provenance: dict[str, Any]
    lookahead_assertions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HsreJanuaryEligibility:
    year: int
    month: int
    first_underlying_lookback_ready: str | None
    first_monthly_status_ready: str | None
    first_fully_context_ready: str | None
    evaluated_sessions: tuple[dict[str, Any], ...]


class NiftyHsreMarketContextBuilder:
    """Build strategy-neutral historical market context from HSRE NIFTY data."""

    def __init__(
        self,
        provider: NiftyHsreHistoricalMarketDataProvider,
        *,
        instrument_group: str = "nifty",
        strategy_root: str | Path = DEFAULT_NIFTY_STRATEGY_ROOT,
        structure_calculator: MarketStructureCalculator | None = None,
    ) -> None:
        self.provider = provider
        self.instrument_group = instrument_group
        self.strategy_root = Path(strategy_root)
        self.structure_calculator = structure_calculator or MarketStructureCalculator()
        self._available_spot_sessions: tuple[date, ...] | None = None
        self._daily_ohlc_cache: dict[date, HistoricalDailyOhlc] = {}

    def build_context(
        self,
        *,
        session_date: date,
        evaluation_time: time = time(9, 16),
    ) -> HsreMarketContextPacket:
        evaluation_timestamp = datetime.combine(session_date, evaluation_time)
        completed_daily = self.completed_spot_daily_bars_before(session_date)
        current_bars = self.provider.get_spot_bars_through(
            session_date,
            evaluation_timestamp,
        )
        current_partial = self._aggregate_spot_bars(session_date, current_bars)
        daily_provenance = tuple(self._daily_provenance(item) for item in completed_daily)
        current_provenance = self._daily_provenance(current_partial)
        lookahead_assertions = (
            f"completed_daily_sessions_all_before_{session_date.isoformat()}",
            f"current_day_bars_all_at_or_before_{evaluation_timestamp.isoformat()}",
            "market_structure_calculator_received_current_partial_as_latest_bar",
            "monthly_status_context_received_grouped_observed_bars_only",
        )

        if len(completed_daily) < 4:
            return self._packet(
                session_date=session_date,
                evaluation_timestamp=evaluation_timestamp,
                context_status="INSUFFICIENT_DAILY_LOOKBACK",
                status_reason="At least 4 completed prior sessions are required for PRV_4DHH/PRV_4DLL.",
                completed_daily=completed_daily,
                current_partial=current_partial,
                weekly_bars=(),
                monthly_bars=(),
                market_levels=None,
                monthly_status_context=None,
                lookahead_assertions=lookahead_assertions,
            )

        daily_window = [
            self._to_ohlc_bar(item) for item in completed_daily
        ] + [self._to_ohlc_bar(current_partial, timestamp=evaluation_timestamp)]
        intraday_window = [self._spot_minute_to_ohlc(item) for item in current_bars]
        try:
            market_levels = self.structure_calculator.build_market_levels(
                daily_window,
                intraday_bars=intraday_window,
            )
        except MarketStructureError as exc:
            return self._packet(
                session_date=session_date,
                evaluation_timestamp=evaluation_timestamp,
                context_status="INSUFFICIENT_DAILY_LOOKBACK",
                status_reason=str(exc),
                completed_daily=completed_daily,
                current_partial=current_partial,
                weekly_bars=(),
                monthly_bars=(),
                market_levels=None,
                monthly_status_context=None,
                lookahead_assertions=lookahead_assertions,
            )

        grouped_input = tuple(completed_daily) + (current_partial,)
        weekly_bars, weekly_provenance = self._aggregate_groups(
            grouped_input,
            kind="weekly",
            current_timestamp=evaluation_timestamp,
        )
        monthly_bars, monthly_provenance = self._aggregate_groups(
            grouped_input,
            kind="monthly",
            current_timestamp=evaluation_timestamp,
        )

        current_week_key = session_date.isocalendar()[:2]
        has_previous_week = any(
            item.timestamp.date().isocalendar()[:2] < current_week_key
            for item in weekly_bars
        )
        if not has_previous_week:
            return self._packet(
                session_date=session_date,
                evaluation_timestamp=evaluation_timestamp,
                context_status="INSUFFICIENT_WEEKLY_LOOKBACK",
                status_reason="No completed previous weekly context is available.",
                completed_daily=completed_daily,
                current_partial=current_partial,
                weekly_bars=weekly_bars,
                monthly_bars=monthly_bars,
                weekly_provenance=weekly_provenance,
                monthly_provenance=monthly_provenance,
                market_levels=market_levels,
                monthly_status_context=None,
                lookahead_assertions=lookahead_assertions,
            )

        current_month_key = (session_date.year, session_date.month)
        has_previous_month = any(
            (item.timestamp.year, item.timestamp.month) < current_month_key
            for item in monthly_bars
        )
        if not has_previous_month:
            return self._packet(
                session_date=session_date,
                evaluation_timestamp=evaluation_timestamp,
                context_status="INSUFFICIENT_MONTHLY_LOOKBACK",
                status_reason="No completed previous monthly context is available.",
                completed_daily=completed_daily,
                current_partial=current_partial,
                weekly_bars=weekly_bars,
                monthly_bars=monthly_bars,
                weekly_provenance=weekly_provenance,
                monthly_provenance=monthly_provenance,
                market_levels=market_levels,
                monthly_status_context=None,
                lookahead_assertions=lookahead_assertions,
            )

        monthly_context = build_monthly_status_context(
            instrument_group=self.instrument_group,
            current_timestamp=evaluation_timestamp,
            monthly_bars=list(monthly_bars),
            weekly_bars=list(weekly_bars),
            strategy_root=self.strategy_root,
        )
        if monthly_context.skip is not None:
            return self._packet(
                session_date=session_date,
                evaluation_timestamp=evaluation_timestamp,
                context_status="INSUFFICIENT_MONTHLY_STATUS_LOOKBACK",
                status_reason=monthly_context.skip.reason,
                completed_daily=completed_daily,
                current_partial=current_partial,
                weekly_bars=weekly_bars,
                monthly_bars=monthly_bars,
                weekly_provenance=weekly_provenance,
                monthly_provenance=monthly_provenance,
                market_levels=market_levels,
                monthly_status_context=monthly_context,
                lookahead_assertions=lookahead_assertions,
            )
        assert monthly_context.context is not None
        if monthly_context.context.status_result.status.value == "UNKNOWN":
            return self._packet(
                session_date=session_date,
                evaluation_timestamp=evaluation_timestamp,
                context_status="INSUFFICIENT_MONTHLY_STATUS_LOOKBACK",
                status_reason="Monthly status remained UNKNOWN after existing lookback resolution.",
                completed_daily=completed_daily,
                current_partial=current_partial,
                weekly_bars=weekly_bars,
                monthly_bars=monthly_bars,
                weekly_provenance=weekly_provenance,
                monthly_provenance=monthly_provenance,
                market_levels=market_levels,
                monthly_status_context=monthly_context,
                lookahead_assertions=lookahead_assertions,
            )

        return self._packet(
            session_date=session_date,
            evaluation_timestamp=evaluation_timestamp,
            context_status="READY",
            status_reason="Historical market context is ready for downstream strategy decision work.",
            completed_daily=completed_daily,
            current_partial=current_partial,
            weekly_bars=weekly_bars,
            monthly_bars=monthly_bars,
            weekly_provenance=weekly_provenance,
            monthly_provenance=monthly_provenance,
            market_levels=market_levels,
            monthly_status_context=monthly_context,
            lookahead_assertions=lookahead_assertions,
        )

    def completed_spot_daily_bars_before(
        self,
        session_date: date,
    ) -> tuple[HistoricalDailyOhlc, ...]:
        sessions = [
            item for item in self._spot_sessions()
            if item < session_date
        ]
        return tuple(self._aggregate_completed_spot_session(item) for item in sessions)

    def discover_january_eligibility(
        self,
        *,
        year: int = 2024,
        evaluation_time: time = time(9, 16),
    ) -> HsreJanuaryEligibility:
        sessions = [
            item for item in self._spot_sessions()
            if item.year == year and item.month == 1
        ]
        evaluated: list[dict[str, Any]] = []
        first_underlying = None
        first_monthly = None
        first_ready = None
        for session in sessions:
            try:
                packet = self.build_context(
                    session_date=session,
                    evaluation_time=evaluation_time,
                )
                status = packet.context_status
                monthly_status = packet.monthly_status
            except HsreDataError as exc:
                status = "DATA_UNAVAILABLE"
                monthly_status = None
                packet = None
                reason = str(exc)
            else:
                reason = packet.status_reason

            if first_underlying is None and status not in {
                "INSUFFICIENT_DAILY_LOOKBACK",
                "DATA_UNAVAILABLE",
            }:
                first_underlying = session.isoformat()
            if first_monthly is None and monthly_status is not None:
                first_monthly = session.isoformat()
            if first_ready is None and status == "READY":
                first_ready = session.isoformat()
            evaluated.append(
                {
                    "session_date": session.isoformat(),
                    "context_status": status,
                    "status_reason": reason,
                    "monthly_status": monthly_status,
                }
            )
        return HsreJanuaryEligibility(
            year=year,
            month=1,
            first_underlying_lookback_ready=first_underlying,
            first_monthly_status_ready=first_monthly,
            first_fully_context_ready=first_ready,
            evaluated_sessions=tuple(evaluated),
        )

    def _spot_sessions(self) -> tuple[date, ...]:
        if self._available_spot_sessions is None:
            self._available_spot_sessions = self.provider.available_spot_sessions()
        return self._available_spot_sessions

    def _aggregate_completed_spot_session(self, session_date: date) -> HistoricalDailyOhlc:
        cached = self._daily_ohlc_cache.get(session_date)
        if cached is not None:
            return cached
        aggregated = self.provider.aggregate_spot_session(session_date)
        self._daily_ohlc_cache[session_date] = aggregated
        return aggregated

    @staticmethod
    def stable_packet_hash(packet: HsreMarketContextPacket) -> str:
        payload = packet_to_dict(packet)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _packet(
        self,
        *,
        session_date: date,
        evaluation_timestamp: datetime,
        context_status: HsreContextStatus,
        status_reason: str,
        completed_daily: tuple[HistoricalDailyOhlc, ...],
        current_partial: HistoricalDailyOhlc,
        weekly_bars: tuple[OhlcBar, ...],
        monthly_bars: tuple[OhlcBar, ...],
        market_levels: MarketLevels | None,
        monthly_status_context: Any,
        lookahead_assertions: tuple[str, ...],
        weekly_provenance: tuple[HsreGroupedProvenance, ...] = (),
        monthly_provenance: tuple[HsreGroupedProvenance, ...] = (),
    ) -> HsreMarketContextPacket:
        monthly_status = None
        monthly_status_trigger = None
        monthly_status_notes = None
        monthly_status_provenance: dict[str, Any] = {}
        if monthly_status_context is not None:
            if monthly_status_context.skip is not None:
                monthly_status_provenance["skip_reason"] = monthly_status_context.skip.reason
            if monthly_status_context.context is not None:
                result = monthly_status_context.context.status_result
                monthly_status = result.status.value
                monthly_status_trigger = result.trigger_name
                monthly_status_notes = result.notes
                monthly_status_provenance = {
                    "timestamp": monthly_status_context.context.timestamp.isoformat(),
                    "selected_branch_unique_codes": tuple(
                        monthly_status_context.context.selected_branch_unique_codes
                    ),
                    "candidate_count": len(result.candidates),
                    "reversal_dominated": result.reversal_dominated,
                    "threshold_value": result.threshold_value,
                }

        return HsreMarketContextPacket(
            session_date=session_date.isoformat(),
            evaluation_timestamp=evaluation_timestamp.isoformat(),
            data_root=str(self.provider.root),
            context_status=context_status,
            status_reason=status_reason,
            completed_prior_sessions_used=tuple(
                item.session_date.isoformat() for item in completed_daily[-4:]
            ),
            market_levels=market_levels,
            current_day_high_through_evaluation=current_partial.high,
            current_day_low_through_evaluation=current_partial.low,
            daily_provenance=tuple(self._daily_provenance(item) for item in completed_daily),
            current_day_provenance=self._daily_provenance(current_partial),
            weekly_context_provenance=weekly_provenance,
            monthly_context_provenance=monthly_provenance,
            monthly_status=monthly_status,
            monthly_status_trigger=monthly_status_trigger,
            monthly_status_notes=monthly_status_notes,
            monthly_status_provenance=monthly_status_provenance,
            lookahead_assertions=lookahead_assertions,
        )

    def _aggregate_groups(
        self,
        daily_bars: tuple[HistoricalDailyOhlc, ...],
        *,
        kind: Literal["weekly", "monthly"],
        current_timestamp: datetime,
    ) -> tuple[tuple[OhlcBar, ...], tuple[HsreGroupedProvenance, ...]]:
        groups: dict[tuple[int, int], list[HistoricalDailyOhlc]] = {}
        for bar in daily_bars:
            key = (
                bar.session_date.isocalendar()[:2]
                if kind == "weekly"
                else (bar.session_date.year, bar.session_date.month)
            )
            groups.setdefault(key, []).append(bar)

        result: list[OhlcBar] = []
        provenance: list[HsreGroupedProvenance] = []
        for key in sorted(groups):
            bars = sorted(groups[key], key=lambda item: item.session_date)
            last = bars[-1]
            timestamp = (
                current_timestamp
                if last.session_date == current_timestamp.date()
                else last.completeness.last_timestamp
            )
            if timestamp is None:
                timestamp = datetime.combine(last.session_date, time(15, 30))
            result.append(
                OhlcBar(
                    timestamp=timestamp,
                    open=bars[0].open,
                    high=max(item.high for item in bars),
                    low=min(item.low for item in bars),
                    close=last.close,
                    volume=sum(item.completeness.observed_minutes for item in bars),
                )
            )
            if kind == "weekly":
                label = f"{key[0]:04d}-W{key[1]:02d}"
            else:
                label = f"{key[0]:04d}-{key[1]:02d}"
            provenance.append(
                HsreGroupedProvenance(
                    label=label,
                    start_session=bars[0].session_date.isoformat(),
                    end_session=bars[-1].session_date.isoformat(),
                    source_sessions=tuple(item.session_date.isoformat() for item in bars),
                    source_files=tuple(
                        sorted(
                            {
                                source
                                for item in bars
                                for source in (str(path) for path in item.source_files)
                            }
                        )
                    ),
                    first_timestamp=bars[0].completeness.first_timestamp.isoformat()
                    if bars[0].completeness.first_timestamp else None,
                    last_timestamp=timestamp.isoformat(),
                    observed_minutes=sum(item.completeness.observed_minutes for item in bars),
                )
            )
        return tuple(result), tuple(provenance)

    @staticmethod
    def _aggregate_spot_bars(
        session_date: date,
        bars: tuple[HistoricalSpotMinuteBar, ...],
    ) -> HistoricalDailyOhlc:
        if not bars:
            raise HsreDataError(
                f"No spot observations at or before requested evaluation time for {session_date.isoformat()}"
            )
        return NiftyHsreHistoricalMarketDataProvider._aggregate_spot_bars(session_date, bars)

    @staticmethod
    def _to_ohlc_bar(
        bar: HistoricalDailyOhlc,
        *,
        timestamp: datetime | None = None,
    ) -> OhlcBar:
        resolved_timestamp = (
            timestamp
            or bar.completeness.last_timestamp
            or datetime.combine(bar.session_date, time(15, 30))
        )
        return OhlcBar(
            timestamp=resolved_timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.completeness.observed_minutes,
        )

    @staticmethod
    def _spot_minute_to_ohlc(bar: HistoricalSpotMinuteBar) -> OhlcBar:
        return OhlcBar(
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
        )

    @staticmethod
    def _daily_provenance(bar: HistoricalDailyOhlc) -> HsreDailyProvenance:
        return HsreDailyProvenance(
            session_date=bar.session_date.isoformat(),
            source_files=tuple(str(path) for path in bar.source_files),
            first_timestamp=bar.completeness.first_timestamp.isoformat()
            if bar.completeness.first_timestamp else None,
            last_timestamp=bar.completeness.last_timestamp.isoformat()
            if bar.completeness.last_timestamp else None,
            observed_minutes=bar.completeness.observed_minutes,
            missing_minutes_synthesized=bar.completeness.missing_minutes_synthesized,
        )


def packet_to_dict(packet: HsreMarketContextPacket) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if isinstance(value, MarketLevels):
            return asdict(value)
        if hasattr(value, "__dataclass_fields__"):
            return {key: convert(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    return convert(packet)
