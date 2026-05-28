from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.paper import (
    CalendarContextEvent,
    CostSlippageSettingsEvent,
    EventEnvelope,
    MonthlyStatusInputEvent,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    PaperReadinessStatus,
    PaperSessionConfigEvent,
    PaperSessionState,
    S23PaperGuardrailSettings,
    S23PaperSessionOrchestrator,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
    UnderlyingSnapshotEvent,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, 27, hour, minute, second, tzinfo=IST)


def _envelope(
    event_type: PaperEventType,
    *,
    effective_timestamp: datetime | None = None,
    source_id: str | None = None,
) -> EventEnvelope:
    effective = effective_timestamp or _ts(9, 15)
    return EventEnvelope(
        event_type=event_type,
        session_date=effective.date(),
        effective_timestamp=effective,
        captured_at=effective + timedelta(seconds=1),
        timezone="Asia/Kolkata",
        source_type="paper_fixture",
        source_id=source_id or f"{event_type.value.lower()}-source",
        synthetic_fixture=True,
        normalized_by="test-fixture",
    )


def _calendar_context() -> CalendarContextEvent:
    return CalendarContextEvent(
        envelope=_envelope(PaperEventType.CALENDAR_CONTEXT, effective_timestamp=_ts(9, 0)),
        is_holiday=False,
        is_expiry_day=False,
        weekly_expiry=date(2026, 5, 28),
        market_open=time(9, 15),
        market_close=time(15, 30),
    )


def _monthly_status(status: MonthlyStatus = MonthlyStatus.BULL) -> MonthlyStatusInputEvent:
    return MonthlyStatusInputEvent(
        envelope=_envelope(PaperEventType.MONTHLY_STATUS_INPUT, effective_timestamp=_ts(9, 1)),
        monthly_status=status,
        status_source="monthly_status_engine",
        reference_date=date(2026, 5, 27),
        threshold_version="v1",
    )


def _paper_config(
    *,
    allow_recalculation: bool = False,
    allow_current_day_fsl_trp: bool = False,
    same_day_square_off_only: bool = True,
    kill_switch_enabled: bool = False,
) -> PaperSessionConfigEvent:
    return PaperSessionConfigEvent(
        envelope=_envelope(PaperEventType.PAPER_SESSION_CONFIG, effective_timestamp=_ts(9, 2)),
        strategy_code="S23",
        paper_mode_enabled=True,
        same_day_square_off_only=same_day_square_off_only,
        allow_recalculation=allow_recalculation,
        allow_current_day_fsl_trp=allow_current_day_fsl_trp,
        kill_switch_enabled=kill_switch_enabled,
        operator_id="operator-1",
    )


def _cost_settings() -> CostSlippageSettingsEvent:
    return CostSlippageSettingsEvent(
        envelope=_envelope(PaperEventType.COST_SLIPPAGE_SETTINGS, effective_timestamp=_ts(9, 3)),
        brokerage_per_lot=20.0,
        slippage_entry_points=1.0,
        slippage_exit_points=1.0,
        spread_buffer_policy="bid_ask_guard",
        version_label="paper-cost-v1",
    )


def _underlying_quote(*, effective_timestamp: datetime | None = None) -> UnderlyingQuoteEvent:
    return UnderlyingQuoteEvent(
        envelope=_envelope(
            PaperEventType.UNDERLYING_QUOTE,
            effective_timestamp=effective_timestamp or _ts(9, 24, 59),
        ),
        symbol="NIFTY",
        ltp=22345.0,
        bid=22344.5,
        ask=22345.5,
        volume=1000.0,
    )


def _snapshot(label: SnapshotLabel) -> UnderlyingSnapshotEvent:
    timestamp = {
        SnapshotLabel.AT_0915: _ts(9, 15),
        SnapshotLabel.ORPT: _ts(9, 24, 59),
        SnapshotLabel.RC: _ts(9, 29, 59),
        SnapshotLabel.EOD: _ts(15, 0),
        SnapshotLabel.PRE_OPEN: _ts(9, 10),
    }[label]
    return UnderlyingSnapshotEvent(
        envelope=_envelope(PaperEventType.UNDERLYING_SNAPSHOT, effective_timestamp=timestamp),
        snapshot_label=label,
        open=22320.0,
        high=22380.0,
        low=22310.0,
        close=22350.0,
        bar_start=timestamp - timedelta(minutes=1),
        bar_end=timestamp,
        complete=True,
    )


