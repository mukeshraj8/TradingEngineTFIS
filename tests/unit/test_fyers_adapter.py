from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

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


class _FakeFyersClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.optionchain_requests: list[dict] = []

    def optionchain(self, request: dict) -> dict:
        self.optionchain_requests.append(dict(request))
        return self.payload


def test_fyers_adapter_normalizes_symbols_round_trip() -> None:
    normalized = FyersBrokerAdapter.normalize_option_symbol("NSE:NIFTY2651225000PE")

    assert normalized == "NIFTY_20260512_25000_PE"
    assert (
        FyersBrokerAdapter.to_fyers_option_symbol(normalized)
        == "NSE:NIFTY2651225000PE"
    )
    assert FyersBrokerAdapter.normalize_underlying_symbol("NSE:NIFTY50-INDEX") == "NIFTY"


def test_fyers_adapter_normalizes_monthly_symbol_with_expiry_hint() -> None:
    normalized = FyersBrokerAdapter.normalize_option_symbol(
        "NSE:NIFTY26JUN23850CE",
        expiry_hint=date(2026, 6, 30),
    )

    assert normalized == "NIFTY_20260630_23850_CE"
    assert (
        FyersBrokerAdapter.to_fyers_option_symbol(normalized)
        == "NSE:NIFTY26JUN23850CE"
    )


def test_fyers_adapter_normalizes_monthly_symbol_without_hint_to_last_tuesday() -> None:
    assert (
        FyersBrokerAdapter.normalize_option_symbol("NSE:NIFTY26JUN23850PE")
        == "NIFTY_20260630_23850_PE"
    )


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
    bars = adapter.get_underlying_bars(
        "NIFTY",
        session_date=date(2026, 5, 8),
        from_time=time(9, 14),
        to_time=time(9, 30),
        interval_minutes=1,
    )
    selected = adapter.get_option_quote(
        "NIFTY_20260512_25000_PE",
        session_date=date(2026, 5, 8),
    )
    stream_events = adapter.stream_ticks()

    assert health.connection_state is BrokerConnectionState.CONNECTED
    assert underlying.envelope.event_type is PaperEventType.UNDERLYING_QUOTE
    assert underlying.symbol == "NIFTY"
    assert len(bars) == 3
    assert bars[0].symbol == "NIFTY"
    assert chain.underlying_symbol == "NIFTY"
    assert chain.contracts[0].symbol == "NIFTY_20260512_25000_PE"
    assert selected.symbol == "NIFTY_20260512_25000_PE"
    assert selected.option_type is OptionType.PUT
    assert len(stream_events) == 1
    assert stream_events[0].envelope.event_type is PaperEventType.SELECTED_CONTRACT_BAR


def test_fyers_adapter_requests_specific_expiry_and_configured_strike_count() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["option_chain"]
    client = _FakeFyersClient(payload)
    adapter = FyersBrokerAdapter(
        client=client,
        source_timezone="Asia/Kolkata",
        option_chain_strike_count=80,
    )
    adapter.connect()

    adapter.get_option_chain("NIFTY", date(2026, 6, 30), session_date=date(2026, 6, 25))

    expected_timestamp = int(
        datetime(2026, 6, 30, 15, 30, tzinfo=ZoneInfo("Asia/Kolkata")).timestamp()
    )
    assert client.optionchain_requests == [
        {
            "symbol": "NSE:NIFTY50-INDEX",
            "strikecount": 80,
            "timestamp": expected_timestamp,
        }
    ]


def test_fyers_adapter_skips_underlying_rows_in_option_chain(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["option_chain"]["optionsChain"] = [
        {
            "symbol": "NSE:NIFTY50-INDEX",
            "ltp": 22440.0,
        },
        *payload["option_chain"]["optionsChain"],
    ]
    fixture_path = tmp_path / "fyers_market_data_payloads_mixed_chain.json"
    fixture_path.write_text(json.dumps(payload), encoding="utf-8")

    adapter = FyersBrokerAdapter.from_payload_file(fixture_path)
    adapter.connect()
    chain = adapter.get_option_chain(
        "NIFTY",
        date(2026, 5, 12),
        session_date=date(2026, 5, 8),
    )

    assert len(chain.contracts) == 1
    assert chain.contracts[0].symbol == "NIFTY_20260512_25000_PE"


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
