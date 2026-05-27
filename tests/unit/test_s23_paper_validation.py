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
    S23PaperContractValidator,
    S23PaperSessionManifestBuilder,
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


def test_valid_minimal_event_passes() -> None:
    validator = S23PaperContractValidator()
    event = _underlying_quote()

    result = validator.validate_event(event)

    assert result.readiness_status is PaperReadinessStatus.READY
    assert result.issues == ()


def test_missing_required_field_fails() -> None:
    validator = S23PaperContractValidator()
    event = UnderlyingQuoteEvent(
        envelope=_envelope(PaperEventType.UNDERLYING_QUOTE),
        symbol="",
        ltp=22345.0,
    )

    result = validator.validate_event(event)

    assert result.readiness_status is PaperReadinessStatus.ABORTED
    assert "missing_symbol" in {issue.code for issue in result.issues}


def test_monthly_status_unknown_fails_as_no_trade() -> None:
    validator = S23PaperContractValidator()

    result = validator.validate_session_readiness(
        calendar_context=_calendar_context(),
        monthly_status_input=_monthly_status(MonthlyStatus.UNKNOWN),
        paper_config=_paper_config(),
        cost_settings=_cost_settings(),
        underlying_quote=_underlying_quote(),
        snapshots=(_snapshot(SnapshotLabel.ORPT),),
        option_chain_snapshot=_option_chain_snapshot(),
        selected_contract_quote=_selected_contract_quote(),
        now=_ts(9, 25, 10),
    )

    assert result.readiness_status is PaperReadinessStatus.NO_TRADE
    assert "monthly_status_unknown" in result.no_trade_reasons


def test_unsupported_continuation_path_is_blocked() -> None:
    validator = S23PaperContractValidator()

    result = validator.validate_session_readiness(
        calendar_context=_calendar_context(),
        monthly_status_input=_monthly_status(),
        paper_config=_paper_config(same_day_square_off_only=False),
        cost_settings=_cost_settings(),
        underlying_quote=_underlying_quote(),
        snapshots=(_snapshot(SnapshotLabel.ORPT),),
        option_chain_snapshot=_option_chain_snapshot(),
        selected_contract_quote=_selected_contract_quote(),
        now=_ts(9, 25, 10),
    )

    assert result.readiness_status is PaperReadinessStatus.ABORTED
    assert "unsupported_continuation_path" in result.abort_reasons


def test_stale_data_produces_validation_failure() -> None:
    validator = S23PaperContractValidator()

    result = validator.validate_session_readiness(
        calendar_context=_calendar_context(),
        monthly_status_input=_monthly_status(),
        paper_config=_paper_config(),
        cost_settings=_cost_settings(),
        underlying_quote=_underlying_quote(effective_timestamp=_ts(9, 20, 0)),
        snapshots=(_snapshot(SnapshotLabel.ORPT),),
        option_chain_snapshot=_option_chain_snapshot(),
        selected_contract_quote=_selected_contract_quote(),
        now=_ts(9, 25, 10),
    )

    assert result.readiness_status is PaperReadinessStatus.NO_TRADE
    assert "stale_underlying_quote" in result.no_trade_reasons


def test_missing_required_snapshots_fail_for_current_day_fsl_trp() -> None:
    validator = S23PaperContractValidator()

    result = validator.validate_session_readiness(
        calendar_context=_calendar_context(),
        monthly_status_input=_monthly_status(),
        paper_config=_paper_config(allow_current_day_fsl_trp=True),
        cost_settings=_cost_settings(),
        underlying_quote=_underlying_quote(),
        snapshots=(_snapshot(SnapshotLabel.ORPT),),
        option_chain_snapshot=_option_chain_snapshot(),
        selected_contract_quote=_selected_contract_quote(),
        now=_ts(9, 25, 10),
    )

    assert result.readiness_status is PaperReadinessStatus.NO_TRADE
    assert result.missing_snapshot_labels == (SnapshotLabel.AT_0915, SnapshotLabel.RC)
    assert "missing_snapshot_0915" in result.no_trade_reasons
    assert "missing_snapshot_RC" in result.no_trade_reasons


def test_manifest_records_provenance_and_readiness_result() -> None:
    validator = S23PaperContractValidator()
    manifest_builder = S23PaperSessionManifestBuilder()
    calendar_context = _calendar_context()
    monthly_status_input = _monthly_status()
    paper_config = _paper_config(allow_recalculation=True)
    cost_settings = _cost_settings()
    underlying_quote = _underlying_quote()
    orpt_snapshot = _snapshot(SnapshotLabel.ORPT)
    rc_snapshot = _snapshot(SnapshotLabel.RC)
    option_chain_snapshot = _option_chain_snapshot()
    selected_contract_quote = _selected_contract_quote()

    result = validator.validate_session_readiness(
        calendar_context=calendar_context,
        monthly_status_input=monthly_status_input,
        paper_config=paper_config,
        cost_settings=cost_settings,
        underlying_quote=underlying_quote,
        snapshots=(orpt_snapshot, rc_snapshot),
        option_chain_snapshot=option_chain_snapshot,
        selected_contract_quote=selected_contract_quote,
        now=_ts(9, 25, 10),
    )

    manifest = manifest_builder.build(
        paper_config=paper_config,
        cost_settings=cost_settings,
        validation_result=result,
        events=(
            calendar_context,
            monthly_status_input,
            paper_config,
            cost_settings,
            underlying_quote,
            orpt_snapshot,
            rc_snapshot,
            option_chain_snapshot,
            selected_contract_quote,
        ),
        generated_at=_ts(9, 25, 11),
    )

    assert manifest.strategy_code == "S23"
    assert manifest.symbol == "NIFTY"
    assert manifest.contract_cycle == "WEEKLY"
    assert manifest.mode == "paper"
    assert manifest.readiness_status is PaperReadinessStatus.READY
    assert manifest.evaluated_state is PaperSessionState.DECISION_READY
    assert manifest.synthetic_fixture_used is True
    assert manifest.cost_slippage_version == "paper-cost-v1"
    assert manifest.overlays_enabled == ("S23_RECALCULATION",)
    assert manifest.no_trade_reasons == ()
    assert {source.event_type for source in manifest.data_sources} >= {
        PaperEventType.CALENDAR_CONTEXT,
        PaperEventType.PAPER_SESSION_CONFIG,
        PaperEventType.OPTION_CHAIN_SNAPSHOT,
        PaperEventType.SELECTED_CONTRACT_QUOTE,
    }