def _option_chain_snapshot() -> OptionChainSnapshotEvent:
    contract = OptionChainContract(
        symbol="NIFTY_20260528_22400_PE",
        option_type=OptionType.PUT,
        strike=22400.0,
        expiry=date(2026, 5, 28),
        bid=198.0,
        ask=201.0,
        ltp=199.5,
        oi=1200.0,
        volume=250.0,
    )
    return OptionChainSnapshotEvent(
        envelope=_envelope(PaperEventType.OPTION_CHAIN_SNAPSHOT, effective_timestamp=_ts(9, 24, 59)),
        underlying_symbol="NIFTY",
        expiry=date(2026, 5, 28),
        contracts=(contract,),
    )


def _selected_contract_quote(
    *,
    effective_timestamp: datetime | None = None,
) -> SelectedContractQuoteEvent:
    return SelectedContractQuoteEvent(
        envelope=_envelope(
            PaperEventType.SELECTED_CONTRACT_QUOTE,
            effective_timestamp=effective_timestamp or _ts(9, 24, 59),
        ),
        symbol="NIFTY_20260528_22400_PE",
        option_type=OptionType.PUT,
        strike=22400.0,
        expiry=date(2026, 5, 28),
        bid=198.0,
        ask=201.0,
        ltp=199.5,
        oi=1200.0,
        volume=250.0,
    )


def _ingest_current_day_happy_path(orchestrator: S23PaperSessionOrchestrator) -> None:
    events = (
        _calendar_context(),
        _monthly_status(),
        _paper_config(allow_current_day_fsl_trp=True),
        _cost_settings(),
        _snapshot(SnapshotLabel.AT_0915),
        _snapshot(SnapshotLabel.ORPT),
        _snapshot(SnapshotLabel.RC),
        _underlying_quote(effective_timestamp=_ts(9, 29, 59)),
        _option_chain_snapshot(),
        _selected_contract_quote(effective_timestamp=_ts(9, 29, 59)),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)


def test_happy_path_reaches_order_planned() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    _ingest_current_day_happy_path(orchestrator)

    result = orchestrator.finalize(now=_ts(9, 30, 10))

    assert result.state is PaperSessionState.ORDER_PLANNED
    assert result.order_plan is not None
    assert result.order_plan.strategy_code == "S23"
    assert result.order_plan.selected_contract_symbol == "NIFTY_20260528_22400_PE"
    assert result.order_plan.required_snapshot_labels == (
        SnapshotLabel.AT_0915,
        SnapshotLabel.ORPT,
        SnapshotLabel.RC,
    )
    assert result.manifest is not None
    assert result.manifest.readiness_status is PaperReadinessStatus.READY
    assert result.latest_guardrail_decision is None


def test_monthly_status_unknown_reaches_no_trade() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        _calendar_context(),
        _monthly_status(MonthlyStatus.UNKNOWN),
        _paper_config(),
        _cost_settings(),
    )
    for event in events:
        snapshot = orchestrator.ingest_event(event, now=event.envelope.captured_at)

    assert snapshot.state is PaperSessionState.NO_TRADE
    assert snapshot.latest_validation_result is not None
    assert "monthly_status_unknown" in snapshot.latest_validation_result.no_trade_reasons
    assert snapshot.latest_guardrail_decision is not None
    assert snapshot.latest_guardrail_decision.code == "monthly_status_unknown"


