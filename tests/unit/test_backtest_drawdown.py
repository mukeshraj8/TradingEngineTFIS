from __future__ import annotations

from datetime import datetime

import pytest

from tfis.backtest.historical_runner import (
    HistoricalCandidateResult,
    HistoricalMarketSnapshot,
    build_realized_equity_curve,
)
from tfis.backtest.trade_lifecycle import TradeLifecycleResult


def _candidate(
    timestamp: datetime,
    *,
    net_pnl_rupees: float | None,
    net_pnl_points: float | None,
) -> HistoricalCandidateResult:
    return HistoricalCandidateResult(
        timestamp=timestamp,
        strategy_code="S23",
        accepted=True,
        rejection_reason="Approved",
        trade_outputs={},
        parameters={},
        validation={"strategy_config_ok": True, "formula_safety_findings": []},
        market_snapshot=HistoricalMarketSnapshot(
            d2hh=0.0,
            d2ll=0.0,
            d3hh=0.0,
            d3ll=0.0,
            d4hh=0.0,
            d4ll=0.0,
            current_day_high=0.0,
            current_day_low=0.0,
            opt_levels={},
        ),
        lifecycle_result=TradeLifecycleResult(
            entered=net_pnl_rupees is not None,
            entry_price=100.0 if net_pnl_rupees is not None else None,
            exit_price=90.0 if net_pnl_rupees is not None else None,
            entry_timestamp=timestamp if net_pnl_rupees is not None else None,
            exit_timestamp=timestamp if net_pnl_rupees is not None else None,
            bars_held=1 if net_pnl_rupees is not None else 0,
            exit_reason="TARGET_HIT" if net_pnl_rupees is not None else "NO_EXIT",
            pnl_points=net_pnl_points,
            max_favorable_excursion=None,
            max_adverse_excursion=None,
            notes="synthetic",
            net_pnl_points=net_pnl_points,
            net_pnl_rupees=net_pnl_rupees,
        ),
    )


def test_increasing_equity_has_zero_drawdown() -> None:
    summary = build_realized_equity_curve(
        [
            _candidate(datetime(2026, 5, 20, 15, 30), net_pnl_rupees=100.0, net_pnl_points=10.0),
            _candidate(datetime(2026, 5, 21, 15, 30), net_pnl_rupees=50.0, net_pnl_points=5.0),
        ]
    )

    assert summary.max_drawdown_rupees == pytest.approx(0.0)
    assert summary.max_drawdown_points == pytest.approx(0.0)
    assert summary.evaluations[0].lifecycle_result is not None
    assert summary.evaluations[0].lifecycle_result.cumulative_net_pnl_rupees == pytest.approx(100.0)
    assert summary.evaluations[0].lifecycle_result.drawdown_rupees == pytest.approx(0.0)
    assert summary.evaluations[1].lifecycle_result is not None
    assert summary.evaluations[1].lifecycle_result.cumulative_net_pnl_rupees == pytest.approx(150.0)
    assert summary.evaluations[1].lifecycle_result.drawdown_rupees == pytest.approx(0.0)


def test_losing_trade_after_peak_creates_drawdown() -> None:
    summary = build_realized_equity_curve(
        [
            _candidate(datetime(2026, 5, 20, 15, 30), net_pnl_rupees=100.0, net_pnl_points=10.0),
            _candidate(datetime(2026, 5, 21, 15, 30), net_pnl_rupees=-40.0, net_pnl_points=-4.0),
            _candidate(datetime(2026, 5, 22, 15, 30), net_pnl_rupees=10.0, net_pnl_points=1.0),
        ]
    )

    assert summary.max_drawdown_rupees == pytest.approx(40.0)
    assert summary.max_drawdown_points == pytest.approx(4.0)
    assert summary.best_trade_net_rupees == pytest.approx(100.0)
    assert summary.worst_trade_net_rupees == pytest.approx(-40.0)
    assert summary.evaluations[1].lifecycle_result is not None
    assert summary.evaluations[1].lifecycle_result.cumulative_net_pnl_rupees == pytest.approx(60.0)
    assert summary.evaluations[1].lifecycle_result.drawdown_rupees == pytest.approx(40.0)
    assert summary.evaluations[2].lifecycle_result is not None
    assert summary.evaluations[2].lifecycle_result.cumulative_net_pnl_rupees == pytest.approx(70.0)
    assert summary.evaluations[2].lifecycle_result.drawdown_rupees == pytest.approx(30.0)


def test_incomplete_trades_are_ignored_for_realized_equity_curve() -> None:
    summary = build_realized_equity_curve(
        [
            _candidate(datetime(2026, 5, 20, 15, 30), net_pnl_rupees=100.0, net_pnl_points=10.0),
            _candidate(datetime(2026, 5, 21, 15, 30), net_pnl_rupees=None, net_pnl_points=None),
            _candidate(datetime(2026, 5, 22, 15, 30), net_pnl_rupees=-20.0, net_pnl_points=-2.0),
        ]
    )

    assert summary.max_drawdown_rupees == pytest.approx(20.0)
    assert summary.max_drawdown_points == pytest.approx(2.0)
    assert summary.evaluations[1].lifecycle_result is not None
    assert summary.evaluations[1].lifecycle_result.cumulative_net_pnl_rupees is None
    assert summary.evaluations[1].lifecycle_result.drawdown_rupees is None
    assert summary.evaluations[2].lifecycle_result is not None
    assert summary.evaluations[2].lifecycle_result.cumulative_net_pnl_rupees == pytest.approx(80.0)
    assert summary.evaluations[2].lifecycle_result.drawdown_rupees == pytest.approx(20.0)
