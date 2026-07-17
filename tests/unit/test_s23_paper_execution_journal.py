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
    S23PaperExecutionJournalError,
    S23PaperExecutionJournalWriter,
    S23PaperGuardrailSettings,
    S23PaperReplayBundleManager,
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


def _monthly_status(
    status: MonthlyStatus = MonthlyStatus.BULL,
) -> MonthlyStatusInputEvent:
    return MonthlyStatusInputEvent(
        envelope=_envelope(
            PaperEventType.MONTHLY_STATUS_INPUT,
            effective_timestamp=_ts(9, 1),
        ),
        monthly_status=status,
        status_source="monthly_status_engine",
        reference_date=date(2026, 5, 27),
        threshold_version="v1",
    )


def _paper_config(
    *,
    allow_current_day_fsl_trp: bool = False,
    same_day_square_off_only: bool = True,
) -> PaperSessionConfigEvent:
    return PaperSessionConfigEvent(
        envelope=_envelope(
            PaperEventType.PAPER_SESSION_CONFIG,
            effective_timestamp=_ts(9, 2),
        ),
        strategy_code="S23",
        paper_mode_enabled=True,
        same_day_square_off_only=same_day_square_off_only,
        allow_recalculation=False,
        allow_current_day_fsl_trp=allow_current_day_fsl_trp,
        kill_switch_enabled=False,
        operator_id="operator-1",
    )


def _cost_settings() -> CostSlippageSettingsEvent:
    return CostSlippageSettingsEvent(
        envelope=_envelope(
            PaperEventType.COST_SLIPPAGE_SETTINGS,
            effective_timestamp=_ts(9, 3),
        ),
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
        envelope=_envelope(
            PaperEventType.UNDERLYING_SNAPSHOT,
            effective_timestamp=timestamp,
        ),
        snapshot_label=label,
        open=22320.0,
        high=22380.0,
        low=22310.0,
        close=22350.0,
        bar_start=timestamp - timedelta(minutes=1),
        bar_end=timestamp,
        complete=True,
    )


def _underlying_quote(
    *,
    effective_timestamp: datetime | None = None,
) -> UnderlyingQuoteEvent:
    return UnderlyingQuoteEvent(
        envelope=_envelope(
            PaperEventType.UNDERLYING_QUOTE,
            effective_timestamp=effective_timestamp or _ts(9, 29, 59),
        ),
        symbol="NIFTY",
        ltp=22345.0,
        bid=22344.5,
        ask=22345.5,
        volume=1000.0,
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
        envelope=_envelope(
            PaperEventType.OPTION_CHAIN_SNAPSHOT,
            effective_timestamp=_ts(9, 24, 59),
        ),
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
            effective_timestamp=effective_timestamp or _ts(9, 29, 59),
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


def _trade_plan_input(
    *,
    planned_entry_price: float | None = 199.5,
    target_price: float | None = 80.0,
    stoploss_price: float | None = 320.0,
) -> PaperTradePlanEvent:
    return PaperTradePlanEvent(
        envelope=_envelope(
            PaperEventType.TRADE_PLAN_INPUT,
            effective_timestamp=_ts(9, 29, 59),
        ),
        strategy_branch="S23_BEAR_PUT",
        order_side="SELL",
        lots=2,
        quantity=100,
        planned_entry_price=planned_entry_price,
        target_price=target_price,
        stoploss_price=stoploss_price,
        order_reference_time=_ts(9, 24, 59),
        order_reference_label="ORPT",
        source_workbook_rule="AB6_OS_Z184",
        workbook_row_number=184,
        fsl_price=352.0,
    )


def _planned_snapshot(*, include_trade_plan: bool = True):
    orchestrator = S23PaperSessionOrchestrator()
    events = [
        _calendar_context(),
        _monthly_status(),
        _paper_config(allow_current_day_fsl_trp=True),
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
        _underlying_quote(effective_timestamp=_ts(9, 24, 59)),
        _option_chain_snapshot(),
        _selected_contract_quote(effective_timestamp=_ts(9, 24, 59)),
    )
    for event in events:
        orchestrator.ingest_event(event, now=event.envelope.captured_at)
    return orchestrator.finalize(now=_ts(9, 25, 30))


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_snapshot(snapshot, root: Path, session_id: str) -> Path:
    writer = S23PaperSessionArtifactWriter(root / "paper_sessions")
    artifact_set = writer.write_snapshot(snapshot, session_id=session_id)
    return artifact_set.session_directory


def _create_bundle(session_dir: Path) -> None:
    manager = S23PaperReplayBundleManager()
    manager.create_bundle(session_dir, created_at=_ts(9, 31, 0), source_artifact_root=session_dir.parent.parent)


def _write_historical_comparison(
    session_dir: Path,
    *,
    status: str = "MATCH",
    go_no_go: str = "GO: the persisted paper intent matches the expected historical trade-plan decision.",
    comparison_reason: str = "Paper and historical planning fields matched.",
) -> Path:
    decision = _read_json(session_dir / "decision_summary.json")
    payload = {
        "artifact_version": 1,
        "status": status,
        "go_no_go": go_no_go,
        "comparison_reason": comparison_reason,
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


def _arm_execution_shell(
    session_dir: Path,
    *,
    created_at: datetime | None = None,
    guardrail_settings: S23PaperGuardrailSettings | None = None,
    comparison_status: str = "MATCH",
    comparison_reason: str = "Paper and historical planning fields matched.",
    go_no_go: str = "GO: the persisted paper intent matches the expected historical trade-plan decision.",
) -> S23PaperExecutionJournalWriter:
    comparison_path = _write_historical_comparison(
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
    writer: S23PaperExecutionJournalWriter,
    created_at: datetime | None = None,
) -> S23PaperExecutionJournalWriter:
    writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=created_at or _ts(9, 30, 50),
    )
    return writer


def _handoff_execution_shell(
    session_dir: Path,
    *,
    writer: S23PaperExecutionJournalWriter,
    created_at: datetime | None = None,
) -> S23PaperExecutionJournalWriter:
    writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=created_at or _ts(9, 30, 55),
    )
    return writer


