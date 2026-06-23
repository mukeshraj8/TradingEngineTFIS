from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tfis.backtest.csv_loader import (
    BacktestCsvError,
    load_daily_bars_csv,
    load_option_levels_csv,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "backtest"
DAILY_CSV = FIXTURES / "s23_daily.csv"
OPTION_LEVELS_CSV = FIXTURES / "s23_option_levels.csv"


def test_csv_loader_parses_daily_bars() -> None:
    bars = load_daily_bars_csv(DAILY_CSV)

    assert len(bars) == 5
    assert bars[0].timestamp.isoformat() == "2026-05-19T15:30:00"
    assert bars[0].open == pytest.approx(22150.0)
    assert bars[-1].close == pytest.approx(22310.0)
    assert bars[-1].volume == pytest.approx(1250.0)


def test_csv_loader_parses_option_levels_latest_snapshot() -> None:
    option_levels = load_option_levels_csv(OPTION_LEVELS_CSV)

    assert option_levels["OPT_PRV_2DHH"] == pytest.approx(300.0)
    assert option_levels["OPT_PRV_2DLL"] == pytest.approx(210.0)
    assert option_levels["OPT_PRV_3DHH"] == pytest.approx(310.0)
    assert option_levels["OPT_PRV_3DLL"] == pytest.approx(220.0)


def test_missing_required_column_fails_clearly(tmp_path: Path) -> None:
    csv_path = tmp_path / "missing_close.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,open,high,low",
                "2026-05-23T15:30:00,22320,22400,22100",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(BacktestCsvError, match="Missing required columns"):
        load_daily_bars_csv(csv_path)


def test_invalid_numeric_value_fails_clearly(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad_option_levels.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,opt_prv_2dhh,opt_prv_2dll,opt_prv_3dhh,opt_prv_3dll",
                "2026-05-23T15:30:00,300,210,310,bad",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(BacktestCsvError, match="Invalid numeric value for opt_prv_3dll"):
        load_option_levels_csv(csv_path)


def test_run_backtest_script_csv_mode_writes_json(tmp_path: Path) -> None:
    output_path = tmp_path / "csv_backtest.json"
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
            "--daily-csv",
            str(DAILY_CSV),
            "--option-levels-csv",
            str(OPTION_LEVELS_CSV),
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
    assert report["mode"] == "csv"
    assert report["result"]["strategy_code"] == "S23"
    assert report["result"]["trade_plan"]["entry_price"] == pytest.approx(203.5)
    assert report["result"]["trade_plan"]["stoploss_price"] == pytest.approx(321.0)
    assert report["metrics"]["accepted_trades"] == 1
