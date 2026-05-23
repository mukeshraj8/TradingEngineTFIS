from __future__ import annotations

import pytest

from tfis.broker.models import OrderSide, OrderType, ProductType
from tfis.domain.enums import OptionType
from tfis.domain.trade_plan import TradePlan
from tfis.execution import OrderPlanner


def test_order_planner_builds_sell_intent_for_option_trade_plan() -> None:
    trade_plan = TradePlan(
        strategy_code="S23",
        symbol="NIFTY",
        option_type=OptionType.CALL,
        start_strike=23100,
        end_strike=21999,
        ideal_premium=22264.0,
        minimum_premium=22198.0,
        entry_price=20350.0,
        stoploss_price=320.0,
        target_price=80.0,
    )

    intent = OrderPlanner().build_order_intent(trade_plan, lot_size=50)

    assert intent.strategy_code == "S23"
    assert intent.symbol == "NIFTY"
    assert intent.option_type is OptionType.CALL
    assert intent.side is OrderSide.SELL
    assert intent.quantity == 50
    assert intent.order_type is OrderType.MARKET
    assert intent.product_type is ProductType.MIS
    assert intent.reference_price == 20350.0


def test_order_planner_rejects_non_positive_lot_size() -> None:
    trade_plan = TradePlan(
        strategy_code="S23",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        start_strike=23100,
        end_strike=21999,
        ideal_premium=22264.0,
        minimum_premium=22198.0,
        entry_price=20350.0,
        stoploss_price=320.0,
        target_price=80.0,
    )

    with pytest.raises(ValueError, match="lot_size must be positive"):
        OrderPlanner().build_order_intent(trade_plan, lot_size=0)


def test_order_planner_rejects_trade_plan_without_option_type() -> None:
    trade_plan = TradePlan(
        strategy_code="EQ01",
        symbol="INFY",
        option_type=None,
        start_strike=None,
        end_strike=None,
        ideal_premium=None,
        minimum_premium=None,
        entry_price=1500.0,
        stoploss_price=1450.0,
        target_price=1600.0,
    )

    with pytest.raises(ValueError, match="supports option trade plans"):
        OrderPlanner().build_order_intent(trade_plan, lot_size=25)
