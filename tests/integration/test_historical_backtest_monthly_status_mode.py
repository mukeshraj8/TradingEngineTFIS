from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "backtest"
DAILY_MULTI_CSV = FIXTURES / "s23_daily_multi.csv"
OPTION_MULTI_CSV = FIXTURES / "s23_option_levels_multi.csv"
OPTION_INTRADAY_CSV = FIXTURES / "s23_option_intraday.csv"
OPTION_CHAIN_CSV = FIXTURES / "s23_option_chain.csv"
MONTHLY_CSV = FIXTURES / "s23_monthly.csv"
WEEKLY_CSV = FIXTURES / "s23_weekly.csv"
STRATEGY_ROOT = "config/strategies/options_sell/nifty"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return env


def test_historical_monthly_status_mode_selects_bull_and_bear_branches(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "historical_monthly_status.json"

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
            str(OPTION_INTRADAY_CSV),
            "--historical",
            "--eod-policy",
            "square_off_at_close",
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

    assert report["mode"] == "historical"
    assert report["use_monthly_status_engine"] is True
    assert "enable_option_chain_selection" not in report
    assert report["strategy_root"].endswith("config\\strategies\\options_sell\\nifty")
    assert report["strategy_path"] is None
    assert report["metrics"]["total_evaluations"] == 10
    assert report["monthly_status_skips"]
    assert report["monthly_status_skips"][0]["reason"] == "no eligible strategy branches for monthly status UNKNOWN"

    first_eval = report["evaluations"][0]
    assert first_eval["monthly_status"] == "BULL"
    assert first_eval["monthly_status_trigger"] == "BULL_A_THRESHOLD"
    assert first_eval["selected_branch_unique_codes"] == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    ]
    assert first_eval["monthly_status_candidates"]
    assert "option_chain_selection" not in first_eval["validation"]

    bear_eval = next(
        item for item in report["evaluations"] if item["monthly_status"] in {"BEAR", "BEAR_CF"}
    )
    assert bear_eval["selected_branch_unique_codes"] == [
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
    ]


def test_historical_monthly_status_mode_requires_monthly_and_weekly_csvs(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "historical_monthly_status_missing.json"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--strategy-root",
            STRATEGY_ROOT,
            "--use-monthly-status-engine",
            "--daily-csv",
            str(DAILY_MULTI_CSV),
            "--option-levels-csv",
            str(OPTION_MULTI_CSV),
            "--historical",
            "--out",
            str(output_path),
        ],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "--use-monthly-status-engine requires monthly and weekly OHLC data from explicit CSV flags or --shared-data-root"
        in result.stderr
    )


def test_historical_monthly_status_mode_skips_when_reference_data_is_insufficient(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "historical_monthly_status_insufficient.json"
    short_monthly_csv = tmp_path / "short_monthly.csv"
    short_monthly_csv.write_text(
        "timestamp,open,high,low,close\n2026-04-30T15:30:00,95,100,90,96\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_backtest.py",
            "--strategy-root",
            STRATEGY_ROOT,
            "--use-monthly-status-engine",
            "--monthly-csv",
            str(short_monthly_csv),
            "--weekly-csv",
            str(WEEKLY_CSV),
            "--daily-csv",
            str(DAILY_MULTI_CSV),
            "--option-levels-csv",
            str(OPTION_MULTI_CSV),
            "--historical",
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
    assert report["evaluations"] == []
    assert report["monthly_status_skips"]
    assert report["monthly_status_skips"][0]["reason"] == "missing current month reference bars"


def test_historical_monthly_status_mode_option_chain_selection_reports_selected_contract(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "historical_monthly_status_option_chain.json"

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
            str(OPTION_INTRADAY_CSV),
            "--option-chain-csv",
            str(OPTION_CHAIN_CSV),
            "--enable-option-chain-selection",
            "--historical",
            "--eod-policy",
            "square_off_at_close",
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
    first_eval = report["evaluations"][0]
    selection = first_eval["validation"]["option_chain_selection"]

    assert report["enable_option_chain_selection"] is True
    assert selection["selected"] is True
    assert selection["selection_reason"] == "Selected contract closest to ideal premium."
    assert selection["selected_contract"]["symbol"] == "NIFTY_20260528_22100_CE"
    assert selection["selected_contract"]["option_type"] == "CALL"
    assert selection["selected_contract"]["ltp"] == pytest.approx(263.0)


def test_historical_monthly_status_mode_rejects_candidate_when_option_chain_selection_fails(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "historical_monthly_status_option_chain_rejected.json"
    bad_chain_csv = tmp_path / "bad_option_chain.csv"
    bad_chain_csv.write_text(
        "\n".join(
            [
                "timestamp,symbol,option_type,strike,expiry,bid,ask,ltp,oi,volume",
                "2026-05-18T15:30:00,NIFTY_20260528_22100_CE,CALL,22100,2026-05-28,261,263,262,100,1000",
                "2026-05-18T15:30:00,NIFTY_20260528_22300_PE,PUT,22300,2026-05-28,267,269,268,100,1000",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

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
            str(OPTION_INTRADAY_CSV),
            "--option-chain-csv",
            str(bad_chain_csv),
            "--enable-option-chain-selection",
            "--historical",
            "--eod-policy",
            "square_off_at_close",
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
    rejected_eval = next(
        item
        for item in report["evaluations"]
        if item["validation"].get("option_chain_selection", {}).get("selected") is False
    )
    selection = rejected_eval["validation"]["option_chain_selection"]

    assert rejected_eval["accepted"] is False
    assert rejected_eval["rejection_reason"].startswith(
        "Rejected: option-chain selection failed - "
    )
    assert selection["selected"] is False
    assert "minimum_oi" in selection["selection_reason"]
