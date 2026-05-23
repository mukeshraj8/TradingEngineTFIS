from __future__ import annotations

from tfis.broker.models import OrderSide, OrderType, ProductType
from tfis.domain.enums import OptionType
from tfis.domain.trade_plan import TradePlan

from .order_plan import OrderIntent


class OrderPlanner:
    """Converts a TradePlan into execution intent without placing any order."""

    def build_order_intent(self, trade_plan: TradePlan, *, lot_size: int) -> OrderIntent:
        if lot_size <= 0:
            raise ValueError("lot_size must be positive")

        option_type = trade_plan.option_type
        if option_type not in {OptionType.CALL, OptionType.PUT}:
            raise ValueError(
                "OrderPlanner currently supports option trade plans with CALL or PUT option_type only"
            )

        return OrderIntent(
            strategy_code=trade_plan.strategy_code,
            symbol=trade_plan.symbol,
            option_type=option_type,
            side=OrderSide.SELL,
            quantity=lot_size,
            order_type=OrderType.MARKET,
            product_type=ProductType.MIS,
            reference_price=trade_plan.entry_price,
            reason="Planned options-sell entry intent from TradePlan",
        )
