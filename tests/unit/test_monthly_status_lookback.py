from __future__ import annotations

from datetime import datetime

from tfis.domain.enums import MonthlyStatus
from tfis.monthly_status import (
    MonthlyStatusHistoricalBar,
    MonthlyStatusLookbackResolver,
    MonthlyStatusLookbackWindow,
    MonthlyStatusReferenceLevels,
    MonthlyStatusRuntimeConfig,
    build_monthly_weekly_context_lookback_windows,
)


def _levels_for_status(status: str) -> MonthlyStatusReferenceLevels:
    if status == "UNKNOWN":
        return MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=95.0,
        )
    if status == "BULL":
        return MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=101.0,
        )
    if status == "BEAR":
        return MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=89.0,
        )
    if status == "BULL_CF":
        return MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.6,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=101.6,
        )
    if status == "BEAR_CF":
        return MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=88.5,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=88.5,
        )
    raise AssertionError(f"Unsupported status fixture: {status}")


def _window(index: int, status: str) -> MonthlyStatusLookbackWindow:
    reference_timestamp = datetime(2026, 5, 29 - index, 15, 29, 59)
    return MonthlyStatusLookbackWindow(
        window_label=f"lookback_{index}",
        reference_timestamp=reference_timestamp,
        context_month_label=f"{reference_timestamp.year:04d}-{reference_timestamp.month:02d}",
        context_week_label=(
            f"{reference_timestamp.isocalendar().year:04d}-W{reference_timestamp.isocalendar().week:02d}"
        ),
        levels=_levels_for_status(status),
    )


def _resolver(limit: int = 6) -> MonthlyStatusLookbackResolver:
    return MonthlyStatusLookbackResolver(
        runtime_config=MonthlyStatusRuntimeConfig(
            max_monthly_status_lookback_windows=limit
        )
    )


