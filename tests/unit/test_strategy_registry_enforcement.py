from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from tfis.backtest import BacktestInput, BacktestRunner
from tfis.execution.order_planner import OrderPlanner
from tfis.importers import assert_backtest_allowed, get_strategy_status
from tfis.market_structure.ohlc import OhlcBar
from tfis.market_structure.structure_calculator import MarketStructureCalculator
from tfis.risk.risk_policy import RiskPolicy
from tfis.strategy.strategy_evaluator import StrategyEvaluator


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"
FOLDER_S23 = STRATEGY_ROOT / "S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
REGISTRY_PATH = ROOT / "config" / "strategy_registry.yaml"


def _daily_bars() -> list[OhlcBar]:
    return [
        OhlcBar(datetime(2026, 5, 19, 15, 30), 22150.0, 22300.0, 21900.0, 22250.0),
        OhlcBar(datetime(2026, 5, 20, 15, 30), 22250.0, 22400.0, 22000.0, 22350.0),
        OhlcBar(datetime(2026, 5, 21, 15, 30), 22350.0, 22500.0, 22100.0, 22420.0),
        OhlcBar(datetime(2026, 5, 22, 15, 30), 22400.0, 22450.0, 22200.0, 22380.0),
        OhlcBar(datetime(2026, 5, 23, 15, 30), 22320.0, 22400.0, 22100.0, 22310.0),
    ]


def _runner() -> BacktestRunner:
    return BacktestRunner(
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


def _backtest_input(strategy_path: Path) -> BacktestInput:
    return BacktestInput(
        strategy_path=strategy_path,
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


def test_s23_active_candidate_is_allowed_for_backtest() -> None:
    assert get_strategy_status("S23_NIFTY_OP_SELL_WK_DIFF_2D_3D") == "ACTIVE_CANDIDATE"
    assert assert_backtest_allowed("S23_NIFTY_OP_SELL_WK_DIFF_2D_3D") == "ACTIVE_CANDIDATE"

    result = _runner().run(_backtest_input(FOLDER_S23))
    assert result.accepted is True


def test_historical_backtest_only_is_allowed_for_backtest_with_registry_helper() -> None:
    assert (
        assert_backtest_allowed("BANKNIFTY_WEEKLY_OPTIONS_SELL")
        == "HISTORICAL_BACKTEST_ONLY"
    )


def test_unknown_requires_review_is_refused() -> None:
    with pytest.raises(
        ValueError,
        match="UNKNOWN_REQUIRES_REVIEW",
    ):
        assert_backtest_allowed("MONTHLY_OPTION_BUYING")


def test_discontinued_is_refused(tmp_path: Path) -> None:
    temp_registry = tmp_path / "strategy_registry.yaml"
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry["strategies"]["TEST_DISCONTINUED"] = {"status": "DISCONTINUED"}
    temp_registry.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="DISCONTINUED"):
        assert_backtest_allowed("TEST_DISCONTINUED", temp_registry)


def test_missing_registry_entry_currently_passes_backtest_gate() -> None:
    assert get_strategy_status("NON_EXISTENT_STRATEGY") is None
    assert assert_backtest_allowed("NON_EXISTENT_STRATEGY") is None


def test_backtest_runner_refuses_unknown_requires_review_strategy(tmp_path: Path) -> None:
    strategy_copy = tmp_path / "monthly_option_buying_folder"
    strategy_copy.mkdir()
    for name in (
        "strategy.yaml",
        "formulas.yaml",
        "parameters.yaml",
        "notes.md",
        "excel_crosscheck.yaml",
    ):
        (strategy_copy / name).write_text((FOLDER_S23 / name).read_text(encoding="utf-8"), encoding="utf-8")

    strategy_data = yaml.safe_load((strategy_copy / "strategy.yaml").read_text(encoding="utf-8"))
    strategy_data["unique_code"] = "MONTHLY_OPTION_BUYING"
    (strategy_copy / "strategy.yaml").write_text(
        yaml.safe_dump(strategy_data, sort_keys=False),
        encoding="utf-8",
    )
    crosscheck_data = yaml.safe_load((strategy_copy / "excel_crosscheck.yaml").read_text(encoding="utf-8"))
    crosscheck_data["unique_code"] = "MONTHLY_OPTION_BUYING"
    (strategy_copy / "excel_crosscheck.yaml").write_text(
        yaml.safe_dump(crosscheck_data, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="UNKNOWN_REQUIRES_REVIEW"):
        _runner().run(_backtest_input(strategy_copy))


def test_validate_strategy_configs_prints_registry_statuses() -> None:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"

    result = subprocess.run(
        [sys.executable, "scripts/validate_strategy_configs.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "STATUS config\\strategies\\options_sell\\nifty\\S23_NIFTY_OP_SELL_WK_DIFF_2D_3D\\strategy.yaml ACTIVE_CANDIDATE"
        in result.stdout
    )
