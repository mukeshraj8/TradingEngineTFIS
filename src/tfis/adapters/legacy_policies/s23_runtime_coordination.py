from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from tfis.adapters.legacy_policies import s23_effective_execution_plan as effective
from tfis.adapters.legacy_policies import s23_opening_context as opening
from tfis.adapters.legacy_policies import s23_position_lifecycle as lifecycle
from tfis.adapters.legacy_policies import s23_premarket_plan as premarket
from tfis.adapters.legacy_policies import s23_vertical_slice as vertical
from tfis.coordination import OfflineTradingDayCoordinationInput
from tfis.runtime import (
    DeterministicRuntimeCoordinator,
    FreshEntryRuntimeCoordinator,
    NormalizedRuntimeEvent,
    PositionCycleRuntimeCoordinator,
    RuntimeEventType,
    RuntimeSimulationResult,
    RuntimeSubscriptionIndex,
)


TRADING_DATE = date(2026, 7, 30)
NIFTY = "NSE:NIFTY"
BANKNIFTY = "NSE:BANKNIFTY"
S23_BULL_A = "S23_NIFTY_ACCOUNT_A_PAPER"
S23_BULL_B = "S23_NIFTY_ACCOUNT_B_PAPER"
S23_BEAR_A = "S23_NIFTY_BEAR_ACCOUNT_A_PAPER"
POSITION_A = f"{S23_BULL_A}:CARRY:NIFTY24JUL22250CE"
POSITION_B = f"{S23_BULL_A}:CARRY:NIFTY24JUL22300CE"
CONTRACT_A = "NIFTY24JUL22250CE"
CONTRACT_B = "NIFTY24JUL22300CE"


def build_s23_runtime_normal_stream() -> RuntimeSimulationResult:
    subscriptions = _subscriptions()
    return DeterministicRuntimeCoordinator().run(
        trading_date=TRADING_DATE,
        events=_fresh_events(S23_BULL_A, gap=False),
        subscriptions=subscriptions,
        fresh_streams={"bull-normal": _fresh_stream(S23_BULL_A, "bull", "normal")},
        configuration_hash="m15-s23-runtime-config",
    )


def build_s23_runtime_gap_stream() -> RuntimeSimulationResult:
    subscriptions = _subscriptions()
    return DeterministicRuntimeCoordinator().run(
        trading_date=TRADING_DATE,
        events=_fresh_events(S23_BULL_A, gap=True),
        subscriptions=subscriptions,
        fresh_streams={"bull-gap": _fresh_stream(S23_BULL_A, "bull", "gap")},
        configuration_hash="m15-s23-runtime-config",
    )


def build_s23_runtime_carried_target_stream() -> RuntimeSimulationResult:
    subscriptions = _subscriptions()
    return DeterministicRuntimeCoordinator().run(
        trading_date=TRADING_DATE,
        events=_carried_events(POSITION_A, CONTRACT_A, include_rc=False, include_eod=False),
        subscriptions=subscriptions,
        position_streams={"target": _position_stream(POSITION_A, "target")},
        configuration_hash="m15-s23-runtime-config",
    )


def build_s23_runtime_carried_revised_sl_stream() -> RuntimeSimulationResult:
    subscriptions = _subscriptions()
    return DeterministicRuntimeCoordinator().run(
        trading_date=TRADING_DATE,
        events=_carried_events(POSITION_A, CONTRACT_A, include_rc=True, include_eod=True),
        subscriptions=subscriptions,
        position_streams={"revised-sl": _position_stream(POSITION_A, "revised_sl")},
        configuration_hash="m15-s23-runtime-config",
    )


def build_s23_runtime_multi_instance_stream() -> RuntimeSimulationResult:
    subscriptions = _subscriptions()
    subscriptions.add_strategy(S23_BULL_B, underlying=NIFTY, contract=CONTRACT_B)
    events = _fresh_events(S23_BULL_A, gap=False) + _fresh_events(S23_BULL_B, gap=False, sequence_offset=100)
    return DeterministicRuntimeCoordinator().run(
        trading_date=TRADING_DATE,
        events=events,
        subscriptions=subscriptions,
        fresh_streams={
            "bull-a": _fresh_stream(S23_BULL_A, "bull", "normal"),
            "bull-b": _fresh_stream(S23_BULL_B, "bull", "normal", account_b=True),
        },
        configuration_hash="m15-s23-runtime-config",
    )


