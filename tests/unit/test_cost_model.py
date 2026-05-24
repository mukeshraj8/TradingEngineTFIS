from __future__ import annotations

from datetime import datetime

import pytest

from tfis.backtest.cost_model import CostModel
from tfis.backtest.trade_lifecycle import TradeLifecycleResult


def _completed_trade_result() -> TradeLifecycleResult:
    return TradeLifecycleResult(
        entered=True,
        entry_price=200.0,
        exit_price=80.0,
        entry_timestamp=datetime(2026, 5, 23, 9, 25),
        exit_timestamp=datetime(2026, 5, 23, 9, 30),
        bars_held=2,
        exit_reason="TARGET_HIT",
        pnl_points=120.0,
        max_favorable_excursion=125.0,
        max_adverse_excursion=5.0,
        notes="Target threshold hit after entry",
    )


def _incomplete_trade_result() -> TradeLifecycleResult:
    return TradeLifecycleResult(
        entered=True,
        entry_price=200.0,
        exit_price=None,
        entry_timestamp=datetime(2026, 5, 23, 9, 25),
        exit_timestamp=None,
        bars_held=3,
        exit_reason="NO_EXIT",
        pnl_points=None,
        max_favorable_excursion=80.0,
        max_adverse_excursion=100.0,
        notes="No exit",
    )


def test_zero_cost_preserves_net_equal_to_gross() -> None:
    result = CostModel().apply_with_quantity(_completed_trade_result(), quantity=50)

    assert result.gross_pnl_points == pytest.approx(120.0)
    assert result.total_cost_points == pytest.approx(0.0)
    assert result.net_pnl_points == pytest.approx(120.0)
    assert result.gross_pnl_rupees == pytest.approx(6000.0)
    assert result.cost_rupees == pytest.approx(0.0)
    assert result.net_pnl_rupees == pytest.approx(6000.0)


def test_positive_cost_reduces_net_pnl() -> None:
    result = CostModel(
        slippage_points_per_side=1.0,
        brokerage_points_per_trade=0.5,
        other_cost_points_per_trade=0.5,
    ).apply_with_quantity(_completed_trade_result(), quantity=50)

    assert result.gross_pnl_points == pytest.approx(120.0)
    assert result.total_cost_points == pytest.approx(3.0)
    assert result.net_pnl_points == pytest.approx(117.0)
    assert result.gross_pnl_rupees == pytest.approx(6000.0)
    assert result.cost_rupees == pytest.approx(150.0)
    assert result.net_pnl_rupees == pytest.approx(5850.0)


def test_incomplete_trades_have_no_net_pnl() -> None:
    result = CostModel(
        slippage_points_per_side=1.0,
        brokerage_points_per_trade=0.5,
        other_cost_points_per_trade=0.5,
    ).apply_with_quantity(_incomplete_trade_result(), quantity=50)

    assert result.gross_pnl_points is None
    assert result.total_cost_points is None
    assert result.net_pnl_points is None
    assert result.gross_pnl_rupees is None
    assert result.cost_rupees is None
    assert result.net_pnl_rupees is None
