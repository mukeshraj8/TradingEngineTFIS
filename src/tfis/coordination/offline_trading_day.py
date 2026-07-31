from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable, Mapping

from tfis.domain.effective_execution_plan import EffectiveExecutionPath, EffectiveExecutionPlan, EffectiveExecutionPlanStatus
from tfis.domain.opening_market_context import OpeningContextStatus, OpeningGapClassification, OpeningMarketContext
from tfis.domain.premarket_plan import PreMarketPlanStatus, PreMarketStrategyPlan
from tfis.domain.trading_day_coordination import (
    CoordinationEventType,
    CoordinationFailure,
    CoordinationTransitionEvidence,
    OfflineCoordinationEvent,
    OfflineExecutionHandoff,
    OfflineHandoffAuthorityMode,
    TradingDayCoordinationResult,
    TradingDayCoordinationState,
    TradingDayPath,
)


@dataclass(frozen=True, slots=True)
class OfflineTradingDayCoordinationInput:
    coordination_id: str
    trading_date: object
    strategy_family: str
    strategy_definition: str
    strategy_version: str
    strategy_instance_id: str
    configuration_hash: str
    events: tuple[OfflineCoordinationEvent, ...]
    premarket_plan_factory: Callable[[], PreMarketStrategyPlan] | None = None
    opening_context_factory: Callable[[], OpeningMarketContext] | None = None
    effective_execution_plan_factory: Callable[[], EffectiveExecutionPlan] | None = None
    enabled: bool = True
    configuration_valid: bool = True
    carried_position_detected: bool = False
    position_cycle_id: str | None = None
    checkpoint_hash: str | None = None
    expected_checkpoint_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(self.events))


@dataclass(slots=True)
class _WorkingState:
    current: TradingDayCoordinationState
    daily_path: TradingDayPath
    terminal: TradingDayCoordinationState | None = None
    block_code: str | None = None
    block_reason: str | None = None
    premarket_plan: PreMarketStrategyPlan | None = None
    opening_context: OpeningMarketContext | None = None
    effective_plan: EffectiveExecutionPlan | None = None
    handoff: OfflineExecutionHandoff | None = None
    transitions: list[CoordinationTransitionEvidence] | None = None
    failures: list[CoordinationFailure] | None = None
    seen_events: dict[str, OfflineCoordinationEvent] | None = None
    startup_event_id: str | None = None
    premarket_event_id: str | None = None
    market_open_event_id: str | None = None
    orpt_event_id: str | None = None
    rc_event_id: str | None = None
    handoff_event_id: str | None = None

    def __post_init__(self) -> None:
        self.transitions = [] if self.transitions is None else self.transitions
        self.failures = [] if self.failures is None else self.failures
        self.seen_events = {} if self.seen_events is None else self.seen_events


