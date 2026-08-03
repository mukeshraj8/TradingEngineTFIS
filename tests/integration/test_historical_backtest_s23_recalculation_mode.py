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
OPTION_INTRADAY_CSV = FIXTURES / "s23_option_intraday.csv"
SPOT_INTRADAY_CSV = FIXTURES / "s23_spot_intraday.csv"
MONTHLY_CSV = FIXTURES / "s23_monthly.csv"
WEEKLY_CSV = FIXTURES / "s23_weekly.csv"
STRATEGY_ROOT = "config/strategies/options_sell/nifty"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return env


def _run_historical_monthly_status_backtest(
    tmp_path: Path,
    *,
    enable_recalculation: bool = False,
    option_intraday_csv: Path = OPTION_INTRADAY_CSV,
    spot_intraday_csv: Path | None = None,
) -> dict[str, object]:
    output_path = tmp_path / "historical_monthly_status_recalc.json"
    command = [
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
        "--historical",
        "--eod-policy",
        "square_off_at_close",
        "--out",
        str(output_path),
    ]
    if spot_intraday_csv is not None:
        command.extend(
            [
                "--spot-intraday-csv",
                str(spot_intraday_csv),
            ]
        )
    if enable_recalculation:
        command.insert(-2, "--enable-s23-recalculation")

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
    entry_missed: bool | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    for evaluation in report["evaluations"]:
        if timestamp is not None and evaluation["timestamp"] != timestamp:
            continue
        audit = evaluation["validation"].get("s23_recalculation")
        if not isinstance(audit, dict):
            continue
        if audit.get("branch_unique_code") != branch_unique_code:
            continue
        if entry_missed is not None and audit.get("entry_missed") is not entry_missed:
            continue
        return evaluation
    raise AssertionError(
        f"Could not find evaluation for branch {branch_unique_code} with entry_missed={entry_missed} timestamp={timestamp}"
    )


