from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path

from tfis.domain import (
    ExpiryType,
    MonthlyStatus,
    OptionType,
    RolloverPolicy,
    Segment,
    StrategyExpiryPolicy,
    StrategyRule,
)
from tfis.normalized_events import (
    EventEnvelope,
    PaperEventType,
    SelectedContractBarEvent,
    SelectedContractQuoteEvent,
)
from tfis.paper import (
    DeterministicExpiryCalendar,
    InMemoryS23PaperLiveStateStore,
    S23OpenPaperPositionDiscovery,
    S23PaperOrderStateStore,
    S23PaperOrderStatus,
    S23PaperExpiryGovernance,
    S23PaperPositionManager,
    S23PaperPositionManagerStatus,
    S23PaperPositionStateStatus,
    S23PaperTradeLedgerStore,
)
from tfis.paper.live_decision import S23PaperTradeDecisionSummary


def test_opens_ready_decision_as_multi_day_position(tmp_path: Path) -> None:
    live_state_store = InMemoryS23PaperLiveStateStore()
    manager = _manager(tmp_path, live_state_store=live_state_store)
    result = manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_OPENED
    assert result.state.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_OPEN
    assert result.state.stoploss_active is True
    assert result.state.stoploss_reset_pending is False
    assert result.state.selected_contract_symbol == "NIFTY_20260625_24150_PE"
    assert (tmp_path / "paper_position_state.json").is_file()
    ledger_rows = _session_ledger_rows(tmp_path)
    assert ledger_rows[-1]["event_type"] == "OPEN"
    assert ledger_rows[-1]["strategy_id"] == "S23:S23_NIFTY_OP_SELL_WK_DIFF_2D_3D"
    trade_id = "S23-S23_NIFTY_OP_SELL_WK_DIFF_2D_3D-NIFTY_20260625_24150_PE-20260622T093100"
    assert (
        "tfis:paper:session:2026-06-22:strategy:s23:state:"
        f"open_position:{trade_id}"
    ) in live_state_store.values
    assert "tfis:paper:session:2026-06-22:strategy:s23:series:trade_events" in live_state_store.lists


def test_ready_decision_creates_waiting_order_before_position(tmp_path: Path) -> None:
    store = S23PaperOrderStateStore()

    order_state, state_path, events_path = store.create_waiting_order_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        created_at=datetime(2026, 6, 22, 9, 30),
    )

    assert order_state.status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
    assert order_state.trigger_rule == "SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY"
    assert state_path == tmp_path / "paper_order_state.json"
    assert events_path == tmp_path / "paper_order_events.jsonl"
    assert not (tmp_path / "paper_position_state.json").exists()


def test_quote_above_entry_keeps_order_waiting_and_does_not_open_position(tmp_path: Path) -> None:
    store = S23PaperOrderStateStore()
    store.create_waiting_order_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        created_at=datetime(2026, 6, 22, 9, 30),
    )

    order_state, event, _state_path, _events_path = store.evaluate_waiting_order(
        tmp_path,
        market_events=(
            _quote(
                session_date=date(2026, 6, 22),
                effective_timestamp=datetime(2026, 6, 22, 9, 31),
                bid=238,
                ask=240,
                ltp=239,
            ),
        ),
        evaluated_at=datetime(2026, 6, 22, 9, 31),
    )

    assert order_state.status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
    assert event.reason_code == "paper_order_waiting_quote_above_entry"
    assert order_state.fill_price is None
    assert not (tmp_path / "paper_position_state.json").exists()


def test_quote_at_entry_fills_order_then_opens_position(tmp_path: Path) -> None:
    store = S23PaperOrderStateStore()
    manager = _manager(tmp_path)
    store.create_waiting_order_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        created_at=datetime(2026, 6, 22, 9, 30),
    )
    order_state, event, _state_path, _events_path = store.evaluate_waiting_order(
        tmp_path,
        market_events=(
            _quote(
                session_date=date(2026, 6, 22),
                effective_timestamp=datetime(2026, 6, 22, 9, 37),
                bid=193.75,
                ask=195,
                ltp=194.25,
            ),
        ),
        evaluated_at=datetime(2026, 6, 22, 9, 37),
    )

    result = manager.open_from_filled_order(tmp_path, order_state=order_state)

    assert event.reason_code == "paper_order_filled_from_quote_entry_trigger"
    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_OPENED
    assert result.state.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_OPEN
    assert result.state.stoploss_active is True
    assert result.state.stoploss_reset_pending is False
    assert result.state.entry_price == 193.75
    assert result.state.entry_timestamp == datetime(2026, 6, 22, 9, 37)


