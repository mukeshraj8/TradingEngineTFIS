from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
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
    PaperHistoricalComparisonStatus,
    PaperSessionConfigEvent,
    PaperTradePlanEvent,
    S23PaperExecutionJournalWriter,
    S23PaperFillSimulator,
    S23PaperGuardrailSettings,
    S23PaperLifecycleSimulator,
    S23PaperReplayBundleManager,
    S23PaperSessionArtifactWriter,
    S23PaperSessionOrchestrator,
    SelectedContractBarEvent,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
    UnderlyingSnapshotEvent,
    compare_paper_session_to_historical,
    render_paper_historical_comparison_markdown,
)


IST = ZoneInfo("Asia/Kolkata")
BRANCH = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
CONTRACT_SYMBOL = "NIFTY_20260528_22400_PE"


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


def _monthly_status() -> MonthlyStatusInputEvent:
    return MonthlyStatusInputEvent(
        envelope=_envelope(PaperEventType.MONTHLY_STATUS_INPUT, effective_timestamp=_ts(9, 1)),
        monthly_status=MonthlyStatus.BEAR,
        status_source="monthly_status_engine",
        reference_date=date(2026, 5, 27),
        threshold_version="v1",
    )


def _paper_config() -> PaperSessionConfigEvent:
    return PaperSessionConfigEvent(
        envelope=_envelope(PaperEventType.PAPER_SESSION_CONFIG, effective_timestamp=_ts(9, 2)),
        strategy_code="S23",
        paper_mode_enabled=True,
        same_day_square_off_only=True,
        allow_recalculation=False,
        allow_current_day_fsl_trp=True,
        kill_switch_enabled=False,
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


def _snapshot(label: SnapshotLabel) -> UnderlyingSnapshotEvent:
    timestamp = {
        SnapshotLabel.AT_0915: _ts(9, 15),
        SnapshotLabel.ORPT: _ts(9, 24, 59),
        SnapshotLabel.RC: _ts(9, 29, 59),
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


def _underlying_quote() -> UnderlyingQuoteEvent:
    return UnderlyingQuoteEvent(
        envelope=_envelope(
            PaperEventType.UNDERLYING_QUOTE,
            effective_timestamp=_ts(9, 29, 59),
        ),
        symbol="NIFTY",
        ltp=22345.0,
        bid=22344.5,
        ask=22345.5,
        volume=1000.0,
    )


def _option_chain_snapshot(*, selected_symbol: str = CONTRACT_SYMBOL) -> OptionChainSnapshotEvent:
    contract = OptionChainContract(
        symbol=selected_symbol,
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
    symbol: str = CONTRACT_SYMBOL,
    effective_timestamp: datetime | None = None,
    bid: float | None = 198.0,
    ask: float | None = 201.0,
    ltp: float | None = 199.5,
) -> SelectedContractQuoteEvent:
    return SelectedContractQuoteEvent(
        envelope=_envelope(
            PaperEventType.SELECTED_CONTRACT_QUOTE,
            effective_timestamp=effective_timestamp or _ts(9, 29, 59),
        ),
        symbol=symbol,
        option_type=OptionType.PUT,
        strike=22400.0,
        expiry=date(2026, 5, 28),
        bid=bid,
        ask=ask,
        ltp=ltp,
        oi=1200.0,
        volume=250.0,
    )


def _selected_contract_bar(
    *,
    effective_timestamp: datetime,
    symbol: str = CONTRACT_SYMBOL,
    open: float | None = 200.0,
    high: float | None = 210.0,
    low: float | None = 190.0,
    close: float | None = 200.0,
) -> SelectedContractBarEvent:
    return SelectedContractBarEvent(
        envelope=_envelope(
            PaperEventType.SELECTED_CONTRACT_BAR,
            effective_timestamp=effective_timestamp,
            source_id=f"selected-contract-bar-{symbol}",
        ),
        symbol=symbol,
        open=open,
        high=high,
        low=low,
        close=close,
        bar_start=effective_timestamp - timedelta(minutes=1),
        bar_end=effective_timestamp,
        volume=250.0,
    )


def _trade_plan_input(
    *,
    planned_entry_price: float = 199.5,
    target_price: float = 80.0,
    stoploss_price: float = 320.0,
    start_strike: float | None = 21470.0,
    end_strike: float | None = 22601.0,
    ideal_premium: float | None = 271.2,
    minimum_premium: float | None = 203.4,
    source_workbook_rule: str = "AB6_OS_Z186",
    workbook_row_number: int = 186,
) -> PaperTradePlanEvent:
    return PaperTradePlanEvent(
        envelope=_envelope(
            PaperEventType.TRADE_PLAN_INPUT,
            effective_timestamp=_ts(9, 29, 59),
        ),
        strategy_branch=BRANCH,
        order_side="SELL",
        lots=2,
        quantity=100,
        planned_entry_price=planned_entry_price,
        target_price=target_price,
        stoploss_price=stoploss_price,
        order_reference_time=_ts(9, 24, 59),
        order_reference_label="ORPT",
        start_strike=start_strike,
        end_strike=end_strike,
        ideal_premium=ideal_premium,
        minimum_premium=minimum_premium,
        source_workbook_rule=source_workbook_rule,
        workbook_row_number=workbook_row_number,
        fsl_price=None,
    )


def _planned_snapshot(*, include_trade_plan: bool = True):
    orchestrator = S23PaperSessionOrchestrator()
    events = [
        _calendar_context(),
        _monthly_status(),
        _paper_config(),
        _cost_settings(),
        _snapshot(SnapshotLabel.AT_0915),
        _snapshot(SnapshotLabel.ORPT),
        _snapshot(SnapshotLabel.RC),
        _underlying_quote(),
        _option_chain_snapshot(),
        _selected_contract_quote(),
    ]
    if include_trade_plan:
        events.append(_trade_plan_input())
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)
    return orchestrator.finalize(now=_ts(9, 30, 10))


def _write_session(snapshot, root: Path, *, session_id: str, create_intent: bool = True) -> Path:
    session_writer = S23PaperSessionArtifactWriter(root / "paper_sessions")
    artifact_set = session_writer.write_snapshot(snapshot, session_id=session_id)
    session_dir = artifact_set.session_directory
    bundle_manager = S23PaperReplayBundleManager()
    bundle_manager.create_bundle(session_dir, created_at=_ts(9, 31, 0))
    if create_intent:
        journal_writer = S23PaperExecutionJournalWriter()
        journal_writer.write_from_session(
            session_dir,
            bundle_directory=session_dir,
            created_at=_ts(9, 30, 20),
        )
    return session_dir


def _write_historical_comparison_artifact(
    session_dir: Path,
    *,
    status: str = "MATCH",
    go_no_go: str = "GO: the persisted paper intent matches the expected historical trade-plan decision.",
    comparison_reason: str = "Paper and historical planning fields matched.",
) -> Path:
    path = session_dir / "paper_vs_historical_comparison.json"
    payload = {
        "artifact_version": 1,
        "status": status,
        "go_no_go": go_no_go,
        "comparison_reason": comparison_reason,
        "session_id": session_dir.name,
        "session_date": "2026-05-27",
        "strategy_code": "S23",
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _arm_execution_shell(
    session_dir: Path,
    *,
    comparison_status: str = "MATCH",
    comparison_reason: str = "Paper and historical planning fields matched.",
    go_no_go: str = "GO: the persisted paper intent matches the expected historical trade-plan decision.",
    guardrail_settings: S23PaperGuardrailSettings | None = None,
    created_at: datetime | None = None,
) -> None:
    comparison_path = _write_historical_comparison_artifact(
        session_dir,
        status=comparison_status,
        comparison_reason=comparison_reason,
        go_no_go=go_no_go,
    )
    writer = S23PaperExecutionJournalWriter(
        guardrail_settings=guardrail_settings
        or S23PaperGuardrailSettings(
            require_operator_review_completed_before_execution=True,
            operator_review_completed=True,
        )
    )
    writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=created_at or _ts(9, 30, 40),
    )
    return writer


def _dispatch_execution_shell(
    session_dir: Path,
    *,
    writer: S23PaperExecutionJournalWriter | None = None,
    created_at: datetime | None = None,
) -> S23PaperExecutionJournalWriter:
    active_writer = writer or S23PaperExecutionJournalWriter()
    active_writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=created_at or _ts(9, 30, 50),
    )
    return active_writer