def build_s23_runtime_multi_position_stream() -> RuntimeSimulationResult:
    subscriptions = _subscriptions()
    subscriptions.add_position(POSITION_B, underlying=NIFTY, contract=CONTRACT_B)
    events = _carried_events(POSITION_A, CONTRACT_A, include_rc=False, include_eod=False) + _carried_events(POSITION_B, CONTRACT_B, include_rc=False, include_eod=True, sequence_offset=100)
    return DeterministicRuntimeCoordinator().run(
        trading_date=TRADING_DATE,
        events=events,
        subscriptions=subscriptions,
        position_streams={
            "target-position": _position_stream(POSITION_A, "target"),
            "normal-position": _position_stream(POSITION_B, "normal_carry"),
        },
        configuration_hash="m15-s23-runtime-config",
    )


def build_s23_runtime_backpressure_stream(quote_count: int = 50) -> RuntimeSimulationResult:
    subscriptions = _subscriptions()
    events = tuple(
        _event(
            f"burst-{index}",
            RuntimeEventType.UNDERLYING_QUOTE,
            index + 1,
            instrument=NIFTY,
            payload={"ltp": 22400 + index, "bid": 22399 + index, "ask": 22401 + index},
        )
        for index in range(quote_count)
    ) + (_event("orpt", RuntimeEventType.ORPT_TIME, quote_count + 1, instrument=NIFTY), _event("rc", RuntimeEventType.RC_TIME, quote_count + 2, instrument=NIFTY))
    return DeterministicRuntimeCoordinator().run(
        trading_date=TRADING_DATE,
        events=events,
        subscriptions=subscriptions,
        configuration_hash="m15-s23-runtime-config",
    )


def _subscriptions() -> RuntimeSubscriptionIndex:
    subscriptions = RuntimeSubscriptionIndex()
    subscriptions.add_strategy(S23_BULL_A, underlying=NIFTY, contract=CONTRACT_A)
    subscriptions.add_strategy(S23_BEAR_A, underlying=NIFTY, contract=CONTRACT_A)
    subscriptions.add_position(POSITION_A, underlying=NIFTY, contract=CONTRACT_A)
    return subscriptions


def _fresh_stream(strategy_instance_id: str, branch: str, path: str, *, account_b: bool = False) -> FreshEntryRuntimeCoordinator:
    def factory(events):
        case = vertical.build_s23_bear_call_vertical_case() if branch == "bear" else vertical.build_s23_bull_call_vertical_case()
        runtime = case.runtime_input
        plan = premarket.build_s23_bear_call_premarket_plan() if branch == "bear" else premarket.build_s23_bull_call_premarket_plan()
        if account_b:
            plan = replace(plan, plan_id=f"{plan.plan_id}:account-b", strategy_instance_id=strategy_instance_id, business_hash="m15-account-b-plan", plan_hash="m15-account-b-plan")
        context_factory = opening.build_s23_bear_call_opening_context if branch == "bear" and path == "gap" else opening.build_s23_bull_call_opening_context
        if path == "normal":
            context = effective._normal_context(branch)
            if account_b:
                context = replace(context, context_id="m15-account-b-context", source_plan_id=plan.plan_id, source_plan_hash=plan.plan_hash, context_hash="")
            context_factory = lambda: context
        elif account_b:
            context = context_factory()
            context = replace(context, context_id="m15-account-b-gap-context", source_plan_id=plan.plan_id, source_plan_hash=plan.plan_hash, context_hash="")
            context_factory = lambda: context
        execution_factory = {
            ("bull", "normal"): effective.build_s23_bull_normal_execution_plan,
            ("bull", "gap"): effective.build_s23_bull_gap_execution_plan,
            ("bear", "normal"): effective.build_s23_bear_normal_execution_plan,
            ("bear", "gap"): effective.build_s23_bear_gap_execution_plan,
        }[(branch, path)]
        if account_b:
            execution_factory = lambda: effective._compose(case, context, force_missed=path == "gap", plan=plan)
        return OfflineTradingDayCoordinationInput(
            coordination_id=f"m15-{strategy_instance_id}-{branch}-{path}",
            trading_date=runtime.evaluated_at.date(),
            strategy_family=runtime.strategy_family_id or "S23",
            strategy_definition=runtime.strategy_definition_id or case.strategy_rule.unique_code,
            strategy_version=getattr(runtime, "strategy_version", None) or "1.0.0",
            strategy_instance_id=strategy_instance_id,
            configuration_hash=runtime.resolved_configuration_hash or "UNKNOWN",
            events=events,
            premarket_plan_factory=lambda: plan,
            opening_context_factory=context_factory,
            effective_execution_plan_factory=execution_factory,
        )

    return FreshEntryRuntimeCoordinator(strategy_instance_id, TRADING_DATE, factory)


