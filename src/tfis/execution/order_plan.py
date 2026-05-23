from __future__ import annotations

from dataclasses import dataclass

from tfis.broker.models import OrderSide, OrderType, ProductType
from tfis.domain.enums import OptionType


@dataclass(frozen=True, slots=True)
class OrderIntent:
    strategy_code: str
    symbol: str
    option_type: OptionType | None
    side: OrderSide
    quantity: int
    order_type: OrderType
    product_type: ProductType
    reference_price: float
    reason: str

    def __post_init__(self) -> None:
        if not self.strategy_code or not self.strategy_code.strip():
            raise ValueError("strategy_code must be a non-empty string")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.reference_price < 0:
            raise ValueError("reference_price must be non-negative")
        if not self.reason or not self.reason.strip():
            raise ValueError("reason must be a non-empty string")
