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
from tfis.paper import (
    S23PaperOrderStateStore,
    S23PaperTradeDecisionSummary,
    append_selected_contract_market_events,
)


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

    path = append_selected_contract_market_events(
        tmp_path,
        events=(event,),
        observed_at=observed_at,
        process_pid=12345,
        trade_id="trade-1",
        process_role="watcher",
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


def test_fetch_selected_contract_events_raises_when_no_stream_evidence_exists(monkeypatch) -> None:
    module = _load_watch_module()

    class _Adapter:
        def stream_ticks(self):
            return ()

    def _fake_fetch(adapter, request, on_bar_fetch_error=None):
        raise BrokerAdapterError("quote fetch failed")

    monkeypatch.setattr(module, "fetch_selected_contract_market_events", _fake_fetch)

    import pytest

    with pytest.raises(BrokerAdapterError, match="quote fetch failed"):
        module._fetch_selected_contract_events(
            adapter=_Adapter(),
            selected_contract_symbol="NIFTY_20260707_24100_CE",
            session_date=date(2026, 7, 3),
            evaluated_at=datetime(2026, 7, 3, 9, 31, 5),
            state=None,
        )


def test_resolve_order_dir_uses_shared_order_discovery_for_same_day_waiting_order(tmp_path: Path) -> None:
    module = _load_watch_module()
    today_dir = tmp_path / "2026-07-21" / "order-today"
    old_dir = tmp_path / "2026-07-20" / "order-old"
    today_dir.mkdir(parents=True)
    old_dir.mkdir(parents=True)

    store = S23PaperOrderStateStore()
    store.create_waiting_order_from_live_decision(
        today_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 21)),
        created_at=datetime(2026, 7, 21, 9, 30),
    )
    store.create_waiting_order_from_live_decision(
        old_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 7, 20)),
        created_at=datetime(2026, 7, 20, 9, 30),
    )

    resolved = module._resolve_order_dir(
        order_dir=None,
        search_roots=(str(tmp_path),),
        default_artifact_root=tmp_path,
        no_open_ok=False,
        session_date=date(2026, 7, 21),
    )

    assert resolved == today_dir.resolve()


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
        "inspect_paper_live_state_store_from_yaml",
        lambda path: SimpleNamespace(
            status="PASS",
            provider="redis",
            backend="redis",
            message="ready",
        ),
    )
    monkeypatch.setattr(
        module,
        "build_paper_live_state_store_from_yaml",
        lambda path, strict=False: live_state_store,
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


def test_watch_runtime_uses_shared_broker_runtime_connect_helper(monkeypatch) -> None:
    module = _load_watch_module()
    calls: list[tuple[str, str, object]] = []

    class FakeStateStore:
        def load_state(self, _path):
            return SimpleNamespace(
                selected_contract_symbol="NIFTY_20260707_24100_CE",
                entry_date=date(2026, 7, 3),
                stoploss_reset_pending=False,
                stoploss_active=True,
                stoploss_reset_session_date=None,
                stoploss_reset_rc_time=None,
            )

    class FakeAdapter:
        def subscribe_symbols(self, symbols):
            return symbols

        def disconnect(self):
            return None

    fake_adapter = FakeAdapter()

    monkeypatch.setattr(
        module,
        "_load_watch_runtime_components",
        lambda args: SimpleNamespace(
            runtime_config=SimpleNamespace(
                broker=SimpleNamespace(provider="fyers"),
                costs=SimpleNamespace(slippage_exit_points=0.0),
            ),
            timezone_name="Asia/Kolkata",
            timezone=module.ZoneInfo("Asia/Kolkata"),
            adapter=fake_adapter,
            live_state_store=SimpleNamespace(
                acquire_trade_lock=lambda **kwargs: True,
                release_trade_lock=lambda **kwargs: None,
                set_watch_heartbeat=lambda **kwargs: None,
            ),
        ),
    )
    monkeypatch.setattr(module, "_resolve_state_dir", lambda **kwargs: Path("D:/tmp/state"))
    monkeypatch.setattr(module, "S23PaperPositionStateStore", lambda: FakeStateStore())
    monkeypatch.setattr(
        module,
        "PaperLifecycleSupervisorContext",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(module, "_watch_process_lock_path", lambda *_args, **_kwargs: Path("D:/tmp/watch.pid.json"))
    monkeypatch.setattr(
        module,
        "acquire_process_lock",
        lambda *args, **kwargs: SimpleNamespace(release=lambda: None),
    )
    monkeypatch.setattr(module, "_acquire_watch_file_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_release_watch_file_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        module,
        "build_paper_position_manager",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        module,
        "PaperLifecycleSupervisor",
        lambda **kwargs: SimpleNamespace(expire_waiting_order_from_previous_session=lambda *a, **k: None),
    )
    monkeypatch.setattr(module, "build_paper_expiry_governance", lambda **kwargs: object())
    monkeypatch.setattr(
        module,
        "connect_paper_broker_runtime",
        lambda *, strategy_code, provider, adapter: calls.append((strategy_code, provider, adapter))
        or SimpleNamespace(connection_state=SimpleNamespace(value="CONNECTED")),
    )
    monkeypatch.setattr(module, "_fetch_selected_contract_events", lambda **kwargs: ())
    monkeypatch.setattr(module, "append_selected_contract_market_events", lambda *args, **kwargs: Path("D:/tmp/events.jsonl"))
    monkeypatch.setattr(
        module,
        "_rebuild_dashboard",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        module,
        "paper_live_state_owner_id",
        lambda prefix="tfis-s23-paper-watch": "owner-1",
    )
    monkeypatch.setattr(
        module,
        "S23PaperTradeLedgerStore",
        SimpleNamespace(trade_id_for_state=lambda state: "trade-1"),
    )
    monkeypatch.setattr(
        module,
        "datetime",
        SimpleNamespace(
            now=lambda tz=None: datetime(2026, 7, 3, 9, 31),
        ),
    )

    lifecycle_result = SimpleNamespace(
        context=SimpleNamespace(
            trade_id="trade-1",
            selected_contract_symbol="NIFTY_20260707_24100_CE",
            session_directory=Path("D:/tmp/state"),
        ),
        steps=(),
        final_step=SimpleNamespace(status="HOLD"),
        terminal=False,
    )
    monkeypatch.setattr(
        module,
        "PaperLifecycleSupervisor",
        lambda **kwargs: SimpleNamespace(
            expire_waiting_order_from_previous_session=lambda *a, **k: None,
            supervise=lambda *a, **k: lifecycle_result,
        ),
    )

    result = module.main(
        [
            "--state-dir",
            "D:/tmp/state",
            "--once",
            "--disable-dashboard-rebuild",
        ]
    )

    assert result == 0
    assert calls == [("S23", "fyers", fake_adapter)]


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


def _strategy_rule():
    from datetime import time

    from tfis.domain import (
        ExpiryType,
        MonthlyStatus,
        OptionType as DomainOptionType,
        RolloverPolicy,
        Segment,
        StrategyExpiryPolicy,
        StrategyRule,
    )

    return StrategyRule(
        strategy_code="S23",
        unique_code="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
            forced_close_time=time(12, 0),
            no_carry_past_expiry=True,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BEAR,),
        option_type=DomainOptionType.PUT,
        entry_time=time(9, 24, 59),
        recalculation_time=time(9, 29, 59),
        start_strike_formula="1",
        end_strike_formula="1",
        ideal_premium_formula="1",
        minimum_premium_formula="1",
        minimum_oi=500,
        entry_formula="1",
        target_formula="1",
        stoploss_formula="1",
        carry_forward_allowed=True,
        parameters={"sl_reference_pct": 7.0},
    )


def _ready_summary(*, session_date: date) -> S23PaperTradeDecisionSummary:
    return S23PaperTradeDecisionSummary(
        status="READY",
        session_date=session_date,
        mode="fresh_entry",
        strategy_code="S23",
        strategy_branch="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        monthly_status="BEAR",
        monthly_status_trigger="BEAR_CONTINUES",
        monthly_status_notes="test",
        required_market_aliases=(),
        required_option_aliases=(),
        checkpoint_labels=("0915", "ORPT", "RC"),
        market_levels={},
        runtime_values={},
        lots=1,
        quantity=65,
        selected_contract_symbol="NIFTY_20260723_24150_PE",
        selected_contract_expiry="2026-07-23",
        selected_contract_strike=24150.0,
        selected_contract_option_type="PUT",
        selected_contract_ltp=194.25,
        selected_contract_oi=1000000.0,
        contract_selection_reason="test",
        contract_selection_failure_code=None,
        contract_selection_attempted_expiries=("2026-07-23",),
        rejected_candidate_counts={},
        ranked_candidates=(),
        planned_entry_price=194.25,
        target_price=77.70,
        stoploss_price=242.0,
        fsl_price=258.94,
        source_workbook_rule="test",
        workbook_row_number=1,
        notes=(),
    )