def test_carried_position_ignores_stoploss_until_orpt_reset(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )
    manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 22),
        market_events=(
            _bar(
                session_date=date(2026, 6, 22),
                high=210,
                low=120,
                close=150,
                bar_time=time(15, 0),
            ),
        ),
        evaluated_at=datetime(2026, 6, 22, 15, 0),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 23),
        market_events=(
            _quote(
                session_date=date(2026, 6, 23),
                effective_timestamp=datetime(2026, 6, 23, 9, 20),
                bid=330,
                ask=331,
                ltp=330.5,
            ),
        ),
        evaluated_at=datetime(2026, 6, 23, 9, 20),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_HELD
    assert result.event.reason_code == "carry_forward_stoploss_waiting_for_orpt"
    assert result.state.stoploss_active is False
    assert result.state.stoploss_reset_pending is True


def test_carried_position_reactivates_original_stop_at_orpt_when_0915_high_does_not_miss_sl(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )
    manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 22),
        market_events=(
            _bar(
                session_date=date(2026, 6, 22),
                high=210,
                low=120,
                close=150,
                bar_time=time(15, 0),
            ),
        ),
        evaluated_at=datetime(2026, 6, 22, 15, 0),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 23),
        market_events=(
            _bar(
                session_date=date(2026, 6, 23),
                high=315,
                low=140,
                close=250,
                bar_time=time(9, 15),
            ),
            _quote(
                session_date=date(2026, 6, 23),
                effective_timestamp=datetime(2026, 6, 23, 9, 25),
                bid=250,
                ask=251,
                ltp=250.5,
            ),
        ),
        evaluated_at=datetime(2026, 6, 23, 9, 25),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_HELD
    assert result.state.stoploss_active is True
    assert result.state.stoploss_reset_pending is False
    assert result.state.stoploss_price == 320


def test_carried_position_recalculates_stop_from_rc_high_when_0915_high_misses_sl(
    tmp_path: Path,
) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )
    manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 22),
        market_events=(
            _bar(
                session_date=date(2026, 6, 22),
                high=210,
                low=120,
                close=150,
                bar_time=time(15, 0),
            ),
        ),
        evaluated_at=datetime(2026, 6, 22, 15, 0),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 23),
        market_events=(
            _bar(
                session_date=date(2026, 6, 23),
                high=330,
                low=140,
                close=250,
                bar_time=time(9, 15),
            ),
            _bar(
                session_date=date(2026, 6, 23),
                high=350,
                low=300,
                close=310,
                bar_time=time(9, 29),
            ),
            _quote(
                session_date=date(2026, 6, 23),
                effective_timestamp=datetime(2026, 6, 23, 9, 30),
                bid=310,
                ask=311,
                ltp=310.5,
            ),
        ),
        evaluated_at=datetime(2026, 6, 23, 9, 30),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_HELD
    assert result.state.stoploss_active is True
    assert result.state.stoploss_reset_pending is False
    assert result.state.stoploss_price == 374.5


def test_waiting_order_can_be_marked_not_filled_at_cutoff(tmp_path: Path) -> None:
    store = S23PaperOrderStateStore()
    store.create_waiting_order_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        created_at=datetime(2026, 6, 22, 9, 30),
    )
    store.evaluate_waiting_order(
        tmp_path,
        market_events=(
            _quote(
                session_date=date(2026, 6, 22),
                effective_timestamp=datetime(2026, 6, 22, 15, 20),
                bid=238,
                ask=240,
                ltp=239,
            ),
        ),
        evaluated_at=datetime(2026, 6, 22, 15, 20),
    )

    order_state, event, _state_path, _events_path = store.mark_not_filled(
        tmp_path,
        marked_at=datetime(2026, 6, 22, 15, 30),
        reason_code="paper_order_not_triggered_by_watch_cutoff",
        message="Entry was not triggered before the paper watch cutoff.",
    )

    assert order_state.status is S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED
    assert event.reason_code == "paper_order_not_triggered_by_watch_cutoff"
    assert order_state.last_market_price == 239
    assert order_state.fill_price is None
    assert not (tmp_path / "paper_position_state.json").exists()


