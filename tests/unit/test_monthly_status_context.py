from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tfis.backtest.monthly_status_context import (
    build_monthly_status_context,
    load_monthly_bars_csv,
    load_weekly_bars_csv,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "backtest"
MONTHLY_CSV = FIXTURES / "s23_monthly.csv"
WEEKLY_CSV = FIXTURES / "s23_weekly.csv"
STRATEGY_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"


def test_monthly_status_context_builds_bull_selection() -> None:
    result = build_monthly_status_context(
        instrument_group="nifty",
        current_timestamp=datetime(2026, 5, 18, 15, 30),
        monthly_bars=load_monthly_bars_csv(MONTHLY_CSV),
        weekly_bars=load_weekly_bars_csv(WEEKLY_CSV),
        strategy_root=STRATEGY_ROOT,
    )

    assert result.skip is None
    assert result.context is not None
    assert result.context.status_result.status.value == "BULL"
    assert result.context.status_result.trigger_name == "BULL_A_THRESHOLD"
    assert result.context.selected_branch_unique_codes == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]


def test_monthly_status_context_builds_bear_selection() -> None:
    result = build_monthly_status_context(
        instrument_group="nifty",
        current_timestamp=datetime(2026, 5, 22, 15, 30),
        monthly_bars=load_monthly_bars_csv(MONTHLY_CSV),
        weekly_bars=load_weekly_bars_csv(WEEKLY_CSV),
        strategy_root=STRATEGY_ROOT,
    )

    assert result.skip is None
    assert result.context is not None
    assert result.context.status_result.status.value == "BEAR_CF"
    assert result.context.status_result.trigger_name == "BEAR_CF_B_THRESHOLD"
    assert result.context.selected_branch_unique_codes == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    ]


def test_monthly_status_context_skips_when_completed_monthly_data_is_insufficient() -> None:
    result = build_monthly_status_context(
        instrument_group="nifty",
        current_timestamp=datetime(2026, 5, 18, 15, 30),
        monthly_bars=load_monthly_bars_csv(MONTHLY_CSV)[:1],
        weekly_bars=load_weekly_bars_csv(WEEKLY_CSV),
        strategy_root=STRATEGY_ROOT,
    )

    assert result.context is None
    assert result.skip is not None
    assert result.skip.reason == "missing current month reference bars"
