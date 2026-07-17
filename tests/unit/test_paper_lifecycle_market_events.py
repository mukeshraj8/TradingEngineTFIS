from __future__ import annotations

from datetime import date, datetime, time

from tfis.brokers import BrokerAdapter, BrokerAdapterError, BrokerHealthEvent
from tfis.domain.enums import OptionType
from tfis.normalized_events import EventEnvelope, PaperEventType, SelectedContractBarEvent, SelectedContractQuoteEvent
from tfis.paper import PaperSelectedContractEventRequest, fetch_selected_contract_market_events


class _FakeBrokerAdapter(BrokerAdapter):
    broker_name = "fake"

    def __init__(self) -> None:
        self.bar_calls: list[tuple[str, date, time, time, int]] = []
        self.quote_calls: list[tuple[str, date]] = []
        self.raise_bar_error = False

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def subscribe_symbols(self, symbols: tuple[str, ...]) -> tuple[str, ...]:
        return symbols

    def get_underlying_quote(self, symbol: str, *, session_date: date):
        raise NotImplementedError

    def get_option_chain(self, symbol: str, expiry: date, *, session_date: date):
        raise NotImplementedError

    def get_option_quote(
        self,
        option_symbol: str,
        *,
        session_date: date,
    ) -> SelectedContractQuoteEvent:
        self.quote_calls.append((option_symbol, session_date))
        return _quote(session_date=session_date, effective_timestamp=datetime(2026, 7, 17, 10, 0))

    def get_underlying_bars(
        self,
        symbol: str,
        *,
        session_date: date,
        from_time: time,
        to_time: time,
        interval_minutes: int = 1,
    ):
        raise NotImplementedError

    def get_option_bars(
        self,
        option_symbol: str,
        *,
        session_date: date,
        from_time: time,
        to_time: time,
        interval_minutes: int = 1,
    ) -> tuple[SelectedContractBarEvent, ...]:
        self.bar_calls.append((option_symbol, session_date, from_time, to_time, interval_minutes))
        if self.raise_bar_error:
            raise BrokerAdapterError("bar fetch failed")
        return (_bar(session_date=session_date, bar_time=to_time),)

    def get_underlying_daily_bars(
        self,
        symbol: str,
        *,
        session_date: date,
        lookback_days: int = 90,
    ):
        raise NotImplementedError

    def stream_ticks(self):
        return ()

    def health(self) -> BrokerHealthEvent:
        raise NotImplementedError

    def reconnect(self) -> BrokerHealthEvent:
        raise NotImplementedError


def test_fetch_selected_contract_market_events_fetches_quote_only_without_sl_reset() -> None:
    adapter = _FakeBrokerAdapter()
    request = PaperSelectedContractEventRequest(
        selected_contract_symbol="NIFTY_20260721_23950_CE",
        session_date=date(2026, 7, 17),
        evaluated_at=datetime(2026, 7, 17, 10, 1),
    )

    events = fetch_selected_contract_market_events(adapter, request)

    assert len(events) == 1
    assert isinstance(events[0], SelectedContractQuoteEvent)
    assert adapter.bar_calls == []
    assert adapter.quote_calls == [("NIFTY_20260721_23950_CE", date(2026, 7, 17))]


def test_fetch_selected_contract_market_events_fetches_reset_bars_before_quote() -> None:
    adapter = _FakeBrokerAdapter()
    request = PaperSelectedContractEventRequest(
        selected_contract_symbol="NIFTY_20260721_23950_CE",
        session_date=date(2026, 7, 17),
        evaluated_at=datetime(2026, 7, 17, 9, 20),
        stoploss_reset_pending=True,
        stoploss_active=False,
        stoploss_reset_session_date=date(2026, 7, 16),
        stoploss_reset_rc_time=time(9, 29, 59),
    )

    events = fetch_selected_contract_market_events(adapter, request)

    assert len(events) == 2
    assert isinstance(events[0], SelectedContractBarEvent)
    assert isinstance(events[1], SelectedContractQuoteEvent)
    assert adapter.bar_calls == [
        (
            "NIFTY_20260721_23950_CE",
            date(2026, 7, 17),
            time(9, 15),
            time(9, 29, 59),
            1,
        )
    ]


def test_fetch_selected_contract_market_events_reports_bar_fetch_error_and_keeps_quote() -> None:
    adapter = _FakeBrokerAdapter()
    adapter.raise_bar_error = True
    request = PaperSelectedContractEventRequest(
        selected_contract_symbol="NIFTY_20260721_23950_CE",
        session_date=date(2026, 7, 17),
        evaluated_at=datetime(2026, 7, 17, 9, 20),
        stoploss_reset_pending=True,
        stoploss_active=False,
        stoploss_reset_session_date=date(2026, 7, 16),
    )
    errors: list[str] = []

    events = fetch_selected_contract_market_events(
        adapter,
        request,
        on_bar_fetch_error=lambda exc: errors.append(str(exc)),
    )

    assert len(events) == 1
    assert isinstance(events[0], SelectedContractQuoteEvent)
    assert errors == ["bar fetch failed"]


def _quote(*, session_date: date, effective_timestamp: datetime) -> SelectedContractQuoteEvent:
    return SelectedContractQuoteEvent(
        envelope=_envelope(
            event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            session_date=session_date,
            effective_timestamp=effective_timestamp,
        ),
        symbol="NIFTY_20260721_23950_CE",
        option_type=OptionType.CALL,
        strike=23950.0,
        expiry=date(2026, 7, 21),
        bid=210.0,
        ask=211.0,
        ltp=210.5,
        oi=100000.0,
    )


def _bar(*, session_date: date, bar_time: time) -> SelectedContractBarEvent:
    timestamp = datetime.combine(session_date, bar_time)
    return SelectedContractBarEvent(
        envelope=_envelope(
            event_type=PaperEventType.SELECTED_CONTRACT_BAR,
            session_date=session_date,
            effective_timestamp=timestamp,
        ),
        symbol="NIFTY_20260721_23950_CE",
        open=210.0,
        high=211.0,
        low=209.0,
        close=210.5,
        bar_start=timestamp,
        bar_end=timestamp,
        volume=100.0,
    )


def _envelope(
    *,
    event_type: PaperEventType,
    session_date: date,
    effective_timestamp: datetime,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        session_date=session_date,
        effective_timestamp=effective_timestamp,
        captured_at=effective_timestamp,
        timezone="Asia/Kolkata",
        source_type="test",
        source_id="test",
        synthetic_fixture=True,
        normalized_by="test",
    )
