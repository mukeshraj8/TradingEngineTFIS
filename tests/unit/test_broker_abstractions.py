from __future__ import annotations

from tfis.broker import (
    BrokerOrder,
    OrderSide,
    OrderType,
    PaperBroker,
    ProductType,
    Quote,
)


def test_paper_broker_returns_configured_quote() -> None:
    broker = PaperBroker([Quote(symbol="NIFTY24APR22500CE", last_price=123.45)])

    quote = broker.get_quote("NIFTY24APR22500CE")

    assert quote.symbol == "NIFTY24APR22500CE"
    assert quote.last_price == 123.45


def test_paper_broker_places_order_and_returns_accepted_result() -> None:
    broker = PaperBroker([Quote(symbol="NIFTY24APR22500CE", last_price=123.45)])

    result = broker.place_order(
        BrokerOrder(
            symbol="NIFTY24APR22500CE",
            side=OrderSide.BUY,
            quantity=2,
            order_type=OrderType.MARKET,
            product_type=ProductType.MIS,
        )
    )

    assert result.accepted is True
    assert result.status == "ACCEPTED"
    assert result.order_id == "PAPER-0001"


def test_paper_broker_records_orders_and_positions() -> None:
    broker = PaperBroker([Quote(symbol="NIFTY24APR22500CE", last_price=100.0)])
    broker.place_order(
        BrokerOrder(
            symbol="NIFTY24APR22500CE",
            side=OrderSide.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            product_type=ProductType.MIS,
        )
    )

    orders = broker.get_orders()
    positions = broker.get_positions()

    assert len(orders) == 1
    assert len(positions) == 1
    assert positions[0].symbol == "NIFTY24APR22500CE"
    assert positions[0].quantity == 1


def test_core_imports_do_not_require_broker_sdk() -> None:
    from tfis.broker import PaperBroker as ImportedPaperBroker
    from tfis.formulas import FormulaEngine
    from tfis.strategy import StrategyEvaluator

    assert ImportedPaperBroker is not None
    assert FormulaEngine is not None
    assert StrategyEvaluator is not None