def test_current_resolves_directly_without_lookback() -> None:
    result = _resolver().resolve(
        "nifty",
        _levels_for_status("BULL"),
        current_reference_timestamp=datetime(2026, 5, 29, 9, 29, 59),
        lookback_windows=(_window(1, "BEAR"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BULL
    assert result.lookback_used is False
    assert result.checked_lookback_windows == 0
    assert result.borrowed_window_result is None
    assert len(result.trace) == 1
    assert result.trace[0].used_for_resolution is True
    assert result.trace[0].context_month_label == "2026-05"


def test_unknown_previous_bull_resolves_current_to_bull() -> None:
    result = _resolver().resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 5, 29, 9, 29, 59),
        lookback_windows=(_window(1, "BULL"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BULL
    assert result.lookback_used is True
    assert result.borrowed_window_result is not None
    assert result.borrowed_window_result.status == MonthlyStatus.BULL
    assert result.trace[1].window_label == "lookback_1"
    assert result.trace[1].used_for_resolution is True


def test_unknown_previous_bear_resolves_current_to_bear() -> None:
    result = _resolver().resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 5, 29, 9, 29, 59),
        lookback_windows=(_window(1, "BEAR"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BEAR
    assert result.lookback_used is True


def test_unknown_previous_bull_cf_resolves_current_to_bull() -> None:
    result = _resolver().resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 5, 29, 9, 29, 59),
        lookback_windows=(_window(1, "BULL_CF"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BULL_CF
    assert result.lookback_used is True


def test_unknown_previous_bear_cf_resolves_current_to_bear() -> None:
    result = _resolver().resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 5, 29, 9, 29, 59),
        lookback_windows=(_window(1, "BEAR_CF"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BEAR_CF
    assert result.lookback_used is True


def test_unknown_prev_unknown_prev_to_prev_resolves() -> None:
    result = _resolver().resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 5, 29, 9, 29, 59),
        lookback_windows=(_window(1, "UNKNOWN"), _window(2, "BULL")),
    )

    assert result.resolved_result.status == MonthlyStatus.BULL
    assert result.checked_lookback_windows == 2
    assert result.trace[1].used_for_resolution is False
    assert result.trace[2].used_for_resolution is True
    assert result.trace[2].normalized_status == MonthlyStatus.BULL


def test_unresolved_after_max_lookback_remains_unknown() -> None:
    result = _resolver(limit=1).resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 5, 29, 9, 29, 59),
        lookback_windows=(_window(1, "UNKNOWN"), _window(2, "BULL")),
    )

    assert result.resolved_result.status == MonthlyStatus.UNKNOWN
    assert result.lookback_used is False
    assert result.borrowed_window_result is None
    assert result.checked_lookback_windows == 1
    assert result.reason.startswith("Current month remained UNKNOWN")


def test_bearish_reverses_to_bullish_from_weekly_trigger() -> None:
    current = MonthlyStatusReferenceLevels(
        PMH=100.0,
        PML=90.0,
        CMH=100.5,
        CML=89.5,
        PWH=100.0,
        PWL=92.0,
        CWH=101.0,
        CWL=93.0,
        current_price=101.2,
    )
    result = _resolver().resolve(
        "nifty",
        current,
        current_reference_timestamp=datetime(2026, 6, 3, 9, 29, 59),
        lookback_windows=(_window(1, "BEAR"),),
    )

    assert result.borrowed_window_result is not None
    assert result.borrowed_window_result.status == MonthlyStatus.BEAR
    assert result.resolved_result.status == MonthlyStatus.BULL
    assert result.resolved_result.trigger_name == "LOOKBACK::REVERSAL_BULL_C_THRESHOLD"


def test_bearish_confirmed_does_not_reverse_from_weekly_trigger_only() -> None:
    current = MonthlyStatusReferenceLevels(
        PMH=110.0,
        PML=90.0,
        CMH=100.5,
        CML=89.5,
        PWH=100.0,
        PWL=92.0,
        CWH=101.0,
        CWL=93.0,
        current_price=101.2,
    )
    result = _resolver().resolve(
        "nifty",
        current,
        current_reference_timestamp=datetime(2026, 6, 3, 9, 29, 59),
        lookback_windows=(_window(1, "BEAR_CF"),),
    )

    assert result.borrowed_window_result is not None
    assert result.borrowed_window_result.status == MonthlyStatus.BEAR_CF
    assert result.resolved_result.status == MonthlyStatus.BEAR_CF


def test_bearish_confirmed_reverses_to_bullish_from_monthly_threshold() -> None:
    current = MonthlyStatusReferenceLevels(
        PMH=100.0,
        PML=90.0,
        CMH=100.5,
        CML=89.5,
        PWH=100.0,
        PWL=92.0,
        CWH=101.0,
        CWL=93.0,
        current_price=100.8,
    )
    result = _resolver().resolve(
        "nifty",
        current,
        current_reference_timestamp=datetime(2026, 6, 3, 9, 29, 59),
        lookback_windows=(_window(1, "BEAR_CF"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BULL
    assert result.resolved_result.trigger_name == "LOOKBACK::BULL_A_THRESHOLD"


def test_bullish_reverses_to_bearish_from_weekly_trigger() -> None:
    current = MonthlyStatusReferenceLevels(
        PMH=100.0,
        PML=90.0,
        CMH=100.5,
        CML=89.5,
        PWH=100.0,
        PWL=95.0,
        CWH=101.0,
        CWL=94.0,
        current_price=93.8,
    )
    result = _resolver().resolve(
        "nifty",
        current,
        current_reference_timestamp=datetime(2026, 6, 3, 9, 29, 59),
        lookback_windows=(_window(1, "BULL"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BEAR
    assert result.resolved_result.trigger_name == "LOOKBACK::REVERSAL_BEAR_C_THRESHOLD"


def test_bullish_confirmed_does_not_reverse_from_weekly_trigger_only() -> None:
    current = MonthlyStatusReferenceLevels(
        PMH=100.0,
        PML=90.0,
        CMH=100.5,
        CML=89.5,
        PWH=100.0,
        PWL=95.0,
        CWH=101.0,
        CWL=94.0,
        current_price=93.8,
    )
    result = _resolver().resolve(
        "nifty",
        current,
        current_reference_timestamp=datetime(2026, 6, 3, 9, 29, 59),
        lookback_windows=(_window(1, "BULL_CF"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BULL_CF


def test_bullish_confirmed_reverses_to_bearish_from_monthly_threshold() -> None:
    current = MonthlyStatusReferenceLevels(
        PMH=100.0,
        PML=90.0,
        CMH=100.5,
        CML=89.5,
        PWH=100.0,
        PWL=95.0,
        CWH=101.0,
        CWL=94.0,
        current_price=89.2,
    )
    result = _resolver().resolve(
        "nifty",
        current,
        current_reference_timestamp=datetime(2026, 6, 3, 9, 29, 59),
        lookback_windows=(_window(1, "BULL_CF"),),
    )

    assert result.resolved_result.status == MonthlyStatus.BEAR
    assert result.resolved_result.trigger_name == "LOOKBACK::BEAR_A_THRESHOLD"


def test_current_unknown_previous_monthly_weekly_context_resolves_bull() -> None:
    bars = (
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 4, 29, 15, 29, 59),
            high=100.0,
            low=90.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 4, 30, 15, 29, 59),
            high=100.0,
            low=90.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 5, 28, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=101.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 5, 29, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=101.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 6, 1, 9, 29, 59),
            high=101.0,
            low=89.0,
            close=95.0,
        ),
    )
    windows = build_monthly_weekly_context_lookback_windows(
        historical_bars=bars,
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
    )

    result = _resolver().resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
        lookback_windows=windows,
    )

    assert result.resolved_result.status == MonthlyStatus.BULL
    assert result.trace[1].context_month_label == "2026-05"
    assert result.trace[1].normalized_status == MonthlyStatus.BULL


def test_current_unknown_previous_monthly_weekly_context_resolves_bear() -> None:
    bars = (
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 4, 29, 15, 29, 59),
            high=100.0,
            low=90.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 4, 30, 15, 29, 59),
            high=100.0,
            low=90.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 5, 28, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=89.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 5, 29, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=89.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 6, 1, 9, 29, 59),
            high=101.0,
            low=89.0,
            close=95.0,
        ),
    )
    windows = build_monthly_weekly_context_lookback_windows(
        historical_bars=bars,
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
    )

    result = _resolver().resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
        lookback_windows=windows,
    )

    assert result.resolved_result.status == MonthlyStatus.BEAR
    assert result.trace[1].normalized_status == MonthlyStatus.BEAR


def test_current_unknown_previous_to_previous_monthly_weekly_context_resolves() -> None:
    bars = (
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 3, 31, 15, 29, 59),
            high=100.0,
            low=90.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 4, 29, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=101.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 4, 30, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=101.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 5, 29, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 6, 1, 9, 29, 59),
            high=101.0,
            low=89.0,
            close=95.0,
        ),
    )
    windows = build_monthly_weekly_context_lookback_windows(
        historical_bars=bars,
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
    )

    result = _resolver(limit=3).resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
        lookback_windows=windows,
    )

    assert result.resolved_result.status == MonthlyStatus.BULL
    assert result.checked_lookback_windows >= 2


