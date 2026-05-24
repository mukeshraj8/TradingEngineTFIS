from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from tfis.domain.market_levels import MarketLevels

from .ohlc import OhlcBar


class MarketStructureError(ValueError):
    """Raised when market-structure inputs are insufficient or inconsistent."""


@dataclass(slots=True)
class MarketStructureCalculator:
    """Builds deterministic MarketLevels from offline OHLC bars.

    Completed-daily semantics:

    - `PRV_2DHH`, `PRV_2DLL`, `PRV_3DHH`, `PRV_3DLL`, `PRV_4DHH`, and
      `PRV_4DLL` are calculated only from completed prior daily candles.
    - The latest daily bar in the provided window is treated as the current day
      context and is excluded from those previous-day calculations.
    - Current-day dynamic levels are represented separately through
      `current_day_high` / `current_day_low`, which can come from intraday bars
      when provided, or from the latest daily bar otherwise.
    """

    def build_market_levels(
        self,
        daily_bars: list[OhlcBar],
        intraday_bars: list[OhlcBar] | None = None,
    ) -> MarketLevels:
        """Build market levels from completed prior daily bars plus current-day context."""
        if not daily_bars:
            raise MarketStructureError("daily_bars must not be empty")

        sorted_daily = sorted(daily_bars, key=lambda bar: bar.timestamp)
        latest_daily = sorted_daily[-1]
        # Previous-day references always exclude the latest/current-day bar.
        previous_daily = sorted_daily[:-1]
        if len(previous_daily) < 4:
            raise MarketStructureError(
                "At least 4 previous daily bars are required to compute 4DHH/4DLL"
            )

        current_day = latest_daily.timestamp.date()
        current_day_high, current_day_low = self._resolve_current_day_levels(
            current_day=current_day,
            latest_daily=latest_daily,
            intraday_bars=intraday_bars,
        )

        previous_month_high, previous_month_low = self._completed_previous_month_levels(
            sorted_daily,
            current_day=current_day,
        )
        previous_week_high, previous_week_low = self._completed_previous_week_levels(
            sorted_daily,
            current_day=current_day,
        )

        trailing_2 = previous_daily[-2:]
        trailing_3 = previous_daily[-3:]
        trailing_4 = previous_daily[-4:]

        return MarketLevels(
            previous_month_high=previous_month_high,
            previous_month_low=previous_month_low,
            previous_week_high=previous_week_high,
            previous_week_low=previous_week_low,
            d2hh=max(bar.high for bar in trailing_2),
            d2ll=min(bar.low for bar in trailing_2),
            d3hh=max(bar.high for bar in trailing_3),
            d3ll=min(bar.low for bar in trailing_3),
            d4hh=max(bar.high for bar in trailing_4),
            d4ll=min(bar.low for bar in trailing_4),
            current_day_high=current_day_high,
            current_day_low=current_day_low,
        )

    def _resolve_current_day_levels(
        self,
        *,
        current_day: date,
        latest_daily: OhlcBar,
        intraday_bars: list[OhlcBar] | None,
    ) -> tuple[float, float]:
        """Resolve current-day dynamic high/low independently from completed prior bars."""
        if intraday_bars:
            matching = [
                bar for bar in intraday_bars if bar.timestamp.date() == current_day
            ]
            if matching:
                return (
                    max(bar.high for bar in matching),
                    min(bar.low for bar in matching),
                )
        return latest_daily.high, latest_daily.low

    def _completed_previous_week_levels(
        self,
        daily_bars: list[OhlcBar],
        *,
        current_day: date,
    ) -> tuple[float | None, float | None]:
        current_iso_year, current_iso_week, _ = current_day.isocalendar()
        matching = [
            bar
            for bar in daily_bars
            if (iso := bar.timestamp.date().isocalendar())[:2]
            != (current_iso_year, current_iso_week)
        ]
        if not matching:
            return None, None

        latest_completed_week = max(
            (bar.timestamp.date().isocalendar()[0], bar.timestamp.date().isocalendar()[1])
            for bar in matching
        )
        week_bars = [
            bar
            for bar in matching
            if (
                bar.timestamp.date().isocalendar()[0],
                bar.timestamp.date().isocalendar()[1],
            )
            == latest_completed_week
        ]
        if not week_bars:
            return None, None
        return max(bar.high for bar in week_bars), min(bar.low for bar in week_bars)

    def _completed_previous_month_levels(
        self,
        daily_bars: list[OhlcBar],
        *,
        current_day: date,
    ) -> tuple[float | None, float | None]:
        current_month = (current_day.year, current_day.month)
        matching = [
            bar
            for bar in daily_bars
            if (bar.timestamp.date().year, bar.timestamp.date().month) != current_month
        ]
        if not matching:
            return None, None

        latest_completed_month = max(
            (bar.timestamp.date().year, bar.timestamp.date().month) for bar in matching
        )
        month_bars = [
            bar
            for bar in matching
            if (bar.timestamp.date().year, bar.timestamp.date().month)
            == latest_completed_month
        ]
        if not month_bars:
            return None, None
        return max(bar.high for bar in month_bars), min(bar.low for bar in month_bars)