def test_missing_0915_snapshot_with_current_day_overlay_reaches_no_trade() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        _calendar_context(),
        _monthly_status(),
        _paper_config(allow_current_day_fsl_trp=True),
        _cost_settings(),
        _snapshot(SnapshotLabel.ORPT),
        _snapshot(SnapshotLabel.RC),
        _underlying_quote(),
        _option_chain_snapshot(),
        _selected_contract_quote(),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)

    result = orchestrator.finalize(now=_ts(9, 30, 10))

    assert result.state is PaperSessionState.NO_TRADE
    assert result.latest_validation_result is not None
    assert "missing_snapshot_0915" in result.latest_validation_result.no_trade_reasons
    assert result.latest_guardrail_decision is not None
    assert result.latest_guardrail_decision.code == "missing_snapshot_0915"


def test_requested_multi_session_continuation_reaches_aborted_in_current_runtime() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        _calendar_context(),
        _monthly_status(),
        _paper_config(same_day_square_off_only=False),
        _cost_settings(),
    )
    for event in events:
        snapshot = orchestrator.ingest_event(event, now=event.envelope.captured_at)

    assert snapshot.state is PaperSessionState.ABORTED
    assert snapshot.latest_validation_result is not None
    assert "unsupported_continuation_path" in snapshot.latest_validation_result.abort_reasons
    assert snapshot.latest_guardrail_decision is not None
    assert snapshot.latest_guardrail_decision.code == "unsupported_continuation_path"


def test_stale_event_is_rejected_and_audited() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    snapshot = orchestrator.ingest_event(
        _underlying_quote(effective_timestamp=_ts(9, 20, 0)),
        now=_ts(9, 25, 10),
    )

    assert snapshot.state is PaperSessionState.ABORTED
    assert snapshot.latest_validation_result is not None
    assert "stale_ingest_quote" in snapshot.latest_validation_result.abort_reasons
    assert snapshot.audit_events[-1].reason == "ingest_guardrail_failed"
    assert snapshot.audit_events[-1].guardrail_code == "stale_ingest_quote"


def test_duplicate_event_is_rejected_and_audited() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    first = _calendar_context()
    second = _calendar_context()

    orchestrator.ingest_event(first, now=first.envelope.captured_at)
    result = orchestrator.ingest_event(second, now=second.envelope.captured_at)

    assert result.state is PaperSessionState.ABORTED
    assert result.latest_validation_result is not None
    assert "duplicate_calendar_context" in result.latest_validation_result.abort_reasons
    assert result.audit_events[-1].terminal_code == "duplicate_calendar_context"
    assert result.audit_events[-1].guardrail_code == "duplicate_calendar_context"


def test_global_paper_disabled_blocks_planning() -> None:
    orchestrator = S23PaperSessionOrchestrator(
        guardrail_settings=S23PaperGuardrailSettings(
            global_paper_trading_enabled=False
        )
    )
    _ingest_current_day_happy_path(orchestrator)

    result = orchestrator.finalize(now=_ts(9, 30, 10))

    assert result.state is PaperSessionState.ABORTED
    assert result.latest_guardrail_decision is not None
    assert result.latest_guardrail_decision.code == "global_paper_trading_disabled"
    assert result.audit_events[-1].guardrail_code == "global_paper_trading_disabled"


def test_s23_paper_disabled_blocks_planning() -> None:
    orchestrator = S23PaperSessionOrchestrator(
        guardrail_settings=S23PaperGuardrailSettings(
            s23_paper_enabled=False
        )
    )
    _ingest_current_day_happy_path(orchestrator)

    result = orchestrator.finalize(now=_ts(9, 30, 10))

    assert result.state is PaperSessionState.NO_TRADE
    assert result.latest_guardrail_decision is not None
    assert result.latest_guardrail_decision.code == "s23_paper_disabled"
    assert result.audit_events[-1].guardrail_code == "s23_paper_disabled"


def test_manual_abort_creates_aborted() -> None:
    orchestrator = S23PaperSessionOrchestrator(
        guardrail_settings=S23PaperGuardrailSettings(
            manual_operator_abort=True,
            manual_abort_reason="Operator halted the S23 paper session.",
        )
    )
    _ingest_current_day_happy_path(orchestrator)

    result = orchestrator.finalize(now=_ts(9, 30, 10))

    assert result.state is PaperSessionState.ABORTED
    assert result.latest_guardrail_decision is not None
    assert result.latest_guardrail_decision.code == "manual_operator_abort"
    assert result.latest_guardrail_decision.message == "Operator halted the S23 paper session."