def test_context_lookback_does_not_walk_previous_trading_days() -> None:
    bars = (
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 4, 29, 15, 29, 59),
            high=100.0,
            low=90.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 4, 30, 15, 29, 59),
            high=100.0,
            low=90.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 5, 28, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 5, 29, 15, 29, 59),
            high=101.0,
            low=89.0,
            close=95.0,
        ),
        MonthlyStatusHistoricalBar(
            timestamp=datetime(2026, 6, 1, 9, 29, 59),
            high=101.0,
            low=89.0,
            close=95.0,
        ),
    )

    windows = build_monthly_weekly_context_lookback_windows(
        historical_bars=bars,
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
    )

    assert len(windows) == 1
    assert windows[0].context_month_label == "2026-05"


def test_insufficient_monthly_weekly_data_remains_unknown_with_clear_reason() -> None:
    windows = build_monthly_weekly_context_lookback_windows(
        historical_bars=(
            MonthlyStatusHistoricalBar(
                timestamp=datetime(2026, 6, 1, 9, 29, 59),
                high=101.0,
                low=89.0,
                close=95.0,
            ),
        ),
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
    )

    result = _resolver().resolve(
        "nifty",
        _levels_for_status("UNKNOWN"),
        current_reference_timestamp=datetime(2026, 6, 1, 9, 29, 59),
        lookback_windows=windows,
    )

    assert result.resolved_result.status == MonthlyStatus.UNKNOWN
    assert "safe lookback limit" in result.reason or "monthly/weekly" in result.reason


