from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from tfis.brokers import BrokerAdapterError
from tfis.domain.enums import OptionType
from tfis.normalized_events import EventEnvelope, PaperEventType, SelectedContractQuoteEvent


def _load_watch_module():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "run_s23_paper_position_watch.py"
    spec = importlib.util.spec_from_file_location("run_s23_paper_position_watch", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_selected_contract_market_events_are_appended_as_jsonl(tmp_path: Path) -> None:
    module = _load_watch_module()
    observed_at = datetime(2026, 7, 3, 9, 31, 5)
    event = SelectedContractQuoteEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            session_date=date(2026, 7, 3),
            effective_timestamp=datetime(2026, 7, 3, 9, 31, 4),
            captured_at=observed_at,
            timezone="Asia/Kolkata",
            source_type="test",
            source_id="quote",
            synthetic_fixture=True,
            normalized_by="test",
        ),
        symbol="NIFTY_20260707_24100_CE",
        option_type=OptionType.CALL,
        strike=24100.0,
        expiry=date(2026, 7, 7),
        bid=285.5,
        ask=286.9,
        ltp=286.85,
        oi=3734250.0,
        volume=100.0,
    )

    path = module._append_selected_contract_market_events(
        tmp_path,
        events=(event,),
        observed_at=observed_at,
        watcher_pid=12345,
        trade_id="trade-1",
    )

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert path.name == "selected_contract_market_events.jsonl"
    assert len(rows) == 1
    assert rows[0]["event_kind"] == "selected_contract_quote"
    assert rows[0]["observed_at"] == "2026-07-03T09:31:05"
    assert rows[0]["watcher_pid"] == 12345
    assert rows[0]["trade_id"] == "trade-1"
    assert rows[0]["symbol"] == "NIFTY_20260707_24100_CE"
    assert rows[0]["payload"]["ltp"] == 286.85
    assert rows[0]["payload"]["envelope"]["event_type"] == "SELECTED_CONTRACT_QUOTE"


def test_fetch_selected_contract_events_combines_stream_and_shared_fetch(monkeypatch) -> None:
    module = _load_watch_module()
    stream_event = _quote_event(
        symbol="NIFTY_20260707_24100_CE",
        effective_timestamp=datetime(2026, 7, 3, 9, 31, 4),
        ltp=286.85,
    )
    fetched_event = _quote_event(
        symbol="NIFTY_20260707_24100_CE",
        effective_timestamp=datetime(2026, 7, 3, 9, 31, 5),
        ltp=287.10,
    )
    requests: list[object] = []

    class _Adapter:
        def stream_ticks(self):
            return (stream_event,)

    def _fake_fetch(adapter, request, on_bar_fetch_error=None):
        requests.append(request)
        return (fetched_event,)

    monkeypatch.setattr(module, "fetch_selected_contract_market_events", _fake_fetch)

    events = module._fetch_selected_contract_events(
        adapter=_Adapter(),
        selected_contract_symbol="NIFTY_20260707_24100_CE",
        session_date=date(2026, 7, 3),
        evaluated_at=datetime(2026, 7, 3, 9, 31, 5),
        state=None,
    )

    assert events == (stream_event, fetched_event)
    assert len(requests) == 1
    assert requests[0].selected_contract_symbol == "NIFTY_20260707_24100_CE"


def test_fetch_selected_contract_events_returns_stream_when_shared_fetch_fails(monkeypatch) -> None:
    module = _load_watch_module()
    stream_event = _quote_event(
        symbol="NIFTY_20260707_24100_CE",
        effective_timestamp=datetime(2026, 7, 3, 9, 31, 4),
        ltp=286.85,
    )

    class _Adapter:
        def stream_ticks(self):
            return (stream_event,)

    def _fake_fetch(adapter, request, on_bar_fetch_error=None):
        raise BrokerAdapterError("quote fetch failed")

    monkeypatch.setattr(module, "fetch_selected_contract_market_events", _fake_fetch)

    events = module._fetch_selected_contract_events(
        adapter=_Adapter(),
        selected_contract_symbol="NIFTY_20260707_24100_CE",
        session_date=date(2026, 7, 3),
        evaluated_at=datetime(2026, 7, 3, 9, 31, 5),
        state=None,
    )

    assert events == (stream_event,)


def test_watch_runtime_bootstrap_uses_shared_paper_runtime_config(monkeypatch) -> None:
    module = _load_watch_module()
    calls: list[tuple[str, object]] = []

    runtime_config = SimpleNamespace(
        broker=SimpleNamespace(timezone="Asia/Kolkata", provider="fyers"),
        costs=SimpleNamespace(slippage_exit_points=0.0),
    )
    adapter = object()
    live_state_store = object()
    monkeypatch.setattr(
        module,
        "load_paper_broker_runtime",
        lambda path, timezone_name=None: SimpleNamespace(
            config=runtime_config,
            timezone_name=timezone_name or "Asia/Kolkata",
            timezone=module.ZoneInfo("Asia/Kolkata"),
            adapter=adapter,
        ),
    )

    def _fake_prepare(config, *, tfis_root, skip_refresh):
        calls.append(("prepare", config))
        assert tfis_root == "D:/TradingEngineTFIS"
        assert skip_refresh is True

    monkeypatch.setattr(module, "prepare_paper_broker_runtime_environment", _fake_prepare)
    monkeypatch.setattr(
        module,
        "build_paper_live_state_store_from_yaml",
        lambda path: live_state_store,
    )

    result = module._load_watch_runtime_components(
        SimpleNamespace(
            config="config/paper.s23.fyers_connect_test.yaml",
            tfis_root="D:/TradingEngineTFIS",
            skip_refresh=True,
            timezone=None,
        )
    )

    assert calls == [("prepare", runtime_config)]
    assert result.runtime_config is runtime_config
    assert result.timezone_name == "Asia/Kolkata"
    assert result.adapter is adapter
    assert result.live_state_store is live_state_store


def _quote_event(*, symbol: str, effective_timestamp: datetime, ltp: float) -> SelectedContractQuoteEvent:
    observed_at = effective_timestamp
    return SelectedContractQuoteEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            session_date=effective_timestamp.date(),
            effective_timestamp=effective_timestamp,
            captured_at=observed_at,
            timezone="Asia/Kolkata",
            source_type="test",
            source_id="quote",
            synthetic_fixture=True,
            normalized_by="test",
        ),
        symbol=symbol,
        option_type=OptionType.CALL,
        strike=24100.0,
        expiry=date(2026, 7, 7),
        bid=ltp - 0.5,
        ask=ltp + 0.5,
        ltp=ltp,
        oi=3734250.0,
        volume=100.0,
    )