def test_holds_position_for_next_day_when_no_exit_hit(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 23),
        market_events=(
            _bar(
                session_date=date(2026, 6, 23),
                high=210,
                low=120,
                close=150,
            ),
        ),
        evaluated_at=datetime(2026, 6, 23, 15, 29),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_HELD
    assert result.state.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_CARRIED_FORWARD
    assert result.state.stoploss_active is False
    assert result.state.stoploss_reset_pending is True
    assert result.event.current_price == 150
    assert result.event.source_kind == "selected_contract_bar"
    ledger_rows = _session_ledger_rows(tmp_path)
    assert ledger_rows[-1]["current_price"] == 150
    assert ledger_rows[-1]["gross_points"] == 44.25
    assert ledger_rows[-1]["gross_pnl"] == 3318.75


def test_1500_rule_carries_forward_with_overnight_stop_inactive(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 23),
        market_events=(
            _bar(
                session_date=date(2026, 6, 23),
                high=210,
                low=120,
                close=150,
            ),
        ),
        evaluated_at=datetime(2026, 6, 23, 15, 0),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_HELD
    assert result.event.reason_code == "s23_1500_carry_forward_stop_inactive"
    assert "overnight stoploss is inactive" in result.event.message
    assert result.state.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_CARRIED_FORWARD
    assert result.state.stoploss_active is False
    assert result.state.stoploss_reset_pending is True


def test_target_hit_requires_fresh_recalculated_entry(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 23),
        market_events=(
            _quote(
                session_date=date(2026, 6, 23),
                effective_timestamp=datetime(2026, 6, 23, 10, 5),
                bid=78,
                ask=79,
                ltp=78.5,
            ),
        ),
        evaluated_at=datetime(2026, 6, 23, 10, 5),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_FRESH_ENTRY_REQUIRED
    assert result.state.lifecycle_status is S23PaperPositionStateStatus.PAPER_FRESH_ENTRY_REQUIRED
    assert result.event.reason_code == "target_hit"
    assert result.event.fresh_entry_required is True
    assert result.event.exit_price == 80
    ledger_rows = _session_ledger_rows(tmp_path)
    assert ledger_rows[-1]["event_type"] == "CLOSE"
    assert ledger_rows[-1]["fresh_entry_required"] is True
    assert ledger_rows[-1]["gross_points"] == 114.25
    assert ledger_rows[-1]["gross_pnl"] == 8568.75


def test_closes_on_stoploss_and_requires_fresh_reverse_decision(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 23),
        market_events=(
            _bar(
                session_date=date(2026, 6, 23),
                high=322,
                low=120,
                close=300,
            ),
        ),
        evaluated_at=datetime(2026, 6, 23, 10, 5),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_REVERSE_ENTRY_REQUIRED
    assert result.state.lifecycle_status is S23PaperPositionStateStatus.PAPER_REVERSE_ENTRY_REQUIRED
    assert result.event.reason_code == "stoploss_or_fsl_hit"
    assert result.event.reverse_entry_required is True
    assert _session_ledger_rows(tmp_path)[-1]["reverse_entry_required"] is True


def test_existing_position_opened_before_rollover_window_holds_on_t_minus_1(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(selected_contract_expiry="2026-06-25"),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 24),
        market_events=(
            _bar(
                session_date=date(2026, 6, 24),
                high=210,
                low=120,
                close=150,
            ),
        ),
        evaluated_at=datetime(2026, 6, 24, 9, 20),
        expiry_governance=S23PaperExpiryGovernance(DeterministicExpiryCalendar()),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_HELD
    assert result.state.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_OPEN
    assert result.event.rollover_required is False
    assert _session_ledger_rows(tmp_path)[-1]["event_type"] == "HOLD"


def test_expiry_day_noon_force_closes_if_target_or_stoploss_not_hit(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(selected_contract_expiry="2026-06-25"),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 25),
        market_events=(
            _bar(
                session_date=date(2026, 6, 25),
                high=210,
                low=120,
                close=150,
            ),
        ),
        evaluated_at=datetime(2026, 6, 25, 12, 0),
        expiry_governance=S23PaperExpiryGovernance(DeterministicExpiryCalendar()),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_FORCE_CLOSED
    assert result.event.reason_code == "expiry_force_close"
    assert result.event.exit_price == 150.0
    assert result.state.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_CLOSED
    assert _session_ledger_rows(tmp_path)[-1]["event_type"] == "CLOSE"