def test_order_planned_creates_intent_ready_shell(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    journal_writer = S23PaperExecutionJournalWriter(reviewer=reviewer)
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "planned-intent-session")

    artifact_set = journal_writer.write_from_session(
        session_dir,
        created_at=_ts(9, 30, 20),
    )

    assert artifact_set.paper_order_intent_path is not None
    assert artifact_set.intent_block_summary_path is None

    intent = _read_json(artifact_set.paper_order_intent_path)
    assert intent["status"] == "INTENT_ONLY"
    assert intent["side"] == "SELL"

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "INTENT_READY"
    assert summary["created_order_intent"] is True
    assert summary["guardrail_code"] is None

    journal_event = json.loads(artifact_set.execution_journal_path.read_text(encoding="utf-8").splitlines()[0])
    assert journal_event["event_type"] == "INTENT_CREATED"
    assert journal_event["status"] == "INTENT_READY"
    assert "No order was placed, no fill was simulated" in journal_event["disclaimer"]


def test_no_trade_does_not_create_intent(tmp_path: Path) -> None:
    journal_writer = S23PaperExecutionJournalWriter()
    session_dir = _write_snapshot(_no_trade_snapshot(), tmp_path, "no-trade-intent-session")

    artifact_set = journal_writer.write_from_session(session_dir, created_at=_ts(9, 5, 0))

    assert artifact_set.paper_order_intent_path is None
    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "INTENT_SKIPPED"
    assert summary["terminal_reason_code"] == "monthly_status_unknown"


def test_aborted_does_not_create_intent(tmp_path: Path) -> None:
    journal_writer = S23PaperExecutionJournalWriter()
    session_dir = _write_snapshot(_aborted_snapshot(), tmp_path, "aborted-intent-session")

    artifact_set = journal_writer.write_from_session(session_dir, created_at=_ts(9, 25, 45))

    assert artifact_set.paper_order_intent_path is None
    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "INTENT_SKIPPED"
    assert summary["terminal_state"] == "ABORTED"


def test_missing_selected_contract_still_fails_structural_validation(tmp_path: Path) -> None:
    journal_writer = S23PaperExecutionJournalWriter()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "missing-selected-contract")
    (session_dir / "selected_contract.json").unlink()

    with pytest.raises(S23PaperExecutionJournalError, match="missing_selected_contract"):
        journal_writer.write_from_session(session_dir)