class OfflineTradingDayCoordinator:
    schema_version = "tfis.offline_trading_day_coordination.v1"

    def coordinate(self, request: OfflineTradingDayCoordinationInput) -> TradingDayCoordinationResult:
        started = perf_counter()
        if request.expected_checkpoint_hash is not None and request.checkpoint_hash != request.expected_checkpoint_hash:
            return self._terminal(
                request,
                _WorkingState(TradingDayCoordinationState.BLOCKED, TradingDayPath.BLOCKED),
                "CHECKPOINT_HASH_MISMATCH",
                "Checkpoint hash does not match expected coordination checkpoint.",
                started,
            )
        if not request.enabled:
            return self._terminal(request, _WorkingState(TradingDayCoordinationState.DISABLED, TradingDayPath.NOT_APPLICABLE), None, None, started)
        if not request.configuration_valid:
            return self._terminal(
                request,
                _WorkingState(TradingDayCoordinationState.BLOCKED_CONFIGURATION, TradingDayPath.BLOCKED),
                "CONFIGURATION_INVALID",
                "Strategy configuration is invalid.",
                started,
            )
        state = _WorkingState(TradingDayCoordinationState.PREPARING_PREMARKET_PLAN, TradingDayPath.NOT_APPLICABLE)
        previous_sequence = -1
        for event in request.events:
            duplicate = self._duplicate_status(state, event)
            if duplicate == "IDEMPOTENT":
                continue
            if duplicate == "CONFLICT":
                return self._block(request, state, event, "CONFLICTING_DUPLICATE_EVENT", "Duplicate event id carries different business content.", started)
            if event.sequence_identity <= previous_sequence:
                return self._block(request, state, event, "EVENT_SEQUENCE_DISCONTINUITY", "Event sequence identities must strictly increase.", started)
            previous_sequence = event.sequence_identity
            if event.strategy_instance_id != request.strategy_instance_id:
                return self._block(request, state, event, "WRONG_STRATEGY_INSTANCE_EVENT", "Event strategy instance does not match coordination stream.", started)
            if event.trading_date != request.trading_date:
                return self._block(request, state, event, "WRONG_TRADING_DATE_EVENT", "Event trading date does not match coordination stream.", started)
            expected_instrument = self._expected_instrument(state)
            if expected_instrument is not None and event.instrument and event.instrument not in ("*", expected_instrument):
                return self._block(request, state, event, "WRONG_INSTRUMENT_EVENT", "Event instrument does not match the coordination artifacts.", started)
            state.seen_events[event.event_id] = event
            if event.event_type in (CoordinationEventType.OPERATOR_CANCELLED, CoordinationEventType.RISK_CANCELLED):
                return self._block(request, state, event, event.event_type.value, "Coordination was cancelled by supplied offline event.", started)
            if event.event_type is CoordinationEventType.SESSION_ENDED:
                return self._block(request, state, event, "SESSION_ENDED_BEFORE_HANDOFF", "Session ended before offline handoff completed.", started)
            handled = self._handle_event(request, state, event)
            if handled is not None:
                return self._block(request, state, event, handled[0], handled[1], started)
            if state.current is TradingDayCoordinationState.COMPLETED_OFFLINE:
                break
        if state.current in (
            TradingDayCoordinationState.COMPLETED_OFFLINE,
            TradingDayCoordinationState.CARRIED_POSITION_HANDOFF_REQUIRED,
            TradingDayCoordinationState.NO_ACTION_TODAY,
            TradingDayCoordinationState.DISABLED,
        ):
            return self._result(request, state, started)
        return self._terminal(
            request,
            state,
            "MISSING_REQUIRED_EVENT",
            "Event stream ended before the offline trading-day coordination completed.",
            started,
            missing=self._missing_events(state),
        )

    def _handle_event(self, request: OfflineTradingDayCoordinationInput, state: _WorkingState, event: OfflineCoordinationEvent) -> tuple[str, str] | None:
        if request.carried_position_detected:
            if event.event_type is CoordinationEventType.STARTUP_COMPLETED:
                state.startup_event_id = event.event_id
                self._transition(state, event, TradingDayCoordinationState.CARRIED_POSITION_HANDOFF_REQUIRED, "Carried position detected; fresh-entry path is not applicable.")
                state.daily_path = TradingDayPath.CARRIED_POSITION
                state.terminal = TradingDayCoordinationState.CARRIED_POSITION_HANDOFF_REQUIRED
                return None
            return "CARRIED_POSITION_ROUTED_TO_FRESH_ENTRY", "Carried-position stream must not enter fresh-entry events."
        if event.event_type is CoordinationEventType.STARTUP_COMPLETED:
            if state.current is not TradingDayCoordinationState.PREPARING_PREMARKET_PLAN:
                return "ILLEGAL_STARTUP_EVENT", "Startup event is only legal before pre-market preparation."
            state.startup_event_id = event.event_id
            self._transition(state, event, TradingDayCoordinationState.PREPARING_PREMARKET_PLAN, "Startup completed.")
            return None
        if event.event_type is CoordinationEventType.PREMARKET_DATA_READY:
            if state.startup_event_id is None:
                return "PREMARKET_BEFORE_STARTUP", "Pre-market data cannot be consumed before startup."
            plan = self._build_plan(request)
            if plan is None:
                return "MISSING_PREMARKET_INPUT", "Pre-market plan factory is required."
            state.premarket_plan = plan
            state.premarket_event_id = event.event_id
            if plan.plan_status is PreMarketPlanStatus.NO_ACTION_TODAY:
                self._transition(state, event, TradingDayCoordinationState.NO_ACTION_TODAY, "Pre-market plan reported no action today.")
                state.daily_path = TradingDayPath.NOT_APPLICABLE
                state.terminal = TradingDayCoordinationState.NO_ACTION_TODAY
                return None
            if plan.plan_status is not PreMarketPlanStatus.PREPARED:
                return "PREMARKET_PLAN_BLOCKED", plan.block_reason or "Pre-market plan did not prepare."
            self._transition(state, event, TradingDayCoordinationState.PREMARKET_PLAN_PREPARED, "Pre-market plan prepared.", self._artifact_hashes(state))
            self._transition(state, event, TradingDayCoordinationState.AWAITING_MARKET_OPEN, "Awaiting market-open evidence.", self._artifact_hashes(state))
            return None
        if event.event_type is CoordinationEventType.MARKET_OPEN_OBSERVED:
            if state.current is not TradingDayCoordinationState.AWAITING_MARKET_OPEN:
                return "MARKET_OPEN_BEFORE_PLAN", "Market-open evidence requires a prepared pre-market plan."
            context = self._build_context(request)
            if context is None:
                return "MISSING_OPENING_CONTEXT_INPUT", "Opening context factory is required."
            state.opening_context = context
            state.market_open_event_id = event.event_id
            if state.premarket_plan and (context.source_plan_id != state.premarket_plan.plan_id or context.source_plan_hash != state.premarket_plan.plan_hash):
                return "PLAN_CONTEXT_HASH_MISMATCH", "Opening context does not reference this pre-market plan."
            self._transition(state, event, TradingDayCoordinationState.OPENING_CONTEXT_BUILDING, "Opening context building.", self._artifact_hashes(state))
            if context.context_status is OpeningContextStatus.PARTIAL:
                plan = self._build_effective_plan(request)
                state.effective_plan = plan
                state.daily_path = TradingDayPath.INSUFFICIENT_EVIDENCE
                return "OPENING_CONTEXT_INCOMPLETE", "Opening context is partial."
            if context.context_status is not OpeningContextStatus.COMPLETE:
                return "OPENING_CONTEXT_BLOCKED", "Opening context is blocked."
            self._transition(state, event, TradingDayCoordinationState.OPENING_CONTEXT_READY, "Opening context ready.", self._artifact_hashes(state))
            if context.gap_context.classification in (OpeningGapClassification.NO_GAP, OpeningGapClassification.NOT_APPLICABLE):
                state.daily_path = TradingDayPath.NORMAL_FRESH_ENTRY
                self._transition(state, event, TradingDayCoordinationState.AWAITING_NORMAL_ORPT, "Normal path selected.", self._artifact_hashes(state))
            else:
                state.daily_path = TradingDayPath.GAP_RECALCULATION
                self._transition(state, event, TradingDayCoordinationState.AWAITING_RECALCULATION, "Gap/recalculation path selected.", self._artifact_hashes(state))
            return None
        if event.event_type is CoordinationEventType.ORPT_REACHED:
            if state.market_open_event_id is None:
                return "ORPT_BEFORE_MARKET_OPEN", "ORPT cannot precede market-open evidence."
            state.orpt_event_id = event.event_id
            if state.current is TradingDayCoordinationState.AWAITING_NORMAL_ORPT:
                plan = self._build_effective_plan(request)
                state.effective_plan = plan
                if plan is None or plan.plan_status is not EffectiveExecutionPlanStatus.READY_OFFLINE:
                    return "EFFECTIVE_PLAN_FAILURE", "Effective execution plan did not become ready."
                if state.opening_context and (plan.source_opening_context_id != state.opening_context.context_id or plan.source_opening_context_hash != state.opening_context.context_hash):
                    return "CONTEXT_EFFECTIVE_PLAN_HASH_MISMATCH", "Effective execution plan does not reference this opening context."
                if plan.path_classification is not EffectiveExecutionPath.NORMAL_RETAINED:
                    return "EFFECTIVE_PLAN_PATH_MISMATCH", "Normal path expected a retained effective plan."
                self._transition(state, event, TradingDayCoordinationState.EFFECTIVE_PLAN_READY, "Normal effective execution plan ready.", self._artifact_hashes(state))
                return None
            if state.current is TradingDayCoordinationState.AWAITING_RECALCULATION:
                self._transition(state, event, TradingDayCoordinationState.AWAITING_RECALCULATION, "ORPT observed for recalculation path.", self._artifact_hashes(state))
                return None
            return "ORPT_NOT_REQUIRED_OR_ILLEGAL", "ORPT event is not legal in the current state."
        if event.event_type is CoordinationEventType.RC_REACHED:
            if state.current is not TradingDayCoordinationState.AWAITING_RECALCULATION:
                return "RC_NOT_REQUIRED_OR_ILLEGAL", "RC event is only legal in recalculation path."
            if state.orpt_event_id is None:
                return "RC_BEFORE_ORPT", "RC cannot precede ORPT for recalculation path."
            state.rc_event_id = event.event_id
            plan = self._build_effective_plan(request)
            state.effective_plan = plan
            if plan is None or plan.plan_status is not EffectiveExecutionPlanStatus.READY_OFFLINE:
                return "EFFECTIVE_PLAN_FAILURE", "Effective execution plan did not become ready."
            if state.opening_context and (plan.source_opening_context_id != state.opening_context.context_id or plan.source_opening_context_hash != state.opening_context.context_hash):
                return "CONTEXT_EFFECTIVE_PLAN_HASH_MISMATCH", "Effective execution plan does not reference this opening context."
            if plan.path_classification is not EffectiveExecutionPath.GAP_RECALCULATED:
                return "EFFECTIVE_PLAN_PATH_MISMATCH", "Recalculation path expected a recalculated effective plan."
            self._transition(state, event, TradingDayCoordinationState.EFFECTIVE_PLAN_READY, "Recalculated effective execution plan ready.", self._artifact_hashes(state))
            return None
        if event.event_type is CoordinationEventType.OFFLINE_HANDOFF_REQUESTED:
            if state.current is not TradingDayCoordinationState.EFFECTIVE_PLAN_READY:
                return "HANDOFF_REQUESTED_TOO_EARLY", "Offline handoff requires a ready effective execution plan."
            if state.effective_plan is None or not state.effective_plan.offline_execution_candidate:
                return "EFFECTIVE_PLAN_NOT_HANDOFF_ELIGIBLE", "Effective plan is not an offline handoff candidate."
            state.handoff_event_id = event.event_id
            state.handoff = self._handoff(state.effective_plan)
            self._transition(state, event, TradingDayCoordinationState.OFFLINE_HANDOFF_READY, "Offline-only handoff produced.", self._artifact_hashes(state))
            self._transition(state, event, TradingDayCoordinationState.COMPLETED_OFFLINE, "Offline coordination completed.", self._artifact_hashes(state))
            state.terminal = TradingDayCoordinationState.COMPLETED_OFFLINE
            return None
        return "ILLEGAL_EVENT_FOR_STATE", f"Event {event.event_type.value} is not legal for state {state.current.value}."

    def _build_plan(self, request: OfflineTradingDayCoordinationInput) -> PreMarketStrategyPlan | None:
        return request.premarket_plan_factory() if request.premarket_plan_factory else None

    def _build_context(self, request: OfflineTradingDayCoordinationInput) -> OpeningMarketContext | None:
        return request.opening_context_factory() if request.opening_context_factory else None

    def _build_effective_plan(self, request: OfflineTradingDayCoordinationInput) -> EffectiveExecutionPlan | None:
        return request.effective_execution_plan_factory() if request.effective_execution_plan_factory else None

    def _handoff(self, plan: EffectiveExecutionPlan) -> OfflineExecutionHandoff:
        return OfflineExecutionHandoff(
            handoff_id=f"{plan.execution_plan_id}:offline-handoff",
            trading_date=plan.trading_date,
            strategy_instance_id=plan.strategy_instance_id,
            effective_execution_plan_id=plan.execution_plan_id,
            effective_execution_plan_hash=plan.execution_plan_hash,
            selected_contract=plan.selected_contract,
            order_side=plan.order_side,
            quantity=plan.quantity,
            lots=plan.lots,
            effective_entry=plan.values.effective_entry,
            effective_target=plan.values.effective_target,
            effective_msl=plan.values.effective_msl,
            authorized_placement_time=plan.values.revised_authorized_time,
            order_type=plan.values.order_type,
            authority_mode=OfflineHandoffAuthorityMode.OFFLINE_ONLY,
        )

    def _duplicate_status(self, state: _WorkingState, event: OfflineCoordinationEvent) -> str | None:
        existing = state.seen_events.get(event.event_id)
        if existing is None:
            return None
        return "IDEMPOTENT" if existing.to_dict() == event.to_dict() else "CONFLICT"

    def _expected_instrument(self, state: _WorkingState) -> str | None:
        if state.opening_context:
            return state.opening_context.underlying_instrument
        if state.premarket_plan:
            return state.premarket_plan.underlying_instrument
        return None

    def _transition(self, state: _WorkingState, event: OfflineCoordinationEvent, to_state: TradingDayCoordinationState, reason: str, artifacts: Mapping[str, str] | None = None) -> None:
        state.transitions.append(CoordinationTransitionEvidence(state.current, event.event_type, to_state, reason, artifacts or {}))
        state.current = to_state

    def _artifact_hashes(self, state: _WorkingState) -> dict[str, str]:
        values: dict[str, str] = {}
        if state.premarket_plan:
            values["premarket_plan"] = state.premarket_plan.plan_hash
        if state.opening_context:
            values["opening_context"] = state.opening_context.context_hash
        if state.effective_plan:
            values["effective_execution_plan"] = state.effective_plan.execution_plan_hash
        if state.handoff:
            values["offline_handoff"] = state.handoff.evidence_hash
        return values

    def _missing_events(self, state: _WorkingState) -> tuple[str, ...]:
        missing: list[str] = []
        if state.startup_event_id is None:
            missing.append(CoordinationEventType.STARTUP_COMPLETED.value)
        if state.premarket_event_id is None:
            missing.append(CoordinationEventType.PREMARKET_DATA_READY.value)
        if state.market_open_event_id is None:
            missing.append(CoordinationEventType.MARKET_OPEN_OBSERVED.value)
        if state.daily_path is TradingDayPath.NORMAL_FRESH_ENTRY and state.orpt_event_id is None:
            missing.append(CoordinationEventType.ORPT_REACHED.value)
        if state.daily_path is TradingDayPath.GAP_RECALCULATION and state.rc_event_id is None:
            missing.append(CoordinationEventType.RC_REACHED.value)
        if state.handoff_event_id is None and state.daily_path not in (TradingDayPath.CARRIED_POSITION, TradingDayPath.INSUFFICIENT_EVIDENCE):
            missing.append(CoordinationEventType.OFFLINE_HANDOFF_REQUESTED.value)
        return tuple(missing)

    def _block(self, request: OfflineTradingDayCoordinationInput, state: _WorkingState, event: OfflineCoordinationEvent, code: str, reason: str, started: float) -> TradingDayCoordinationResult:
        state.failures.append(CoordinationFailure(state.current, event.event_id, code, reason))
        state.block_code = code
        state.block_reason = reason
        state.terminal = TradingDayCoordinationState.BLOCKED
        self._transition(state, event, TradingDayCoordinationState.BLOCKED, reason, self._artifact_hashes(state))
        return self._result(request, state, started)

    def _terminal(self, request: OfflineTradingDayCoordinationInput, state: _WorkingState, code: str | None, reason: str | None, started: float, *, missing: tuple[str, ...] = ()) -> TradingDayCoordinationResult:
        if code:
            state.failures.append(CoordinationFailure(state.current, None, code, reason or code))
            state.block_code = code
            state.block_reason = reason
            state.terminal = TradingDayCoordinationState.BLOCKED
            state.current = TradingDayCoordinationState.BLOCKED
        return self._result(request, state, started, missing=missing)

    def _result(self, request: OfflineTradingDayCoordinationInput, state: _WorkingState, started: float, *, missing: tuple[str, ...] = ()) -> TradingDayCoordinationResult:
        plan = state.premarket_plan
        context = state.opening_context
        effective = state.effective_plan
        return TradingDayCoordinationResult(
            coordination_id=request.coordination_id,
            schema_version=self.schema_version,
            trading_date=request.trading_date,
            strategy_family=request.strategy_family,
            strategy_definition=request.strategy_definition,
            strategy_version=request.strategy_version,
            strategy_instance_id=request.strategy_instance_id,
            configuration_hash=request.configuration_hash,
            daily_path=state.daily_path,
            current_state=state.current,
            terminal_state=state.terminal,
            fresh_entry_eligible=not request.carried_position_detected and state.current not in (TradingDayCoordinationState.DISABLED, TradingDayCoordinationState.NO_ACTION_TODAY, TradingDayCoordinationState.CARRIED_POSITION_HANDOFF_REQUIRED),
            carried_position_status="DETECTED" if request.carried_position_detected else "NOT_DETECTED",
            block_code=state.block_code,
            block_reason=state.block_reason,
            premarket_plan_id=plan.plan_id if plan else None,
            premarket_plan_hash=plan.plan_hash if plan else None,
            opening_context_id=context.context_id if context else None,
            opening_context_hash=context.context_hash if context else None,
            effective_execution_plan_id=effective.execution_plan_id if effective else None,
            effective_execution_plan_hash=effective.execution_plan_hash if effective else None,
            execution_handoff_id=state.handoff.handoff_id if state.handoff else None,
            startup_event_id=state.startup_event_id,
            premarket_completion_event_id=state.premarket_event_id,
            market_open_event_id=state.market_open_event_id,
            orpt_event_id=state.orpt_event_id,
            rc_event_id=state.rc_event_id,
            effective_plan_ready_event_id=state.rc_event_id or state.orpt_event_id,
            offline_handoff_event_id=state.handoff_event_id,
            transition_evidence=tuple(state.transitions),
            missing_events=missing,
            derived_fields=("coordination_hash", "handoff_id") if state.handoff else ("coordination_hash",),
            supplemented_fields=("offline_fixture_events",),
            policy_identities=effective.policy_identities if effective else (plan.planned_values.policy_identities if plan else {}),
            failures=tuple(state.failures),
            offline_handoff=state.handoff,
            performance={"event_count": len(request.events), "coordination_seconds": perf_counter() - started},
        )
