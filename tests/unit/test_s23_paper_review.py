from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.paper import (
    CalendarContextEvent,
    CostSlippageSettingsEvent,
    EventEnvelope,
    MonthlyStatusInputEvent,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    PaperSessionConfigEvent,
    PaperTradePlanEvent,
    S23PaperGuardrailSettings,
    S23PaperExecutionJournalWriter,
    S23PaperReplayBundleManager,
    S23PaperReviewError,
    S23PaperSessionArtifactWriter,
    S23PaperSessionOrchestrator,
    S23PaperSessionReviewer,
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
) -> PaperSessionConfigEvent:
    return PaperSessionConfigEvent(
        envelope=_envelope(PaperEventType.PAPER_SESSION_CONFIG, effective_timestamp=_ts(9, 2)),
        strategy_code="S23",
        paper_mode_enabled=True,
        same_day_square_off_only=same_day_square_off_only,
        allow_recalculation=allow_recalculation,
        allow_current_day_fsl_trp=allow_current_day_fsl_trp,
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


def _selected_contract_quote(*, effective_timestamp: datetime | None = None) -> SelectedContractQuoteEvent:
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


def _trade_plan_input() -> PaperTradePlanEvent:
    return PaperTradePlanEvent(
        envelope=_envelope(
            PaperEventType.TRADE_PLAN_INPUT,
            effective_timestamp=_ts(9, 29, 59),
        ),
        strategy_branch="S23_BEAR_PUT",
        order_side="SELL",
        lots=2,
        quantity=100,
        planned_entry_price=199.5,
        target_price=80.0,
        stoploss_price=320.0,
        order_reference_time=_ts(9, 24, 59),
        order_reference_label="ORPT",
        source_workbook_rule="AB6_OS_Z184",
        workbook_row_number=184,
        fsl_price=352.0,
    )


def _planned_snapshot():
    orchestrator = S23PaperSessionOrchestrator()
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
    return orchestrator.finalize(now=_ts(9, 30, 10))


def _planned_trade_snapshot():
    orchestrator = S23PaperSessionOrchestrator()
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
        _trade_plan_input(),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)
    return orchestrator.finalize(now=_ts(9, 30, 10))


def _no_trade_snapshot():
    orchestrator = S23PaperSessionOrchestrator()
    events = (
        _calendar_context(),
        _monthly_status(MonthlyStatus.UNKNOWN),
        _paper_config(),
        _cost_settings(),
    )
    for event in events:
        snapshot = orchestrator.ingest_event(event, now=event.envelope.captured_at)
    return snapshot


def _aborted_snapshot():
    orchestrator = S23PaperSessionOrchestrator(
        guardrail_settings=S23PaperGuardrailSettings(
            manual_operator_abort=True,
            manual_abort_reason="Operator halted the S23 paper session.",
        )
    )
    events = (
        _calendar_context(),
        _monthly_status(),
        _paper_config(),
        _cost_settings(),
        _snapshot(SnapshotLabel.ORPT),
        _underlying_quote(),
        _option_chain_snapshot(),
        _selected_contract_quote(),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)
    return orchestrator.finalize(now=_ts(9, 25, 30))


def _write_snapshot(snapshot, root: Path, session_id: str) -> Path:
    writer = S23PaperSessionArtifactWriter(root / "paper_sessions")
    artifact_set = writer.write_snapshot(snapshot, session_id=session_id)
    return artifact_set.session_directory


def _write_historical_comparison(session_dir: Path) -> Path:
    decision = json.loads((session_dir / "decision_summary.json").read_text(encoding="utf-8"))
    payload = {
        "artifact_version": 1,
        "status": "MATCH",
        "go_no_go": "GO",
        "comparison_reason": "Paper and historical planning fields matched.",
        "session_id": decision["session_id"],
        "session_date": decision["session_date"],
        "strategy_code": decision["strategy_code"],
    }
    path = session_dir / "paper_vs_historical_comparison.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def test_order_planned_review_summary(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    manager = S23PaperReplayBundleManager()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "planned-session")
    manager.create_bundle(session_dir, created_at=_ts(9, 31, 0))

    summary = reviewer.review_session(session_dir)

    assert summary.terminal_state.value == "ORDER_PLANNED"
    assert summary.order_plan is not None
    assert summary.selected_contract.symbol == "NIFTY_20260528_22400_PE"
    assert summary.replay_bundle.manifest_present is True
    assert summary.replay_bundle.is_valid is True
    assert summary.runtime_contracts.shell is None
    assert summary.runtime_contracts.intent is None
    assert summary.runtime_contracts.fill is None
    assert summary.runtime_contracts.lifecycle is None
    assert summary.no_execution_disclaimer.startswith("No order was placed")


def test_no_trade_review_summary(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_no_trade_snapshot(), tmp_path, "no-trade-session")

    summary = reviewer.review_session(session_dir)

    assert summary.terminal_state.value == "NO_TRADE"
    assert summary.terminal_reason_code == "monthly_status_unknown"
    assert summary.guardrail.code == "monthly_status_unknown"
    assert summary.order_plan is None
    assert summary.runtime_contracts.shell is None
    assert summary.runtime_contracts.intent is None
    assert summary.runtime_contracts.fill is None
    assert summary.runtime_contracts.lifecycle is None


