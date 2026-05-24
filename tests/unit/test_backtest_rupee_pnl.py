from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tfis.backtest import CostModel, EodExitPolicy, HistoricalBacktestRunner, load_daily_bars_csv, load_option_levels_series_csv
from tfis.backtest.backtest_runner import BacktestRunner
from tfis.backtest.trade_lifecycle import TradeLifecycleResult
from tfis.execution.order_planner import OrderPlanner
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


def _historical_runner(*, cost_model: CostModel | None = None) -> HistoricalBacktestRunner:
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
        eod_policy=EodExitPolicy.SQUARE_OFF_AT_CLOSE,
        cost_model=cost_model,
    )


def test_completed_trade_rupee_pnl_is_quantity_times_points() -> None:
    result = CostModel(
        slippage_points_per_side=1.0,
        brokerage_points_per_trade=0.5,
        other_cost_points_per_trade=0.5,
    ).apply_with_quantity(
        TradeLifecycleResult(
            entered=True,
            entry_price=200.0,
            exit_price=80.0,
            entry_timestamp=None,
            exit_timestamp=None,
            bars_held=2,
            exit_reason="TARGET_HIT",
            pnl_points=120.0,
            max_favorable_excursion=125.0,
            max_adverse_excursion=5.0,
            notes="completed",
        ),
        quantity=50,
    )

    assert result.gross_pnl_rupees == pytest.approx(6000.0)
    assert result.cost_rupees == pytest.approx(150.0)
    assert result.net_pnl_rupees == pytest.approx(5850.0)


def test_incomplete_trade_rupee_pnl_is_null() -> None:
    result = CostModel(
        slippage_points_per_side=1.0,
        brokerage_points_per_trade=0.5,
        other_cost_points_per_trade=0.5,
    ).apply_with_quantity(
        TradeLifecycleResult(
            entered=True,
            entry_price=200.0,
            exit_price=None,
            entry_timestamp=None,
            exit_timestamp=None,
            bars_held=3,
            exit_reason="NO_EXIT",
            pnl_points=None,
            max_favorable_excursion=80.0,
            max_adverse_excursion=100.0,
            notes="incomplete",
        ),
        quantity=50,
    )

    assert result.gross_pnl_rupees is None
    assert result.cost_rupees is None
    assert result.net_pnl_rupees is None


def test_zero_cost_mode_keeps_net_rupees_equal_to_gross_rupees() -> None:
    report = _historical_runner(cost_model=CostModel()).run(
        strategy_path=FOLDER_S23,
        daily_bars=load_daily_bars_csv(DAILY_MULTI_CSV),
        option_levels_series=load_option_levels_series_csv(OPTION_MULTI_CSV),
        option_intraday_bars=load_daily_bars_csv(OPTION_INTRADAY_CSV),
        runtime_values_base={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert report.metrics.total_cost_rupees == pytest.approx(0.0)
    assert report.metrics.total_gross_pnl_rupees == pytest.approx(
        report.metrics.total_net_pnl_rupees
    )
    assert report.metrics.average_net_pnl_rupees == pytest.approx(-496.7)


def test_markdown_report_includes_rupee_metrics(tmp_path: Path) -> None:
    json_output = tmp_path / "historical_costed.json"
    markdown_output = tmp_path / "historical_costed.md"
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--strategy-path",
            "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
            "--historical",
            "--daily-csv",
            str(DAILY_MULTI_CSV),
            "--option-levels-csv",
            str(OPTION_MULTI_CSV),
            "--option-intraday-csv",
            str(OPTION_INTRADAY_CSV),
            "--eod-policy",
            "square_off_at_close",
            "--slippage-points-per-side",
            "1.0",
            "--brokerage-points-per-trade",
            "0.5",
            "--other-cost-points-per-trade",
            "0.5",
            "--out",
            str(json_output),
            "--markdown-out",
            str(markdown_output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    markdown = markdown_output.read_text(encoding="utf-8")
    assert "total_gross_pnl_rupees" in markdown
    assert "total_net_pnl_rupees" in markdown
    assert "average_net_pnl_rupees" in markdown
    assert "Net Rupees" in markdown

    report = json.loads(json_output.read_text(encoding="utf-8"))
    assert report["metrics"]["total_gross_pnl_rupees"] is not None
    assert report["metrics"]["total_net_pnl_rupees"] is not None