def _handoff_execution_shell(
    session_dir: Path,
    *,
    writer: S23PaperExecutionJournalWriter | None = None,
    created_at: datetime | None = None,
) -> S23PaperExecutionJournalWriter:
    active_writer = writer or S23PaperExecutionJournalWriter()
    active_writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=created_at or _ts(9, 30, 55),
    )
    return active_writer


def _handoff_ready_session(root: Path, *, session_id: str) -> Path:
    session_dir = _write_session(_planned_snapshot(), root, session_id=session_id)
    writer = _arm_execution_shell(session_dir)
    writer = _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(session_dir, writer=writer)
    return session_dir


def _filled_session(
    root: Path,
    *,
    session_id: str,
    bid: float = 201.0,
    ask: float = 202.0,
    ltp: float = 201.5,
) -> Path:
    session_dir = _handoff_ready_session(root, session_id=session_id)
    simulator = S23PaperFillSimulator()
    simulator.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 30, 56),
                bid=bid,
                ask=ask,
                ltp=ltp,
            ),
        ),
        created_at=_ts(9, 30, 57),
    )
    return session_dir


def _lifecycle_closed_session(
    root: Path,
    *,
    session_id: str,
    fill_bid: float = 201.0,
    fill_ask: float = 202.0,
    fill_ltp: float = 201.5,
    market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    created_at: datetime,
) -> Path:
    session_dir = _filled_session(
        root,
        session_id=session_id,
        bid=fill_bid,
        ask=fill_ask,
        ltp=fill_ltp,
    )
    lifecycle = S23PaperLifecycleSimulator()
    lifecycle.simulate_from_session(
        session_dir,
        bundle_directory=session_dir,
        market_events=market_events,
        created_at=created_at,
    )
    return session_dir


