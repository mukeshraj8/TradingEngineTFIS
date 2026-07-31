from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from tfis.adapters.legacy_policies import s23_effective_execution_plan as effective
from tfis.adapters.legacy_policies import s23_opening_context as opening
from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.coordination import OfflineTradingDayCoordinationInput, OfflineTradingDayCoordinator
from tfis.domain import TFISContractIdentity
from tfis.domain.trading_day_coordination import CoordinationEventType, OfflineCoordinationEvent, TradingDayCoordinationResult


def build_s23_bull_normal_trading_day() -> TradingDayCoordinationResult:
    case = vertical.build_s23_bull_call_vertical_case()
    return _coordinate(
        "m12-s23-bull-normal",
        case,
        premarket.build_s23_bull_call_premarket_plan,
        lambda: effective._normal_context("bull"),
        effective.build_s23_bull_normal_execution_plan,
        _normal_events(case.runtime_input.strategy_instance_id),
    )


def build_s23_bull_gap_trading_day() -> TradingDayCoordinationResult:
    case = vertical.build_s23_bull_call_vertical_case()
    return _coordinate(
        "m12-s23-bull-gap",
        case,
        premarket.build_s23_bull_call_premarket_plan,
        opening.build_s23_bull_call_opening_context,
        effective.build_s23_bull_gap_execution_plan,
        _gap_events(case.runtime_input.strategy_instance_id),
    )


def build_s23_bear_normal_trading_day() -> TradingDayCoordinationResult:
    case = vertical.build_s23_bear_call_vertical_case()
    return _coordinate(
        "m12-s23-bear-normal",
        case,
        premarket.build_s23_bear_call_premarket_plan,
        lambda: effective._normal_context("bear"),
        effective.build_s23_bear_normal_execution_plan,
        _normal_events(case.runtime_input.strategy_instance_id),
    )


def build_s23_bear_gap_trading_day() -> TradingDayCoordinationResult:
    case = vertical.build_s23_bear_call_vertical_case()
    return _coordinate(
        "m12-s23-bear-gap",
        case,
        premarket.build_s23_bear_call_premarket_plan,
        opening.build_s23_bear_call_opening_context,
        effective.build_s23_bear_gap_execution_plan,
        _gap_events(case.runtime_input.strategy_instance_id),
    )


def build_s23_partial_real_blocked_trading_day() -> TradingDayCoordinationResult:
    case = vertical.build_s23_bull_call_vertical_case()
    context = opening.build_s23_partial_real_opening_context()
    plan = _partial_real_plan(context.selected_contract, context.trading_date, context.source_plan_hash)
    return _coordinate(
        "m12-s23-partial-real",
        case,
        lambda: plan,
        opening.build_s23_partial_real_opening_context,
        effective.build_s23_partial_real_execution_plan,
        _gap_events(case.runtime_input.strategy_instance_id, trading_date=context.trading_date),
        trading_date=context.trading_date,
    )


def build_s23_carried_position_trading_day() -> TradingDayCoordinationResult:
    case = vertical.build_s23_bull_call_vertical_case()
    return _coordinate(
        "m12-s23-carried-position",
        case,
        None,
        None,
        None,
        (_event("startup", case.runtime_input.strategy_instance_id, 1, CoordinationEventType.STARTUP_COMPLETED),),
        carried_position_detected=True,
        position_cycle_id="S23_NIFTY_CARRY_FORWARD_FIXTURE",
    )


def _coordinate(
    coordination_id: str,
    case: vertical.S23VerticalSliceCase,
    plan_factory,
    context_factory,
    execution_plan_factory,
    events: tuple[OfflineCoordinationEvent, ...],
    *,
    carried_position_detected: bool = False,
    position_cycle_id: str | None = None,
    trading_date: date | None = None,
) -> TradingDayCoordinationResult:
    runtime = case.runtime_input
    return OfflineTradingDayCoordinator().coordinate(
        OfflineTradingDayCoordinationInput(
            coordination_id=coordination_id,
            trading_date=trading_date or runtime.evaluated_at.date(),
            strategy_family=runtime.strategy_family_id or "S23",
            strategy_definition=runtime.strategy_definition_id or case.strategy_rule.unique_code,
            strategy_version=getattr(runtime, "strategy_version", None) or "1.0.0",
            strategy_instance_id=runtime.strategy_instance_id or "S23_NIFTY_ACCOUNT_A_PAPER",
            configuration_hash=runtime.resolved_configuration_hash or "UNKNOWN",
            events=events,
            premarket_plan_factory=plan_factory,
            opening_context_factory=context_factory,
            effective_execution_plan_factory=execution_plan_factory,
            carried_position_detected=carried_position_detected,
            position_cycle_id=position_cycle_id,
        )
    )


