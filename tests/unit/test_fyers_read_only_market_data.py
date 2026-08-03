from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import time
from zoneinfo import ZoneInfo

import pytest

from tfis.fyers_read_only import (
    FyersReadOnlyAdapter,
    FyersReadOnlyCredentials,
    FyersReadOnlyStatus,
    InstrumentMasterRecord,
    OIQuality,
    canonical_hash,
    normalize_history_payload,
    redact_sensitive,
)


IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 8, 2, 10, 0, tzinfo=IST)


class FakeFyersClient:
    def __init__(self, *, profile=None, history=None, quotes=None, option_chain=None, depth=None) -> None:
        self.profile_payload = profile or {"s": "ok", "data": {"name": "fixture"}}
        self.history_payload = history or {"s": "ok", "candles": []}
        self.quotes_payload = quotes or {"s": "ok", "d": []}
        self.option_chain_payload = option_chain or {"s": "ok", "data": {"optionsChain": []}}
        self.depth_payload = depth or {"s": "ok", "d": {}}

    def get_profile(self):
        return self.profile_payload

    def history(self, request):
        return self.history_payload

    def quotes(self, request):
        return self.quotes_payload

    def optionchain(self, request):
        self.last_optionchain_request = request
        return self.option_chain_payload

    def depth(self, request):
        return self.depth_payload


def _adapter(client: FakeFyersClient) -> FyersReadOnlyAdapter:
    return FyersReadOnlyAdapter(client=client, now_provider=lambda: NOW, sleeper=lambda _: None)


def test_valid_authentication_session_is_redacted() -> None:
    result = _adapter(FakeFyersClient(profile={"s": "ok", "access_token": "SECRET"})).validate_session()

    assert result.status == FyersReadOnlyStatus.AUTHENTICATED
    assert result.payload == {"profile": "REDACTED"}
    assert result.source_hash == canonical_hash({"s": "ok", "access_token": "REDACTED"})


def test_authentication_required_without_credentials_or_client() -> None:
    result = FyersReadOnlyAdapter(now_provider=lambda: NOW).validate_session()

    assert result.status == FyersReadOnlyStatus.AUTHENTICATION_REQUIRED
    assert "FYERS_APP_ID" in result.warnings[0]


def test_missing_env_credentials_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FYERS_APP_ID", raising=False)
    monkeypatch.delenv("FYERS_ACCESS_TOKEN", raising=False)

    with pytest.raises(Exception) as exc:
        FyersReadOnlyCredentials.from_env()

    assert "FYERS_APP_ID" in str(exc.value)


def test_token_expired_response_is_classified() -> None:
    client = FakeFyersClient(profile={"s": "error", "message": "token expired"})

    result = _adapter(client).validate_session()

    assert result.status == FyersReadOnlyStatus.TOKEN_EXPIRED


def test_symbol_master_download_is_normalized_without_network() -> None:
    csv_text = (
        "symbol,segment,underlying,expiry,strike,option_type,lotSize,tickSize,fyToken\n"
        "NSE:RELIANCE26AUG3000CE,NSEFO,RELIANCE,2026-08-27,3000,CE,250,0.05,TOKEN1\n"
    )
    adapter = FyersReadOnlyAdapter(
        now_provider=lambda: NOW,
        symbol_master_downloader=lambda exchange: csv_text,
    )

    result = adapter.fetch_symbol_master("NSEFO")

    assert result.status == FyersReadOnlyStatus.SUCCESS
    assert result.payload[0].underlying == "RELIANCE"
    assert result.payload[0].lot_size == 250
    assert result.payload[0].tick_size == Decimal("0.05")


def test_history_normalization_excludes_incomplete_and_deduplicates() -> None:
    payload = {
        "candles": [
            [1785527100, 100, 110, 95, 105, 1000],
            [1785527100, 100, 110, 95, 105, 1000],
            [1785613500, 106, 111, 101, 109, 900],
        ]
    }

    candles = normalize_history_payload(
        payload,
        symbol="NSE:RELIANCE-EQ",
        interval="D",
        source_id="fixture",
        as_of=NOW,
        exclude_incomplete_after=datetime(2026, 8, 1, 23, 59, tzinfo=IST),
    )

    assert candles.duplicate_count == 1
    assert len(candles.candles) == 1
    assert len(candles.excluded_incomplete) == 1


def test_option_chain_normalizes_ce_pe_expiry_strike_and_oi_quality() -> None:
    payload = {
        "s": "ok",
        "data": {
            "optionsChain": [
                {
                    "symbol": "NSE:RELIANCE26AUG3000CE",
                    "expiry": "2026-08-27",
                    "strike": "3000",
                    "option_type": "CE",
                    "ltp": "42.5",
                    "bid": "42.0",
                    "ask": "43.0",
                    "oi": "1000",
                    "lotSize": "250",
                    "tickSize": "0.05",
                },
                {
                    "symbol": "NSE:RELIANCE26AUG3000PE",
                    "expiry": "2026-08-27",
                    "strike": "3000",
                    "option_type": "PE",
                    "ltp": "37.5",
                    "oi": "0",
                    "lotSize": "250",
                    "tickSize": "0.05",
                },
                {
                    "symbol": "NSE:RELIANCE26SEP3000CE",
                    "expiry": "2026-09-24",
                    "strike": "3000",
                    "option_type": "CE",
                    "ltp": "55.0",
                },
            ]
        },
    }

    result = _adapter(FakeFyersClient(option_chain=payload)).fetch_option_chain(
        underlying="NSE:RELIANCE-EQ",
        expiry=date(2026, 8, 27),
    )

    assert result.status == FyersReadOnlyStatus.SUCCESS
    assert {contract.option_type for contract in result.payload.contracts} == {"CALL", "PUT"}
    assert {contract.expiry for contract in result.payload.contracts} == {date(2026, 8, 27), date(2026, 9, 24)}
    ce = next(contract for contract in result.payload.contracts if contract.option_type == "CALL" and contract.expiry == date(2026, 8, 27))
    pe = next(contract for contract in result.payload.contracts if contract.option_type == "PUT")
    assert ce.oi_quality == OIQuality.AVAILABLE
    assert pe.oi_quality == OIQuality.ZERO


