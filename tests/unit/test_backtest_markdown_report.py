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


def test_run_backtest_writes_markdown_report_and_keeps_json_valid(
    tmp_path: Path,
) -> None:
    json_output = tmp_path / "historical_backtest.json"
    markdown_output = tmp_path / "historical_backtest.md"
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
            "--historical",
            "--daily-csv",
            str(DAILY_MULTI_CSV),
            "--option-levels-csv",
            str(OPTION_MULTI_CSV),
            "--option-intraday-csv",
            str(OPTION_INTRADAY_CSV),
            "--eod-policy",
            "square_off_at_close",
            "--slippage-points-per-side",
            "1.0",
            "--brokerage-points-per-trade",
            "0.5",
            "--other-cost-points-per-trade",
            "0.5",
            "--out",
            str(json_output),
            "--markdown-out",
            str(markdown_output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert markdown_output.is_file()

    markdown = markdown_output.read_text(encoding="utf-8")
    assert "S23" in markdown
    assert "## Summary Metrics" in markdown
    assert "## Cost Assumptions" in markdown
    assert "## Equity And Drawdown" in markdown
    assert "total_evaluations" in markdown
    assert "total_net_pnl_points" in markdown
    assert "total_net_pnl_rupees" in markdown
    assert "final_net_pnl_rupees" in markdown
    assert "max_drawdown_rupees" in markdown
    assert "entered_trades" in markdown
    assert "This is offline simulation. It does not include brokerage, slippage, liquidity, or real fill modeling yet." in markdown
    assert "slippage_points_per_side: `1.00`" in markdown
    assert "brokerage_points_per_trade: `0.50`" in markdown
    assert "other_cost_points_per_trade: `0.50`" in markdown
    assert "| Timestamp | Monthly Status | Selected Branches | Entry Price | Exit Price | Exit Reason | Gross PnL | Costs | Net PnL | Net Rupees | Cumulative Net Rupees | Drawdown Rupees | MFE | MAE | Bars Held |" in markdown

    report = json.loads(json_output.read_text(encoding="utf-8"))
    assert report["mode"] == "historical"
    assert report["eod_policy"] == "square_off_at_close"
    assert report["cost_model"]["slippage_points_per_side"] == 1.0
    assert report["cost_model"]["brokerage_points_per_trade"] == 0.5
    assert report["cost_model"]["other_cost_points_per_trade"] == 0.5
    assert report["metrics"]["eod_square_off"] == 1
    assert report["metrics"]["total_net_pnl_rupees"] is not None
    assert report["metrics"]["final_net_pnl_rupees"] is not None
    assert report["metrics"]["max_drawdown_rupees"] is not None
    assert report["evaluations"][0]["lifecycle_result"]["cumulative_net_pnl_rupees"] is not None