def test_aborted_review_summary(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_aborted_snapshot(), tmp_path, "aborted-session")

    summary = reviewer.review_session(session_dir)

    assert summary.terminal_state.value == "ABORTED"
    assert summary.terminal_reason_code == "manual_operator_abort"
    assert summary.guardrail.code == "manual_operator_abort"
    assert summary.order_plan is None


def test_review_uses_execution_arm_summary_when_execution_summary_fields_missing(
    tmp_path: Path,
) -> None:
    reviewer = S23PaperSessionReviewer()
    manager = S23PaperReplayBundleManager()
    session_dir = _write_snapshot(
        _planned_trade_snapshot(),
        tmp_path,
        "review-arm-summary-fallback",
    )
    manager.create_bundle(session_dir, created_at=_ts(9, 31, 0))

    writer = S23PaperExecutionJournalWriter(reviewer=reviewer)
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=_write_historical_comparison(session_dir),
        created_at=_ts(9, 30, 40),
    )

    execution_summary_path = session_dir / "execution_summary.json"
    execution_summary = json.loads(execution_summary_path.read_text(encoding="utf-8"))
    execution_summary.pop("execution_shell_status", None)
    execution_summary.pop("historical_comparison_status", None)
    execution_summary.pop("historical_comparison_reason", None)
    execution_summary.pop("historical_comparison_go_no_go", None)
    execution_summary.pop("message", None)
    execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    summary = reviewer.review_session(session_dir)

    assert summary.order_intent is not None
    assert summary.order_intent.execution_shell_status == "EXECUTION_ARMED"
    assert summary.order_intent.historical_comparison_status == "MATCH"
    assert summary.order_intent.historical_comparison_go_no_go == "GO"
    assert summary.order_intent.message is not None
    assert summary.runtime_contracts.shell is not None
    assert summary.runtime_contracts.shell.execution_shell_status == "EXECUTION_ARMED"


def test_review_uses_persisted_intent_when_summary_intent_status_missing(
    tmp_path: Path,
) -> None:
    reviewer = S23PaperSessionReviewer()
    manager = S23PaperReplayBundleManager()
    session_dir = _write_snapshot(
        _planned_trade_snapshot(),
        tmp_path,
        "review-intent-status-fallback",
    )
    manager.create_bundle(session_dir, created_at=_ts(9, 31, 0))

    writer = S23PaperExecutionJournalWriter(reviewer=reviewer)
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )

    execution_summary_path = session_dir / "execution_summary.json"
    execution_summary = json.loads(execution_summary_path.read_text(encoding="utf-8"))
    execution_summary.pop("intent_status", None)
    execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    summary = reviewer.review_session(session_dir)

    assert summary.order_intent is not None
    assert summary.order_intent.status == "INTENT_READY"
    assert summary.runtime_contracts.shell is not None
    assert summary.runtime_contracts.shell.intent_status == "INTENT_READY"


def test_bundle_validation_status_included(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    manager = S23PaperReplayBundleManager()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "bundle-session")
    manager.create_bundle(session_dir, created_at=_ts(9, 31, 0))

    review_a = reviewer.review_session(session_dir)
    review_b = reviewer.review_bundle(session_dir)

    assert review_a.replay_bundle.manifest_present is True
    assert review_a.replay_bundle.is_valid is True
    assert review_b.replay_bundle.bundle_directory == str(session_dir)


def test_missing_required_artifact_fails_clearly(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "missing-artifact-session")
    (session_dir / "decision_summary.json").unlink()

    with pytest.raises(S23PaperReviewError, match="Missing required artifact"):
        reviewer.review_session(session_dir)


def test_corrupt_artifact_fails_clearly(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "corrupt-artifact-session")
    (session_dir / "decision_summary.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(S23PaperReviewError, match="Corrupt JSON artifact"):
        reviewer.review_session(session_dir)


def test_markdown_contains_terminal_state_reason_and_disclaimer(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_no_trade_snapshot(), tmp_path, "markdown-session")

    summary = reviewer.review_session(session_dir)
    markdown = reviewer.render_review_markdown(summary)

    assert "Terminal State: `NO_TRADE`" in markdown
    assert "monthly_status_unknown" in markdown
    assert "No order was placed, no fill was simulated, no position was opened" in markdown


def test_review_summary_is_deterministic(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    manager = S23PaperReplayBundleManager()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "deterministic-session")
    manager.create_bundle(session_dir, created_at=_ts(9, 31, 0))

    summary_a = reviewer.review_bundle(session_dir)
    summary_b = reviewer.review_bundle(session_dir)
    json_a = reviewer.render_review_json(summary_a)
    json_b = reviewer.render_review_json(summary_b)

    assert summary_a == summary_b
    assert json_a == json_b
    payload = json.loads(json_a)
    assert payload["replay_bundle"]["is_valid"] is True
    assert payload["runtime_contracts"]["shell"] is None
    assert payload["runtime_contracts"]["intent"] is None
