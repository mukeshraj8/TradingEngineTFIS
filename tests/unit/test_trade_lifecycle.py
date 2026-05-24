from __future__ import annotations

from datetime import datetime

import pytest

from tfis.backtest.trade_lifecycle import TradeLifecycleSimulator
from tfis.domain.enums import OptionType
from tfis.domain.trade_plan import TradePlan
from tfis.market_structure.ohlc import OhlcBar


def _trade_plan() -> TradePlan:
    return TradePlan(
        strategy_code="S23",
        symbol="NIFTY",
        option_type=OptionType.CALL,
        start_strike=23100,
        end_strike=21999,
        ideal_premium=264.0,
        minimum_premium=198.0,
        entry_price=200.0,
        stoploss_price=320.0,
        target_price=80.0,
    )


def test_trade_lifecycle_hits_target_after_entry() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 220.0, 225.0, 210.0, 212.0),
            OhlcBar(datetime(2026, 5, 23, 9, 25), 202.0, 205.0, 195.0, 198.0),
            OhlcBar(datetime(2026, 5, 23, 9, 30), 198.0, 200.0, 75.0, 90.0),
        ],
    )

    assert result.entered is True
    assert result.exit_reason == "TARGET_HIT"
    assert result.entry_price == pytest.approx(200.0)
    assert result.exit_price == pytest.approx(80.0)
    assert result.entry_timestamp == datetime(2026, 5, 23, 9, 25)
    assert result.exit_timestamp == datetime(2026, 5, 23, 9, 30)
    assert result.bars_held == 2
    assert result.pnl_points == pytest.approx(120.0)
    assert result.max_favorable_excursion == pytest.approx(125.0)
    assert result.max_adverse_excursion == pytest.approx(5.0)


def test_trade_lifecycle_hits_stoploss_after_entry() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 202.0, 205.0, 198.0, 200.0),
            OhlcBar(datetime(2026, 5, 23, 9, 30), 250.0, 325.0, 245.0, 315.0),
        ],
    )

    assert result.entered is True
    assert result.exit_reason == "STOPLOSS_HIT"
    assert result.exit_price == pytest.approx(320.0)
    assert result.entry_timestamp == datetime(2026, 5, 23, 9, 20)
    assert result.exit_timestamp == datetime(2026, 5, 23, 9, 30)
    assert result.bars_held == 2
    assert result.pnl_points == pytest.approx(-120.0)
    assert result.max_favorable_excursion == pytest.approx(2.0)
    assert result.max_adverse_excursion == pytest.approx(125.0)


def test_trade_lifecycle_same_bar_target_and_stoploss_uses_conservative_stop() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 25), 220.0, 330.0, 75.0, 300.0),
        ],
    )

    assert result.entered is True
    assert result.exit_reason == "STOPLOSS_HIT"
    assert result.exit_price == pytest.approx(320.0)
    assert result.entry_timestamp == datetime(2026, 5, 23, 9, 25)
    assert result.exit_timestamp == datetime(2026, 5, 23, 9, 25)
    assert result.bars_held == 1
    assert result.max_favorable_excursion == pytest.approx(125.0)
    assert result.max_adverse_excursion == pytest.approx(130.0)


def test_trade_lifecycle_returns_no_entry_when_entry_never_touched() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 220.0, 230.0, 205.0, 228.0),
            OhlcBar(datetime(2026, 5, 23, 9, 25), 228.0, 235.0, 210.0, 232.0),
        ],
    )

    assert result.entered is False
    assert result.exit_reason == "NO_ENTRY"
    assert result.entry_price is None
    assert result.exit_price is None
    assert result.entry_timestamp is None
    assert result.exit_timestamp is None
    assert result.bars_held == 0
    assert result.pnl_points is None
    assert result.max_favorable_excursion is None
    assert result.max_adverse_excursion is None


def test_trade_lifecycle_returns_no_exit_when_entry_hit_without_target_or_stop() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 202.0, 205.0, 198.0, 200.0),
            OhlcBar(datetime(2026, 5, 23, 9, 25), 200.0, 250.0, 150.0, 220.0),
            OhlcBar(datetime(2026, 5, 23, 9, 30), 220.0, 300.0, 120.0, 260.0),
        ],
    )

    assert result.entered is True
    assert result.exit_reason == "NO_EXIT"
    assert result.entry_price == pytest.approx(200.0)
    assert result.exit_price is None
    assert result.entry_timestamp == datetime(2026, 5, 23, 9, 20)
    assert result.exit_timestamp is None
    assert result.bars_held == 3
    assert result.pnl_points is None
    assert result.max_favorable_excursion == pytest.approx(80.0)
    assert result.max_adverse_excursion == pytest.approx(100.0)


def test_trade_lifecycle_default_eod_policy_is_mark_no_exit() -> None:
    simulator = TradeLifecycleSimulator()

    result = simulator.simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 202.0, 205.0, 198.0, 200.0),
            OhlcBar(datetime(2026, 5, 23, 9, 25), 200.0, 250.0, 150.0, 220.0),
            OhlcBar(datetime(2026, 5, 23, 9, 30), 220.0, 300.0, 120.0, 260.0),
        ],
    )

    assert result.exit_reason == "NO_EXIT"
    assert result.pnl_points is None
    assert "no-exit diagnostic state" in result.notes.lower()
