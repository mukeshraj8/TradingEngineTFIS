from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tfis.brokers import FyersBrokerAdapter
from tfis.brokers.base import BrokerNormalizationError
from tfis.domain.enums import MonthlyStatus
from tfis.market_data import UnderlyingHistoryBar
from tfis.monthly_status.current_data import (
    MonthlyStatusCurrentDataError,
    derive_monthly_status_reference_levels,
    fetch_current_monthly_status,
    load_monthly_status_instrument_registry,
)
from tfis.monthly_status.lookback import MonthlyStatusHistoricalBar


IST = ZoneInfo("Asia/Kolkata")


def _bar(day: date, high: float, low: float, close: float) -> MonthlyStatusHistoricalBar:
    return MonthlyStatusHistoricalBar(
        timestamp=datetime.combine(day, datetime.min.time(), tzinfo=IST),
        high=high,
        low=low,
        close=close,
    )


def _history_bar(day: date, high: float, low: float, close: float) -> UnderlyingHistoryBar:
    start = datetime.combine(day, datetime.min.time(), tzinfo=IST)
    return UnderlyingHistoryBar(
        symbol="INFY",
        bar_start=start,
        bar_end=start,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1000,
    )


def test_derive_monthly_status_reference_levels_uses_previous_and_current_windows() -> None:
    levels = derive_monthly_status_reference_levels(
        historical_bars=(
            _bar(date(2026, 5, 28), 100, 90, 95),
            _bar(date(2026, 5, 29), 110, 85, 100),
            _bar(date(2026, 6, 15), 120, 101, 115),
            _bar(date(2026, 6, 16), 122, 102, 118),
            _bar(date(2026, 6, 22), 130, 111, 126),
        ),
        as_of=date(2026, 6, 22),
    )

    assert levels.PMH == 110
    assert levels.PML == 85
    assert levels.CMH == 130
    assert levels.CML == 101
    assert levels.PWH == 122
    assert levels.PWL == 101
    assert levels.CWH == 130
    assert levels.CWL == 111
    assert levels.current_price == 126


def test_fetch_current_monthly_status_uses_registry_and_history_fetcher(tmp_path: Path) -> None:
    registry = tmp_path / "monthly_status_instruments.yaml"
    registry.write_text(
        """
default_symbol: INFY
default_price_source: spot
instruments:
  INFY:
    label: INFY
    instrument_group: stock
    spot_symbol: NSE:INFY-EQ
    futures_continuous_symbol: NSE:INFY-FUT-CONT
    lot_size: 400
""",
        encoding="utf-8",
    )
    calls: list[tuple[str, str, date, int, bool]] = []

    def fetcher(
        raw_symbol: str,
        normalized_symbol: str,
        as_of: date,
        lookback_days: int,
        continuous: bool,
    ) -> tuple[UnderlyingHistoryBar, ...]:
        calls.append((raw_symbol, normalized_symbol, as_of, lookback_days, continuous))
        return (
            _history_bar(date(2026, 5, 28), 100, 90, 95),
            _history_bar(date(2026, 5, 29), 110, 85, 100),
            _history_bar(date(2026, 6, 15), 120, 101, 115),
            _history_bar(date(2026, 6, 16), 122, 102, 118),
            _history_bar(date(2026, 6, 22), 130, 111, 126),
        )

    result = fetch_current_monthly_status(
        symbol="INFY",
        price_source="futures_continuous",
        as_of=date(2026, 6, 22),
        effective_status=MonthlyStatus.UNKNOWN,
        registry_path=registry,
        history_fetcher=fetcher,
    )

    assert calls == [("NSE:INFY-FUT-CONT", "INFY", date(2026, 6, 22), 180, True)]
    assert result.snapshot.instrument.instrument_group == "stock"
    assert result.snapshot.price_source == "futures_continuous"
    assert result.result.status in {MonthlyStatus.BULL, MonthlyStatus.BULL_CF}
    payload = result.to_json()
    assert len(payload["chart"]["daily"]) == 5
    assert len(payload["chart"]["weekly"]) == 3
    assert len(payload["chart"]["monthly"]) == 2
    assert payload["chart"]["monthly"][0] == {
        "label": "2026-05",
        "start_date": "2026-05-28",
        "end_date": "2026-05-29",
        "open": 95.0,
        "high": 110.0,
        "low": 85.0,
        "close": 100.0,
    }
    assert payload["chart"]["monthly"][1]["label"] == "2026-06"
    assert payload["chart"]["monthly"][1]["high"] == 130.0
    assert payload["chart"]["monthly"][1]["low"] == 101.0


