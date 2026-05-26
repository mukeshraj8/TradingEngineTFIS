from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tfis.backtest import BacktestCsvError
from tfis.backtest.shared_data_adapter import (
    discover_shared_data_roots,
    resolve_shared_backtest_dataset,
)


ROOT = Path(__file__).resolve().parents[2]
SHARED_FIXTURES_ROOT = ROOT / "tests" / "fixtures" / "shared_data"
SCOPED_NIFTY_ROOT = SHARED_FIXTURES_ROOT / "nifty"
STRATEGY_ROOT = ROOT / "config" / "strategies" / "options_sell" / "nifty"
BACKTEST_DAILY_CSV = ROOT / "tests" / "fixtures" / "backtest" / "s23_daily.csv"
BACKTEST_OPTION_LEVELS_CSV = (
    ROOT / "tests" / "fixtures" / "backtest" / "s23_option_levels.csv"
)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return env


def test_complete_normalized_root_resolves_all_files() -> None:
    dataset = resolve_shared_backtest_dataset(SCOPED_NIFTY_ROOT)

    assert dataset.is_complete is True
    assert dataset.missing_files == ()
    assert dataset.daily_csv == SCOPED_NIFTY_ROOT / "daily.csv"
    assert dataset.weekly_csv == SCOPED_NIFTY_ROOT / "weekly.csv"
    assert dataset.monthly_csv == SCOPED_NIFTY_ROOT / "monthly.csv"
    assert dataset.option_levels_csv == SCOPED_NIFTY_ROOT / "option_levels.csv"
    assert dataset.option_chain_csv == SCOPED_NIFTY_ROOT / "option_chain.csv"
    assert dataset.option_intraday_csv == SCOPED_NIFTY_ROOT / "option_intraday.csv"


def test_parent_shared_root_discovers_and_infers_instrument_dataset() -> None:
    discovered = discover_shared_data_roots(SHARED_FIXTURES_ROOT)
    dataset = resolve_shared_backtest_dataset(
        SHARED_FIXTURES_ROOT,
        strategy_root=STRATEGY_ROOT,
    )

    assert SCOPED_NIFTY_ROOT in discovered
    assert dataset.daily_csv == SCOPED_NIFTY_ROOT / "daily.csv"


def test_missing_files_reported_clearly(tmp_path: Path) -> None:
    shared_root = tmp_path / "nifty"
    shared_root.mkdir(parents=True)
    (shared_root / "daily.csv").write_text(
        "timestamp,open,high,low,close\n2026-05-18T15:30:00,1,2,0.5,1.5\n",
        encoding="utf-8",
    )

    with pytest.raises(BacktestCsvError, match="missing required normalized files"):
        resolve_shared_backtest_dataset(shared_root)


def test_allow_partial_shared_data_returns_incomplete_dataset(tmp_path: Path) -> None:
    shared_root = tmp_path / "nifty"
    shared_root.mkdir(parents=True)
    (shared_root / "daily.csv").write_text(
        "timestamp,open,high,low,close\n2026-05-18T15:30:00,1,2,0.5,1.5\n",
        encoding="utf-8",
    )

    dataset = resolve_shared_backtest_dataset(shared_root, allow_partial=True)

    assert dataset.is_complete is False
    assert "weekly.csv" in dataset.missing_files
    assert dataset.daily_csv == shared_root / "daily.csv"


def test_shared_data_adapter_has_no_tradingengine_import_dependency() -> None:
    source_path = ROOT / "src" / "tfis" / "backtest" / "shared_data_adapter.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_roots: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])

    assert "TradingEngine" not in imported_roots
    assert "TradingEngineProd" not in imported_roots
    assert "NiftyTradingEngine" not in imported_roots


def test_explicit_csv_args_still_work_unchanged_without_shared_root(tmp_path: Path) -> None:
    output_path = tmp_path / "csv_backtest.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--strategy-path",
            "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
            "--daily-csv",
            str(BACKTEST_DAILY_CSV),
            "--option-levels-csv",
            str(BACKTEST_OPTION_LEVELS_CSV),
            "--out",
            str(output_path),
        ],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["mode"] == "csv"
    assert "shared_data_root" not in report
    assert report["result"]["trade_plan"]["entry_price"] == pytest.approx(203.5)


def test_shared_root_path_can_be_instrument_scoped() -> None:
    dataset = resolve_shared_backtest_dataset(SHARED_FIXTURES_ROOT / "nifty")

    assert dataset.daily_csv is not None
    assert dataset.option_levels_csv is not None