def _write_sparse_intraday_csv(path: Path) -> None:
    rows = [
        ["timestamp", "open", "high", "low", "close", "volume"],
        ["2026-05-18T10:00:00", "220", "230", "210", "225", "100"],
        ["2026-05-19T10:00:00", "220", "230", "210", "225", "100"],
        ["2026-05-20T10:00:00", "220", "230", "210", "225", "100"],
        ["2026-05-21T10:00:00", "220", "230", "210", "225", "100"],
        ["2026-05-22T10:00:00", "220", "230", "210", "225", "100"],
        ["2026-05-23T10:00:00", "220", "230", "210", "225", "100"],
    ]
    path.write_text(
        "\n".join(",".join(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_put_missed_intraday_csv(path: Path) -> None:
    with OPTION_INTRADAY_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    for row in rows:
        if row["timestamp"] == "2026-05-18T09:20:00":
            row["low"] = "180"
            row["close"] = "185"
        if row["timestamp"] == "2026-05-18T09:25:00":
            row["low"] = "170"
            row["close"] = "175"

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_default_historical_monthly_status_backtest_is_unchanged_without_flag(
    tmp_path: Path,
) -> None:
    report = _run_historical_monthly_status_backtest(
        tmp_path,
        enable_recalculation=False,
    )

    assert "enable_s23_recalculation" not in report
    assert report["metrics"]["total_evaluations"] == 12
    assert report["evaluations"][0]["trade_outputs"]["entry_price"] == pytest.approx(197.95)
    assert "s23_recalculation" not in report["evaluations"][0]["validation"]


def test_recalculation_mode_uses_recalculated_entry_when_entry_is_missed(
    tmp_path: Path,
) -> None:
    report = _run_historical_monthly_status_backtest(
        tmp_path,
        enable_recalculation=True,
    )

    evaluation = _find_eval(
        report,
        branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        entry_missed=True,
    )
    audit = evaluation["validation"]["s23_recalculation"]

    assert report["enable_s23_recalculation"] is True
    assert audit["recalculation_applied"] is True
    assert (
        audit["spot_snapshot_source"]
        == "current_day_low_high_fallback_from_market_levels"
    )
    assert evaluation["trade_outputs"]["entry_price"] == pytest.approx(
        audit["recalculated_trade_plan"]["entry_price"]
    )
    assert evaluation["trade_outputs"]["entry_price"] != pytest.approx(
        audit["base_trade_plan"]["entry_price"]
    )
    assert evaluation["lifecycle_result"]["entry_price"] == pytest.approx(
        audit["recalculated_trade_plan"]["entry_price"]
    )


def test_recalculation_mode_uses_spot_intraday_csv_when_provided(
    tmp_path: Path,
) -> None:
    report = _run_historical_monthly_status_backtest(
        tmp_path,
        enable_recalculation=True,
        spot_intraday_csv=SPOT_INTRADAY_CSV,
    )

    evaluation = _find_eval(
        report,
        branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        entry_missed=True,
    )
    audit = evaluation["validation"]["s23_recalculation"]

    assert audit["spot_snapshot_source"] == "spot_intraday_csv"
    assert audit["recalculation_spot_snapshot_source"] == "spot_intraday_csv"
    assert audit["orpt_snapshot"]["spot_high"] == pytest.approx(22520.0)
    assert audit["recalculation_snapshot"]["spot_high"] == pytest.approx(22850.0)
    assert audit["recalculated_trade_plan"]["start_strike"] == 22576
    assert audit["recalculated_trade_plan"]["end_strike"] == 22851
    assert evaluation["trade_outputs"]["start_strike"] == 22576


def test_recalculation_mode_keeps_base_plan_when_entry_is_not_missed(
    tmp_path: Path,
) -> None:
    report = _run_historical_monthly_status_backtest(
        tmp_path,
        enable_recalculation=True,
    )

    evaluation = _find_eval(
        report,
        branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        entry_missed=False,
    )
    audit = evaluation["validation"]["s23_recalculation"]

    assert audit["recalculation_applied"] is False
    assert audit["recalculated_trade_plan"] is None
    assert evaluation["trade_outputs"]["entry_price"] == pytest.approx(
        audit["base_trade_plan"]["entry_price"]
    )


def test_missing_orpt_snapshot_produces_clear_audit_warning(
    tmp_path: Path,
) -> None:
    sparse_intraday_csv = tmp_path / "sparse_intraday.csv"
    _write_sparse_intraday_csv(sparse_intraday_csv)
    report = _run_historical_monthly_status_backtest(
        tmp_path,
        enable_recalculation=True,
        option_intraday_csv=sparse_intraday_csv,
    )

    evaluation = report["evaluations"][0]
    audit = evaluation["validation"]["s23_recalculation"]
    assert audit["recalculation_applied"] is False
    assert "Missing ORPT snapshot" in audit["warning"]
    assert evaluation["trade_outputs"]["entry_price"] == pytest.approx(
        audit["base_trade_plan"]["entry_price"]
    )


def test_put_branch_recalculation_surfaces_resolved_workbook_correction_metadata(
    tmp_path: Path,
) -> None:
    put_missed_csv = tmp_path / "put_missed_intraday.csv"
    _write_put_missed_intraday_csv(put_missed_csv)
    report = _run_historical_monthly_status_backtest(
        tmp_path,
        enable_recalculation=True,
        option_intraday_csv=put_missed_csv,
    )

    evaluation = _find_eval(
        report,
        branch_unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
        entry_missed=True,
    )
    audit = evaluation["validation"]["s23_recalculation"]

    assert audit["recalculation_applied"] is True
    assert audit["unresolved_open_questions"] == []
    assert audit["resolved_workbook_corrections"]
    assert (
        audit["resolved_workbook_corrections"][0]["id"]
        == "s23_put_recalc_strike_ll_vs_high"
    )
    assert audit["resolved_workbook_corrections"][0]["status"] == "RESOLVED"