def _position_stream(position_cycle_id: str, fixture: str) -> PositionCycleRuntimeCoordinator:
    def context_factory(_events):
        mapping = {
            "target": lifecycle.build_s23_bull_carried_target_exit_day,
            "normal_carry": lifecycle.build_s23_bull_carried_normal_day_carry,
            "normal_equal": lifecycle.build_s23_bull_carried_normal_day_equal_carry,
            "square_off": lifecycle.build_s23_bull_carried_normal_day_square_off,
            "revised_sl": lifecycle.build_s23_bull_carried_adverse_day_revised_fsl_carry,
            "missing_rc": lifecycle.build_s23_missing_rc_lifecycle,
        }
        built = mapping[fixture]()
        context = built.lifecycle_fixture.context if hasattr(built, "lifecycle_fixture") else built.context
        if context.position_snapshot and context.position_snapshot.position_cycle_id != position_cycle_id:
            position = replace(context.position_snapshot, position_cycle_id=position_cycle_id)
            context = replace(context, position_snapshot=position, context_id=f"{context.context_id}:{position_cycle_id}", context_hash="")
        return context

    def eod_factory(context):
        mapping = {
            "normal_carry": lifecycle.build_s23_bull_carried_normal_day_carry,
            "normal_equal": lifecycle.build_s23_bull_carried_normal_day_equal_carry,
            "square_off": lifecycle.build_s23_bull_carried_normal_day_square_off,
            "revised_sl": lifecycle.build_s23_bull_carried_adverse_day_revised_fsl_carry,
        }
        return mapping[fixture]().trading_day.eod_decision

    return PositionCycleRuntimeCoordinator(position_cycle_id, TRADING_DATE, context_factory, eod_factory if fixture in {"normal_carry", "normal_equal", "square_off", "revised_sl"} else None)


def _fresh_events(strategy_instance_id: str, *, gap: bool, sequence_offset: int = 0) -> tuple[NormalizedRuntimeEvent, ...]:
    base = (
        _event("config", RuntimeEventType.CONFIGURATION_READY, sequence_offset + 1, instrument=NIFTY, strategy=strategy_instance_id),
        _event("enabled", RuntimeEventType.STRATEGY_ENABLED, sequence_offset + 2, instrument=NIFTY, strategy=strategy_instance_id),
        _event("premarket", RuntimeEventType.PREMARKET_PREPARATION_TIME, sequence_offset + 3, instrument=NIFTY, strategy=strategy_instance_id),
        _event("open", RuntimeEventType.SESSION_OPEN_OBSERVATION, sequence_offset + 4, instrument=NIFTY, strategy=strategy_instance_id, payload={"opening_value": 22410.0}),
        _event("orpt", RuntimeEventType.ORPT_TIME, sequence_offset + 5, instrument=NIFTY, strategy=strategy_instance_id),
    )
    if not gap:
        return base + (_event("handoff", RuntimeEventType.EOD_EVALUATION_TIME, sequence_offset + 6, instrument=NIFTY, strategy=strategy_instance_id),)
    return base + (
        _event("rc-quote", RuntimeEventType.OPTION_CONTRACT_QUOTE, sequence_offset + 6, instrument=NIFTY, contract=CONTRACT_A, strategy=strategy_instance_id, payload={"ltp": 252.0, "observation": "RC"}),
        _event("rc", RuntimeEventType.RC_TIME, sequence_offset + 7, instrument=NIFTY, strategy=strategy_instance_id),
        _event("handoff", RuntimeEventType.EOD_EVALUATION_TIME, sequence_offset + 8, instrument=NIFTY, strategy=strategy_instance_id),
    )


