from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tfis.market_data import UnderlyingHistoryBar
from tfis.market_structure import MarketStructureCalculator, OhlcBar
from tfis.monthly_status import MonthlyStatusReferenceLevels

from .fyers_snapshot_collector import PaperCollectedSnapshotInputs
from .runtime_input_derivation import (
    PaperDecisionReferencePacket,
    PaperMarketReferencePacket,
    PaperMonthlyStatusReferencePacket,
)


class S23LiveReferenceDerivationError(RuntimeError):
    """Raised when TFIS cannot derive live monthly-status references safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class S23LiveReferenceDerivationResult:
    effective_reference_packet: PaperDecisionReferencePacket
    monthly_status_levels: MonthlyStatusReferenceLevels
    current_day_high_used: float
    current_day_low_used: float


class S23LiveReferenceDeriver:
    def __init__(
        self,
        *,
        market_structure_calculator: MarketStructureCalculator | None = None,
    ) -> None:
        self._market_structure_calculator = (
            market_structure_calculator or MarketStructureCalculator()
        )

    def derive(
        self,
        *,
        base_reference_packet: PaperDecisionReferencePacket,
        collected_inputs: PaperCollectedSnapshotInputs,
    ) -> S23LiveReferenceDerivationResult:
        daily_bars = collected_inputs.daily_bars
        if not daily_bars:
            raise S23LiveReferenceDerivationError(
                "MISSING_DAILY_HISTORY_BARS",
                "TFIS live monthly-status derivation requires normalized daily history bars.",
            )

        session_date = collected_inputs.session_context.session_date
        current_price = collected_inputs.underlying_quote.ltp
        if current_price is None:
            raise S23LiveReferenceDerivationError(
                "MISSING_CURRENT_PRICE",
                "Underlying LTP is required for live monthly-status derivation.",
            )

        intraday_ohlc = self._to_intraday_ohlc(collected_inputs.underlying_bars)
        daily_ohlc = self._to_daily_ohlc(daily_bars)
        try:
            market_levels = self._market_structure_calculator.build_market_levels(
                daily_ohlc,
                intraday_bars=intraday_ohlc,
            )
        except Exception as exc:
            raise S23LiveReferenceDerivationError(
                "LIVE_MARKET_LEVEL_DERIVATION_FAILED",
                f"Unable to derive TFIS live market levels safely: {exc}",
            ) from exc

        current_day_high = market_levels.current_day_high
        current_day_low = market_levels.current_day_low
        if current_day_high is None or current_day_low is None:
            raise S23LiveReferenceDerivationError(
                "MISSING_CURRENT_DAY_LEVELS",
                "TFIS live monthly-status derivation requires current-day high and low.",
            )

        previous_month = self._completed_previous_month(daily_ohlc, session_date=session_date)
        previous_week = self._completed_previous_week(daily_ohlc, session_date=session_date)
        current_month_completed = [
            bar
            for bar in daily_ohlc
            if self._same_month(bar.timestamp, session_date) and bar.timestamp.date() < session_date
        ]
        current_week_completed = [
            bar
            for bar in daily_ohlc
            if self._same_iso_week(bar.timestamp, session_date)
            and bar.timestamp.date() < session_date
        ]

        monthly_status_levels = MonthlyStatusReferenceLevels(
            PMH=previous_month.high,
            PML=previous_month.low,
            CMH=max([bar.high for bar in current_month_completed] + [current_day_high]),
            CML=min([bar.low for bar in current_month_completed] + [current_day_low]),
            PWH=previous_week.high,
            PWL=previous_week.low,
            CWH=max([bar.high for bar in current_week_completed] + [current_day_high]),
            CWL=min([bar.low for bar in current_week_completed] + [current_day_low]),
            current_price=float(current_price),
        )

        effective_packet = PaperDecisionReferencePacket(
            instrument_group=base_reference_packet.instrument_group,
            strategy_branch=base_reference_packet.strategy_branch,
            monthly_status_levels=PaperMonthlyStatusReferencePacket(
                PMH=monthly_status_levels.PMH,
                PML=monthly_status_levels.PML,
                CMH=monthly_status_levels.CMH,
                CML=monthly_status_levels.CML,
                PWH=monthly_status_levels.PWH,
                PWL=monthly_status_levels.PWL,
                CWH=monthly_status_levels.CWH,
                CWL=monthly_status_levels.CWL,
            ),
            market_reference_levels=PaperMarketReferencePacket(
                d2hh=market_levels.d2hh,
                d2ll=market_levels.d2ll,
                d3hh=market_levels.d3hh,
                d3ll=market_levels.d3ll,
                d4hh=market_levels.d4hh,
                d4ll=market_levels.d4ll,
            ),
            option_reference_values=dict(base_reference_packet.option_reference_values),
            lots=base_reference_packet.lots,
            quantity=base_reference_packet.quantity,
            source_workbook_rule=base_reference_packet.source_workbook_rule,
            workbook_row_number=base_reference_packet.workbook_row_number,
            fsl_price=base_reference_packet.fsl_price,
            monthly_status_source="tfis_live_daily_history",
            monthly_status_threshold_version=base_reference_packet.monthly_status_threshold_version,
            runtime_value_overrides=base_reference_packet.runtime_value_overrides,
            monthly_status_reference_date=session_date,
        )
        return S23LiveReferenceDerivationResult(
            effective_reference_packet=effective_packet,
            monthly_status_levels=monthly_status_levels,
            current_day_high_used=current_day_high,
            current_day_low_used=current_day_low,
        )

    def _to_daily_ohlc(
        self,
        daily_bars: tuple[UnderlyingHistoryBar, ...],
    ) -> list[OhlcBar]:
        converted: list[OhlcBar] = []
        for bar in daily_bars:
            if None in (bar.open, bar.high, bar.low, bar.close):
                raise S23LiveReferenceDerivationError(
                    "INCOMPLETE_DAILY_BAR",
                    "TFIS live monthly-status derivation requires complete daily OHLC bars.",
                )
            converted.append(
                OhlcBar(
                    timestamp=bar.bar_start,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=bar.volume,
                )
            )
        return converted

    def _to_intraday_ohlc(
        self,
        bars: tuple[UnderlyingHistoryBar, ...],
    ) -> list[OhlcBar]:
        converted: list[OhlcBar] = []
        for bar in bars:
            if None in (bar.open, bar.high, bar.low, bar.close):
                continue
            converted.append(
                OhlcBar(
                    timestamp=bar.bar_start,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=bar.volume,
                )
            )
        return converted

    def _completed_previous_month(
        self,
        daily_bars: list[OhlcBar],
        *,
        session_date,
    ) -> OhlcBar:
        previous_month_bars = [
            bar
            for bar in daily_bars
            if (bar.timestamp.year, bar.timestamp.month)
            != (session_date.year, session_date.month)
        ]
        if not previous_month_bars:
            raise S23LiveReferenceDerivationError(
                "MISSING_PREVIOUS_MONTH_BARS",
                "TFIS live monthly-status derivation requires completed previous-month daily bars.",
            )
        latest_completed_month = max(
            (bar.timestamp.year, bar.timestamp.month) for bar in previous_month_bars
        )
        month_bars = [
            bar
            for bar in previous_month_bars
            if (bar.timestamp.year, bar.timestamp.month) == latest_completed_month
        ]
        return OhlcBar(
            timestamp=max(bar.timestamp for bar in month_bars),
            open=month_bars[0].open,
            high=max(bar.high for bar in month_bars),
            low=min(bar.low for bar in month_bars),
            close=month_bars[-1].close,
        )

    def _completed_previous_week(
        self,
        daily_bars: list[OhlcBar],
        *,
        session_date,
    ) -> OhlcBar:
        current_week = session_date.isocalendar()[:2]
        previous_week_bars = [
            bar for bar in daily_bars if bar.timestamp.date().isocalendar()[:2] != current_week
        ]
        if not previous_week_bars:
            raise S23LiveReferenceDerivationError(
                "MISSING_PREVIOUS_WEEK_BARS",
                "TFIS live monthly-status derivation requires completed previous-week daily bars.",
            )
        latest_completed_week = max(
            bar.timestamp.date().isocalendar()[:2] for bar in previous_week_bars
        )
        week_bars = [
            bar
            for bar in previous_week_bars
            if bar.timestamp.date().isocalendar()[:2] == latest_completed_week
        ]
        return OhlcBar(
            timestamp=max(bar.timestamp for bar in week_bars),
            open=week_bars[0].open,
            high=max(bar.high for bar in week_bars),
            low=min(bar.low for bar in week_bars),
            close=week_bars[-1].close,
        )

    @staticmethod
    def _same_month(timestamp: datetime, session_date) -> bool:
        return (timestamp.year, timestamp.month) == (session_date.year, session_date.month)

    @staticmethod
    def _same_iso_week(timestamp: datetime, session_date) -> bool:
        return timestamp.date().isocalendar()[:2] == session_date.isocalendar()[:2]


PaperLiveReferenceDerivationError = S23LiveReferenceDerivationError
PaperLiveReferenceDerivationResult = S23LiveReferenceDerivationResult
PaperLiveReferenceDeriver = S23LiveReferenceDeriver

