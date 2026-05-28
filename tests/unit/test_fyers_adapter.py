from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from tfis.brokers import (
    BrokerConnectionState,
    BrokerCredentialsError,
    BrokerOrderPlacementBlockedError,
    FyersBrokerAdapter,
    FyersCredentials,
)
from tfis.domain.enums import OptionType
from tfis.paper.models import PaperEventType


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "paper"
    / "fyers_market_data_payloads.json"
)


def test_fyers_adapter_normalizes_symbols_round_trip() -> None:
    normalized = FyersBrokerAdapter.normalize_option_symbol("NSE:NIFTY2651225000PE")

    assert normalized == "NIFTY_20260512_25000_PE"
    assert (
        FyersBrokerAdapter.to_fyers_option_symbol(normalized)
        == "NSE:NIFTY2651225000PE"
    )
    assert FyersBrokerAdapter.normalize_underlying_symbol("NSE:NIFTY50-INDEX") == "NIFTY"


def test_fyers_adapter_normalizes_market_payloads() -> None:
    adapter = FyersBrokerAdapter.from_payload_file(FIXTURE_PATH)

    adapter.connect()
    health = adapter.health()
    underlying = adapter.get_underlying_quote("NIFTY", session_date=date(2026, 5, 8))
    chain = adapter.get_option_chain(
        "NIFTY",
        date(2026, 5, 12),
        session_date=date(2026, 5, 8),
    )
    selected = adapter.get_option_quote(
        "NIFTY_20260512_25000_PE",
        session_date=date(2026, 5, 8),
    )
    stream_events = adapter.stream_ticks()

    assert health.connection_state is BrokerConnectionState.CONNECTED
    assert underlying.envelope.event_type is PaperEventType.UNDERLYING_QUOTE
    assert underlying.symbol == "NIFTY"
    assert chain.underlying_symbol == "NIFTY"
    assert chain.contracts[0].symbol == "NIFTY_20260512_25000_PE"
    assert selected.symbol == "NIFTY_20260512_25000_PE"
    assert selected.option_type is OptionType.PUT
    assert len(stream_events) == 1
    assert stream_events[0].envelope.event_type is PaperEventType.SELECTED_CONTRACT_BAR


def test_fyers_adapter_blocks_order_placement() -> None:
    adapter = FyersBrokerAdapter.from_payload_file(FIXTURE_PATH)

    with pytest.raises(BrokerOrderPlacementBlockedError):
        adapter.place_order(symbol="NSE:NIFTY2651225000PE")


def test_fyers_credentials_require_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FYERS_APP_ID", raising=False)
    monkeypatch.delenv("FYERS_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("FYERS_CLIENT_ID", raising=False)

    with pytest.raises(BrokerCredentialsError):
        FyersCredentials.from_env()