def test_option_chain_uses_symbol_master_expiry_and_strike_price_shape() -> None:
    payload = {
        "s": "ok",
        "data": {
            "optionsChain": [
                {
                    "symbol": "NSE:RELIANCE26AUG1260CE",
                    "strike_price": 1260,
                    "option_type": "CE",
                    "ltp": 57.6,
                    "bid": 57.6,
                    "ask": 58.05,
                    "oi": 632500,
                }
            ]
        },
    }
    record = InstrumentMasterRecord(
        source_symbol="NSE:RELIANCE26AUG1260CE",
        instrument_id="1011260825141826",
        exchange="NSEFO",
        segment="NSEFO",
        instrument_type="OPTION",
        underlying="RELIANCE",
        expiry=date(2026, 8, 25),
        strike=Decimal("1260"),
        option_type="CALL",
        lot_size=500,
        tick_size=Decimal("0.05"),
        instrument_token="141826",
        status="ACTIVE",
        source_row={"expiry": "1787652000"},
        source_version="fixture",
        downloaded_at=NOW,
        source_hash="hash",
    )
    client = FakeFyersClient(option_chain=payload)

    result = _adapter(client).fetch_option_chain(
        underlying="NSE:RELIANCE-EQ",
        expiry=date(2026, 8, 25),
        strike_count=5,
        instrument_records=(record,),
    )

    assert client.last_optionchain_request["timestamp"] == 1787652000
    assert result.status == FyersReadOnlyStatus.SUCCESS
    assert result.payload.contracts[0].expiry == date(2026, 8, 25)
    assert result.payload.contracts[0].strike == Decimal("1260")
    assert result.payload.contracts[0].lot_size == 500


def test_missing_and_malformed_oi_are_distinct() -> None:
    payload = {
        "data": {
            "optionsChain": [
                {"symbol": "NSE:RELIANCE26AUG3000CE", "expiry": "2026-08-27", "strike": "3000", "option_type": "CE"},
                {
                    "symbol": "NSE:RELIANCE26AUG3000PE",
                    "expiry": "2026-08-27",
                    "strike": "3000",
                    "option_type": "PE",
                    "oi": "bad",
                },
            ]
        }
    }

    result = _adapter(FakeFyersClient(option_chain=payload)).fetch_option_chain(
        underlying="RELIANCE",
        expiry=date(2026, 8, 27),
    )

    qualities = {contract.option_type: contract.oi_quality for contract in result.payload.contracts}
    assert qualities == {"CALL": OIQuality.MISSING, "PUT": OIQuality.MALFORMED}


def test_rate_limit_timeout_and_malformed_payloads_are_classified() -> None:
    rate_limited = _adapter(FakeFyersClient(history={"s": "error", "code": 429, "message": "rate limit"}))
    timeout = _adapter(FakeFyersClient())
    malformed = _adapter(FakeFyersClient(history={"s": "ok", "candles": "bad"}))

    class TimeoutHistoryClient(FakeFyersClient):
        def history(self, request):
            raise TimeoutError("timeout")

    assert rate_limited.fetch_historical_candles(
        symbol="NSE:RELIANCE-EQ",
        resolution="D",
        range_from=date(2026, 7, 1),
        range_to=date(2026, 8, 1),
    ).status == FyersReadOnlyStatus.RATE_LIMITED
    assert _adapter(TimeoutHistoryClient()).fetch_historical_candles(
        symbol="NSE:RELIANCE-EQ",
        resolution="D",
        range_from=date(2026, 7, 1),
        range_to=date(2026, 8, 1),
    ).status == FyersReadOnlyStatus.TIMEOUT
    assert malformed.fetch_historical_candles(
        symbol="NSE:RELIANCE-EQ",
        resolution="D",
        range_from=date(2026, 7, 1),
        range_to=date(2026, 8, 1),
    ).status == FyersReadOnlyStatus.MALFORMED


def test_quotes_timeout_is_bounded_by_adapter_timeout() -> None:
    class HangingQuotesClient(FakeFyersClient):
        def quotes(self, request):
            time.sleep(0.2)
            return {"s": "ok", "d": []}

    adapter = FyersReadOnlyAdapter(
        client=HangingQuotesClient(),
        now_provider=lambda: NOW,
        sleeper=lambda _: None,
        timeout_seconds=0.05,
        max_retries=0,
    )

    result = adapter.fetch_quotes(("NSE:RELIANCE-EQ",))

    assert result.status == FyersReadOnlyStatus.TIMEOUT


def test_redaction_preserves_instrument_token_metadata_but_removes_credentials() -> None:
    redacted = redact_sensitive(
        {
            "access_token": "SECRET",
            "refresh_token": "SECRET",
            "instrument_token": "RELIANCE_TOKEN",
            "nested": {"client_secret": "SECRET"},
        }
    )

    assert redacted["access_token"] == "REDACTED"
    assert redacted["refresh_token"] == "REDACTED"
    assert redacted["instrument_token"] == "RELIANCE_TOKEN"
    assert redacted["nested"]["client_secret"] == "REDACTED"