def test_missing_price_fields_still_fail_structural_validation(tmp_path: Path) -> None:
    journal_writer = S23PaperExecutionJournalWriter()
    session_dir = _write_snapshot(
        _planned_snapshot(include_trade_plan=False),
        tmp_path,
        "missing-price-fields",
    )

    with pytest.raises(S23PaperExecutionJournalError, match="missing_planned_entry_price"):
        journal_writer.write_from_session(session_dir)


def test_execution_globally_disabled_creates_intent_blocked(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "global-execution-disabled")
    journal_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            global_paper_execution_enabled=False,
        )
    )

    artifact_set = journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 20))

    assert artifact_set.paper_order_intent_path is None
    assert artifact_set.intent_block_summary_path is not None
    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "INTENT_BLOCKED"
    assert summary["guardrail_code"] == "global_paper_execution_disabled"


def test_s23_execution_disabled_creates_intent_blocked(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "s23-execution-disabled")
    journal_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            s23_paper_execution_enabled=False,
        )
    )

    artifact_set = journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 20))

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "INTENT_BLOCKED"
    assert summary["guardrail_code"] == "s23_paper_execution_disabled"


def test_manual_abort_after_order_intent_creates_intent_aborted(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "manual-abort-after-intent")
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 20))

    abort_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            manual_operator_abort_after_planning=True,
            manual_abort_after_planning_reason="Operator aborted after reviewing the intent shell.",
        )
    )
    artifact_set = abort_writer.write_from_session(session_dir, created_at=_ts(9, 30, 30))

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "INTENT_ABORTED"
    assert summary["guardrail_code"] == "manual_operator_abort_after_planning"
    assert artifact_set.intent_block_summary_path is not None


def test_duplicate_intent_generation_is_blocked(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "duplicate-intent")
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 20))

    artifact_set = journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 30))

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "INTENT_BLOCKED"
    assert summary["guardrail_code"] == "duplicate_paper_order_intent_generation"
    journal_lines = artifact_set.execution_journal_path.read_text(encoding="utf-8").splitlines()
    assert len(journal_lines) == 2
    assert json.loads(journal_lines[-1])["event_type"] == "INTENT_BLOCKED"


def test_corrupt_intent_artifact_blocks_readiness(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "corrupt-intent")
    journal_writer = S23PaperExecutionJournalWriter()
    artifact_set = journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 20))
    assert artifact_set.paper_order_intent_path is not None
    artifact_set.paper_order_intent_path.write_text("{not-json", encoding="utf-8")

    blocked = journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 30))

    summary = _read_json(blocked.execution_summary_path)
    assert summary["status"] == "INTENT_BLOCKED"
    assert summary["guardrail_code"] == "corrupt_order_intent_artifact"


def test_selected_contract_mismatch_blocks_intent_readiness(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "selected-contract-mismatch")
    journal_writer = S23PaperExecutionJournalWriter()
    artifact_set = journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 20))

    intent_payload = _read_json(artifact_set.paper_order_intent_path)
    intent_payload["selected_contract_symbol"] = "NIFTY_20260528_22500_PE"
    artifact_set.paper_order_intent_path.write_text(
        json.dumps(intent_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    blocked = journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 30))

    summary = _read_json(blocked.execution_summary_path)
    assert summary["status"] == "INTENT_BLOCKED"
    assert summary["guardrail_code"] == "selected_contract_mismatch_between_order_plan_and_intent"


def test_invalid_replay_bundle_blocks_readiness(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "invalid-replay-bundle")
    _create_bundle(session_dir)
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )

    payload = _read_json(session_dir / "paper_order_plan.json")
    payload["order_plan"]["planned_entry_price"] = 188.0
    (session_dir / "paper_order_plan.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    blocked = journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 30),
    )

    summary = _read_json(blocked.execution_summary_path)
    assert summary["status"] == "INTENT_BLOCKED"
    assert summary["guardrail_code"] == "session_artifact_hash_mismatch"
    assert summary["bundle_valid"] is False