def test_2026_05_29_live_monthly_weekly_context_trace_remains_unknown_after_safe_lookback() -> None:
    current_levels = MonthlyStatusReferenceLevels(
        PMH=24601.7,
        PML=22182.55,
        CMH=24482.1,
        CML=23262.55,
        PWH=23859.9,
        PWL=23317.1,
        CWH=24089.8,
        CWL=23858.25,
        current_price=23893.4,
    )
    lookback_windows = (
        MonthlyStatusLookbackWindow(
            window_label="lookback_1",
            reference_timestamp=datetime(2026, 5, 27, 15, 29, 59),
            context_month_label="2026-05",
            context_week_label="2026-W22",
            levels=MonthlyStatusReferenceLevels(
                PMH=24601.7,
                PML=22182.55,
                CMH=24482.1,
                CML=23262.55,
                PWH=23859.9,
                PWL=23317.1,
                CWH=24089.8,
                CWL=23858.25,
                current_price=23907.15,
            ),
        ),
        MonthlyStatusLookbackWindow(
            window_label="lookback_2",
            reference_timestamp=datetime(2026, 4, 30, 15, 29, 59),
            context_month_label="2026-04",
            context_week_label="2026-W18",
            levels=MonthlyStatusReferenceLevels(
                PMH=25060.4,
                PML=22896.15,
                CMH=24601.7,
                CML=23262.55,
                PWH=23997.45,
                PWL=23262.55,
                CWH=24089.8,
                CWL=23858.25,
                current_price=23913.7,
            ),
        ),
    )

    result = _resolver(limit=6).resolve(
        "nifty",
        current_levels,
        current_reference_timestamp=datetime(2026, 5, 29, 9, 29, 59),
        lookback_windows=lookback_windows,
    )

    assert result.resolved_result.status == MonthlyStatus.UNKNOWN
    assert result.checked_lookback_windows == 2
    assert [item.status for item in result.trace] == [
        MonthlyStatus.UNKNOWN,
        MonthlyStatus.UNKNOWN,
        MonthlyStatus.UNKNOWN,
    ]
    assert [item.context_month_label for item in result.trace] == [
        "2026-05",
        "2026-05",
        "2026-04",
    ]


def test_2026_06_03_documented_example_resolves_bearish_confirmed() -> None:
    current_levels = MonthlyStatusReferenceLevels(
        PMH=24482.10,
        PML=23262.55,
        CMH=23733.70,
        CML=23229.15,
        PWH=23717.40,
        PWL=23229.15,
        CWH=23633.40,
        CWL=23229.15,
        current_price=23483.55,
    )
    lookback_windows = (
        MonthlyStatusLookbackWindow(
            window_label="lookback_1",
            reference_timestamp=datetime(2026, 5, 31, 15, 29, 59),
            context_month_label="2026-05",
            context_week_label="2026-W22",
            levels=MonthlyStatusReferenceLevels(
                PMH=24601.70,
                PML=22182.55,
                CMH=24482.10,
                CML=23262.55,
                PWH=24089.80,
                PWL=23317.10,
                CWH=24089.80,
                CWL=23858.25,
                current_price=23893.40,
            ),
        ),
        MonthlyStatusLookbackWindow(
            window_label="lookback_2",
            reference_timestamp=datetime(2026, 4, 30, 15, 29, 59),
            context_month_label="2026-04",
            context_week_label="2026-W18",
            levels=MonthlyStatusReferenceLevels(
                PMH=24989.35,
                PML=22283.85,
                CMH=24601.70,
                CML=22182.55,
                PWH=23997.45,
                PWL=23262.55,
                CWH=24089.80,
                CWL=23858.25,
                current_price=23913.70,
            ),
        ),
        MonthlyStatusLookbackWindow(
            window_label="lookback_3",
            reference_timestamp=datetime(2026, 3, 31, 15, 29, 59),
            context_month_label="2026-03",
            context_week_label="2026-W14",
            levels=MonthlyStatusReferenceLevels(
                PMH=26341.20,
                PML=24571.75,
                CMH=24989.35,
                CML=22283.85,
                PWH=25710.00,
                PWL=24571.75,
                CWH=24989.35,
                CWL=22283.85,
                current_price=22283.85,
            ),
        ),
    )

    result = _resolver(limit=6).resolve(
        "nifty",
        current_levels,
        current_reference_timestamp=datetime(2026, 6, 3, 9, 29, 59),
        lookback_windows=lookback_windows,
    )

    assert result.current_window_result.status == MonthlyStatus.UNKNOWN
    assert result.borrowed_window_result is not None
    assert result.borrowed_window_result.status == MonthlyStatus.BEAR_CF
    assert result.resolved_result.status == MonthlyStatus.BEAR_CF
    assert result.checked_lookback_windows == 3
