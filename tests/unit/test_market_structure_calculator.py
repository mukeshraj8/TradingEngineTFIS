from __future__ import annotations

from datetime import datetime

import pytest

from tfis.market_structure import (
    MarketStructureCalculator,
    MarketStructureError,
    OhlcBar,
)


def _bar(ts: str, open_: float, high: float, low: float, close: float) -> OhlcBar:
    return OhlcBar(
        timestamp=datetime.fromisoformat(ts),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def test_builds_2d_3d_4d_levels_from_unsorted_daily_bars() -> None:
    daily_bars = [
        _bar("2026-01-07T15:30:00", 115, 122, 110, 118),
        _bar("2026-01-03T15:30:00", 100, 110, 95, 105),
        _bar("2026-01-06T15:30:00", 110, 118, 105, 112),
        _bar("2026-01-04T15:30:00", 103, 112, 101, 110),
        _bar("2026-01-05T15:30:00", 109, 115, 100, 111),
    ]

    levels = MarketStructureCalculator().build_market_levels(daily_bars)

    assert levels.d2hh == 118
    assert levels.d2ll == 100
    assert levels.d3hh == 118
    assert levels.d3ll == 100
    assert levels.d4hh == 118
    assert levels.d4ll == 95


def test_current_day_high_low_uses_intraday_when_available() -> None:
    daily_bars = [
        _bar("2026-01-03T15:30:00", 100, 110, 95, 105),
        _bar("2026-01-04T15:30:00", 103, 112, 101, 110),
        _bar("2026-01-05T15:30:00", 109, 115, 100, 111),
        _bar("2026-01-06T15:30:00", 110, 118, 105, 112),
        _bar("2026-01-07T15:30:00", 115, 122, 110, 118),
    ]
    intraday = [
        _bar("2026-01-07T09:15:00", 116, 119, 114, 118),
        _bar("2026-01-07T10:15:00", 118, 125, 113, 117),
        _bar("2026-01-07T11:15:00", 117, 121, 111, 112),
    ]

    levels = MarketStructureCalculator().build_market_levels(
        daily_bars,
        intraday_bars=intraday,
    )

    assert levels.current_day_high == 125
    assert levels.current_day_low == 111


def test_current_day_high_low_falls_back_to_latest_daily_bar() -> None:
    daily_bars = [
        _bar("2026-01-03T15:30:00", 100, 110, 95, 105),
        _bar("2026-01-04T15:30:00", 103, 112, 101, 110),
        _bar("2026-01-05T15:30:00", 109, 115, 100, 111),
        _bar("2026-01-06T15:30:00", 110, 118, 105, 112),
        _bar("2026-01-07T15:30:00", 115, 122, 110, 118),
    ]

    levels = MarketStructureCalculator().build_market_levels(daily_bars)

    assert levels.current_day_high == 122
    assert levels.current_day_low == 110


def test_raises_clear_error_with_fewer_than_four_previous_daily_bars() -> None:
    daily_bars = [
        _bar("2026-01-04T15:30:00", 103, 112, 101, 110),
        _bar("2026-01-05T15:30:00", 109, 115, 100, 111),
        _bar("2026-01-06T15:30:00", 110, 118, 105, 112),
        _bar("2026-01-07T15:30:00", 115, 122, 110, 118),
    ]

    with pytest.raises(MarketStructureError, match="At least 4 previous daily bars"):
        MarketStructureCalculator().build_market_levels(daily_bars)


def test_ohlcbar_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="high must be greater than or equal to low"):
        _bar("2026-01-07T15:30:00", 100, 90, 95, 98)

    with pytest.raises(ValueError, match="open must be non-negative"):
        _bar("2026-01-07T15:30:00", -1, 10, 0, 5)


def test_previous_week_and_month_levels_are_calculated_when_available() -> None:
    daily_bars = [
        _bar("2026-01-28T15:30:00", 90, 100, 80, 95),
        _bar("2026-01-29T15:30:00", 95, 104, 84, 98),
        _bar("2026-01-30T15:30:00", 98, 108, 82, 103),
        _bar("2026-02-02T15:30:00", 101, 111, 96, 108),
        _bar("2026-02-03T15:30:00", 108, 116, 102, 110),
        _bar("2026-02-04T15:30:00", 110, 118, 104, 115),
        _bar("2026-02-05T15:30:00", 115, 121, 109, 118),
        _bar("2026-02-06T15:30:00", 118, 124, 112, 120),
    ]

    levels = MarketStructureCalculator().build_market_levels(daily_bars)

    assert levels.previous_month_high == 108
    assert levels.previous_month_low == 80
    assert levels.previous_week_high == 108
    assert levels.previous_week_low == 80