def _historical_report(
    *,
    trade_date: str = "2026-05-27",
    selected_contract_symbol: str = CONTRACT_SYMBOL,
    entry_price: float = 199.5,
    target_price: float = 80.0,
    stoploss_price: float = 320.0,
    start_strike: float | None = 21470.0,
    end_strike: float | None = 22601.0,
    ideal_premium: float | None = 271.2,
    minimum_premium: float | None = 203.4,
    source_rule: str = "AB6_OS_Z186",
    workbook_row_number: int = 186,
    enable_current_day: bool = True,
    enable_recalc: bool = False,
    historical_exit_price: float = 120.0,
    historical_net_pnl_rupees: float = 3825.0,
    historical_exit_reason_code: str | None = None,
    historical_exit_timestamp: str | None = None,
    historical_exit_outcome: str | None = None,
) -> dict[str, object]:
    return {
        "mode": "historical",
        "strategy_path": "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "strategy_root": None,
        "cost_model": {
            "slippage_points_per_side": 1.0,
            "brokerage_points_per_trade": 0.5,
            "other_cost_points_per_trade": 0.5,
        },
        "input_metadata": {
            "datasets": {},
            "synthetic_fixture_data_used": True,
            "project_fixture_data_used": True,
        },
        "use_monthly_status_engine": True,
        "enable_s23_recalculation": enable_recalc,
        "enable_s23_current_day_fsl_trp": enable_current_day,
        "enable_option_chain_selection": True,
        "enable_contract_specific_lifecycle": False,
        "eod_policy": "square_off_at_close",
        "metrics": {
            "total_evaluations": 1,
            "accepted_candidates": 1,
            "rejected_candidates": 0,
            "entered_trades": 1,
            "target_hits": 1,
            "stoploss_hits": 0,
            "eod_square_off": 0,
            "no_entry": 0,
            "no_exit": 0,
            "total_net_pnl_points": 119.5,
            "total_net_pnl_rupees": 5975.0,
            "average_net_pnl_rupees": 5975.0,
            "max_drawdown_rupees": 0.0,
            "win_rate": 1.0,
            "loss_rate": 0.0,
            "expiry_day_candidates": 0,
            "expiry_day_exit_satisfied": 0,
            "expiry_day_exit_pending": 0,
            "rejection_reason_distribution": {},
        },
        "evaluations": [
            {
                "timestamp": f"{trade_date}T15:30:00",
                "strategy_code": "S23",
                "accepted": True,
                "rejection_reason": "Approved",
                "trade_outputs": {
                    "start_strike": start_strike,
                    "end_strike": end_strike,
                    "ideal_premium": ideal_premium,
                    "minimum_premium": minimum_premium,
                    "entry_price": entry_price,
                    "stoploss_price": stoploss_price,
                    "target_price": target_price,
                },
                "lifecycle_result": {
                    "exit_price": historical_exit_price,
                    "net_pnl_points": 76.5,
                    "net_pnl_rupees": historical_net_pnl_rupees,
                    "exit_reason_code": historical_exit_reason_code,
                    "exit_timestamp": historical_exit_timestamp,
                    "outcome": historical_exit_outcome,
                },
                "monthly_status": "BEAR",
                "monthly_status_trigger": "BEAR_A_THRESHOLD",
                "selected_branch_unique_codes": [BRANCH],
                "validation": {
                    "s23_current_day_fsl_trp": {
                        "applied": enable_current_day,
                        "branch_unique_code": BRANCH,
                        "base_trade_plan": {
                            "symbol": "NIFTY",
                            "option_type": "PUT",
                        },
                        "effective_trade_plan": {
                            "symbol": "NIFTY",
                            "option_type": "PUT",
                        },
                        "result": {
                            "row_number": workbook_row_number,
                            "source_rule": source_rule,
                        },
                    },
                    "option_chain_selection": {
                        "selected": True,
                        "selected_contract": {
                            "symbol": selected_contract_symbol,
                            "option_type": "PUT",
                            "strike": 22400,
                            "expiry": "2026-05-28",
                            "bid": 198.0,
                            "ask": 201.0,
                            "ltp": 199.5,
                            "oi": 1200,
                            "volume": 250,
                        },
                    },
                },
            }
        ],
        "monthly_status_skips": [],
    }


