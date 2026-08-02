from __future__ import annotations

import inspect

from tfis.fyers_read_only import FyersReadOnlyAdapter


PROHIBITED_METHODS = {
    "place_order",
    "modify_order",
    "cancel_order",
    "exit_position",
    "convert_position",
    "transfer_funds",
}


def test_fyers_read_only_adapter_exposes_no_write_methods() -> None:
    public_methods = {
        name
        for name, value in inspect.getmembers(FyersReadOnlyAdapter, predicate=inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods.isdisjoint(PROHIBITED_METHODS)
    assert {
        "validate_session",
        "fetch_symbol_master",
        "fetch_historical_candles",
        "fetch_quotes",
        "fetch_market_depth",
        "fetch_option_chain",
        "resolve_contracts",
        "retrieve_source_health",
    }.issubset(public_methods)


def test_fyers_read_only_adapter_does_not_inherit_broker_write_api() -> None:
    assert all(not hasattr(FyersReadOnlyAdapter, method) for method in PROHIBITED_METHODS)


def test_fyers_read_only_sdk_import_is_isolated_to_adapter_module() -> None:
    module = inspect.getmodule(FyersReadOnlyAdapter)
    assert module is not None
    source = inspect.getsource(module)

    assert "from fyers_apiv3 import fyersModel" in source
    for prohibited_call in PROHIBITED_METHODS:
        assert f".{prohibited_call}(" not in source
