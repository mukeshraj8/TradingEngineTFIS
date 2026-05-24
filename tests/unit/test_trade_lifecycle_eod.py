from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tfis.backtest import EodExitPolicy, HistoricalBacktestRunner, load_daily_bars_csv, load_option_levels_series_csv
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


def _historical_runner(eod_policy: EodExitPolicy) -> HistoricalBacktestRunner:
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
        ),
        eod_policy=eod_policy,
    )


def test_square_off_at_close_calculates_pnl_for_options_sell() -> None:
    result = TradeLifecycleSimulator(
        eod_policy=EodExitPolicy.SQUARE_OFF_AT_CLOSE
    ).simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 202.0, 205.0, 198.0, 200.0),
            OhlcBar(datetime(2026, 5, 23, 9, 25), 200.0, 250.0, 150.0, 220.0),
            OhlcBar(datetime(2026, 5, 23, 9, 30), 220.0, 300.0, 120.0, 260.0),
        ],
    )

    assert result.exit_reason == "EOD_SQUARE_OFF"
    assert result.exit_price == pytest.approx(260.0)
    assert result.exit_timestamp == datetime(2026, 5, 23, 9, 30)
    assert result.pnl_points == pytest.approx(-60.0)


def test_carry_forward_pending_marks_trade_without_realized_pnl() -> None:
    result = TradeLifecycleSimulator(
        eod_policy=EodExitPolicy.CARRY_FORWARD_PENDING
    ).simulate(
        _trade_plan(),
        [
            OhlcBar(datetime(2026, 5, 23, 9, 20), 202.0, 205.0, 198.0, 200.0),
            OhlcBar(datetime(2026, 5, 23, 9, 25), 200.0, 250.0, 150.0, 220.0),
            OhlcBar(datetime(2026, 5, 23, 9, 30), 220.0, 300.0, 120.0, 260.0),
        ],
    )

    assert result.exit_reason == "CARRY_FORWARD_PENDING"
    assert result.exit_price is None
    assert result.pnl_points is None
    assert "not implemented yet" in result.notes.lower()


def test_historical_runner_metrics_include_eod_square_off_counts() -> None:
    report = _historical_runner(EodExitPolicy.SQUARE_OFF_AT_CLOSE).run(
        strategy_path=FOLDER_S23,
        daily_bars=load_daily_bars_csv(DAILY_MULTI_CSV),
        option_levels_series=load_option_levels_series_csv(OPTION_MULTI_CSV),
        option_intraday_bars=load_daily_bars_csv(OPTION_INTRADAY_CSV),
        runtime_values_base={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert report.metrics.no_exit == 0
    assert report.metrics.eod_square_off == 1
    assert report.metrics.carry_forward_pending == 0
    assert report.evaluations[3].lifecycle_result is not None
    assert report.evaluations[3].lifecycle_result.exit_reason == "EOD_SQUARE_OFF"


def test_historical_runner_metrics_include_carry_forward_pending_counts() -> None:
    report = _historical_runner(EodExitPolicy.CARRY_FORWARD_PENDING).run(
        strategy_path=FOLDER_S23,
        daily_bars=load_daily_bars_csv(DAILY_MULTI_CSV),
        option_levels_series=load_option_levels_series_csv(OPTION_MULTI_CSV),
        option_intraday_bars=load_daily_bars_csv(OPTION_INTRADAY_CSV),
        runtime_values_base={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert report.metrics.no_exit == 0
    assert report.metrics.eod_square_off == 0
    assert report.metrics.carry_forward_pending == 1
    assert report.evaluations[3].lifecycle_result is not None
    assert report.evaluations[3].lifecycle_result.exit_reason == "CARRY_FORWARD_PENDING"