def _carried_events(position_cycle_id: str, contract: str, *, include_rc: bool, include_eod: bool, sequence_offset: int = 0) -> tuple[NormalizedRuntimeEvent, ...]:
    events = [
        _event("reconcile", RuntimeEventType.POSITION_RECONCILIATION_AVAILABLE, sequence_offset + 1, instrument=NIFTY, contract=contract, position=position_cycle_id),
        _event("open", RuntimeEventType.SESSION_OPEN_OBSERVATION, sequence_offset + 2, instrument=NIFTY, contract=contract, position=position_cycle_id, payload={"opening_value": 22410.0}),
        _event("orpt-quote", RuntimeEventType.OPTION_CONTRACT_QUOTE, sequence_offset + 3, instrument=NIFTY, contract=contract, position=position_cycle_id, payload={"ltp": 300.0, "current_day_high": 300.0, "observation": "ORPT"}),
        _event("orpt", RuntimeEventType.ORPT_TIME, sequence_offset + 4, instrument=NIFTY, contract=contract, position=position_cycle_id),
    ]
    if include_rc:
        events.extend(
            [
                _event("rc-quote", RuntimeEventType.OPTION_CONTRACT_QUOTE, sequence_offset + 5, instrument=NIFTY, contract=contract, position=position_cycle_id, payload={"ltp": 335.0, "current_day_high": 335.0, "observation": "RC"}),
                _event("rc", RuntimeEventType.RC_TIME, sequence_offset + 6, instrument=NIFTY, contract=contract, position=position_cycle_id),
            ]
        )
    if include_eod:
        events.append(_event("eod", RuntimeEventType.EOD_EVALUATION_TIME, sequence_offset + 7, instrument=NIFTY, contract=contract, position=position_cycle_id, payload={"ltp": 250.0}))
    return tuple(events)


def _event(
    label: str,
    event_type: RuntimeEventType,
    sequence: int,
    *,
    instrument: str,
    contract: str | None = None,
    strategy: str | None = None,
    position: str | None = None,
    payload: dict | None = None,
) -> NormalizedRuntimeEvent:
    ts = datetime.combine(TRADING_DATE, _time_for(event_type), tzinfo=ZoneInfo("Asia/Kolkata"))
    target = strategy or position or "market"
    return NormalizedRuntimeEvent(
        event_id=f"m15-{target}-{label}-{sequence}",
        event_type=event_type,
        trading_date=TRADING_DATE,
        exchange="NSE",
        session="REGULAR",
        effective_timestamp=ts,
        source_timestamp=ts,
        dispatch_timestamp=ts,
        sequence_identity=sequence,
        instrument_identity=instrument,
        contract_identity=contract,
        strategy_instance_target=strategy,
        position_cycle_target=position,
        provenance={"source": "phase3d_m15_s23_runtime_fixture"},
        payload=payload or {},
    )


def _time_for(event_type: RuntimeEventType) -> time:
    values = {
        RuntimeEventType.CONFIGURATION_READY: time(8, 45),
        RuntimeEventType.STRATEGY_ENABLED: time(8, 46),
        RuntimeEventType.POSITION_RECONCILIATION_AVAILABLE: time(8, 55),
        RuntimeEventType.PREMARKET_PREPARATION_TIME: time(9, 0),
        RuntimeEventType.SESSION_OPEN_OBSERVATION: time(9, 15),
        RuntimeEventType.MARKET_OPEN_TIME: time(9, 15),
        RuntimeEventType.UNDERLYING_QUOTE: time(9, 15, 1),
        RuntimeEventType.OPTION_CONTRACT_QUOTE: time(9, 19, 58),
        RuntimeEventType.ORPT_TIME: time(9, 19, 59),
        RuntimeEventType.RC_TIME: time(9, 29, 59),
        RuntimeEventType.EOD_EVALUATION_TIME: time(15, 0),
        RuntimeEventType.SESSION_END_TIME: time(15, 30),
    }
    return values.get(event_type, time(9, 0))