def test_fetch_current_monthly_status_resolves_unknown_from_lookback(tmp_path: Path) -> None:
    registry = tmp_path / "monthly_status_instruments.yaml"
    registry.write_text(
        """
default_symbol: TESTSTOCK
default_price_source: spot
instruments:
  TESTSTOCK:
    label: TESTSTOCK
    instrument_group: stock
    spot_symbol: NSE:TESTSTOCK-EQ
    futures_continuous_symbol: null
    lot_size: 100
""",
        encoding="utf-8",
    )

    def fetcher(
        raw_symbol: str,
        normalized_symbol: str,
        as_of: date,
        lookback_days: int,
        continuous: bool,
    ) -> tuple[UnderlyingHistoryBar, ...]:
        return (
            _history_bar(date(2026, 4, 20), 100, 90, 95),
            _history_bar(date(2026, 4, 27), 99, 91, 95),
            _history_bar(date(2026, 5, 4), 103, 95, 102),
            _history_bar(date(2026, 5, 11), 102, 96, 101),
            _history_bar(date(2026, 5, 29), 101, 97, 100),
            _history_bar(date(2026, 6, 15), 104, 96, 103),
            _history_bar(date(2026, 6, 22), 103, 98, 104),
        )

    result = fetch_current_monthly_status(
        symbol="TESTSTOCK",
        price_source="spot",
        as_of=date(2026, 6, 22),
        registry_path=registry,
        history_fetcher=fetcher,
    )

    payload = result.to_json()
    assert result.result.status == MonthlyStatus.BULL
    assert result.result.trigger_name == "LOOKBACK::BULL_CONTINUES"
    assert payload["lookback_used"] is True
    assert payload["checked_lookback_windows"] == 1
    steps_text = "\n".join(payload["steps"])
    assert "Direct current-month test" in steps_text
    assert "Current month was not decisive" in steps_text
    assert "Lookback 1: lookback_1" in steps_text
    assert "borrowed as BULL" in steps_text
    assert "Final result: BULL" in steps_text


def test_registry_requires_configured_futures_continuous_symbol(tmp_path: Path) -> None:
    registry = tmp_path / "monthly_status_instruments.yaml"
    registry.write_text(
        """
default_symbol: INFY
default_price_source: spot
instruments:
  INFY:
    label: INFY
    instrument_group: stock
    spot_symbol: NSE:INFY-EQ
    futures_continuous_symbol: null
    lot_size: 400
""",
        encoding="utf-8",
    )

    loaded = load_monthly_status_instrument_registry(registry)

    with pytest.raises(MonthlyStatusCurrentDataError, match="Futures continuous symbol"):
        loaded.get("INFY").fyers_symbol_for("futures_continuous")


def test_fyers_configured_daily_bars_use_cont_flag_by_price_source() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.requests: list[dict[str, str]] = []

        def history(self, request: dict[str, str]) -> dict[str, object]:
            self.requests.append(request)
            timestamp = int(datetime(2026, 6, 22, tzinfo=IST).timestamp())
            return {"candles": [[timestamp, 100, 110, 90, 105, 1000]]}

    client = FakeClient()
    adapter = FyersBrokerAdapter(client=client)
    adapter.connect()

    adapter.get_daily_bars_for_symbol(
        raw_symbol="NSE:INFY-EQ",
        normalized_symbol="INFY",
        session_date=date(2026, 6, 22),
        continuous=False,
    )
    adapter.get_daily_bars_for_symbol(
        raw_symbol="NSE:INFY-FUT-CONT",
        normalized_symbol="INFY",
        session_date=date(2026, 6, 22),
        continuous=True,
    )

    assert client.requests[0]["cont_flag"] == "0"
    assert client.requests[1]["cont_flag"] == "1"


def test_fyers_history_error_payload_is_reported() -> None:
    class FakeClient:
        def history(self, request: dict[str, str]) -> dict[str, object]:
            return {"s": "error", "code": -99, "message": "Bad request"}

    adapter = FyersBrokerAdapter(client=FakeClient())
    adapter.connect()

    with pytest.raises(BrokerNormalizationError, match=r"FYERS history request failed \[-99\]: Bad request"):
        adapter.get_daily_bars_for_symbol(
            raw_symbol="NSE:INFY-EQ",
            normalized_symbol="INFY",
            session_date=date(2026, 6, 22),
            continuous=False,
        )
