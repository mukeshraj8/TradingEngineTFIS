from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from tfis.backtest import BacktestInput, BacktestRunner, build_backtest_metrics
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
LEGACY_S23 = ROOT / "config" / "strategies" / "legacy" / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml"


def _daily_bars() -> list[OhlcBar]:
    return [
        OhlcBar(datetime(2026, 5, 19, 15, 30), 22150.0, 22300.0, 21900.0, 22250.0),
        OhlcBar(datetime(2026, 5, 20, 15, 30), 22250.0, 22400.0, 22000.0, 22350.0),
        OhlcBar(datetime(2026, 5, 21, 15, 30), 22350.0, 22500.0, 22100.0, 22420.0),
        OhlcBar(datetime(2026, 5, 22, 15, 30), 22400.0, 22450.0, 22200.0, 22380.0),
        OhlcBar(datetime(2026, 5, 23, 15, 30), 22320.0, 22400.0, 22100.0, 22310.0),
    ]


def _runner(*, max_trades_per_day: int = 3) -> BacktestRunner:
    return BacktestRunner(
        structure_calculator=MarketStructureCalculator(),
        strategy_evaluator=StrategyEvaluator(),
        order_planner=OrderPlanner(),
        risk_policy=RiskPolicy(
            max_lots_per_trade=100,
            max_trades_per_day=max_trades_per_day,
            allow_short_options=True,
            paper_only=True,
        ),
    )


def test_backtest_accepts_valid_folder_strategy() -> None:
    result = _runner().run(
        BacktestInput(
            strategy_path=FOLDER_S23,
            daily_bars=_daily_bars(),
            intraday_bars=None,
            runtime_values={
                "ENTRY": 200.0,
                "OPT_LEVELS": {
                    "OPT_PRV_3DLL": 220.0,
                    "OPT_PRV_2DHH": 300.0,
                },
            },
            lot_size=50,
            trades_taken_today=1,
        )
    )

    assert result.strategy_code == "S23"
    assert result.accepted is True
    assert result.reason == "Approved"
    assert result.validation.strategy_config_ok is True
    assert result.validation.formula_safety_findings == []
    assert result.trade_plan.ideal_premium == pytest.approx(264.0)
    assert result.trade_plan.entry_price == pytest.approx(203.5)


def test_backtest_refuses_legacy_yaml_path() -> None:
    with pytest.raises(
        ValueError,
        match="folder-based strategy paths only",
    ):
        _runner().run(
            BacktestInput(
                strategy_path=LEGACY_S23,
                daily_bars=_daily_bars(),
                intraday_bars=None,
                runtime_values={"ENTRY": 200.0},
                lot_size=50,
                trades_taken_today=1,
            )
        )


def test_backtest_risk_rejection_appears_in_metrics() -> None:
    result = _runner(max_trades_per_day=1).run(
        BacktestInput(
            strategy_path=FOLDER_S23,
            daily_bars=_daily_bars(),
            intraday_bars=None,
            runtime_values={
                "ENTRY": 200.0,
                "OPT_LEVELS": {
                    "OPT_PRV_3DLL": 220.0,
                    "OPT_PRV_2DHH": 300.0,
                },
            },
            lot_size=50,
            trades_taken_today=1,
        )
    )

    metrics = build_backtest_metrics([result])

    assert result.accepted is False
    assert metrics.total_candidates == 1
    assert metrics.accepted_trades == 0
    assert metrics.rejected_trades == 1
    assert metrics.rejection_reasons == {
        "Rejected: max_trades_per_day reached": 1
    }


def test_run_backtest_script_sample_mode_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "sample_backtest.json"
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
            "--sample",
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
    assert report["mode"] == "sample"
    assert report["validation"]["strategy_config_ok"] is True
    assert report["validation"]["formula_safety_findings"] == []
    assert report["result"]["strategy_code"] == "S23"
    assert report["result"]["trade_plan"]["entry_price"] == pytest.approx(203.5)
    assert report["result"]["trade_plan"]["stoploss_price"] == pytest.approx(321.0)
    assert report["metrics"]["accepted_trades"] == 1
