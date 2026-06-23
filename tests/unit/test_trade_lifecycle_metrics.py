from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tfis.backtest import HistoricalBacktestRunner, load_daily_bars_csv, load_option_levels_series_csv
from tfis.backtest.backtest_runner import BacktestRunner
from tfis.backtest.trade_lifecycle import TradeLifecycleSimulator
from tfis.domain.enums import OptionType
from tfis.domain.trade_plan import TradePlan
from tfis.execution.order_planner import OrderPlanner
from tfis.market_structure.ohlc import OhlcBar
from tfis.market_structure.structure_calculator import MarketStructureCalculator
from tfis.risk.risk_policy import RiskPolicy
from tfis.strategy.strategy_evaluator import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
FOLDER_S23 = (
    ROOT
    / "config"
    / "strategies"
    / "options_sell"
    / "nifty"
    / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
)
FIXTURES = ROOT / "tests" / "fixtures" / "backtest"
DAILY_MULTI_CSV = FIXTURES / "s23_daily_multi.csv"
OPTION_MULTI_CSV = FIXTURES / "s23_option_levels_multi.csv"
OPTION_INTRADAY_CSV = FIXTURES / "s23_option_intraday.csv"


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


def _historical_runner() -> HistoricalBacktestRunner:
    return HistoricalBacktestRunner(
        BacktestRunner(
            structure_calculator=MarketStructureCalculator(),
            strategy_evaluator=StrategyEvaluator(),
            order_planner=OrderPlanner(),
            risk_policy=RiskPolicy(
                max_lots_per_trade=100,
                max_trades_per_day=3,
                allow_short_options=True,
                paper_only=True,
            ),
        )
    )


def test_target_hit_reports_expected_mfe_and_mae() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 220.0, 225.0, 210.0, 212.0),
            OhlcBar(datetime(2026, 5, 23, 9, 25), 202.0, 205.0, 195.0, 198.0),
            OhlcBar(datetime(2026, 5, 23, 9, 30), 198.0, 200.0, 75.0, 90.0),
        ],
    )

    assert result.exit_reason == "TARGET_HIT"
    assert result.max_favorable_excursion == pytest.approx(125.0)
    assert result.max_adverse_excursion == pytest.approx(5.0)


def test_stoploss_hit_reports_expected_mfe_and_mae() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 202.0, 205.0, 198.0, 200.0),
            OhlcBar(datetime(2026, 5, 23, 9, 30), 250.0, 325.0, 245.0, 315.0),
        ],
    )

    assert result.exit_reason == "STOPLOSS_HIT"
    assert result.max_favorable_excursion == pytest.approx(2.0)
    assert result.max_adverse_excursion == pytest.approx(125.0)


def test_no_entry_has_null_excursion_metrics() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 220.0, 230.0, 205.0, 228.0),
            OhlcBar(datetime(2026, 5, 23, 9, 25), 228.0, 235.0, 210.0, 232.0),
        ],
    )

    assert result.exit_reason == "NO_ENTRY"
    assert result.max_favorable_excursion is None
    assert result.max_adverse_excursion is None


def test_same_bar_target_and_stoploss_remains_conservative_stoploss() -> None:
    result = TradeLifecycleSimulator().simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 25), 220.0, 330.0, 75.0, 300.0),
        ],
    )

    assert result.exit_reason == "STOPLOSS_HIT"
    assert result.exit_timestamp == datetime(2026, 5, 23, 9, 25)


def test_historical_summary_win_loss_and_excursion_rates_are_correct() -> None:
    report = _historical_runner().run(
        strategy_path=FOLDER_S23,
        daily_bars=load_daily_bars_csv(DAILY_MULTI_CSV),
        option_levels_series=load_option_levels_series_csv(OPTION_MULTI_CSV),
        option_intraday_bars=load_daily_bars_csv(OPTION_INTRADAY_CSV),
        runtime_values_base={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert report.metrics.win_rate == pytest.approx(0.5)
    assert report.metrics.loss_rate == pytest.approx(0.5)
    assert report.metrics.no_entry_rate == pytest.approx(1 / 6)
    assert report.metrics.no_exit_rate == pytest.approx(1 / 5)
    assert report.metrics.average_pnl_points == pytest.approx(1.79375)
    assert report.metrics.average_mfe == pytest.approx(85.94)
    assert report.metrics.average_mae == pytest.approx(70.46)
