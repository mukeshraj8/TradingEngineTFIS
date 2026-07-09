from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from tfis.domain import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment, StrategyExpiryPolicy, StrategyRule
from tfis.normalized_events import EventEnvelope, PaperEventType, SelectedContractQuoteEvent
from tfis.paper import (
    DeterministicExpiryCalendar,
    S23PaperExpiryGovernance,
    S23PaperLifecycleSupervisor,
    S23PaperLifecycleSupervisorContext,
    S23PaperOrderStateStore,
    S23PaperPositionManager,
)
from tfis.paper.live_decision import S23PaperTradeDecisionSummary


def test_supervisor_expires_previous_session_waiting_order(tmp_path: Path) -> None:
    order_store = S23PaperOrderStateStore()
    order_state, _state_path, _events_path = order_store.create_waiting_order_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 6, 22)),
        created_at=datetime(2026, 6, 22, 9, 30),
    )
    supervisor = S23PaperLifecycleSupervisor(order_store=order_store)
    context = S23PaperLifecycleSupervisorContext(
        session_directory=tmp_path,
        session_date=date(2026, 6, 23),
        trade_id="waiting-trade",
        selected_contract_symbol=order_state.selected_contract_symbol,
        order_state=order_state,
    )

    result = supervisor.expire_waiting_order_from_previous_session(
        context,
        evaluated_at=datetime(2026, 6, 23, 9, 20),
    )

    assert result is not None
    assert result.terminal is True
    assert result.final_step.status == "PAPER_ORDER_NOT_FILLED"
    assert result.final_step.reason_code == "paper_order_expired_untriggered_previous_session"
    assert result.context.order_state is not None
    assert result.context.order_state.status.value == "PAPER_ORDER_NOT_FILLED"


def test_supervisor_promotes_filled_order_into_open_position_and_processes_same_batch(tmp_path: Path) -> None:
    order_store = S23PaperOrderStateStore()
    order_state, _state_path, _events_path = order_store.create_waiting_order_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 6, 22)),
        created_at=datetime(2026, 6, 22, 9, 30),
    )
    supervisor = S23PaperLifecycleSupervisor(
        order_store=order_store,
        position_manager=S23PaperPositionManager(slippage_exit_points=0.0),
    )
    context = S23PaperLifecycleSupervisorContext(
        session_directory=tmp_path,
        session_date=date(2026, 6, 22),
        trade_id="waiting-trade",
        selected_contract_symbol=order_state.selected_contract_symbol,
        order_state=order_state,
    )

    result = supervisor.supervise(
        context,
        market_events=(
            _quote_event(
                session_date=date(2026, 6, 22),
                effective_timestamp=datetime(2026, 6, 22, 9, 31),
                symbol=order_state.selected_contract_symbol,
                ltp=194.0,
                bid=193.5,
                ask=194.5,
            ),
        ),
        evaluated_at=datetime(2026, 6, 22, 9, 31),
        watch_cutoff_time=time(15, 30),
        expiry_governance=S23PaperExpiryGovernance(DeterministicExpiryCalendar()),
        provenance_source_ids=("test-supervisor",),
    )

    assert result.terminal is False
    assert [step.status for step in result.steps] == [
        "PAPER_ORDER_FILLED",
        "PAPER_POSITION_OPENED",
        "PAPER_POSITION_HELD",
    ]
    assert result.context.position_state is not None
    assert result.context.order_state is None
    assert result.context.trade_id != "waiting-trade"


def test_supervisor_processes_open_position_terminal_exit(tmp_path: Path) -> None:
    manager = S23PaperPositionManager(slippage_exit_points=0.0)
    opened = manager.open_from_live_decision(
        tmp_path,
        strategy_rule=_strategy_rule(),
        decision=_ready_summary(session_date=date(2026, 6, 22)),
        opened_at=datetime(2026, 6, 22, 9, 31),
    )
    supervisor = S23PaperLifecycleSupervisor(position_manager=manager)
    context = S23PaperLifecycleSupervisorContext(
        session_directory=tmp_path,
        session_date=date(2026, 6, 22),
        trade_id="open-trade",
        selected_contract_symbol=opened.state.selected_contract_symbol,
        position_state=opened.state,
    )

    result = supervisor.supervise(
        context,
        market_events=(
            _quote_event(
                session_date=date(2026, 6, 22),
                effective_timestamp=datetime(2026, 6, 22, 9, 32),
                symbol=opened.state.selected_contract_symbol,
                ltp=70.0,
                bid=69.5,
                ask=70.5,
            ),
        ),
        evaluated_at=datetime(2026, 6, 22, 9, 32),
        watch_cutoff_time=time(15, 30),
        expiry_governance=S23PaperExpiryGovernance(DeterministicExpiryCalendar()),
        provenance_source_ids=("test-supervisor",),
    )

    assert result.terminal is True
    assert result.final_step.status == "PAPER_POSITION_FRESH_ENTRY_REQUIRED"
    assert result.final_step.reason_code == "target_hit"


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
        selected_contract_symbol="NIFTY_20260625_24150_PE",
        selected_contract_expiry="2026-06-25",
        selected_contract_strike=24150.0,
        selected_contract_option_type="PUT",
        selected_contract_ltp=194.25,
        selected_contract_oi=1000000.0,
        contract_selection_reason="test",
        contract_selection_failure_code=None,
        contract_selection_attempted_expiries=("2026-06-25",),
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


def _quote_event(
    *,
    session_date: date,
    effective_timestamp: datetime,
    symbol: str,
    ltp: float,
    bid: float,
    ask: float,
) -> SelectedContractQuoteEvent:
    return SelectedContractQuoteEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            session_date=session_date,
            effective_timestamp=effective_timestamp,
            captured_at=effective_timestamp,
            timezone="Asia/Kolkata",
            source_type="test",
            source_id="selected_contract_quote",
            synthetic_fixture=True,
            normalized_by="test",
        ),
        symbol=symbol,
        option_type=OptionType.PUT,
        strike=24150.0,
        expiry=date(2026, 6, 25),
        bid=bid,
        ask=ask,
        ltp=ltp,
        oi=1000.0,
        volume=100.0,
    )
