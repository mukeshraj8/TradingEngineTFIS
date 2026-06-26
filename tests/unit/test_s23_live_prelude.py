from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from tfis.domain import MarketLevels, StrategyExpiryPolicy, StrategyRule
from tfis.domain.enums import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment
from tfis.monthly_status import MonthlyStatusResult
from tfis.paper import (
    DeterministicExpiryCalendar,
    EventEnvelope,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperContractSelectionFailureCode,
    PaperEventType,
    S23LivePreludeError,
    S23PaperExpiryGovernance,
    S23PaperLivePreludeBuilder,
    S23PaperLivePreludeRequest,
    S23PaperPositionStateEventType,
    S23PaperPositionStateStore,
    S23PaperPreludeMode,
    S23PaperPreludeSessionContext,
    S23PaperSnapshotInput,
    SnapshotLabel,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, second, tzinfo=IST)


def _strategy_rule() -> StrategyRule:
    return StrategyRule(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
            forced_close_time=time(15, 15),
            no_carry_past_expiry=True,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        option_type=OptionType.PUT,
        entry_time=time(9, 25),
        recalculation_time=time(9, 30),
        start_strike_formula="ROUND_UP(PRV_3DHH - PARAM(strike_buffer_pct)%)",
        end_strike_formula="ROUND_UP(PRV_3DHH) + PARAM(strike_step)",
        ideal_premium_formula="PRV_3DHH * PARAM(ideal_premium_pct)%",
        minimum_premium_formula="PRV_3DHH * PARAM(minimum_premium_pct)%",
        minimum_oi=500,
        entry_formula="OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        target_formula="ENTRY - PARAM(target_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
        carry_forward_allowed=True,
        parameters={
            "strike_buffer_pct": 5.0,
            "strike_step": 50.0,
            "ideal_premium_pct": 1.2,
            "minimum_premium_pct": 0.9,
            "entry_discount_pct": 7.5,
            "target_pct": 60.0,
            "sl_entry_pct": 60.0,
            "sl_reference_pct": 7.0,
        },
    )


def _monthly_status_result(status: MonthlyStatus = MonthlyStatus.BEAR) -> MonthlyStatusResult:
    return MonthlyStatusResult(
        status=status,
        trigger_name="BEAR_A_THRESHOLD",
        threshold_value=22100.0,
        reversal_dominated=False,
        candidates=[],
        notes="unit-test",
    )


def _market_levels() -> MarketLevels:
    return MarketLevels(
        d2hh=22500.0,
        d2ll=22300.0,
        d3hh=22400.0,
        d3ll=22200.0,
        current_day_high=22480.0,
        current_day_low=22340.0,
    )


def _session_context(*, day: int = 27, generated_at: datetime | None = None) -> S23PaperPreludeSessionContext:
    return S23PaperPreludeSessionContext(
        session_date=date(2026, 5, day),
        timezone="Asia/Kolkata",
        generated_at=generated_at or _ts(day, 9, 30, 3),
    )


def _snapshots(*, day: int = 27) -> tuple[S23PaperSnapshotInput, ...]:
    return (
        S23PaperSnapshotInput(
            snapshot_label=SnapshotLabel.AT_0915,
            open=22410.0,
            high=22425.0,
            low=22395.0,
            close=22420.0,
            bar_start=_ts(day, 9, 14),
            bar_end=_ts(day, 9, 15),
        ),
        S23PaperSnapshotInput(
            snapshot_label=SnapshotLabel.ORPT,
            open=22420.0,
            high=22455.0,
            low=22400.0,
            close=22448.0,
            bar_start=_ts(day, 9, 23, 59),
            bar_end=_ts(day, 9, 24, 59),
        ),
        S23PaperSnapshotInput(
            snapshot_label=SnapshotLabel.RC,
            open=22448.0,
            high=22462.0,
            low=22435.0,
            close=22440.0,
            bar_start=_ts(day, 9, 28, 59),
            bar_end=_ts(day, 9, 29, 59),
        ),
    )


def _option_chain_contract(
    *,
    symbol: str,
    strike: float,
    ltp: float | None,
    oi: float | None,
    expiry: date = date(2026, 5, 29),
    option_type: OptionType = OptionType.PUT,
) -> OptionChainContract:
    return OptionChainContract(
        symbol=symbol,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        bid=ltp - 1 if ltp is not None else None,
        ask=ltp + 1 if ltp is not None else None,
        ltp=ltp,
        oi=oi,
        volume=120.0,
    )


def _option_chain_snapshot(*contracts: OptionChainContract, day: int = 27) -> OptionChainSnapshotEvent:
    effective = _ts(day, 9, 29, 59)
    return OptionChainSnapshotEvent(
        envelope=EventEnvelope(
            event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
            session_date=effective.date(),
            effective_timestamp=effective,
            captured_at=effective + timedelta(seconds=1),
            timezone="Asia/Kolkata",
            source_type="unit_test",
            source_id="unit-test-option-chain",
            synthetic_fixture=True,
            normalized_by="unit-test",
        ),
        underlying_symbol="NIFTY",
        expiry=date(2026, 5, 29),
        contracts=contracts,
    )


def _expiry_governance(*, explicit_expiry_for_day: int) -> S23PaperExpiryGovernance:
    calendar = DeterministicExpiryCalendar(
        explicit_expiries={
            (ExpiryType.WEEKLY, date(2026, 5, explicit_expiry_for_day)): date(2026, 5, 29)
        }
    )
    return S23PaperExpiryGovernance(calendar)


def _request(**overrides: object) -> S23PaperLivePreludeRequest:
    base = {
        "strategy_rule": _strategy_rule(),
        "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        "monthly_status_result": _monthly_status_result(),
        "market_levels": _market_levels(),
        "runtime_values": {"OPT_PRV_3DLL": 216.22, "OPT_PRV_2DHH": 300.0},
        "option_chain_snapshot": _option_chain_snapshot(
            _option_chain_contract(
                symbol="NIFTY_20260529_22300_PE",
                strike=22300.0,
                ltp=198.0,
                oi=900.0,
            ),
            _option_chain_contract(
                symbol="NIFTY_20260529_22400_PE",
                strike=22400.0,
                ltp=270.0,
                oi=1200.0,
            ),
            _option_chain_contract(
                symbol="NIFTY_20260529_22500_PE",
                strike=22500.0,
                ltp=205.0,
                oi=1500.0,
            ),
        ),
        "snapshots": _snapshots(),
        "session_context": _session_context(),
        "expiry_governance": _expiry_governance(explicit_expiry_for_day=27),
        "lots": 2,
        "quantity": 100,
        "source_workbook_rule": "AB6_OS_Z186",
        "workbook_row_number": 186,
        "fsl_price": 352.0,
    }
    base.update(overrides)
    return S23PaperLivePreludeRequest(**base)


def _open_position_state() -> object:
    store = S23PaperPositionStateStore()
    return store.create_open_position_state(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260529_22400_PE",
        expiry_date=date(2026, 5, 29),
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=time(15, 15),
        no_carry_past_expiry=True,
        entry_date=date(2026, 5, 27),
        entry_timestamp=_ts(27, 9, 30),
        entry_price=199.5,
        lots=2,
        quantity=100,
        side="SELL",
        target_price=80.0,
        stoploss_price=320.0,
        fsl_price=352.0,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=_ts(27, 15, 20),
        provenance_source_ids=("paper_order_intent.json",),
    )


def test_fresh_session_prelude_generation() -> None:
    result = S23PaperLivePreludeBuilder().build(_request())

    assert result.mode is S23PaperPreludeMode.FRESH_ENTRY
    assert result.trade_plan_event is not None
    assert result.selected_contract_event is not None
    assert result.selected_contract_event.symbol == "NIFTY_20260529_22400_PE"
    assert result.trade_plan_event.strategy_branch == "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    assert result.trade_plan_event.order_reference_label == "RC"
    assert result.selected_contract_provenance == "runtime_option_chain_selection"
    assert [event.envelope.event_type for event in result.prelude_events] == [
        PaperEventType.CALENDAR_CONTEXT,
        PaperEventType.MONTHLY_STATUS_INPUT,
        PaperEventType.UNDERLYING_SNAPSHOT,
        PaperEventType.UNDERLYING_SNAPSHOT,
        PaperEventType.UNDERLYING_SNAPSHOT,
        PaperEventType.TRADE_PLAN_INPUT,
        PaperEventType.SELECTED_CONTRACT_QUOTE,
    ]


def test_fresh_session_falls_back_to_next_weekly_expiry_when_near_weekly_fails() -> None:
    result = S23PaperLivePreludeBuilder().build(
        _request(
            option_chain_snapshot=_option_chain_snapshot(
                _option_chain_contract(
                    symbol="NIFTY_20260529_22400_PE",
                    strike=22400.0,
                    ltp=200.0,
                    oi=100.0,
                    expiry=date(2026, 5, 29),
                ),
                _option_chain_contract(
                    symbol="NIFTY_20260605_22400_PE",
                    strike=22400.0,
                    ltp=270.0,
                    oi=1200.0,
                    expiry=date(2026, 6, 5),
                ),
            )
        )
    )

    assert result.selected_contract_event is not None
    assert result.selected_contract_event.symbol == "NIFTY_20260605_22400_PE"
    assert result.contract_selection is not None
    assert result.contract_selection.attempted_expiries == (
        date(2026, 5, 29),
        date(2026, 6, 5),
    )
    assert "Near expiry 2026-05-29 failed" in result.contract_selection.selection_reason


def test_fresh_session_uses_next_weekly_expiry_on_t_minus_1_even_when_near_weekly_qualifies() -> None:
    result = S23PaperLivePreludeBuilder().build(
        _request(
            session_context=_session_context(day=28, generated_at=_ts(28, 9, 30, 3)),
            snapshots=_snapshots(day=28),
            expiry_governance=_expiry_governance(explicit_expiry_for_day=28),
            option_chain_snapshot=_option_chain_snapshot(
                _option_chain_contract(
                    symbol="NIFTY_20260529_22400_PE",
                    strike=22400.0,
                    ltp=200.0,
                    oi=1200.0,
                    expiry=date(2026, 5, 29),
                ),
                _option_chain_contract(
                    symbol="NIFTY_20260605_22400_PE",
                    strike=22400.0,
                    ltp=205.0,
                    oi=1300.0,
                    expiry=date(2026, 6, 5),
                ),
                day=28,
            ),
        )
    )

    assert result.selected_contract_event is not None
    assert result.selected_contract_event.symbol == "NIFTY_20260605_22400_PE"
    assert result.contract_selection is not None
    assert result.contract_selection.attempted_expiries == (date(2026, 6, 5),)


def test_fresh_session_uses_next_weekly_expiry_on_expiry_day() -> None:
    result = S23PaperLivePreludeBuilder().build(
        _request(
            session_context=_session_context(day=29, generated_at=_ts(29, 9, 30, 3)),
            snapshots=_snapshots(day=29),
            expiry_governance=_expiry_governance(explicit_expiry_for_day=29),
            option_chain_snapshot=_option_chain_snapshot(
                _option_chain_contract(
                    symbol="NIFTY_20260529_22400_PE",
                    strike=22400.0,
                    ltp=200.0,
                    oi=1200.0,
                    expiry=date(2026, 5, 29),
                ),
                _option_chain_contract(
                    symbol="NIFTY_20260605_22400_PE",
                    strike=22400.0,
                    ltp=205.0,
                    oi=1300.0,
                    expiry=date(2026, 6, 5),
                ),
                day=29,
            ),
        )
    )

    assert result.selected_contract_event is not None
    assert result.selected_contract_event.symbol == "NIFTY_20260605_22400_PE"
    assert result.contract_selection is not None
    assert result.contract_selection.attempted_expiries == (date(2026, 6, 5),)


def test_fresh_session_fails_inside_rollover_window_when_next_weekly_expiry_missing() -> None:
    with pytest.raises(S23LivePreludeError) as exc_info:
        S23PaperLivePreludeBuilder().build(
            _request(
                session_context=_session_context(day=28, generated_at=_ts(28, 9, 30, 3)),
                snapshots=_snapshots(day=28),
                expiry_governance=_expiry_governance(explicit_expiry_for_day=28),
                option_chain_snapshot=_option_chain_snapshot(
                    _option_chain_contract(
                        symbol="NIFTY_20260529_22400_PE",
                        strike=22400.0,
                        ltp=200.0,
                        oi=1200.0,
                        expiry=date(2026, 5, 29),
                    ),
                    day=28,
                ),
            )
        )

    assert exc_info.value.code == PaperContractSelectionFailureCode.NO_CONTRACT_SELECTED.value
    assert "must use the next weekly expiry" in str(exc_info.value)


def test_missing_option_chain_fails_safely() -> None:
    with pytest.raises(S23LivePreludeError) as exc_info:
        S23PaperLivePreludeBuilder().build(_request(option_chain_snapshot=None))

    assert exc_info.value.code == PaperContractSelectionFailureCode.OPTION_CHAIN_MISSING.value


def test_missing_oi_fails_safely() -> None:
    with pytest.raises(S23LivePreludeError) as exc_info:
        S23PaperLivePreludeBuilder().build(
            _request(
                option_chain_snapshot=_option_chain_snapshot(
                    _option_chain_contract(
                        symbol="NIFTY_20260529_22400_PE",
                        strike=22400.0,
                        ltp=270.0,
                        oi=None,
                    )
                )
            )
        )

    assert exc_info.value.code == PaperContractSelectionFailureCode.MISSING_CONTRACT_OI.value


def test_branch_pinned_unknown_monthly_status_override_is_explicit() -> None:
    with pytest.raises(S23LivePreludeError) as exc_info:
        S23PaperLivePreludeBuilder().build(
            _request(monthly_status_result=_monthly_status_result(MonthlyStatus.UNKNOWN))
        )

    assert exc_info.value.code == "MONTHLY_STATUS_BRANCH_MISMATCH"

    result = S23PaperLivePreludeBuilder().build(
        _request(
            monthly_status_result=_monthly_status_result(MonthlyStatus.UNKNOWN),
            allow_branch_pinned_unknown_monthly_status=True,
        )
    )

    assert result.trade_plan_event is not None
    assert result.selected_contract_event is not None


def test_explicit_smoke_override_only_applies_when_enabled_and_is_provenance_tagged() -> None:
    builder = S23PaperLivePreludeBuilder()

    ignored = builder.build(
        _request(smoke_override_selected_contract_symbol="NIFTY_20260529_22400_PE")
    )
    applied = builder.build(
        _request(
            smoke_override_enabled=True,
            smoke_override_selected_contract_symbol="NIFTY_20260529_22400_PE",
        )
    )

    assert ignored.selected_contract_event is not None
    assert ignored.selected_contract_event.symbol == "NIFTY_20260529_22400_PE"
    assert applied.selected_contract_event is not None
    assert applied.selected_contract_event.symbol == "NIFTY_20260529_22400_PE"
    assert applied.selected_contract_provenance == "smoke_override"
    assert applied.selected_contract_event.envelope.data_quality_flags == (
        "smoke_override_selected_contract",
    )


def test_open_carry_forward_position_produces_resume_without_rollover_on_t_minus_1() -> None:
    result = S23PaperLivePreludeBuilder().build(
        _request(
            carry_forward_position=_open_position_state(),
            session_context=_session_context(day=28, generated_at=_ts(28, 9, 30, 3)),
            snapshots=_snapshots(day=28),
            expiry_governance=_expiry_governance(explicit_expiry_for_day=28),
            option_chain_snapshot=_option_chain_snapshot(day=28),
        )
    )

    assert result.mode is S23PaperPreludeMode.CARRY_FORWARD_RESUME
    assert result.trade_plan_event is None
    assert result.selected_contract_event is None
    assert result.resume_event is not None
    assert result.resume_event.event_type is S23PaperPositionStateEventType.PAPER_POSITION_RESUMED
    assert result.governance_events == ()


def test_open_carry_forward_position_on_t_minus_1_does_not_force_close_before_expiry() -> None:
    result = S23PaperLivePreludeBuilder().build(
        _request(
            carry_forward_position=_open_position_state(),
            session_context=_session_context(day=28, generated_at=_ts(28, 15, 20, 0)),
            snapshots=_snapshots(day=28),
            expiry_governance=_expiry_governance(explicit_expiry_for_day=28),
            option_chain_snapshot=_option_chain_snapshot(day=28),
        )
    )

    assert result.governance_events == ()


def test_unsupported_workbook_path_still_blocked() -> None:
    with pytest.raises(S23LivePreludeError, match="blocked") as exc_info:
        S23PaperLivePreludeBuilder().build(
            _request(
                source_workbook_rule="AB6_OS_J191",
                workbook_row_number=191,
            )
        )

    assert exc_info.value.code == "UNSUPPORTED_WORKBOOK_PATH"
