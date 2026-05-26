from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "backtest"
DAILY_MULTI_CSV = FIXTURES / "s23_daily_multi.csv"
OPTION_MULTI_CSV = FIXTURES / "s23_option_levels_multi.csv"
OPTION_INTRADAY_CSV = FIXTURES / "s23_option_intraday.csv"
OPTION_INTRADAY_EXPIRY_PENDING_CSV = FIXTURES / "s23_option_intraday_expiry_pending.csv"
OPTION_CHAIN_EXPIRY_DAY_CSV = FIXTURES / "s23_option_chain_expiry_day.csv"
MONTHLY_CSV = FIXTURES / "s23_monthly.csv"
WEEKLY_CSV = FIXTURES / "s23_weekly.csv"
STRATEGY_ROOT = "config/strategies/options_sell/nifty"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return env


def _output_path(name: str) -> Path:
    output_dir = ROOT / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / name


def _run_expiry_day_report(
    *,
    output_name: str,
    option_intraday_csv: Path,
    eod_policy: str,
) -> dict[str, object]:
    output_path = _output_path(output_name)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--strategy-root",
            STRATEGY_ROOT,
            "--use-monthly-status-engine",
            "--monthly-csv",
            str(MONTHLY_CSV),
            "--weekly-csv",
            str(WEEKLY_CSV),
            "--daily-csv",
            str(DAILY_MULTI_CSV),
            "--option-levels-csv",
            str(OPTION_MULTI_CSV),
            "--option-intraday-csv",
            str(option_intraday_csv),
            "--option-chain-csv",
            str(OPTION_CHAIN_EXPIRY_DAY_CSV),
            "--enable-option-chain-selection",
            "--historical",
            "--eod-policy",
            eod_policy,
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
    return json.loads(output_path.read_text(encoding="utf-8"))


def test_expiry_day_review_marks_satisfied_exit_when_contract_expires_on_trade_date() -> None:
    report = _run_expiry_day_report(
        output_name="historical_expiry_day_review_satisfied.json",
        option_intraday_csv=OPTION_INTRADAY_CSV,
        eod_policy="square_off_at_close",
    )

    expiry_day_evaluations = [
        item
        for item in report["evaluations"]
        if item["validation"]["expiry_day_review"]["is_expiry_day"] is True
    ]

    assert report["metrics"]["expiry_day_candidates"] == 2
    assert report["metrics"]["expiry_day_exit_satisfied"] == 2
    assert report["metrics"]["expiry_day_exit_pending"] == 0
    assert expiry_day_evaluations
    assert all(
        item["validation"]["expiry_day_review"]["exit_satisfied"] is True
        for item in expiry_day_evaluations
    )


def test_expiry_day_review_warns_when_expiry_day_position_remains_open() -> None:
    report = _run_expiry_day_report(
        output_name="historical_expiry_day_review_pending.json",
        option_intraday_csv=OPTION_INTRADAY_EXPIRY_PENDING_CSV,
        eod_policy="mark_no_exit",
    )

    pending_evaluation = next(
        item
        for item in report["evaluations"]
        if item["validation"]["expiry_day_review"]["exit_satisfied"] is False
    )

    assert report["metrics"]["expiry_day_candidates"] == 2
    assert report["metrics"]["expiry_day_exit_pending"] >= 1
    assert pending_evaluation["lifecycle_result"]["exit_reason"] == "NO_EXIT"
    assert "requires full exit" in pending_evaluation["validation"]["expiry_day_review"]["warning"]
