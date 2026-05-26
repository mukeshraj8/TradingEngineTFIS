from __future__ import annotations

import csv
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
DATES = [
    "2026-05-18",
    "2026-05-19",
    "2026-05-20",
    "2026-05-21",
    "2026-05-22",
    "2026-05-23",
]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return env


def _make_local_tmp_dir() -> Path:
    base = ROOT / "tests" / "_tmp_pytest_local"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _strategy_path(folder_name: str) -> str:
    return f"config/strategies/options_sell/nifty/{folder_name}"


def _write_intraday_option_csv(
    path: Path,
    *,
    trigger_high: float,
    orpt_high: float,
    orpt_low: float,
    rc_high: float,
    rc_low: float,
    post_cutoff_high: float,
    post_cutoff_low: float,
) -> None:
    def row_values(high: float, low: float) -> tuple[float, float]:
        midpoint = (high + low) / 2.0
        return midpoint, midpoint

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for day in DATES:
            open_0915, close_0915 = row_values(trigger_high, 240.0)
            open_orpt, close_orpt = row_values(orpt_high, orpt_low)
            open_rc, close_rc = row_values(rc_high, rc_low)
            open_post, close_post = row_values(post_cutoff_high, post_cutoff_low)
            writer.writerow([f"{day}T09:15:00", open_0915, trigger_high, 240.0, close_0915, 100])
            writer.writerow([f"{day}T09:20:00", open_orpt, orpt_high, orpt_low, close_orpt, 120])
            writer.writerow([f"{day}T09:25:00", open_rc, rc_high, rc_low, close_rc, 140])
            writer.writerow([f"{day}T09:30:00", open_post, post_cutoff_high, post_cutoff_low, close_post, 160])


def _write_intraday_spot_csv(
    path: Path,
    *,
    trigger_high: float,
    trigger_low: float,
    orpt_high: float,
    orpt_low: float,
    rc_high: float,
    rc_low: float,
    post_cutoff_high: float,
    post_cutoff_low: float,
) -> None:
    def row_values(high: float, low: float) -> tuple[float, float]:
        midpoint = (high + low) / 2.0
        return midpoint, midpoint

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for day in DATES:
            open_0915, close_0915 = row_values(trigger_high, trigger_low)
            open_orpt, close_orpt = row_values(orpt_high, orpt_low)
            open_rc, close_rc = row_values(rc_high, rc_low)
            open_post, close_post = row_values(post_cutoff_high, post_cutoff_low)
            writer.writerow([f"{day}T09:15:00", open_0915, trigger_high, trigger_low, close_0915, 100])
            writer.writerow([f"{day}T09:20:00", open_orpt, orpt_high, orpt_low, close_orpt, 120])
            writer.writerow([f"{day}T09:25:00", open_rc, rc_high, rc_low, close_rc, 140])
            writer.writerow([f"{day}T09:30:00", open_post, post_cutoff_high, post_cutoff_low, close_post, 160])


