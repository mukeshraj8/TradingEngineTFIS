from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

from tfis.backtest.report_comparison import (
    BacktestReportComparisonError,
    ComparisonLimits,
    compare_backtest_reports,
    comparison_to_dict,
    load_backtest_report,
    render_comparison_markdown,
    summarize_backtest_report,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "report_comparison"


def _load_compare_script_module():
    script_path = ROOT / "scripts" / "compare_backtest_reports.py"
    spec = importlib.util.spec_from_file_location("compare_backtest_reports_script", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Could not load compare_backtest_reports.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_report(
    *,
    total_net_pnl_rupees: float,
    win_rate: float,
    max_drawdown_rupees: float,
    enable_recalc: bool = False,
    enable_chain: bool = False,
    enable_contract: bool = False,
    use_monthly_status: bool = True,
    strategy_path: str | None = "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
    strategy_root: str | None = None,
    cost_model: dict[str, float] | None = None,
    daily_path: str = "tests/fixtures/backtest/s23_daily_multi.csv",
    option_levels_path: str = "tests/fixtures/backtest/s23_option_levels_multi.csv",
    option_intraday_path: str = "tests/fixtures/backtest/s23_option_intraday.csv",
    spot_intraday_path: str | None = "tests/fixtures/backtest/s23_spot_intraday.csv",
    monthly_path: str | None = "tests/fixtures/backtest/s23_monthly.csv",
    weekly_path: str | None = "tests/fixtures/backtest/s23_weekly.csv",
    option_chain_path: str | None = "tests/fixtures/backtest/s23_option_chain.csv",
    contract_intraday_path: str | None = "tests/fixtures/backtest/s23_contract_intraday.csv",
    synthetic_fixture_data_used: bool = False,
    current_day_warning: str | None = None,
) -> dict[str, object]:
    validation: dict[str, object] = {}
    if enable_recalc:
        validation["s23_recalculation"] = {
            "recalculation_applied": True,
            "branch_unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
            "base_trade_plan": {
                "option_type": "CALL",
                "symbol": "NIFTY",
            },
        }
    if enable_chain:
        validation["option_chain_selection"] = {
            "selected": True,
            "selected_contract": {
                "symbol": "NIFTY_20260528_22100_CE",
                "option_type": "CALL",
            },
        }
    if enable_contract:
        validation["contract_specific_lifecycle"] = {
            "selected_contract_symbol": "NIFTY_20260528_22100_CE",
            "lifecycle_price_source": "contract_specific_series",
            "contract_specific_intraday_found": True,
            "generic_fallback_used": False,
            "fallback_reason": None,
            "contract_specific_bars_available_count": 3,
            "contract_specific_bars_usable_count": 3,
            "generic_intraday_bar_count": 4,
            "lifecycle_bars_used_count": 3,
            "warning": None,
        }
    if current_day_warning is not None:
        validation["s23_current_day_fsl_trp"] = {
            "warning": current_day_warning,
            "branch_unique_code": "NIFTY_OP_SELL_WK_DIFF_2D_3D",
        }

    return {
        "mode": "historical",
        "strategy_path": strategy_path,
        "strategy_root": strategy_root,
        "cost_model": cost_model
        or {
            "slippage_points_per_side": 0.0,
            "brokerage_points_per_trade": 0.0,
            "other_cost_points_per_trade": 0.0,
        },
        "input_metadata": {
            "datasets": {
                "daily": {
                    "path": daily_path,
                    "provided": True,
                    "used": True,
                    "fallback_behavior": None,
                    "project_fixture": True,
                    "synthetic_fixture": synthetic_fixture_data_used,
                },
                "option_levels": {
                    "path": option_levels_path,
                    "provided": True,
                    "used": True,
                    "fallback_behavior": None,
                    "project_fixture": True,
                    "synthetic_fixture": synthetic_fixture_data_used,
                },
                "option_intraday": {
                    "path": option_intraday_path,
                    "provided": True,
                    "used": True,
                    "fallback_behavior": None,
                    "project_fixture": True,
                    "synthetic_fixture": synthetic_fixture_data_used,
                },
                "spot_intraday": {
                    "path": spot_intraday_path,
                    "provided": spot_intraday_path is not None,
                    "used": spot_intraday_path is not None,
                    "fallback_behavior": None,
                    "project_fixture": True,
                    "synthetic_fixture": synthetic_fixture_data_used,
                },
                "monthly": {
                    "path": monthly_path,
                    "provided": monthly_path is not None,
                    "used": monthly_path is not None and use_monthly_status,
                    "fallback_behavior": None,
                    "project_fixture": True,
                    "synthetic_fixture": synthetic_fixture_data_used,
                },
                "weekly": {
                    "path": weekly_path,
                    "provided": weekly_path is not None,
                    "used": weekly_path is not None and use_monthly_status,
                    "fallback_behavior": None,
                    "project_fixture": True,
                    "synthetic_fixture": synthetic_fixture_data_used,
                },
                "option_chain": {
                    "path": option_chain_path,
                    "provided": option_chain_path is not None,
                    "used": option_chain_path is not None and enable_chain,
                    "fallback_behavior": None,
                    "project_fixture": True,
                    "synthetic_fixture": synthetic_fixture_data_used,
                },
                "contract_intraday": {
                    "path": contract_intraday_path,
                    "provided": contract_intraday_path is not None,
                    "used": contract_intraday_path is not None and enable_contract,
                    "fallback_behavior": None,
                    "project_fixture": True,
                    "synthetic_fixture": synthetic_fixture_data_used,
                },
            },
            "project_fixture_data_used": True,
            "synthetic_fixture_data_used": synthetic_fixture_data_used,
        },
        "use_monthly_status_engine": use_monthly_status,
        "eod_policy": "square_off_at_close",
        "metrics": {
            "total_evaluations": 2,
            "accepted_candidates": 2,
            "rejected_candidates": 0,
            "entered_trades": 2,
            "target_hits": 1,
            "stoploss_hits": 1,
            "eod_square_off": 0,
            "no_entry": 0,
            "no_exit": 0,
            "total_net_pnl_points": 20.0,
            "total_net_pnl_rupees": total_net_pnl_rupees,
            "average_net_pnl_rupees": total_net_pnl_rupees / 2.0,
            "max_drawdown_rupees": max_drawdown_rupees,
            "win_rate": win_rate,
            "loss_rate": 1.0 - win_rate,
            "expiry_day_candidates": 1,
            "expiry_day_exit_satisfied": 1,
            "expiry_day_exit_pending": 0,
            "rejection_reason_distribution": {},
        },
        "evaluations": [
            {
                "timestamp": "2026-05-18T15:30:00",
                "strategy_code": "S23",
                "accepted": True,
                "rejection_reason": "",
                "trade_outputs": {
                    "start_strike": 23047,
                    "end_strike": 21949,
                    "ideal_premium": 263.4,
                    "minimum_premium": 197.55,
                    "entry_price": 197.95,
                    "stoploss_price": 314.58,
                    "target_price": 80.0,
                },
                "lifecycle_result": {
                    "exit_price": 120.0,
                    "net_pnl_points": 77.95,
                    "net_pnl_rupees": total_net_pnl_rupees / 2.0,
                },
                "validation": copy.deepcopy(validation),
            },
            {
                "timestamp": "2026-05-19T15:30:00",
                "strategy_code": "S23",
                "accepted": True,
                "rejection_reason": "",
                "trade_outputs": {
                    "start_strike": 23047,
                    "end_strike": 21949,
                    "ideal_premium": 263.4,
                    "minimum_premium": 197.55,
                    "entry_price": 197.95,
                    "stoploss_price": 314.58,
                    "target_price": 80.0,
                },
                "lifecycle_result": {
                    "exit_price": 118.0,
                    "net_pnl_points": 79.95,
                    "net_pnl_rupees": total_net_pnl_rupees / 2.0,
                },
                "validation": copy.deepcopy(validation),
            },
        ],
        "monthly_status_skips": [],
        "enable_s23_recalculation": enable_recalc,
        "enable_option_chain_selection": enable_chain,
        "enable_contract_specific_lifecycle": enable_contract,
    }


def test_compare_backtest_reports_summarizes_and_ranks_modes() -> None:
    baseline = _build_report(
        total_net_pnl_rupees=1000.0,
        win_rate=0.5,
        max_drawdown_rupees=300.0,
    )
    advanced = _build_report(
        total_net_pnl_rupees=1500.0,
        win_rate=0.75,
        max_drawdown_rupees=250.0,
        enable_recalc=True,
        enable_chain=True,
        enable_contract=True,
        strategy_root="config/strategies/options_sell/nifty",
    )

    comparison = compare_backtest_reports(
        [
            ("base", "baseline.json", baseline),
            ("advanced", "advanced.json", advanced),
        ],
        limits=ComparisonLimits(max_trades=100, timeout_seconds=5.0),
    )

    assert comparison.best_total_net_pnl_rupees_label == "advanced"
    assert comparison.best_win_rate_label == "advanced"
    assert comparison.lowest_max_drawdown_label == "advanced"
    assert comparison.reports[1].label == "advanced"
    assert comparison.reports[1].recalculation_applied_count == 2
    assert comparison.reports[1].option_chain_selected_count == 2
    assert comparison.reports[1].contract_specific_series_count == 2
    assert comparison.reports[1].contract_specific_coverage_pct == 100.0
    assert comparison.reports[1].contract_specific_fallback_pct == 0.0
    assert comparison.comparisons[0].label == "advanced"
    assert comparison.comparisons[0].pnl_diff_count == 2
    assert comparison.apples_to_apples is True
    assert comparison.apples_to_apples_issues == ()

    markdown = render_comparison_markdown(comparison)
    assert "S23 Backtest Mode Comparison" in markdown
    assert "advanced" in markdown
    assert "apples_to_apples: `yes`" in markdown
    assert "Runtime And Performance Summary" in markdown
    payload = comparison_to_dict(comparison)
    assert payload["baseline_label"] == "base"
    assert payload["apples_to_apples"] is True


def test_compare_backtest_reports_flags_input_and_cost_mismatches() -> None:
    baseline = _build_report(
        total_net_pnl_rupees=1000.0,
        win_rate=0.5,
        max_drawdown_rupees=300.0,
        cost_model={
            "slippage_points_per_side": 1.0,
            "brokerage_points_per_trade": 0.5,
            "other_cost_points_per_trade": 0.5,
        },
    )
    mismatched = _build_report(
        total_net_pnl_rupees=900.0,
        win_rate=0.25,
        max_drawdown_rupees=350.0,
        daily_path="tests/_tmp_pytest_local/s23_daily_multi.csv",
        synthetic_fixture_data_used=True,
    )

    comparison = compare_backtest_reports(
        [
            ("base", "baseline.json", baseline),
            ("mismatched", "mismatched.json", mismatched),
        ],
        limits=ComparisonLimits(max_trades=100, timeout_seconds=5.0),
    )

    assert comparison.apples_to_apples is False
    assert any("Cost model mismatch" in item for item in comparison.apples_to_apples_issues)
    assert any("Dataset path mismatch for daily" in item for item in comparison.apples_to_apples_issues)
    assert any("Synthetic-fixture mismatch for daily" in item for item in comparison.apples_to_apples_issues)


def test_compare_backtest_reports_tracks_contract_specific_provenance_and_fallbacks() -> None:
    baseline = _build_report(
        total_net_pnl_rupees=1000.0,
        win_rate=0.5,
        max_drawdown_rupees=300.0,
        enable_chain=True,
    )
    candidate = _build_report(
        total_net_pnl_rupees=900.0,
        win_rate=0.5,
        max_drawdown_rupees=325.0,
        enable_chain=True,
        enable_contract=True,
    )
    candidate["evaluations"][1]["validation"]["option_chain_selection"]["selected_contract"] = {
        "symbol": "NIFTY_20260528_22300_PE",
        "option_type": "PUT",
    }
    candidate["evaluations"][1]["validation"]["contract_specific_lifecycle"] = {
        "selected_contract_symbol": "NIFTY_20260528_22300_PE",
        "lifecycle_price_source": "generic_option_series",
        "contract_specific_intraday_found": False,
        "generic_fallback_used": True,
        "fallback_reason": "missing_contract_intraday_for_selected_symbol",
        "contract_specific_bars_available_count": 0,
        "contract_specific_bars_usable_count": 0,
        "generic_intraday_bar_count": 4,
        "lifecycle_bars_used_count": 4,
        "warning": "Selected contract intraday bars were not found; fell back to generic option intraday series.",
    }
    candidate["evaluations"][1]["lifecycle_result"]["net_pnl_rupees"] = 350.0
    candidate["evaluations"][1]["lifecycle_result"]["exit_price"] = 140.0

    comparison = compare_backtest_reports(
        [
            ("base", "baseline.json", baseline),
            ("contract_specific_lifecycle", "contract.json", candidate),
        ],
        limits=ComparisonLimits(max_trades=100, timeout_seconds=5.0),
    )

    report = comparison.reports[1]
    assert report.contract_specific_series_count == 1
    assert report.contract_specific_fallback_count == 1
    assert report.contract_specific_intraday_found_count == 1
    assert report.contract_specific_missing_symbol_count == 1
    assert report.contract_specific_pre_cutoff_only_count == 0
    assert report.contract_specific_coverage_pct == 50.0
    assert report.contract_specific_fallback_pct == 50.0

    markdown = render_comparison_markdown(comparison)
    assert "Contract-Specific Lifecycle Provenance" in markdown
    assert "Coverage %" in markdown
    assert "50.0%" in markdown
    assert "Contract-Specific Lifecycle Details" in markdown
    assert "missing_contract_intraday_for_selected_symbol" in markdown


def test_summarize_backtest_report_collects_mode_warnings() -> None:
    report = _build_report(
        total_net_pnl_rupees=1000.0,
        win_rate=0.5,
        max_drawdown_rupees=300.0,
        current_day_warning="Missing aggregated 09:15:00 option or spot snapshot for S23 current-day FSL/TRP handling; base trade plan kept.",
    )

    summary = summarize_backtest_report(
        label="warning_case",
        path="warning.json",
        report=report,
        limits=ComparisonLimits(max_trades=10, timeout_seconds=5.0),
    )

    assert any("s23_current_day_fsl_trp:" in warning for warning in summary.warnings)


def test_compare_backtest_reports_cli_writes_json_and_markdown() -> None:
    out_path = Path("D:/TradingEngineTFIS/tmp_pytest_compare/comparison.json")
    markdown_path = Path("D:/TradingEngineTFIS/tmp_pytest_compare/comparison.md")
    module = _load_compare_script_module()
    argv = [
        "compare_backtest_reports.py",
        "--report",
        f"base={FIXTURES / 'base.json'}",
        "--report",
        f"advanced={FIXTURES / 'advanced.json'}",
        "--max-trades",
        "10",
        "--timeout-seconds",
        "5",
        "--out",
        str(out_path),
        "--markdown-out",
        str(markdown_path),
    ]
    written: dict[str, str] = {}

    def _capture_write_text(self: Path, data: str, encoding: str | None = None) -> int:
        written[str(self)] = data
        return len(data)

    with patch.object(sys, "argv", argv):
        with patch.object(Path, "mkdir", return_value=None):
            with patch.object(Path, "write_text", new=_capture_write_text):
                assert module.main() == 0

    output = json.loads(written[str(out_path)])
    assert output["best_total_net_pnl_rupees_label"] == "base"
    assert output["baseline_label"] == "base"
    assert output["runtime"]["max_trades"] == 10
    assert len(output["reports"]) == 2
    markdown = written[str(markdown_path)]
    assert "baseline" in markdown
    assert "advanced" in markdown


def test_load_and_summarize_backtest_report_limits_trades() -> None:
    report = _build_report(
        total_net_pnl_rupees=1000.0,
        win_rate=0.5,
        max_drawdown_rupees=300.0,
        strategy_path="config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        strategy_root=None,
        use_monthly_status=False,
    )
    report["metrics"]["total_evaluations"] = 5
    report["evaluations"] = report["evaluations"] * 3

    summary = summarize_backtest_report(
        label="bounded",
        path="many.json",
        report=report,
        limits=ComparisonLimits(max_trades=2, timeout_seconds=5.0),
    )

    assert len(summary.normalized_trades) == 2
    assert summary.performance.truncated_trade_count == 3
    assert any("max_trades=2" in warning for warning in summary.warnings)


def test_load_backtest_report_fails_fast_for_oversized_file_without_parsing() -> None:
    report_path = FIXTURES / "oversized.json"

    with patch("tfis.backtest.report_comparison.json.loads", side_effect=AssertionError("should not parse")):
        try:
            load_backtest_report(report_path, max_file_bytes=100)
        except BacktestReportComparisonError as exc:
            assert "above the limit" in str(exc)
        else:
            raise AssertionError("Expected oversized report to fail before parsing.")


def test_load_backtest_report_fails_clearly_for_malformed_json() -> None:
    report_path = FIXTURES / "malformed.json"

    try:
        load_backtest_report(report_path, max_file_bytes=1000)
    except BacktestReportComparisonError as exc:
        assert "not valid JSON" in str(exc)
    else:
        raise AssertionError("Expected malformed JSON to raise a comparison error.")