def test_review_displays_post_planning_guardrail_result(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "review-blocked-intent")
    journal_writer = S23PaperExecutionJournalWriter(
        reviewer=reviewer,
        guardrail_settings=S23PaperGuardrailSettings(
            global_paper_execution_enabled=False,
        ),
    )
    journal_writer.write_from_session(session_dir, created_at=_ts(9, 30, 20))

    review_summary = reviewer.review_session(session_dir)
    markdown = reviewer.render_review_markdown(review_summary)

    assert review_summary.order_intent is not None
    assert review_summary.order_intent.available is False
    assert review_summary.order_intent.status == "INTENT_BLOCKED"
    assert review_summary.order_intent.guardrail_code == "global_paper_execution_disabled"
    assert "INTENT_BLOCKED" in markdown
    assert "global_paper_execution_disabled" in markdown


def test_output_is_deterministic(tmp_path: Path) -> None:
    writer = S23PaperExecutionJournalWriter()
    session_dir_a = _write_snapshot(_planned_snapshot(), tmp_path / "a", "stable-session")
    session_dir_b = _write_snapshot(_planned_snapshot(), tmp_path / "b", "stable-session")

    artifacts_a = writer.write_from_session(session_dir_a, created_at=_ts(9, 30, 20))
    artifacts_b = writer.write_from_session(session_dir_b, created_at=_ts(9, 30, 20))

    assert artifacts_a.execution_summary_path.read_text(encoding="utf-8") == artifacts_b.execution_summary_path.read_text(encoding="utf-8")
    assert artifacts_a.execution_journal_path.read_text(encoding="utf-8") == artifacts_b.execution_journal_path.read_text(encoding="utf-8")
    assert artifacts_a.paper_order_intent_path is not None
    assert artifacts_b.paper_order_intent_path is not None
    assert artifacts_a.paper_order_intent_path.read_text(encoding="utf-8") == artifacts_b.paper_order_intent_path.read_text(encoding="utf-8")


def test_valid_intent_with_valid_comparison_and_review_arms_execution_shell(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "execution-armed")
    _create_bundle(session_dir)
    comparison_path = _write_historical_comparison(session_dir)
    journal_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            require_operator_review_completed_before_execution=True,
            operator_review_completed=True,
        )
    )
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )

    artifact_set = journal_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "EXECUTION_ARMED"
    assert summary["intent_status"] == "INTENT_READY"
    assert summary["execution_shell_status"] == "EXECUTION_ARMED"
    assert summary["historical_comparison_status"] == "MATCH"
    assert artifact_set.execution_arm_summary_path is not None
    journal_lines = artifact_set.execution_journal_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(journal_lines[-1])["event_type"] == "EXECUTION_ARMED"


def test_operator_review_missing_blocks_execution_shell(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "execution-review-missing")
    _create_bundle(session_dir)
    comparison_path = _write_historical_comparison(session_dir)
    initial_writer = S23PaperExecutionJournalWriter()
    initial_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    arm_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            require_operator_review_completed_before_execution=True,
            operator_review_completed=False,
        )
    )

    artifact_set = arm_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "EXECUTION_BLOCKED"
    assert summary["guardrail_code"] == "operator_review_incomplete"
    assert artifact_set.execution_block_summary_path is not None


def test_historical_comparison_mismatch_blocks_execution_shell(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "execution-comparison-mismatch")
    _create_bundle(session_dir)
    comparison_path = _write_historical_comparison(
        session_dir,
        status="MISMATCH",
        go_no_go="NO-GO: paper and historical planning diverged.",
        comparison_reason="Selected contract differed.",
    )
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )

    artifact_set = journal_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "EXECUTION_BLOCKED"
    assert summary["guardrail_code"] == "historical_comparison_mismatch"
    assert summary["historical_comparison_status"] == "MISMATCH"


