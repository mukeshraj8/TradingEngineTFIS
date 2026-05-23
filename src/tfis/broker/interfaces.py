from __future__ import annotations

from typing import Protocol

from .models import BrokerOrder, BrokerOrderResult, BrokerPosition, Quote


class MarketDataProvider(Protocol):
    def get_quote(self, symbol: str) -> Quote:
        ...


class OptionChainProvider(Protocol):
    def get_option_chain(self, underlying: str, expiry: str | None = None) -> list[Quote]:
        ...


class OrderExecutor(Protocol):
    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        ...


class PositionProvider(Protocol):
    def get_positions(self) -> list[BrokerPosition]:
        ...


class BrokerGateway(
    MarketDataProvider,
    OptionChainProvider,
    OrderExecutor,
    PositionProvider,
    Protocol,
):
    pass
