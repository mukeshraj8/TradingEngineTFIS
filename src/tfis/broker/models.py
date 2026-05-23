from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class ProductType(str, Enum):
    MIS = "MIS"
    NRML = "NRML"


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    symbol: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    product_type: ProductType
    limit_price: float | None = None


@dataclass(frozen=True, slots=True)
class BrokerOrderResult:
    order_id: str
    accepted: bool
    status: str
    symbol: str
    filled_quantity: int


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    symbol: str
    quantity: int
    average_price: float


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    last_price: float
    bid_price: float | None = None
    ask_price: float | None = None
    expiry: str | None = None