def test_invalid_replay_bundle_blocks_execution_shell(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "execution-invalid-bundle")
    _create_bundle(session_dir)
    comparison_path = _write_historical_comparison(session_dir)
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )

    payload = _read_json(session_dir / "paper_order_plan.json")
    payload["order_plan"]["planned_entry_price"] = 188.0
    (session_dir / "paper_order_plan.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    artifact_set = journal_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "EXECUTION_BLOCKED"
    assert summary["guardrail_code"] == "session_artifact_hash_mismatch"


def test_manual_abort_creates_execution_aborted(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "execution-manual-abort")
    _create_bundle(session_dir)
    comparison_path = _write_historical_comparison(session_dir)
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    abort_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            manual_operator_abort_after_planning=True,
            manual_abort_after_planning_reason="Operator halted the execution shell before any future handoff.",
        )
    )

    artifact_set = abort_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "EXECUTION_ABORTED"
    assert summary["guardrail_code"] == "manual_operator_abort_after_planning"


def test_selected_contract_stale_blocks_execution_shell(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "execution-stale-contract")
    _create_bundle(session_dir)
    comparison_path = _write_historical_comparison(session_dir)
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )

    artifact_set = journal_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 40, 0),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "EXECUTION_BLOCKED"
    assert summary["guardrail_code"] == "selected_contract_stale_before_execution"


def test_duplicate_execution_arming_attempt_is_deterministic(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "execution-duplicate-arm")
    _create_bundle(session_dir)
    comparison_path = _write_historical_comparison(session_dir)
    journal_writer = S23PaperExecutionJournalWriter()
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    journal_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )

    artifact_set = journal_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 50),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "EXECUTION_BLOCKED"
    assert summary["guardrail_code"] == "duplicate_execution_shell_arming_attempt"
    journal_lines = artifact_set.execution_journal_path.read_text(encoding="utf-8").splitlines()
    assert json.loads(journal_lines[-1])["event_type"] == "EXECUTION_BLOCKED"


def test_review_shows_execution_shell_readiness(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "review-execution-armed")
    _create_bundle(session_dir)
    comparison_path = _write_historical_comparison(session_dir)
    journal_writer = S23PaperExecutionJournalWriter(
        reviewer=reviewer,
        guardrail_settings=S23PaperGuardrailSettings(
            require_operator_review_completed_before_execution=True,
            operator_review_completed=True,
        ),
    )
    journal_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    journal_writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=comparison_path,
        created_at=_ts(9, 30, 40),
    )

    review_summary = reviewer.review_session(session_dir, bundle_directory=session_dir)
    markdown = reviewer.render_review_markdown(review_summary)

    assert review_summary.order_intent is not None
    assert review_summary.order_intent.status == "INTENT_READY"
    assert review_summary.order_intent.execution_shell_status == "EXECUTION_ARMED"
    assert review_summary.order_intent.historical_comparison_status == "MATCH"
    assert review_summary.runtime_contracts.shell is not None
    assert review_summary.runtime_contracts.shell.intent_status == "INTENT_READY"
    assert review_summary.runtime_contracts.shell.execution_shell_status == "EXECUTION_ARMED"
    assert review_summary.runtime_contracts.shell.historical_comparison_status == "MATCH"
    assert review_summary.runtime_contracts.intent is not None
    assert review_summary.runtime_contracts.intent.selected_contract_symbol == "NIFTY_20260528_22400_PE"
    assert review_summary.runtime_contracts.intent.planned_entry_price == 199.5
    assert "EXECUTION_ARMED" in markdown
    assert "Historical Comparison Status" in markdown