def _normal_events(strategy_instance_id: str, *, trading_date: date = date(2026, 7, 30)) -> tuple[OfflineCoordinationEvent, ...]:
    return (
        _event("startup", strategy_instance_id, 1, CoordinationEventType.STARTUP_COMPLETED, trading_date=trading_date),
        _event("premarket", strategy_instance_id, 2, CoordinationEventType.PREMARKET_DATA_READY, trading_date=trading_date),
        _event("market-open", strategy_instance_id, 3, CoordinationEventType.MARKET_OPEN_OBSERVED, trading_date=trading_date),
        _event("orpt", strategy_instance_id, 4, CoordinationEventType.ORPT_REACHED, trading_date=trading_date),
        _event("handoff", strategy_instance_id, 5, CoordinationEventType.OFFLINE_HANDOFF_REQUESTED, trading_date=trading_date),
    )


def _gap_events(strategy_instance_id: str, *, trading_date: date = date(2026, 7, 30)) -> tuple[OfflineCoordinationEvent, ...]:
    return (
        _event("startup", strategy_instance_id, 1, CoordinationEventType.STARTUP_COMPLETED, trading_date=trading_date),
        _event("premarket", strategy_instance_id, 2, CoordinationEventType.PREMARKET_DATA_READY, trading_date=trading_date),
        _event("market-open", strategy_instance_id, 3, CoordinationEventType.MARKET_OPEN_OBSERVED, trading_date=trading_date),
        _event("orpt", strategy_instance_id, 4, CoordinationEventType.ORPT_REACHED, trading_date=trading_date),
        _event("rc", strategy_instance_id, 5, CoordinationEventType.RC_REACHED, trading_date=trading_date),
        _event("handoff", strategy_instance_id, 6, CoordinationEventType.OFFLINE_HANDOFF_REQUESTED, trading_date=trading_date),
    )


def _event(label: str, strategy_instance_id: str, sequence: int, event_type: CoordinationEventType, *, trading_date: date = date(2026, 7, 30), instrument: str = "NSE:NIFTY") -> OfflineCoordinationEvent:
    event_time = _event_time(trading_date, event_type)
    return OfflineCoordinationEvent(
        event_id=f"m12-{strategy_instance_id}-{label}",
        strategy_instance_id=strategy_instance_id,
        trading_date=trading_date,
        event_type=event_type,
        effective_timestamp=event_time,
        source_timestamp=event_time,
        source_classification="OFFLINE_FIXTURE",
        provenance={"source": "phase3d_m12_s23_fixture"},
        sequence_identity=sequence,
        instrument=instrument,
    )


def _event_time(trading_date: date, event_type: CoordinationEventType) -> datetime:
    times = {
        CoordinationEventType.STARTUP_COMPLETED: time(8, 45),
        CoordinationEventType.PREMARKET_DATA_READY: time(9, 0),
        CoordinationEventType.MARKET_OPEN_OBSERVED: time(9, 15),
        CoordinationEventType.ORPT_REACHED: time(9, 19, 59),
        CoordinationEventType.RC_REACHED: time(9, 29, 59),
        CoordinationEventType.OFFLINE_HANDOFF_REQUESTED: time(9, 30),
    }
    return datetime.combine(trading_date, times.get(event_type, time(15, 30)), tzinfo=ZoneInfo("Asia/Kolkata"))


def _partial_real_plan(selected: TFISContractIdentity, trading_date: date, plan_hash: str):
    return opening._replace_plan_selected_contract_for_partial_real(
        premarket.build_s23_bull_call_premarket_plan(),
        selected,
        trading_date,
        plan_hash,
    )
