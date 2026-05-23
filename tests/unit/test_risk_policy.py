from __future__ import annotations

from tfis.broker.models import OrderSide, OrderType, ProductType
from tfis.domain.enums import OptionType
from tfis.execution.order_plan import OrderIntent
from tfis.risk import RiskPolicy


def _intent(*, quantity: int = 50, option_type: OptionType | None = OptionType.CALL) -> OrderIntent:
    return OrderIntent(
        strategy_code="S23",
        symbol="NIFTY",
        option_type=option_type,
        side=OrderSide.SELL,
        quantity=quantity,
        order_type=OrderType.MARKET,
        product_type=ProductType.MIS,
        reference_price=200.0,
        reason="Test intent",
    )


def test_risk_policy_approves_valid_order() -> None:
    policy = RiskPolicy(
        max_lots_per_trade=100,
        max_trades_per_day=3,
        allow_short_options=True,
        paper_only=True,
    )

    decision = policy.evaluate_order(_intent(quantity=50), trades_taken_today=1)

    assert decision.approved is True
    assert decision.reason == "Approved"
    assert decision.checks["paper_only"] is True


def test_risk_policy_rejects_lot_size_over_limit() -> None:
    policy = RiskPolicy(
        max_lots_per_trade=25,
        max_trades_per_day=3,
        allow_short_options=True,
        paper_only=True,
    )

    decision = policy.evaluate_order(_intent(quantity=50), trades_taken_today=0)

    assert decision.approved is False
    assert "max_lots_per_trade" in decision.reason


def test_risk_policy_rejects_when_daily_trade_limit_reached() -> None:
    policy = RiskPolicy(
        max_lots_per_trade=100,
        max_trades_per_day=2,
        allow_short_options=True,
        paper_only=True,
    )

    decision = policy.evaluate_order(_intent(quantity=10), trades_taken_today=2)

    assert decision.approved is False
    assert "max_trades_per_day" in decision.reason


def test_risk_policy_rejects_short_options_when_disabled() -> None:
    policy = RiskPolicy(
        max_lots_per_trade=100,
        max_trades_per_day=3,
        allow_short_options=False,
        paper_only=True,
    )

    decision = policy.evaluate_order(_intent(quantity=10, option_type=OptionType.PUT), trades_taken_today=0)

    assert decision.approved is False
    assert "short options" in decision.reason


def test_risk_policy_allows_non_option_sell_when_short_options_disabled() -> None:
    policy = RiskPolicy(
        max_lots_per_trade=100,
        max_trades_per_day=3,
        allow_short_options=False,
        paper_only=True,
    )

    decision = policy.evaluate_order(_intent(quantity=10, option_type=None), trades_taken_today=0)

    assert decision.approved is True