def test_arm_execution_uses_runtime_intent_status_when_summary_intent_status_missing(
    tmp_path: Path,
) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "arm-runtime-intent-status")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )

    execution_summary_path = session_dir / "execution_summary.json"
    execution_summary = _read_json(execution_summary_path)
    execution_summary.pop("intent_status", None)
    execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    artifact_set = writer.arm_execution_from_session(
        session_dir,
        bundle_directory=session_dir,
        historical_comparison_path=_write_historical_comparison(
            session_dir,
            status="MATCH",
            go_no_go="GO",
        ),
        created_at=_ts(9, 30, 40),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "EXECUTION_ARMED"
    assert summary["intent_status"] == "INTENT_READY"
    assert summary["execution_shell_status"] == "EXECUTION_ARMED"


def test_armed_session_can_dispatch_fillless_intent(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "dispatch-ready")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))

    artifact_set = writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 50),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "ORDER_INTENT_DISPATCHED"
    assert summary["execution_shell_status"] == "EXECUTION_ARMED"
    assert summary["dispatch_shell_status"] == "ORDER_INTENT_DISPATCHED"
    assert summary["intent_dispatched"] is True
    assert summary["order_placed"] is False
    assert summary["fill_simulated"] is False
    assert summary["position_opened"] is False
    assert artifact_set.intent_dispatch_summary_path is not None
    journal_rows = [
        json.loads(line)
        for line in artifact_set.execution_journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert journal_rows[-2]["event_type"] == "ORDER_INTENT_DISPATCH_READY"
    assert journal_rows[-1]["event_type"] == "ORDER_INTENT_DISPATCHED"


def test_dispatch_uses_runtime_shell_when_execution_summary_shell_fields_missing(
    tmp_path: Path,
) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "dispatch-runtime-shell")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))

    execution_summary_path = session_dir / "execution_summary.json"
    execution_summary = _read_json(execution_summary_path)
    execution_summary.pop("execution_shell_status", None)
    execution_summary.pop("historical_comparison_status", None)
    execution_summary.pop("historical_comparison_reason", None)
    execution_summary.pop("historical_comparison_go_no_go", None)
    execution_summary.pop("selected_contract_symbol", None)
    execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    artifact_set = writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 50),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "ORDER_INTENT_DISPATCHED"
    assert summary["execution_shell_status"] == "EXECUTION_ARMED"
    assert summary["dispatch_shell_status"] == "ORDER_INTENT_DISPATCHED"


def test_duplicate_dispatch_attempt_is_blocked(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "dispatch-duplicate")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 50),
    )

    artifact_set = writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 55),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "ORDER_INTENT_DISPATCH_BLOCKED"
    assert summary["guardrail_code"] == "duplicate_order_intent_dispatch_attempt"


def test_manual_abort_before_dispatch_cancels_intent(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "dispatch-manual-abort")
    _create_bundle(session_dir)
    initial_writer = S23PaperExecutionJournalWriter()
    initial_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    dispatch_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            manual_operator_abort_before_dispatch=True,
            manual_abort_before_dispatch_reason="Operator cancelled dispatch before any future handoff.",
            require_operator_review_completed_before_execution=True,
            operator_review_completed=True,
        )
    )

    artifact_set = dispatch_writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 50),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "ORDER_INTENT_CANCELLED"
    assert summary["guardrail_code"] == "manual_operator_abort_before_dispatch"


def test_stale_selected_contract_blocks_dispatch(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "dispatch-stale-contract")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))

    artifact_set = writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 40, 0),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "ORDER_INTENT_DISPATCH_BLOCKED"
    assert summary["guardrail_code"] == "selected_contract_stale_before_execution"


def test_invalid_replay_bundle_blocks_dispatch(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "dispatch-invalid-bundle")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))

    payload = _read_json(session_dir / "paper_order_plan.json")
    payload["order_plan"]["planned_entry_price"] = 188.0
    (session_dir / "paper_order_plan.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    artifact_set = writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 50),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "ORDER_INTENT_DISPATCH_BLOCKED"
    assert summary["guardrail_code"] == "session_artifact_hash_mismatch"


def test_review_shows_dispatch_shell_state(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "review-dispatch-state")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter(reviewer=reviewer)
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer.dispatch_order_intent_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 50),
    )

    review_summary = reviewer.review_session(session_dir, bundle_directory=session_dir)
    markdown = reviewer.render_review_markdown(review_summary)

    assert review_summary.order_intent is not None
    assert review_summary.order_intent.dispatch_shell_status == "ORDER_INTENT_DISPATCHED"
    assert "ORDER_INTENT_DISPATCHED" in markdown
    assert "no position was opened" in markdown.lower()


def test_dispatched_session_reaches_execution_handoff_ready(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "handoff-ready")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer = _dispatch_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 50))

    artifact_set = writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 55),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_EXECUTION_HANDOFF_READY"
    assert summary["handoff_shell_status"] == "PAPER_EXECUTION_HANDOFF_READY"
    assert summary["future_fill_simulation_eligible"] is True
    assert summary["order_placed"] is False
    assert summary["fill_simulated"] is False
    assert summary["position_opened"] is False
    assert artifact_set.execution_handoff_summary_path is not None
    journal_rows = [
        json.loads(line)
        for line in artifact_set.execution_journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert journal_rows[-1]["event_type"] == "PAPER_EXECUTION_HANDOFF_READY"


def test_duplicate_handoff_attempt_is_blocked(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "handoff-duplicate")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer = _dispatch_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 50))
    writer = _handoff_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 55))

    artifact_set = writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 56),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_EXECUTION_HANDOFF_BLOCKED"
    assert summary["guardrail_code"] == "duplicate_execution_handoff_attempt"


