from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tfis.backtest import (
    EodExitPolicy,
    HistoricalBacktestRunner,
    load_daily_bars_csv,
    load_option_levels_series_csv,
)
from tfis.backtest.backtest_runner import BacktestRunner
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


def _runner(
    *,
    max_trades_per_day: int = 3,
    eod_policy: EodExitPolicy = EodExitPolicy.MARK_NO_EXIT,
) -> HistoricalBacktestRunner:
    return HistoricalBacktestRunner(
        BacktestRunner(
            structure_calculator=MarketStructureCalculator(),
            strategy_evaluator=StrategyEvaluator(),
            order_planner=OrderPlanner(),
            risk_policy=RiskPolicy(
                max_lots_per_trade=100,
                max_trades_per_day=max_trades_per_day,
                allow_short_options=True,
                paper_only=True,
            ),
        ),
        eod_policy=eod_policy,
    )


def test_historical_runner_processes_rows_chronologically_and_skips_initial_history() -> None:
    report = _runner().run(
        strategy_path=FOLDER_S23,
        daily_bars=load_daily_bars_csv(DAILY_MULTI_CSV),
        option_levels_series=load_option_levels_series_csv(OPTION_MULTI_CSV),
        runtime_values_base={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert report.metrics.total_evaluations == 6
    assert report.metrics.accepted_candidates == 6
    assert report.metrics.rejected_candidates == 0
    timestamps = [item.timestamp for item in report.evaluations]
    assert timestamps == sorted(timestamps)
    assert timestamps[0].isoformat() == "2026-05-18T15:30:00"
    assert report.strategy_root is None
    assert report.use_monthly_status_engine is False
    assert report.monthly_status_skips == ()
    assert report.evaluations[0].validation["strategy_config_ok"] is True
    assert report.evaluations[0].trade_outputs["entry_price"] == pytest.approx(197.95)
    assert report.evaluations[0].monthly_status is None
    assert report.evaluations[0].lifecycle_result is None


def test_historical_runner_rejected_counts_are_computed() -> None:
    report = _runner(max_trades_per_day=1).run(
        strategy_path=FOLDER_S23,
        daily_bars=load_daily_bars_csv(DAILY_MULTI_CSV),
        option_levels_series=load_option_levels_series_csv(OPTION_MULTI_CSV),
        runtime_values_base={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert report.metrics.total_evaluations == 6
    assert report.metrics.accepted_candidates == 0
    assert report.metrics.rejected_candidates == 6
    assert report.metrics.rejection_reason_distribution == {
        "Rejected: max_trades_per_day reached": 6
    }


def test_historical_runner_with_intraday_lifecycle_computes_trade_metrics() -> None:
    report = _runner().run(
        strategy_path=FOLDER_S23,
        daily_bars=load_daily_bars_csv(DAILY_MULTI_CSV),
        option_levels_series=load_option_levels_series_csv(OPTION_MULTI_CSV),
        option_intraday_bars=load_daily_bars_csv(OPTION_INTRADAY_CSV),
        runtime_values_base={"ENTRY": 200.0},
        lot_size=50,
        trades_taken_today=1,
    )

    assert report.metrics.total_evaluations == 6
    assert report.metrics.entered_trades == 5
    assert report.metrics.target_hits == 2
    assert report.metrics.stoploss_hits == 2
    assert report.metrics.no_entry == 1
    assert report.metrics.no_exit == 1
    assert report.metrics.eod_square_off == 0
    assert report.metrics.carry_forward_pending == 0
    assert report.metrics.total_pnl_points == pytest.approx(7.175)
    assert report.metrics.total_gross_pnl_points == pytest.approx(7.175)
    assert report.metrics.total_cost_points == pytest.approx(0.0)
    assert report.metrics.total_net_pnl_points == pytest.approx(7.175)
    assert report.metrics.total_gross_pnl_rupees == pytest.approx(358.75)
    assert report.metrics.total_cost_rupees == pytest.approx(0.0)
    assert report.metrics.total_net_pnl_rupees == pytest.approx(358.75)
    assert report.metrics.final_net_pnl_rupees == pytest.approx(358.75)
    assert report.metrics.max_drawdown_rupees == pytest.approx(11684.75)
    assert report.metrics.max_drawdown_points == pytest.approx(233.695)
    assert report.metrics.best_trade_net_rupees == pytest.approx(6105.0)
    assert report.metrics.worst_trade_net_rupees == pytest.approx(-5846.0)
    assert report.metrics.average_pnl_points == pytest.approx(1.79375)
    assert report.metrics.average_net_pnl_points == pytest.approx(1.79375)
    assert report.metrics.average_net_pnl_rupees == pytest.approx(89.6875)
    assert report.metrics.average_mfe == pytest.approx(85.94)
    assert report.metrics.average_mae == pytest.approx(70.46)
    assert report.metrics.win_rate == pytest.approx(0.5)
    assert report.metrics.loss_rate == pytest.approx(0.5)
    assert report.metrics.no_entry_rate == pytest.approx(1 / 6)
    assert report.metrics.no_exit_rate == pytest.approx(1 / 5)
    assert report.evaluations[0].lifecycle_result is not None
    assert report.evaluations[0].lifecycle_result.exit_reason == "TARGET_HIT"
    assert report.evaluations[0].lifecycle_result.entry_timestamp is not None
    assert report.evaluations[0].lifecycle_result.exit_timestamp is not None
    assert report.evaluations[0].lifecycle_result.max_favorable_excursion == pytest.approx(122.95)
    assert report.evaluations[0].lifecycle_result.max_adverse_excursion == pytest.approx(7.05)
    assert report.evaluations[0].lifecycle_result.cumulative_net_pnl_rupees == pytest.approx(5938.5)
    assert report.evaluations[0].lifecycle_result.drawdown_rupees == pytest.approx(0.0)
    assert report.evaluations[1].lifecycle_result is not None
    assert report.evaluations[1].lifecycle_result.cumulative_net_pnl_rupees == pytest.approx(92.5)
    assert report.evaluations[1].lifecycle_result.drawdown_rupees == pytest.approx(5846.0)
    assert report.evaluations[2].lifecycle_result is not None
    assert report.evaluations[2].lifecycle_result.exit_reason == "NO_ENTRY"
    assert report.evaluations[2].lifecycle_result.max_favorable_excursion is None
    assert report.evaluations[2].lifecycle_result.cumulative_net_pnl_rupees is None
    assert report.evaluations[2].lifecycle_result.drawdown_rupees is None
    assert report.evaluations[4].lifecycle_result is not None
    assert report.evaluations[4].lifecycle_result.cumulative_net_pnl_rupees == pytest.approx(-5746.25)
    assert report.evaluations[4].lifecycle_result.drawdown_rupees == pytest.approx(11684.75)
    assert report.evaluations[4].lifecycle_result is not None
    assert report.evaluations[4].lifecycle_result.exit_reason == "STOPLOSS_HIT"


def test_historical_runner_validation_is_still_enforced(tmp_path: Path) -> None:
    strategy_copy = tmp_path / "unsafe_s23"
    shutil.copytree(FOLDER_S23, strategy_copy)
    formulas_path = strategy_copy / "formulas.yaml"
    formulas = yaml.safe_load(formulas_path.read_text(encoding="utf-8"))
    formulas["entry_formula"] = "PRV_3DLL - PARAM(entry_discount_pct)%"
    formulas_path.write_text(
        yaml.safe_dump(formulas, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="entry_formula uses plain PRV_\\* reference",
    ):
        _runner().run(
            strategy_path=strategy_copy,
            daily_bars=load_daily_bars_csv(DAILY_MULTI_CSV),
            option_levels_series=load_option_levels_series_csv(OPTION_MULTI_CSV),
            runtime_values_base={"ENTRY": 200.0},
            lot_size=50,
            trades_taken_today=1,
        )


def test_run_backtest_script_historical_mode_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "historical_backtest.json"
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
            "--out",
            str(output_path),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["mode"] == "historical"
    assert len(report["evaluations"]) == 6
    assert report["metrics"]["accepted_candidates"] == 6
    assert report["evaluations"][0]["timestamp"] == "2026-05-18T15:30:00"
    assert report["use_monthly_status_engine"] is False
    assert report["monthly_status_skips"] == []
    assert report["evaluations"][0]["monthly_status"] is None


def test_run_backtest_script_historical_mode_with_lifecycle_writes_json(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "historical_backtest_with_lifecycle.json"
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
            "--out",
            str(output_path),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["mode"] == "historical"
    assert report["metrics"]["entered_trades"] == 5
    assert report["metrics"]["target_hits"] == 2
    assert report["metrics"]["stoploss_hits"] == 2
    assert report["metrics"]["no_entry"] == 1
    assert report["metrics"]["no_exit"] == 1
    assert report["metrics"]["eod_square_off"] == 0
    assert report["metrics"]["carry_forward_pending"] == 0
    assert report["metrics"]["total_gross_pnl_points"] == pytest.approx(7.175)
    assert report["metrics"]["total_cost_points"] == pytest.approx(0.0)
    assert report["metrics"]["total_net_pnl_points"] == pytest.approx(7.175)
    assert report["metrics"]["total_gross_pnl_rupees"] == pytest.approx(358.75)
    assert report["metrics"]["total_cost_rupees"] == pytest.approx(0.0)
    assert report["metrics"]["total_net_pnl_rupees"] == pytest.approx(358.75)
    assert report["metrics"]["final_net_pnl_rupees"] == pytest.approx(358.75)
    assert report["metrics"]["max_drawdown_rupees"] == pytest.approx(11684.75)
    assert report["metrics"]["max_drawdown_points"] == pytest.approx(233.695)
    assert report["metrics"]["best_trade_net_rupees"] == pytest.approx(6105.0)
    assert report["metrics"]["worst_trade_net_rupees"] == pytest.approx(-5846.0)
    assert report["metrics"]["average_pnl_points"] == pytest.approx(1.79375)
    assert report["metrics"]["average_net_pnl_points"] == pytest.approx(1.79375)
    assert report["metrics"]["average_net_pnl_rupees"] == pytest.approx(89.6875)
    assert report["metrics"]["average_mfe"] == pytest.approx(85.94)
    assert report["metrics"]["average_mae"] == pytest.approx(70.46)
    assert report["metrics"]["win_rate"] == pytest.approx(0.5)
    assert report["metrics"]["loss_rate"] == pytest.approx(0.5)
    assert report["evaluations"][0]["lifecycle_result"]["exit_reason"] == "TARGET_HIT"
    assert report["evaluations"][0]["lifecycle_result"]["bars_held"] == 2
    assert report["evaluations"][0]["lifecycle_result"]["quantity"] == 50
    assert report["evaluations"][0]["lifecycle_result"]["net_pnl_rupees"] == pytest.approx(5938.5)
    assert report["evaluations"][0]["lifecycle_result"]["cumulative_net_pnl_rupees"] == pytest.approx(5938.5)
    assert report["evaluations"][0]["lifecycle_result"]["drawdown_rupees"] == pytest.approx(0.0)
