from __future__ import annotations

from datetime import datetime

from tfis.market_structure import MarketStructureCalculator, OhlcBar


def _bar(ts: str, open_: float, high: float, low: float, close: float) -> OhlcBar:
    return OhlcBar(
        timestamp=datetime.fromisoformat(ts),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def test_previous_day_levels_exclude_latest_current_day_bar() -> None:
    daily_bars = [
        _bar("2026-03-10T15:30:00", 100, 110, 95, 105),
        _bar("2026-03-11T15:30:00", 105, 112, 96, 108),
        _bar("2026-03-12T15:30:00", 108, 115, 98, 110),
        _bar("2026-03-13T15:30:00", 110, 118, 99, 114),
        _bar("2026-03-14T15:30:00", 114, 500, 10, 120),
    ]
    intraday_bars = [
        _bar("2026-03-14T09:15:00", 115, 122, 113, 118),
        _bar("2026-03-14T10:15:00", 118, 124, 112, 117),
    ]

    levels = MarketStructureCalculator().build_market_levels(
        daily_bars,
        intraday_bars=intraday_bars,
    )

    assert levels.d2hh == 118
    assert levels.d2ll == 98
    assert levels.d3hh == 118
    assert levels.d3ll == 96
    assert levels.d4hh == 118
    assert levels.d4ll == 95
    assert levels.current_day_high == 124
    assert levels.current_day_low == 112


def test_prv_3d_levels_use_only_previous_three_completed_daily_bars() -> None:
    daily_bars = [
        _bar("2026-04-01T15:30:00", 100, 120, 80, 110),
        _bar("2026-04-02T15:30:00", 110, 130, 90, 120),
        _bar("2026-04-03T15:30:00", 120, 140, 70, 130),
        _bar("2026-04-04T15:30:00", 130, 150, 60, 140),
        _bar("2026-04-05T15:30:00", 140, 160, 50, 150),
        _bar("2026-04-06T15:30:00", 150, 300, 10, 200),
    ]

    levels = MarketStructureCalculator().build_market_levels(daily_bars)

    assert levels.d3hh == 160
    assert levels.d3ll == 50
    assert levels.current_day_high == 300
    assert levels.current_day_low == 10


def test_current_day_levels_come_from_intraday_when_provided() -> None:
    daily_bars = [
        _bar("2026-05-01T15:30:00", 100, 110, 90, 105),
        _bar("2026-05-02T15:30:00", 105, 112, 94, 108),
        _bar("2026-05-03T15:30:00", 108, 116, 96, 110),
        _bar("2026-05-04T15:30:00", 110, 118, 98, 112),
        _bar("2026-05-05T15:30:00", 112, 130, 100, 120),
    ]
    intraday_bars = [
        _bar("2026-05-05T09:15:00", 113, 121, 111, 118),
        _bar("2026-05-05T10:15:00", 118, 125, 109, 112),
        _bar("2026-05-05T11:15:00", 112, 123, 108, 110),
    ]

    levels = MarketStructureCalculator().build_market_levels(
        daily_bars,
        intraday_bars=intraday_bars,
    )

    assert levels.current_day_high == 125
    assert levels.current_day_low == 108