def _write_historical_report(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_exact_match_returns_match(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="match-session")
    writer = _arm_execution_shell(session_dir)
    writer = _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(session_dir, writer=writer)
    historical_report = _write_historical_report(
        tmp_path,
        "historical_match.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MATCH
    assert summary.paper_execution_shell_status == "EXECUTION_ARMED"
    assert summary.paper_dispatch_shell_status == "ORDER_INTENT_DISPATCHED"
    assert summary.paper_handoff_shell_status == "PAPER_EXECUTION_HANDOFF_READY"
    assert summary.matched_historical_trade_key is not None
    assert summary.bundle_valid is True
    assert "GO:" in render_paper_historical_comparison_markdown(summary)


def test_handoff_shell_status_is_included_when_ready(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="dispatch-match")
    writer = _arm_execution_shell(session_dir)
    _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(session_dir, writer=writer)
    historical_report = _write_historical_report(
        tmp_path,
        "historical_dispatch_match.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MATCH
    assert summary.paper_execution_shell_status == "EXECUTION_ARMED"
    assert summary.paper_dispatch_shell_status == "ORDER_INTENT_DISPATCHED"
    assert summary.paper_handoff_shell_status == "PAPER_EXECUTION_HANDOFF_READY"


def test_numeric_tolerance_allows_near_match(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="tolerance-session")
    writer = _arm_execution_shell(session_dir)
    writer = _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(session_dir, writer=writer)
    historical_report = _write_historical_report(
        tmp_path,
        "historical_tolerance.json",
        _historical_report(entry_price=199.505),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
        numeric_tolerance=0.01,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MATCH
    entry_delta = next(
        item for item in summary.field_comparisons if item.field_name == "entry_price"
    )
    assert entry_delta.matched is True


def test_selected_contract_mismatch_returns_mismatch(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="contract-mismatch")
    writer = _arm_execution_shell(session_dir)
    writer = _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(session_dir, writer=writer)
    historical_report = _write_historical_report(
        tmp_path,
        "historical_contract_mismatch.json",
        _historical_report(selected_contract_symbol="NIFTY_20260528_22500_PE"),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MISMATCH
    mismatch = next(
        item
        for item in summary.field_comparisons
        if item.field_name == "selected_contract_symbol"
    )
    assert mismatch.matched is False


def test_missing_historical_trade_returns_uncomparable(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="missing-historical")
    writer = _arm_execution_shell(session_dir)
    writer = _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(session_dir, writer=writer)
    historical_report = _write_historical_report(
        tmp_path,
        "historical_missing_trade.json",
        _historical_report(trade_date="2026-05-26"),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.UNCOMPARABLE
    assert summary.matched_historical_trade_key is None


def test_paper_session_without_intent_ready_is_uncomparable(tmp_path: Path) -> None:
    session_dir = _write_session(
        _planned_snapshot(),
        tmp_path,
        session_id="not-intent-ready",
        create_intent=False,
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_for_uncomparable.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.UNCOMPARABLE
    assert summary.paper_intent_status is None


def test_comparison_uses_persisted_intent_when_summary_intent_status_missing(
    tmp_path: Path,
) -> None:
    session_dir = _handoff_ready_session(
        tmp_path,
        session_id="intent-status-fallback",
    )
    execution_summary_path = session_dir / "execution_summary.json"
    execution_summary = json.loads(execution_summary_path.read_text(encoding="utf-8"))
    execution_summary.pop("intent_status", None)
    execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_intent_status_fallback.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.paper_intent_status == "INTENT_READY"
    assert summary.status is PaperHistoricalComparisonStatus.MATCH


def test_comparison_uses_staged_shell_artifacts_when_summary_fields_missing(
    tmp_path: Path,
) -> None:
    session_dir = _handoff_ready_session(
        tmp_path,
        session_id="comparison-shell-fallback",
    )
    execution_summary_path = session_dir / "execution_summary.json"
    execution_summary = json.loads(execution_summary_path.read_text(encoding="utf-8"))
    execution_summary.pop("historical_comparison_status", None)
    execution_summary.pop("historical_comparison_go_no_go", None)
    execution_summary.pop("historical_comparison_reason", None)
    execution_summary.pop("terminal_reason_code", None)
    execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_shell_fallback.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.historical_comparison_status_used == "MATCH"
    assert summary.historical_comparison_go_no_go_used is not None
    assert summary.historical_comparison_reason_used is not None
    assert summary.status is PaperHistoricalComparisonStatus.MATCH


def test_planning_match_but_execution_blocked_is_partial_match(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="execution-blocked")
    _arm_execution_shell(
        session_dir,
        guardrail_settings=S23PaperGuardrailSettings(
            require_operator_review_completed_before_execution=True,
            operator_review_completed=False,
        ),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_execution_blocked.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.PARTIAL_MATCH
    assert summary.paper_execution_shell_status == "EXECUTION_BLOCKED"
    assert summary.execution_shell_guardrail_code == "operator_review_incomplete"


def test_planning_match_but_dispatch_blocked_is_partial_match(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="dispatch-blocked")
    writer = _arm_execution_shell(session_dir)
    _dispatch_execution_shell(
        session_dir,
        writer=writer,
        created_at=_ts(9, 40, 0),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_dispatch_blocked.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.PARTIAL_MATCH
    assert summary.paper_dispatch_shell_status == "ORDER_INTENT_DISPATCH_BLOCKED"
    assert summary.execution_shell_guardrail_code == "selected_contract_stale_before_execution"


def test_planning_match_but_handoff_blocked_is_partial_match(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="handoff-blocked")
    writer = _arm_execution_shell(session_dir)
    writer = _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(
        session_dir,
        writer=writer,
        created_at=_ts(9, 40, 0),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_handoff_blocked.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.PARTIAL_MATCH
    assert summary.paper_handoff_shell_status == "PAPER_EXECUTION_HANDOFF_BLOCKED"
    assert summary.execution_shell_guardrail_code == "selected_contract_stale_before_execution"


def test_workbook_row_and_source_rule_mismatch_is_reported(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="row-mismatch")
    writer = _arm_execution_shell(session_dir)
    writer = _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(session_dir, writer=writer)
    historical_report = _write_historical_report(
        tmp_path,
        "historical_row_mismatch.json",
        _historical_report(
            source_rule="AB6_OS_Z185",
            workbook_row_number=185,
        ),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MISMATCH
    field_names = {item.field_name for item in summary.field_comparisons if not item.matched}
    assert "source_rule" in field_names
    assert "workbook_row_number" in field_names


def test_missing_optional_premium_fields_yields_partial_match(tmp_path: Path) -> None:
    # Build a planned session that intentionally omits the optional
    # strike/premium metadata while keeping the core prices intact.
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        _calendar_context(),
        _monthly_status(),
        _paper_config(),
        _cost_settings(),
        _snapshot(SnapshotLabel.AT_0915),
        _snapshot(SnapshotLabel.ORPT),
        _snapshot(SnapshotLabel.RC),
        _underlying_quote(),
        _option_chain_snapshot(),
        _selected_contract_quote(),
        _trade_plan_input(
            start_strike=None,
            end_strike=None,
            ideal_premium=None,
            minimum_premium=None,
        ),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)
    session_dir = _write_session(
        orchestrator.finalize(now=_ts(9, 30, 10)),
        tmp_path,
        session_id="partial-match",
    )
    writer = _arm_execution_shell(session_dir)
    writer = _dispatch_execution_shell(session_dir, writer=writer)
    _handoff_execution_shell(session_dir, writer=writer)
    historical_report = _write_historical_report(
        tmp_path,
        "historical_partial_match.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.PARTIAL_MATCH
    missing_fields = {
        item.field_name for item in summary.field_comparisons if not item.matched
    }
    assert "start_strike" in missing_fields
    assert "ideal_premium" in missing_fields


def test_missing_execution_summary_is_uncomparable(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="missing-execution-summary")
    (session_dir / "execution_summary.json").unlink()
    historical_report = _write_historical_report(
        tmp_path,
        "historical_missing_execution_summary.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.UNCOMPARABLE
    assert "missing_execution_summary" in summary.warnings


def test_invalid_replay_bundle_status_surfaces_in_comparison(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="invalid-replay-bundle")
    comparison_path = _write_historical_comparison_artifact(session_dir)
    writer = S23PaperExecutionJournalWriter()
    payload = json.loads((session_dir / "paper_order_plan.json").read_text(encoding="utf-8"))
    payload["order_plan"]["planned_entry_price"] = 188.0
    (session_dir / "paper_order_plan.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_invalid_bundle.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.UNCOMPARABLE
    assert summary.bundle_valid is False
    assert summary.execution_shell_guardrail_code == "session_artifact_hash_mismatch"


def test_markdown_contains_execution_shell_readiness_section(tmp_path: Path) -> None:
    session_dir = _write_session(_planned_snapshot(), tmp_path, session_id="markdown-session")
    _arm_execution_shell(
        session_dir,
        guardrail_settings=S23PaperGuardrailSettings(
            require_operator_review_completed_before_execution=True,
            operator_review_completed=False,
        ),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_markdown.json",
        _historical_report(),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )
    markdown = render_paper_historical_comparison_markdown(summary)

    assert "## Execution-Shell Readiness" in markdown
    assert "operator_review_incomplete" in markdown
    assert "Dispatch Shell Status" in markdown
    assert "Handoff Shell Status" in markdown
    assert "No order was placed, no fill was simulated, no position was opened" in markdown


def test_exact_same_day_lifecycle_match_returns_match(tmp_path: Path) -> None:
    session_dir = _lifecycle_closed_session(
        tmp_path,
        session_id="lifecycle-exact-match",
        fill_bid=200.5,
        fill_ask=201.5,
        fill_ltp=201.0,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_lifecycle_exact_match.json",
        _historical_report(
            entry_price=199.5,
            historical_exit_price=81.0,
            historical_net_pnl_rupees=11810.0,
            historical_exit_reason_code="target_hit",
            historical_exit_timestamp="2026-05-27T09:31:30+05:30",
            historical_exit_outcome="TARGET_HIT",
        ),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MATCH
    assert summary.lifecycle_comparable is True
    assert summary.paper_fill_price == 199.5
    assert summary.paper_exit_price == 81.0
    assert summary.lifecycle_acceptable_drift_count == 0


def test_acceptable_lifecycle_drift_returns_match_with_acceptable_drift(tmp_path: Path) -> None:
    session_dir = _lifecycle_closed_session(
        tmp_path,
        session_id="lifecycle-acceptable-drift",
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_lifecycle_acceptable_drift.json",
        _historical_report(
            entry_price=199.5,
            historical_exit_price=82.0,
            historical_net_pnl_rupees=11710.0,
            historical_exit_reason_code="target_hit",
            historical_exit_timestamp="2026-05-27T09:32:00+05:30",
            historical_exit_outcome="TARGET_HIT",
        ),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MATCH_WITH_ACCEPTABLE_DRIFT
    assert summary.lifecycle_acceptable_drift_count >= 1
    drift_fields = {
        item.field_name
        for item in summary.lifecycle_field_comparisons
        if item.acceptable_drift
    }
    assert "fill_price_vs_historical_entry_price" in drift_fields
    assert "exit_price" in drift_fields
    assert "net_pnl_rupees" in drift_fields


def test_exit_reason_mismatch_is_blocker(tmp_path: Path) -> None:
    session_dir = _lifecycle_closed_session(
        tmp_path,
        session_id="lifecycle-exit-reason-mismatch",
        fill_bid=200.5,
        fill_ask=201.5,
        fill_ltp=201.0,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_lifecycle_reason_mismatch.json",
        _historical_report(
            entry_price=199.5,
            historical_exit_price=322.0,
            historical_net_pnl_rupees=-12290.0,
            historical_exit_reason_code="stoploss_or_fsl_hit",
            historical_exit_timestamp="2026-05-27T09:31:30+05:30",
            historical_exit_outcome="STOPLOSS_OR_FSL_HIT",
        ),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MISMATCH
    mismatch_fields = {
        item.field_name
        for item in summary.lifecycle_field_comparisons
        if not item.matched and item.severity.value == "blocker"
    }
    assert "exit_reason_code" in mismatch_fields
    assert "exit_outcome" in mismatch_fields


def test_missing_historical_lifecycle_artifact_is_uncomparable(tmp_path: Path) -> None:
    session_dir = _lifecycle_closed_session(
        tmp_path,
        session_id="lifecycle-uncomparable",
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )
    payload = _historical_report()
    payload["evaluations"][0].pop("lifecycle_result", None)
    historical_report = _write_historical_report(
        tmp_path,
        "historical_lifecycle_missing.json",
        payload,
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.UNCOMPARABLE
    assert summary.lifecycle_comparable is False


def test_eod_square_off_comparison_is_supported(tmp_path: Path) -> None:
    session_dir = _lifecycle_closed_session(
        tmp_path,
        session_id="lifecycle-eod",
        fill_bid=200.5,
        fill_ask=201.5,
        fill_ltp=201.0,
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(15, 28, 30),
                bid=149.0,
                ask=150.0,
                ltp=149.5,
            ),
        ),
        created_at=_ts(15, 28, 31),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_lifecycle_eod.json",
        _historical_report(
            entry_price=199.5,
            historical_exit_price=151.0,
            historical_net_pnl_rupees=4810.0,
            historical_exit_reason_code="eod_square_off",
            historical_exit_timestamp="2026-05-27T15:28:30+05:30",
            historical_exit_outcome="EOD_SQUARE_OFF",
        ),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MATCH
    assert summary.paper_lifecycle_status == "PAPER_EOD_SQUARE_OFF"
    assert summary.paper_exit_reason_code == "eod_square_off"


def test_same_bar_conflict_comparison_is_supported(tmp_path: Path) -> None:
    session_dir = _lifecycle_closed_session(
        tmp_path,
        session_id="lifecycle-same-bar-conflict",
        fill_bid=200.5,
        fill_ask=201.5,
        fill_ltp=201.0,
        market_events=(
            _selected_contract_bar(
                effective_timestamp=_ts(10, 0, 0),
                high=330.0,
                low=70.0,
                close=200.0,
            ),
        ),
        created_at=_ts(10, 0, 1),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_lifecycle_same_bar_conflict.json",
        _historical_report(
            entry_price=199.5,
            historical_exit_price=321.0,
            historical_net_pnl_rupees=-12190.0,
            historical_exit_reason_code="same_bar_target_stop_conflict_stoploss_wins",
            historical_exit_timestamp="2026-05-27T10:00:00+05:30",
            historical_exit_outcome="STOPLOSS_OR_FSL_HIT",
        ),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )

    assert summary.status is PaperHistoricalComparisonStatus.MATCH
    assert summary.paper_exit_reason_code == "same_bar_target_stop_conflict_stoploss_wins"


def test_markdown_contains_lifecycle_parity_and_pnl_drift_sections(tmp_path: Path) -> None:
    session_dir = _lifecycle_closed_session(
        tmp_path,
        session_id="lifecycle-markdown",
        market_events=(
            _selected_contract_quote(
                effective_timestamp=_ts(9, 31, 30),
                bid=78.0,
                ask=79.0,
                ltp=78.5,
            ),
        ),
        created_at=_ts(9, 31, 31),
    )
    historical_report = _write_historical_report(
        tmp_path,
        "historical_lifecycle_markdown.json",
        _historical_report(
            entry_price=199.5,
            historical_exit_price=82.0,
            historical_net_pnl_rupees=11710.0,
            historical_exit_reason_code="target_hit",
            historical_exit_timestamp="2026-05-27T09:32:00+05:30",
            historical_exit_outcome="TARGET_HIT",
        ),
    )

    summary = compare_paper_session_to_historical(
        session_dir,
        historical_report,
        bundle_directory=session_dir,
    )
    markdown = render_paper_historical_comparison_markdown(summary)

    assert "## Lifecycle Parity" in markdown
    assert "## P&L Drift" in markdown
    assert "MATCH_WITH_ACCEPTABLE_DRIFT" in markdown
    assert "same-day" in markdown.lower()
