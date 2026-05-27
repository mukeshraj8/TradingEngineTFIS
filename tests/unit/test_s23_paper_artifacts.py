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
    PaperSessionConfigEvent,
    S23PaperGuardrailSettings,
    S23PaperSessionArtifactWriter,
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


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_order_planned_writes_expected_artifacts(tmp_path: Path) -> None:
    snapshot = _planned_snapshot()
    writer = S23PaperSessionArtifactWriter(tmp_path / "paper_sessions")

    artifact_set = writer.write_snapshot(snapshot, session_id="planned-session")

    assert artifact_set.session_manifest_path.exists()
    assert artifact_set.audit_events_path.exists()
    assert artifact_set.decision_summary_path.exists()
    assert artifact_set.selected_contract_path is not None
    assert artifact_set.selected_contract_path.exists()
    assert artifact_set.paper_order_plan_path is not None
    assert artifact_set.paper_order_plan_path.exists()
    assert artifact_set.no_trade_summary_path is None
    assert artifact_set.abort_summary_path is None

    decision_summary = _read_json(artifact_set.decision_summary_path)
    assert decision_summary["state"] == "ORDER_PLANNED"
    assert decision_summary["paper_order_planned"] is True
    assert decision_summary["selected_contract_symbol"] == "NIFTY_20260528_22400_PE"
    assert decision_summary["guardrail_code"] is None

    order_plan = _read_json(artifact_set.paper_order_plan_path)
    assert order_plan["execution_started"] is False
    assert order_plan["fill_simulation_started"] is False
    assert order_plan["guardrail_code"] is None


def test_no_trade_writes_terminal_summary_without_order_plan(tmp_path: Path) -> None:
    snapshot = _no_trade_snapshot()
    writer = S23PaperSessionArtifactWriter(tmp_path / "paper_sessions")

    artifact_set = writer.write_snapshot(snapshot, session_id="no-trade-session")

    assert artifact_set.paper_order_plan_path is None
    assert artifact_set.no_trade_summary_path is not None
    assert artifact_set.no_trade_summary_path.exists()
    assert artifact_set.abort_summary_path is None

    no_trade_summary = _read_json(artifact_set.no_trade_summary_path)
    assert no_trade_summary["terminal_state"] == "NO_TRADE"
    assert no_trade_summary["terminal_reason_code"] == "monthly_status_unknown"
    assert no_trade_summary["guardrail_code"] == "monthly_status_unknown"
    assert no_trade_summary["blocking_event_type"] == "MONTHLY_STATUS_INPUT"
    assert no_trade_summary["blocking_source_id"] == "monthly_status_input-source"
    assert no_trade_summary["operator_action_required"] is not None
    assert no_trade_summary["execution_started"] is False


def test_aborted_writes_terminal_summary_without_order_plan(tmp_path: Path) -> None:
    snapshot = _aborted_snapshot()
    writer = S23PaperSessionArtifactWriter(tmp_path / "paper_sessions")

    artifact_set = writer.write_snapshot(snapshot, session_id="aborted-session")

    assert artifact_set.paper_order_plan_path is None
    assert artifact_set.abort_summary_path is not None
    assert artifact_set.abort_summary_path.exists()
    assert artifact_set.no_trade_summary_path is None

    abort_summary = _read_json(artifact_set.abort_summary_path)
    assert abort_summary["terminal_state"] == "ABORTED"
    assert abort_summary["terminal_reason_code"] == "manual_operator_abort"
    assert abort_summary["guardrail_code"] == "manual_operator_abort"
    assert abort_summary["guardrail_message"] == "Operator halted the S23 paper session."
    assert abort_summary["blocking_source_id"] == "manual_operator"
    assert abort_summary["operator_action_required"] is not None
    assert abort_summary["execution_started"] is False


def test_serialization_is_deterministic(tmp_path: Path) -> None:
    snapshot = _planned_snapshot()
    writer_a = S23PaperSessionArtifactWriter(tmp_path / "a")
    writer_b = S23PaperSessionArtifactWriter(tmp_path / "b")

    artifact_a = writer_a.write_snapshot(snapshot, session_id="stable-session")
    artifact_b = writer_b.write_snapshot(snapshot, session_id="stable-session")

    assert artifact_a.decision_summary_path.read_text(encoding="utf-8") == artifact_b.decision_summary_path.read_text(encoding="utf-8")
    assert artifact_a.audit_events_path.read_text(encoding="utf-8") == artifact_b.audit_events_path.read_text(encoding="utf-8")
    assert artifact_a.paper_order_plan_path is not None
    assert artifact_b.paper_order_plan_path is not None
    assert artifact_a.paper_order_plan_path.read_text(encoding="utf-8") == artifact_b.paper_order_plan_path.read_text(encoding="utf-8")


def test_atomic_write_does_not_leave_temp_files_on_success(tmp_path: Path) -> None:
    snapshot = _planned_snapshot()
    writer = S23PaperSessionArtifactWriter(tmp_path / "paper_sessions")

    artifact_set = writer.write_snapshot(snapshot, session_id="atomic-session")

    temp_paths = [path for path in artifact_set.session_directory.iterdir() if path.suffix == ".tmp"]
    assert temp_paths == []


def test_artifacts_include_provenance_and_terminal_reason(tmp_path: Path) -> None:
    snapshot = _aborted_snapshot()
    writer = S23PaperSessionArtifactWriter(tmp_path / "paper_sessions")

    artifact_set = writer.write_snapshot(snapshot, session_id="provenance-session")

    manifest = _read_json(artifact_set.session_manifest_path)
    decision = _read_json(artifact_set.decision_summary_path)
    abort_summary = _read_json(artifact_set.abort_summary_path)

    assert manifest["synthetic_fixture_used"] is True
    assert len(manifest["data_sources"]) >= 4
    assert decision["terminal_reason_code"] == "manual_operator_abort"
    assert decision["guardrail_code"] == "manual_operator_abort"
    assert abort_summary["terminal_reason_code"] == "manual_operator_abort"
    assert abort_summary["guardrail_code"] == "manual_operator_abort"