def _run_historical_backtest(
    tmp_path: Path,
    *,
    strategy_folder_name: str,
    option_intraday_csv: Path,
    spot_intraday_csv: Path,
    enable_current_day_fsl_trp: bool,
) -> dict[str, object]:
    output_path = tmp_path / "historical_current_day_fsl_trp.json"
    command = [
        sys.executable,
        "scripts/run_backtest.py",
        "--strategy-path",
        _strategy_path(strategy_folder_name),
        "--historical",
        "--daily-csv",
        str(DAILY_MULTI_CSV),
        "--option-levels-csv",
        str(OPTION_MULTI_CSV),
        "--option-intraday-csv",
        str(option_intraday_csv),
        "--spot-intraday-csv",
        str(spot_intraday_csv),
        "--eod-policy",
        "square_off_at_close",
        "--out",
        str(output_path),
    ]
    if enable_current_day_fsl_trp:
        command.insert(-2, "--enable-s23-current-day-fsl-trp")

    result = subprocess.run(
        command,
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(output_path.read_text(encoding="utf-8"))


def _find_eval(
    report: dict[str, object],
    *,
    branch_unique_code: str,
) -> dict[str, object]:
    for evaluation in report["evaluations"]:
        audit = evaluation["validation"].get("s23_current_day_fsl_trp")
        if not isinstance(audit, dict):
            continue
        if audit.get("branch_unique_code") == branch_unique_code:
            return evaluation
    raise AssertionError(f"Could not find evaluation for {branch_unique_code}")


def test_default_historical_backtest_is_unchanged_without_current_day_fsl_trp_flag() -> None:
    tmp_path = _make_local_tmp_dir()
    option_csv = tmp_path / "option.csv"
    spot_csv = tmp_path / "spot.csv"
    _write_intraday_option_csv(
        option_csv,
        trigger_high=320.0,
        orpt_high=325.0,
        orpt_low=240.0,
        rc_high=330.0,
        rc_low=220.0,
        post_cutoff_high=340.0,
        post_cutoff_low=190.0,
    )
    _write_intraday_spot_csv(
        spot_csv,
        trigger_high=22320.0,
        trigger_low=22210.0,
        orpt_high=22480.0,
        orpt_low=22150.0,
        rc_high=22650.0,
        rc_low=22120.0,
        post_cutoff_high=22720.0,
        post_cutoff_low=22080.0,
    )

    report = _run_historical_backtest(
        tmp_path,
        strategy_folder_name="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        option_intraday_csv=option_csv,
        spot_intraday_csv=spot_csv,
        enable_current_day_fsl_trp=False,
    )

    assert "enable_s23_current_day_fsl_trp" not in report
    assert "s23_current_day_fsl_trp" not in report["evaluations"][0]["validation"]


def test_row_184_bull_call_missed_updates_effective_plan_entry_and_records_resolution_audit() -> None:
    tmp_path = _make_local_tmp_dir()
    option_csv = tmp_path / "option_row_184.csv"
    spot_csv = tmp_path / "spot_row_184.csv"
    _write_intraday_option_csv(
        option_csv,
        trigger_high=320.0,
        orpt_high=325.0,
        orpt_low=245.0,
        rc_high=330.0,
        rc_low=220.0,
        post_cutoff_high=360.0,
        post_cutoff_low=190.0,
    )
    _write_intraday_spot_csv(
        spot_csv,
        trigger_high=22320.0,
        trigger_low=22210.0,
        orpt_high=22480.0,
        orpt_low=22150.0,
        rc_high=22650.0,
        rc_low=22120.0,
        post_cutoff_high=22720.0,
        post_cutoff_low=22080.0,
    )

    report = _run_historical_backtest(
        tmp_path,
        strategy_folder_name="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        option_intraday_csv=option_csv,
        spot_intraday_csv=spot_csv,
        enable_current_day_fsl_trp=True,
    )

    evaluation = _find_eval(
        report,
        branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
    )
    audit = evaluation["validation"]["s23_current_day_fsl_trp"]

    assert report["enable_s23_current_day_fsl_trp"] is True
    assert audit["applied"] is True
    assert audit["result"]["row_number"] == 184
    assert audit["result"]["effective_option_type"] == "PUT"
    assert audit["result"]["recalculated_entry_price"] == pytest.approx(188.7)
    assert audit["result"]["entry_override_source_cell"] == "AB6_OS_Z184"
    assert audit["entry_override"] == {
        "applied": True,
        "source_cell": "AB6_OS_Z184",
        "original_entry_price": pytest.approx(197.95),
        "overridden_entry_price": pytest.approx(188.7),
        "effective_entry_price": pytest.approx(188.7),
    }
    assert audit["resolved_workbook_clarifications"]
    assert (
        audit["resolved_workbook_clarifications"][0]["id"]
        == "s23_fsl_trp_row_184_mixed_mapping"
    )
    assert evaluation["trade_outputs"]["start_strike"] == 21518
    assert evaluation["trade_outputs"]["entry_price"] == pytest.approx(188.7)
    assert evaluation["trade_outputs"]["ideal_premium"] == pytest.approx(265.44)
    assert evaluation["trade_outputs"]["minimum_premium"] == pytest.approx(199.08)
    assert evaluation["trade_outputs"]["stoploss_price"] == pytest.approx(353.1)


def test_row_187_bull_put_missed_is_fsl_only_and_does_not_infer_blank_entry_fields() -> None:
    tmp_path = _make_local_tmp_dir()
    option_csv = tmp_path / "option_row_187.csv"
    spot_csv = tmp_path / "spot_row_187.csv"
    _write_intraday_option_csv(
        option_csv,
        trigger_high=325.0,
        orpt_high=330.0,
        orpt_low=240.0,
        rc_high=340.0,
        rc_low=230.0,
        post_cutoff_high=350.0,
        post_cutoff_low=200.0,
    )
    _write_intraday_spot_csv(
        spot_csv,
        trigger_high=22320.0,
        trigger_low=22210.0,
        orpt_high=22420.0,
        orpt_low=22170.0,
        rc_high=22520.0,
        rc_low=22100.0,
        post_cutoff_high=22610.0,
        post_cutoff_low=22090.0,
    )

    report = _run_historical_backtest(
        tmp_path,
        strategy_folder_name="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
        option_intraday_csv=option_csv,
        spot_intraday_csv=spot_csv,
        enable_current_day_fsl_trp=True,
    )

    evaluation = _find_eval(
        report,
        branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
    )
    audit = evaluation["validation"]["s23_current_day_fsl_trp"]

    assert audit["applied"] is True
    assert audit["result"]["row_number"] == 187
    assert audit["result"]["recalculated_entry_price"] is None
    assert audit["result"]["entry_override_source_cell"] is None
    assert audit["entry_override"] == {
        "applied": False,
        "source_cell": None,
        "original_entry_price": pytest.approx(audit["base_trade_plan"]["entry_price"]),
        "overridden_entry_price": None,
        "effective_entry_price": pytest.approx(audit["effective_trade_plan"]["entry_price"]),
    }
    assert evaluation["trade_outputs"]["start_strike"] == pytest.approx(
        audit["base_trade_plan"]["start_strike"]
    )
    assert evaluation["trade_outputs"]["entry_price"] == pytest.approx(
        audit["base_trade_plan"]["entry_price"]
    )
    assert evaluation["trade_outputs"]["ideal_premium"] == pytest.approx(
        audit["base_trade_plan"]["ideal_premium"]
    )
    assert evaluation["trade_outputs"]["stoploss_price"] == pytest.approx(374.0)
    assert "entry_price" in audit["result"]["unsupported_fields"]
    assert "minimum_premium" in audit["result"]["unsupported_fields"]