def test_expiry_day_target_hit_wins_before_noon_force_close(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(selected_contract_expiry="2026-06-25"),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    result = manager.process_session(
        tmp_path,
        session_date=date(2026, 6, 25),
        market_events=(
            _quote(
                session_date=date(2026, 6, 25),
                effective_timestamp=datetime(2026, 6, 25, 11, 50),
                bid=78,
                ask=79,
                ltp=78.5,
            ),
        ),
        evaluated_at=datetime(2026, 6, 25, 12, 0),
        expiry_governance=S23PaperExpiryGovernance(DeterministicExpiryCalendar()),
    )

    assert result.status is S23PaperPositionManagerStatus.PAPER_POSITION_FRESH_ENTRY_REQUIRED
    assert result.event.reason_code == "target_hit"
    assert result.event.exit_price == 80


def test_discovers_latest_open_position(tmp_path: Path) -> None:
    older_dir = tmp_path / "2026-06-20" / "old"
    newer_dir = tmp_path / "2026-06-22" / "new"
    _manager(tmp_path).open_from_live_decision(
        older_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 20, 9, 31),
    )
    _manager(tmp_path).open_from_live_decision(
        newer_dir,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )

    candidate = S23OpenPaperPositionDiscovery().find_latest_open_position((tmp_path,))

    assert candidate is not None
    assert candidate.state_directory == newer_dir


def _manager(
    tmp_path: Path,
    *,
    live_state_store=None,
) -> S23PaperPositionManager:
    return S23PaperPositionManager(
        ledger_store=S23PaperTradeLedgerStore(global_ledger_root=tmp_path / "_ledger"),
        live_state_store=live_state_store,
    )


def _session_ledger_rows(session_dir: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (session_dir / "paper_trade_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def _strategy_rule() -> StrategyRule:
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
        option_type=OptionType.PUT,
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


def _ready_summary(
    *,
    selected_contract_expiry: str = "2026-06-25",
) -> S23PaperTradeDecisionSummary:
    return S23PaperTradeDecisionSummary(
        status="READY",
        session_date=date(2026, 6, 22),
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
        quantity=75,
        selected_contract_symbol="NIFTY_20260625_24150_PE",
        selected_contract_expiry=selected_contract_expiry,
        selected_contract_strike=24150,
        selected_contract_option_type="PUT",
        selected_contract_ltp=194.25,
        selected_contract_oi=1000000,
        contract_selection_reason="test",
        contract_selection_failure_code=None,
        contract_selection_attempted_expiries=(selected_contract_expiry,),
        rejected_candidate_counts={},
        ranked_candidates=(),
        planned_entry_price=194.25,
        target_price=80,
        stoploss_price=320,
        fsl_price=None,
        source_workbook_rule="test",
        workbook_row_number=1,
    )


def _quote(
    *,
    session_date: date,
    effective_timestamp: datetime,
    bid: float,
    ask: float,
    ltp: float,
) -> SelectedContractQuoteEvent:
    return SelectedContractQuoteEvent(
        envelope=_envelope(
            event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            session_date=session_date,
            effective_timestamp=effective_timestamp,
        ),
        symbol="NIFTY_20260625_24150_PE",
        option_type=OptionType.PUT,
        strike=24150,
        expiry=date(2026, 6, 25),
        bid=bid,
        ask=ask,
        ltp=ltp,
        oi=1000000,
    )


def _bar(
    *,
    session_date: date,
    high: float,
    low: float,
    close: float,
    bar_time: time = time(10, 5),
) -> SelectedContractBarEvent:
    timestamp = datetime.combine(session_date, bar_time)
    return SelectedContractBarEvent(
        envelope=_envelope(
            event_type=PaperEventType.SELECTED_CONTRACT_BAR,
            session_date=session_date,
            effective_timestamp=timestamp,
        ),
        symbol="NIFTY_20260625_24150_PE",
        open=180,
        high=high,
        low=low,
        close=close,
        bar_start=timestamp,
        bar_end=timestamp,
        volume=1000,
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
        source_type="unit_test",
        source_id=f"unit:{event_type.value}:{effective_timestamp.isoformat()}",
        synthetic_fixture=True,
        normalized_by="unit-test",
    )
