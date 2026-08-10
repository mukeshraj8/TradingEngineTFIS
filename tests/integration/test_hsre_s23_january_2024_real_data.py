from __future__ import annotations

from pathlib import Path

import pytest

from tfis.backtest.hsre_s23_month_run import run_hsre_s23_january_2024


REAL_NIFTY_ROOT = Path(r"D:\HistoricalData\Nifty")


@pytest.mark.skipif(
    not REAL_NIFTY_ROOT.exists(),
    reason="Real HSRE NIFTY data root is not available on this machine.",
)
def test_real_january_2024_s23_month_run(tmp_path: Path) -> None:
    result = run_hsre_s23_january_2024(
        data_root=REAL_NIFTY_ROOT,
        output_dir=tmp_path / "jan2024",
    )
    summary = result.summary

    assert summary["date_coverage"]["observed_trading_days"] == 22
    assert summary["date_coverage"]["sessions"][0] == "2024-01-01"
    assert summary["date_coverage"]["sessions"][-1] == "2024-01-31"
    assert summary["status_counts"] == {
        "ENTRY_NOT_TRIGGERED": 7,
        "FINAL_ORDER_NOT_READY": 14,
        "TRADE_CLOSED": 1,
    }
    assert summary["funnel"] == {
        "observed_trading_days": 22,
        "base_orders_created": 8,
        "final_orders_ready": 8,
        "normal_orders_ready": 8,
        "recalculated_orders_ready": 0,
        "entry_missed_at_orpt": 0,
        "rc_rejected": 0,
        "no_qualifying_recalculated_contract": 0,
        "entries_triggered": 1,
        "entries_not_triggered": 7,
        "closed_trades": 1,
        "incomplete_trades": 0,
    }
    assert summary["trade_metrics"]["orders_ready"] == 8
    assert summary["trade_metrics"]["entries_triggered"] == 1
    assert summary["trade_metrics"]["trigger_rate"] == pytest.approx(0.125)
    assert summary["trade_metrics"]["trades"] == 1
    assert summary["trade_metrics"]["wins"] == 1
    assert summary["trade_metrics"]["losses"] == 0
    assert summary["trade_metrics"]["exit_distribution"] == {"TARGET_HIT": 1}
    assert summary["trade_metrics"]["net_total_points"] == pytest.approx(75.61875)
    assert summary["trade_metrics"]["profit_factor"] is None
    assert summary["trade_metrics"]["max_drawdown_points"] == pytest.approx(0.0)
    assert summary["ce_pe_breakdown"]["CALL"] == {
        "orders_ready": 3,
        "entries_triggered": 1,
        "trades": 1,
        "wins": 1,
        "losses": 0,
        "net_points": pytest.approx(75.61875),
    }
    assert summary["ce_pe_breakdown"]["PUT"] == {
        "orders_ready": 5,
        "entries_triggered": 0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "net_points": 0,
    }
    assert summary["orpt_recalculation"] == {
        "orders_evaluated": 8,
        "entry_missed_at_orpt": 0,
        "recalculation_required": 0,
        "rc_required": 0,
        "recalculated_orders_ready": 0,
    }
    assert summary["entry_distance"]["rows"] == 8
    assert summary["entry_distance"]["entry_touched"] == 1
    assert summary["entry_distance"]["not_touched"] == 7
    assert summary["rupee_pnl_status"] == "NOT_CERTIFIED"
    assert summary["hashes"] == {
        "daily_decisions.csv": "81c7a776afc13851c058f644cc9ec28277699e2a8b995308d5da92744d75dd26",
        "trades.csv": "93ced60ab848d887f42fd7962e7e8bfae4fabf75afd10a7b81c7085e7c3aa878",
        "non_trades.csv": "18faafa87c012feda5004c739f01c009bac152ab0abe4090f8c92d4859544499",
        "rejected_candidates_summary.csv": "5766a2a3d3a0b868755a7f26fe04eadc49e5b2276bbe0f58f8cab3766314cdd4",
        "entry_distance.csv": "225b5ed7a8a644a23a4fea9ec9db1faaa397822012a747988ea73e9507b6ddc5",
    }

    jan_3 = next(packet for packet in result.packets if packet.session_date == "2024-01-03")
    assert jan_3.status == "ENTRY_NOT_TRIGGERED"
    assert jan_3.contract == "NIFTY04JAN2421900PE"
    assert jan_3.entry_threshold == pytest.approx(85.60875)

    jan_17 = next(packet for packet in result.packets if packet.session_date == "2024-01-17")
    assert jan_17.status == "TRADE_CLOSED"
    assert jan_17.contract == "NIFTY18JAN2421700CE"
    assert jan_17.exit_reason == "TARGET_HIT"
    assert jan_17.pnl.net_points == pytest.approx(75.61875)

    for name in (
        "daily_decisions.csv",
        "trades.csv",
        "non_trades.csv",
        "rejected_candidates_summary.csv",
        "entry_distance.csv",
        "summary.json",
        "summary.md",
    ):
        assert (result.output_dir / name).is_file()
