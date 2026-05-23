from __future__ import annotations

from dataclasses import replace

from .models import (
    BrokerOrder,
    BrokerOrderResult,
    BrokerPosition,
    OrderSide,
    OrderType,
    Quote,
)


class PaperBroker:
    """Deterministic in-memory broker for tests and offline development."""

    def __init__(self, quotes: list[Quote] | None = None) -> None:
        self._quotes: dict[str, Quote] = {quote.symbol: quote for quote in quotes or []}
        self._orders: list[BrokerOrder] = []
        self._positions: dict[str, BrokerPosition] = {}
        self._next_order_id = 1

    def set_quote(self, quote: Quote) -> None:
        self._quotes[quote.symbol] = quote

    def get_quote(self, symbol: str) -> Quote:
        try:
            return self._quotes[symbol]
        except KeyError as exc:
            raise KeyError(f"No quote configured for symbol: {symbol}") from exc

    def get_option_chain(self, underlying: str, expiry: str | None = None) -> list[Quote]:
        matches: list[Quote] = []
        for quote in self._quotes.values():
            if not quote.symbol.startswith(underlying):
                continue
            if expiry is not None and quote.expiry != expiry:
                continue
            matches.append(quote)
        return sorted(matches, key=lambda item: item.symbol)

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        if order.quantity <= 0:
            raise ValueError("order quantity must be positive")
        if order.order_type is OrderType.LIMIT and order.limit_price is None:
            raise ValueError("limit_price is required for limit orders")

        self._orders.append(order)
        fill_price = self._resolve_fill_price(order)
        self._apply_position(order, fill_price)
        order_id = f"PAPER-{self._next_order_id:04d}"
        self._next_order_id += 1
        return BrokerOrderResult(
            order_id=order_id,
            accepted=True,
            status="ACCEPTED",
            symbol=order.symbol,
            filled_quantity=order.quantity,
        )

    def get_positions(self) -> list[BrokerPosition]:
        return list(self._positions.values())

    def get_orders(self) -> list[BrokerOrder]:
        return list(self._orders)

    def _resolve_fill_price(self, order: BrokerOrder) -> float:
        if order.order_type is OrderType.LIMIT:
            assert order.limit_price is not None
            return float(order.limit_price)
        quote = self.get_quote(order.symbol)
        return float(quote.last_price)

    def _apply_position(self, order: BrokerOrder, fill_price: float) -> None:
        signed_qty = order.quantity if order.side is OrderSide.BUY else -order.quantity
        current = self._positions.get(order.symbol)
        if current is None:
            self._positions[order.symbol] = BrokerPosition(
                symbol=order.symbol,
                quantity=signed_qty,
                average_price=fill_price,
            )
            return

        new_quantity = current.quantity + signed_qty
        if new_quantity == 0:
            self._positions.pop(order.symbol, None)
            return

        if current.quantity == 0 or (current.quantity > 0) == (signed_qty > 0):
            weighted_notional = (current.average_price * abs(current.quantity)) + (
                fill_price * abs(signed_qty)
            )
            average_price = weighted_notional / abs(new_quantity)
        else:
            average_price = current.average_price

        self._positions[order.symbol] = replace(
            current,
            quantity=new_quantity,
            average_price=average_price,
        )