def test_duplicate_order_planning_is_blocked() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    _ingest_current_day_happy_path(orchestrator)

    first = orchestrator.finalize(now=_ts(9, 30, 10))
    second = orchestrator.finalize(now=_ts(9, 30, 11))

    assert first.state is PaperSessionState.ORDER_PLANNED
    assert second.state is PaperSessionState.ORDER_PLANNED
    assert second.latest_guardrail_decision is not None
    assert second.latest_guardrail_decision.code == "max_planned_orders_per_session_exceeded"
    assert second.audit_events[-1].reason == "session_finalize_rejected_after_terminal_state"


def test_selected_contract_missing_creates_no_trade() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        _calendar_context(),
        _monthly_status(),
        _paper_config(),
        _cost_settings(),
        _snapshot(SnapshotLabel.ORPT),
        _underlying_quote(),
        _option_chain_snapshot(),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)

    result = orchestrator.finalize(now=_ts(9, 25, 30))

    assert result.state is PaperSessionState.NO_TRADE
    assert result.latest_guardrail_decision is not None
    assert result.latest_guardrail_decision.code == "missing_selected_contract_quote"
    assert result.audit_events[-1].guardrail_code == "missing_selected_contract_quote"


def test_option_chain_missing_creates_no_trade() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        _calendar_context(),
        _monthly_status(),
        _paper_config(),
        _cost_settings(),
        _snapshot(SnapshotLabel.ORPT),
        _underlying_quote(),
        _selected_contract_quote(),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)

    result = orchestrator.finalize(now=_ts(9, 25, 30))

    assert result.state is PaperSessionState.NO_TRADE
    assert result.latest_guardrail_decision is not None
    assert result.latest_guardrail_decision.code == "missing_option_chain_snapshot"
    assert result.audit_events[-1].guardrail_code == "missing_option_chain_snapshot"


def test_stale_data_guardrail_blocks_planning() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        _calendar_context(),
        _monthly_status(),
        _paper_config(),
        _cost_settings(),
        _snapshot(SnapshotLabel.ORPT),
        _underlying_quote(effective_timestamp=_ts(9, 24, 59)),
        _option_chain_snapshot(),
        _selected_contract_quote(effective_timestamp=_ts(9, 24, 59)),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)

    result = orchestrator.finalize(now=_ts(9, 26, 10))

    assert result.state is PaperSessionState.NO_TRADE
    assert result.latest_guardrail_decision is not None
    assert result.latest_guardrail_decision.code == "stale_underlying_quote"
    assert result.audit_events[-1].guardrail_code == "stale_underlying_quote"


def test_audit_transitions_are_deterministic() -> None:
    orchestrator = S23PaperSessionOrchestrator()
    _ingest_current_day_happy_path(orchestrator)
    result = orchestrator.finalize(now=_ts(9, 30, 10))

    state_pairs = [
        (entry.previous_state, entry.new_state, entry.reason)
        for entry in result.audit_events
    ]

    assert state_pairs == [
        (
            PaperSessionState.NOT_STARTED,
            PaperSessionState.PRE_MARKET_READY,
            "pre_market_inputs_ready",
        ),
        (
            PaperSessionState.PRE_MARKET_READY,
            PaperSessionState.WAITING_FOR_0915,
            "awaiting_0915_snapshot",
        ),
        (
            PaperSessionState.WAITING_FOR_0915,
            PaperSessionState.WAITING_FOR_ORPT,
            "awaiting_orpt_snapshot",
        ),
        (
            PaperSessionState.WAITING_FOR_ORPT,
            PaperSessionState.WAITING_FOR_RC,
            "awaiting_rc_snapshot",
        ),
        (
            PaperSessionState.WAITING_FOR_RC,
            PaperSessionState.DECISION_READY,
            "planning_inputs_ready",
        ),
        (
            PaperSessionState.DECISION_READY,
            PaperSessionState.ORDER_PLANNED,
            "paper_order_plan_created",
        ),
    ]
