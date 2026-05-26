from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from tfis.backtest.report_comparison import ComparisonLimits, compare_backtest_reports


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "backtest" / "s23_current_day_applied"


def _env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return env


def _make_local_tmp_dir() -> Path:
    path = ROOT / "tests" / "_tmp_pytest_local"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_backtest(*, report_name: str, enable_current_day_fsl_trp: bool) -> dict[str, object]:
    output_path = _make_local_tmp_dir() / report_name
    command = [
        sys.executable,
        "scripts/run_backtest.py",
        "--strategy-path",
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "--historical",
        "--daily-csv",
        str(FIXTURE_DIR / "daily.csv"),
        "--option-levels-csv",
        str(FIXTURE_DIR / "option_levels.csv"),
        "--option-intraday-csv",
        str(FIXTURE_DIR / "option_intraday.csv"),
        "--spot-intraday-csv",
        str(FIXTURE_DIR / "spot_intraday.csv"),
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


def test_current_day_fsl_trp_applied_case_is_apples_to_apples_and_uses_workbook_backed_entry_override() -> None:
    base_report = _run_backtest(
        report_name="s23_applied_case_base.json",
        enable_current_day_fsl_trp=False,
    )
    current_day_report = _run_backtest(
        report_name="s23_applied_case_current_day_fsl_trp.json",
        enable_current_day_fsl_trp=True,
    )

    assert base_report["input_metadata"]["synthetic_fixture_data_used"] is False
    assert current_day_report["input_metadata"]["synthetic_fixture_data_used"] is False
    for dataset_name in ("daily", "option_levels", "option_intraday", "spot_intraday"):
        assert (
            base_report["input_metadata"]["datasets"][dataset_name]["path"]
            == current_day_report["input_metadata"]["datasets"][dataset_name]["path"]
        )

    base_evaluation = base_report["evaluations"][0]
    current_day_evaluation = current_day_report["evaluations"][0]
    current_day_audit = current_day_evaluation["validation"]["s23_current_day_fsl_trp"]

    assert current_day_report["enable_s23_current_day_fsl_trp"] is True
    assert current_day_audit["applied"] is True
    assert current_day_audit["result"]["row_number"] == 183
    assert current_day_audit["result"]["source_rule"] == "AB6_OS_ROW_183"
    assert current_day_audit["result"]["effective_option_type"] == "CALL"
    assert current_day_audit["result"]["recalculated_entry_price"] == 194.25
    assert current_day_audit["result"]["entry_override_source_cell"] == "AB6_OS_Z183"
    assert current_day_audit["entry_override"] == {
        "applied": True,
        "source_cell": "AB6_OS_Z183",
        "original_entry_price": 203.5,
        "overridden_entry_price": 194.25,
        "effective_entry_price": 194.25,
    }

    assert base_evaluation["trade_outputs"]["start_strike"] == 23100
    assert current_day_evaluation["trade_outputs"]["start_strike"] == 22785
    assert base_evaluation["trade_outputs"]["ideal_premium"] == 264.0
    assert current_day_evaluation["trade_outputs"]["ideal_premium"] == 260.4
    assert base_evaluation["trade_outputs"]["minimum_premium"] == 198.00000000000003
    assert current_day_evaluation["trade_outputs"]["minimum_premium"] == 195.3
    assert base_evaluation["trade_outputs"]["entry_price"] == 203.5
    assert current_day_evaluation["trade_outputs"]["entry_price"] == 194.25

    assert base_evaluation["lifecycle_result"]["entry_timestamp"] == "2026-05-23T09:29:59"
    assert current_day_evaluation["lifecycle_result"]["entry_timestamp"] == "2026-05-23T09:30:00"
    assert base_evaluation["lifecycle_result"]["exit_price"] == current_day_evaluation["lifecycle_result"]["exit_price"] == 80.0
    assert base_evaluation["lifecycle_result"]["exit_reason"] == current_day_evaluation["lifecycle_result"]["exit_reason"] == "TARGET_HIT"
    assert base_evaluation["lifecycle_result"]["net_pnl_points"] == 123.5
    assert current_day_evaluation["lifecycle_result"]["net_pnl_points"] == 114.25
    assert base_evaluation["lifecycle_result"]["net_pnl_rupees"] == 6175.0
    assert current_day_evaluation["lifecycle_result"]["net_pnl_rupees"] == 5712.5

    comparison = compare_backtest_reports(
        [
            ("base", "applied_case_base.json", base_report),
            ("current_day_fsl_trp", "applied_case_current_day_fsl_trp.json", current_day_report),
        ],
        limits=ComparisonLimits(max_trades=10, timeout_seconds=5.0),
    )

    assert comparison.apples_to_apples is True
    assert comparison.apples_to_apples_issues == ()
    assert len(comparison.comparisons) == 1

    diff = comparison.comparisons[0]
    assert diff.label == "current_day_fsl_trp"
    assert diff.added_trades == ()
    assert diff.removed_trades == ()
    assert diff.entry_stoploss_target_diff_count == 1
    assert diff.pnl_diff_count == 1
    assert diff.branch_or_row_diff_count == 1
    assert len(diff.changed_trades) == 1

    field_differences = diff.changed_trades[0].field_differences
    assert field_differences["current_day_fsl_trp_applied"] == {
        "baseline": False,
        "candidate": True,
    }
    assert field_differences["start_strike"] == {"baseline": 23100.0, "candidate": 22785.0}
    assert field_differences["ideal_premium"] == {"baseline": 264.0, "candidate": 260.4}
    assert field_differences["minimum_premium"] == {"baseline": 198.00000000000003, "candidate": 195.3}
    assert field_differences["entry_price"] == {"baseline": 203.5, "candidate": 194.25}
    assert field_differences["net_pnl_points"] == {"baseline": 123.5, "candidate": 114.25}
    assert field_differences["net_pnl_rupees"] == {"baseline": 6175.0, "candidate": 5712.5}
    assert field_differences["symbol"] == {"baseline": None, "candidate": "NIFTY"}
    assert field_differences["workbook_row_number"] == {"baseline": None, "candidate": 183}
    assert field_differences["source_rule"] == {"baseline": None, "candidate": "AB6_OS_ROW_183"}