def test_manual_abort_before_handoff_aborts_shell(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "handoff-manual-abort")
    _create_bundle(session_dir)
    initial_writer = S23PaperExecutionJournalWriter()
    initial_writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer = _dispatch_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 50))
    abort_writer = S23PaperExecutionJournalWriter(
        guardrail_settings=S23PaperGuardrailSettings(
            manual_operator_abort_before_handoff=True,
            manual_abort_before_handoff_reason="Operator halted the future fill-simulator handoff.",
            require_operator_review_completed_before_execution=True,
            operator_review_completed=True,
        )
    )

    artifact_set = abort_writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 55),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_EXECUTION_HANDOFF_ABORTED"
    assert summary["guardrail_code"] == "manual_operator_abort_before_handoff"


def test_stale_selected_contract_blocks_handoff(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "handoff-stale-contract")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer = _dispatch_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 50))

    artifact_set = writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 40, 0),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_EXECUTION_HANDOFF_BLOCKED"
    assert summary["guardrail_code"] == "selected_contract_stale_before_execution"


def test_invalid_replay_bundle_blocks_handoff(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "handoff-invalid-bundle")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer = _dispatch_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 50))

    payload = _read_json(session_dir / "paper_order_plan.json")
    payload["order_plan"]["planned_entry_price"] = 188.0
    (session_dir / "paper_order_plan.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    artifact_set = writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 55),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_EXECUTION_HANDOFF_BLOCKED"
    assert summary["guardrail_code"] == "session_artifact_hash_mismatch"


def test_comparison_mismatch_blocks_handoff(tmp_path: Path) -> None:
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "handoff-comparison-mismatch")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter()
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer = _dispatch_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 50))

    execution_summary_path = session_dir / "execution_summary.json"
    execution_summary = _read_json(execution_summary_path)
    execution_summary["historical_comparison_status"] = "MISMATCH"
    execution_summary["historical_comparison_reason"] = "Workbook row mismatch."
    execution_summary["historical_comparison_go_no_go"] = "NO-GO"
    execution_summary_path.write_text(
        json.dumps(execution_summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _create_bundle(session_dir)

    artifact_set = writer.mark_execution_handoff_ready_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 55),
    )

    summary = _read_json(artifact_set.execution_summary_path)
    assert summary["status"] == "PAPER_EXECUTION_HANDOFF_BLOCKED"
    assert summary["guardrail_code"] == "historical_comparison_mismatch"


def test_review_shows_handoff_readiness(tmp_path: Path) -> None:
    reviewer = S23PaperSessionReviewer()
    session_dir = _write_snapshot(_planned_snapshot(), tmp_path, "review-handoff-ready")
    _create_bundle(session_dir)
    writer = S23PaperExecutionJournalWriter(reviewer=reviewer)
    writer.write_from_session(
        session_dir,
        bundle_directory=session_dir,
        created_at=_ts(9, 30, 20),
    )
    writer = _arm_execution_shell(session_dir, created_at=_ts(9, 30, 40))
    writer = _dispatch_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 50))
    writer = _handoff_execution_shell(session_dir, writer=writer, created_at=_ts(9, 30, 55))

    review_summary = reviewer.review_session(session_dir, bundle_directory=session_dir)
    markdown = reviewer.render_review_markdown(review_summary)

    assert review_summary.order_intent is not None
    assert review_summary.order_intent.handoff_shell_status == "PAPER_EXECUTION_HANDOFF_READY"
    assert review_summary.order_intent.future_fill_simulation_eligible is True
    assert "PAPER_EXECUTION_HANDOFF_READY" in markdown
    assert "No order was placed, no fill was simulated, no position was opened" in markdown
