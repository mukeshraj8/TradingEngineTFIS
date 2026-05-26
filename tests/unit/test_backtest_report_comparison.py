from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from tfis.backtest.report_comparison import (
    compare_backtest_reports,
    render_comparison_markdown,
)


ROOT = Path(__file__).resolve().parents[2]


def _env() -> dict[str, str]:
    env = os.environ.copy()
    pythonpath = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = pythonpath if not existing else f"{pythonpath}{os.pathsep}{existing}"
    return env


def _make_local_tmp_dir() -> Path:
    base_dir = ROOT / "tmp" / "pytest-local"
    base_dir.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(dir=base_dir))


def _build_report(
    *,
    total_net_pnl_rupees: float,
    win_rate: float,
    max_drawdown_rupees: float,
    enable_recalc: bool = False,
    enable_chain: bool = False,
    enable_contract: bool = False,
) -> dict[str, object]:
    validation: dict[str, object] = {}
    if enable_recalc:
        validation["s23_recalculation"] = {
            "recalculation_applied": True,
        }
    if enable_chain:
        validation["option_chain_selection"] = {
            "selected": True,
        }
    if enable_contract:
        validation["contract_specific_lifecycle"] = {
            "lifecycle_price_source": "contract_specific_series",
            "warning": None,
        }

    return {
        "mode": "historical",
        "strategy_root": "config/strategies/options_sell/nifty",
        "use_monthly_status_engine": True,
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
        },
        "evaluations": [
            {
                "accepted": True,
                "validation": validation,
            },
            {
                "accepted": True,
                "validation": validation,
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
    )

    comparison = compare_backtest_reports(
        [
            ("baseline", "baseline.json", baseline),
            ("advanced", "advanced.json", advanced),
        ]
    )

    assert comparison.best_total_net_pnl_rupees_label == "advanced"
    assert comparison.best_win_rate_label == "advanced"
    assert comparison.lowest_max_drawdown_label == "advanced"
    assert comparison.reports[1].recalculation_applied_count == 2
    assert comparison.reports[1].option_chain_selected_count == 2
    assert comparison.reports[1].contract_specific_series_count == 2

    markdown = render_comparison_markdown(comparison)
    assert "Backtest Mode Comparison" in markdown
    assert "advanced" in markdown
    assert "Contract Series Used" in markdown


def test_compare_backtest_reports_cli_writes_json_and_markdown() -> None:
    tmp_dir = _make_local_tmp_dir()
    baseline_path = tmp_dir / "baseline.json"
    advanced_path = tmp_dir / "advanced.json"
    out_path = tmp_dir / "comparison.json"
    markdown_path = tmp_dir / "comparison.md"
    baseline_path.write_text(
        json.dumps(
            _build_report(
                total_net_pnl_rupees=1000.0,
                win_rate=0.5,
                max_drawdown_rupees=300.0,
            )
        ),
        encoding="utf-8",
    )
    advanced_path.write_text(
        json.dumps(
            _build_report(
                total_net_pnl_rupees=1500.0,
                win_rate=0.75,
                max_drawdown_rupees=250.0,
                enable_recalc=True,
                enable_chain=True,
                enable_contract=True,
            )
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/compare_backtest_reports.py",
            "--report",
            f"baseline={baseline_path}",
            "--report",
            f"advanced={advanced_path}",
            "--out",
            str(out_path),
            "--markdown-out",
            str(markdown_path),
        ],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    output = json.loads(out_path.read_text(encoding="utf-8"))
    assert output["best_total_net_pnl_rupees_label"] == "advanced"
    assert len(output["reports"]) == 2
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "baseline" in markdown
    assert "advanced" in markdown
