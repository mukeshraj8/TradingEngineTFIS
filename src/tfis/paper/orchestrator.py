from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from tfis.domain.enums import MonthlyStatus, OptionType

from .guardrails import (
    PaperGuardrailDecision,
    S23PaperGuardrailEvaluator,
    S23PaperGuardrailSettings,
)
from .models import (
    CalendarContextEvent,
    CostSlippageSettingsEvent,
    MonthlyStatusInputEvent,
    OptionChainSnapshotEvent,
    PaperEventType,
    PaperReadinessStatus,
    PaperSessionConfigEvent,
    PaperSessionManifest,
    PaperTradePlanEvent,
    PaperSessionState,
    PaperValidationIssue,
    PaperValidationResult,
    SelectedContractBarEvent,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
    UnderlyingSnapshotEvent,
)
from .validation import (
    DEFAULT_MAX_QUOTE_AGE,
    PaperEvent,
    S23PaperContractValidator,
    S23PaperSessionManifestBuilder,
    required_snapshot_labels_for_config,
)


_TERMINAL_STATES = frozenset(
    {
        PaperSessionState.ORDER_PLANNED,
        PaperSessionState.NO_TRADE,
        PaperSessionState.ABORTED,
    }
)
_SNAPSHOT_ORDER = {
    SnapshotLabel.PRE_OPEN: 0,
    SnapshotLabel.AT_0915: 1,
    SnapshotLabel.ORPT: 2,
    SnapshotLabel.RC: 3,
    SnapshotLabel.EOD: 4,
}


@dataclass(frozen=True, slots=True)
class PaperAuditTrailEntry:
    timestamp: datetime
    previous_state: PaperSessionState
    new_state: PaperSessionState
    event_type: PaperEventType | None
    reason: str
    validation_result: PaperValidationResult | None = None
    terminal_code: str | None = None
    guardrail_code: str | None = None
    guardrail_message: str | None = None
    blocking_event_type: PaperEventType | None = None
    blocking_source_id: str | None = None
    operator_action_required: str | None = None


@dataclass(frozen=True, slots=True)
class S23PaperOrderPlan:
    strategy_code: str
    session_date: date
    selected_contract_symbol: str
    selected_contract_option_type: OptionType
    selected_contract_expiry: date
    selected_contract_ltp: float
    monthly_status: MonthlyStatus
    overlays_enabled: tuple[str, ...]
    required_snapshot_labels: tuple[SnapshotLabel, ...]
    planning_timestamp: datetime
    strategy_branch: str | None = None
    order_side: str | None = None
    lots: int | None = None
    quantity: int | None = None
    planned_entry_price: float | None = None
    target_price: float | None = None
    stoploss_price: float | None = None
    start_strike: float | None = None
    end_strike: float | None = None
    ideal_premium: float | None = None
    minimum_premium: float | None = None
    fsl_price: float | None = None
    order_reference_time: datetime | None = None
    order_reference_label: str | None = None
    source_workbook_rule: str | None = None
    workbook_row_number: int | None = None


@dataclass(frozen=True, slots=True)
class S23PaperSessionSnapshot:
    state: PaperSessionState
    manifest: PaperSessionManifest | None
    audit_events: tuple[PaperAuditTrailEntry, ...]
    order_plan: S23PaperOrderPlan | None
    selected_contract_quote: SelectedContractQuoteEvent | None
    latest_validation_result: PaperValidationResult | None
    latest_guardrail_decision: PaperGuardrailDecision | None


class S23PaperSessionOrchestrator:
    def __init__(
        self,
        *,
        validator: S23PaperContractValidator | None = None,
        manifest_builder: S23PaperSessionManifestBuilder | None = None,
        guardrail_settings: S23PaperGuardrailSettings | None = None,
        guardrail_evaluator: S23PaperGuardrailEvaluator | None = None,
        max_quote_age: timedelta = DEFAULT_MAX_QUOTE_AGE,
    ) -> None:
        self._validator = validator or S23PaperContractValidator()
        self._manifest_builder = manifest_builder or S23PaperSessionManifestBuilder()
        self._guardrail_evaluator = guardrail_evaluator or S23PaperGuardrailEvaluator(
            guardrail_settings
        )
        self._max_quote_age = max_quote_age

        self._state = PaperSessionState.NOT_STARTED
        self._manifest: PaperSessionManifest | None = None
        self._latest_validation_result: PaperValidationResult | None = None
        self._latest_guardrail_decision: PaperGuardrailDecision | None = None
        self._order_plan: S23PaperOrderPlan | None = None
        self._planned_order_count = 0
        self._audit_events: list[PaperAuditTrailEntry] = []

        self._calendar_context: CalendarContextEvent | None = None
        self._monthly_status_input: MonthlyStatusInputEvent | None = None
        self._paper_config: PaperSessionConfigEvent | None = None
        self._cost_settings: CostSlippageSettingsEvent | None = None
        self._underlying_quote: UnderlyingQuoteEvent | None = None
        self._option_chain_snapshot: OptionChainSnapshotEvent | None = None
        self._selected_contract_quote: SelectedContractQuoteEvent | None = None
        self._trade_plan_input: PaperTradePlanEvent | None = None
        self._snapshots: dict[SnapshotLabel, UnderlyingSnapshotEvent] = {}
        self._selected_contract_bars: dict[
            tuple[str, datetime, datetime], SelectedContractBarEvent
        ] = {}
        self._accepted_events: list[PaperEvent] = []

    def ingest_event(
        self,
        event: PaperEvent,
        *,
        now: datetime | None = None,
    ) -> S23PaperSessionSnapshot:
        evaluation_time = now or event.envelope.captured_at

        if self._state in _TERMINAL_STATES:
            decision = self._guardrail_evaluator.decision_for_terminal_event(
                current_state=self._state,
                event_type=event.envelope.event_type,
                source_id=event.envelope.source_id,
            )
            self._latest_guardrail_decision = decision
            self._refresh_manifest(evaluation_time)
            self._record_audit(
                timestamp=evaluation_time,
                previous_state=self._state,
                new_state=self._state,
                event_type=event.envelope.event_type,
                reason="event_rejected_after_terminal_state",
                terminal_code=decision.code,
                guardrail_decision=decision,
            )
            return self.snapshot()

        validation_result = self._validator.validate_event(event, now=evaluation_time)
        if validation_result.readiness_status is PaperReadinessStatus.ABORTED:
            self._transition(
                PaperSessionState.ABORTED,
                timestamp=evaluation_time,
                event_type=event.envelope.event_type,
                reason="event_validation_failed",
                validation_result=validation_result,
                terminal_code=(
                    validation_result.abort_reasons[0]
                    if validation_result.abort_reasons
                    else "event_validation_failed"
                ),
            )
            return self.snapshot()

        ingest_guard_result = self._validate_ingest_guardrails(event, now=evaluation_time)
        if ingest_guard_result is not None:
            self._transition(
                PaperSessionState.ABORTED,
                timestamp=evaluation_time,
                event_type=event.envelope.event_type,
                reason="ingest_guardrail_failed",
                validation_result=ingest_guard_result,
                terminal_code=(
                    ingest_guard_result.abort_reasons[0]
                    if ingest_guard_result.abort_reasons
                    else "ingest_guardrail_failed"
                ),
            )
            return self.snapshot()

        self._store_event(event)
        self._accepted_events.append(event)
        self._advance_state(now=evaluation_time, trigger_event_type=event.envelope.event_type)
        return self.snapshot()

    def finalize(self, *, now: datetime) -> S23PaperSessionSnapshot:
        if self._state in _TERMINAL_STATES:
            decision = self._guardrail_evaluator.decision_for_terminal_event(
                current_state=self._state,
                event_type=None,
                source_id=None,
            )
            self._latest_guardrail_decision = decision
            self._refresh_manifest(now)
            self._record_audit(
                timestamp=now,
                previous_state=self._state,
                new_state=self._state,
                event_type=None,
                reason="session_finalize_rejected_after_terminal_state",
                terminal_code=decision.code,
                guardrail_decision=decision,
            )
            return self.snapshot()

        self._advance_state(now=now, trigger_event_type=None)

        if self._state in _TERMINAL_STATES:
            return self.snapshot()

        if not self._has_pre_market_inputs():
            result = self._manual_result(
                readiness_status=PaperReadinessStatus.ABORTED,
                evaluated_state=self._state,
                timestamp=now,
                abort_issues=(
                    self._issue(
                        "session_missing_pre_market_inputs",
                        "S23 paper-session finalize requires calendar, status, config, and cost inputs.",
                        PaperReadinessStatus.ABORTED,
                    ),
                ),
            )
            self._transition(
                PaperSessionState.ABORTED,
                timestamp=now,
                event_type=None,
                reason="session_finalize_failed",
                validation_result=result,
                terminal_code="session_missing_pre_market_inputs",
            )
            return self.snapshot()

        readiness_result = self._build_readiness_result(now=now)
        if readiness_result.readiness_status is PaperReadinessStatus.ABORTED:
            self._transition(
                PaperSessionState.ABORTED,
                timestamp=now,
                event_type=None,
                reason="session_finalize_aborted",
                validation_result=readiness_result,
                terminal_code=(
                    readiness_result.abort_reasons[0]
                    if readiness_result.abort_reasons
                    else "session_finalize_aborted"
                ),
            )
            return self.snapshot()
        if readiness_result.readiness_status is PaperReadinessStatus.NO_TRADE:
            self._transition(
                PaperSessionState.NO_TRADE,
                timestamp=now,
                event_type=None,
                reason="session_finalize_no_trade",
                validation_result=readiness_result,
                terminal_code=(
                    readiness_result.no_trade_reasons[0]
                    if readiness_result.no_trade_reasons
                    else "session_finalize_no_trade"
                ),
            )
            return self.snapshot()

        if self._state is not PaperSessionState.DECISION_READY:
            self._transition(
                PaperSessionState.DECISION_READY,
                timestamp=now,
                event_type=None,
                reason="planning_inputs_ready",
                validation_result=readiness_result,
            )

        planning_guardrail = self._guardrail_evaluator.evaluate_pre_planning(
            paper_config=self._paper_config,
            option_chain_snapshot=self._option_chain_snapshot,
            selected_contract_quote=self._selected_contract_quote,
            validation_result=readiness_result,
            existing_order_plans=self._planned_order_count,
            source_ids=self._source_ids(),
        )
        if planning_guardrail is not None:
            guardrail_result = self._guardrail_evaluator.build_validation_result(
                planning_guardrail,
                evaluated_state=PaperSessionState.DECISION_READY,
                timestamp=now,
                required_snapshot_labels=readiness_result.required_snapshot_labels,
                missing_snapshot_labels=readiness_result.missing_snapshot_labels,
            )
            self._transition(
                planning_guardrail.terminal_state,
                timestamp=now,
                event_type=None,
                reason="planning_guardrail_blocked",
                validation_result=guardrail_result,
                terminal_code=planning_guardrail.code,
                guardrail_decision=planning_guardrail,
            )
            return self.snapshot()

        self._order_plan = self._build_order_plan(now=now)
        self._planned_order_count += 1
        order_planned_result = self._manual_result(
            readiness_status=PaperReadinessStatus.READY,
            evaluated_state=PaperSessionState.ORDER_PLANNED,
            timestamp=now,
            required_snapshot_labels=readiness_result.required_snapshot_labels,
        )
        self._transition(
            PaperSessionState.ORDER_PLANNED,
            timestamp=now,
            event_type=None,
            reason="paper_order_plan_created",
            validation_result=order_planned_result,
        )
        return self.snapshot()

    def snapshot(self) -> S23PaperSessionSnapshot:
        return S23PaperSessionSnapshot(
            state=self._state,
            manifest=self._manifest,
            audit_events=tuple(self._audit_events),
            order_plan=self._order_plan,
            selected_contract_quote=self._selected_contract_quote,
            latest_validation_result=self._latest_validation_result,
            latest_guardrail_decision=self._latest_guardrail_decision,
        )

    def _validate_ingest_guardrails(
        self,
        event: PaperEvent,
        *,
        now: datetime,
    ) -> PaperValidationResult | None:
        if isinstance(event, UnderlyingSnapshotEvent):
            if event.snapshot_label in self._snapshots:
                return self._manual_result(
                    readiness_status=PaperReadinessStatus.ABORTED,
                    evaluated_state=self._state,
                    timestamp=now,
                    abort_issues=(
                        self._issue(
                            f"duplicate_snapshot_{event.snapshot_label.value}",
                            f"Duplicate {event.snapshot_label.value} snapshot received for one S23 paper session.",
                            PaperReadinessStatus.ABORTED,
                            event_type=event.envelope.event_type,
                        ),
                    ),
                )
            latest_seen_order = max(
                (_SNAPSHOT_ORDER[label] for label in self._snapshots),
                default=-1,
            )
            if _SNAPSHOT_ORDER[event.snapshot_label] < latest_seen_order:
                return self._manual_result(
                    readiness_status=PaperReadinessStatus.ABORTED,
                    evaluated_state=self._state,
                    timestamp=now,
                    abort_issues=(
                        self._issue(
                            "late_snapshot_out_of_order",
                            "Snapshot events must arrive in non-decreasing session phase order.",
                            PaperReadinessStatus.ABORTED,
                            event_type=event.envelope.event_type,
                        ),
                    ),
                )
            return None

        if isinstance(event, SelectedContractBarEvent):
            bar_key = (event.symbol, event.bar_start, event.bar_end)
            if bar_key in self._selected_contract_bars:
                return self._manual_result(
                    readiness_status=PaperReadinessStatus.ABORTED,
                    evaluated_state=self._state,
                    timestamp=now,
                    abort_issues=(
                        self._issue(
                            "duplicate_selected_contract_bar",
                            "Duplicate selected-contract bar received for one S23 paper session.",
                            PaperReadinessStatus.ABORTED,
                            event_type=event.envelope.event_type,
                        ),
                    ),
                )
            return None

        if self._event_type_already_seen(event.envelope.event_type):
            return self._manual_result(
                readiness_status=PaperReadinessStatus.ABORTED,
                evaluated_state=self._state,
                timestamp=now,
                abort_issues=(
                    self._issue(
                        f"duplicate_{event.envelope.event_type.value.lower()}",
                        f"Duplicate {event.envelope.event_type.value} event received for one S23 paper session.",
                        PaperReadinessStatus.ABORTED,
                        event_type=event.envelope.event_type,
                    ),
                ),
            )

        if isinstance(event, UnderlyingQuoteEvent | SelectedContractQuoteEvent):
            if now < event.envelope.effective_timestamp:
                return self._manual_result(
                    readiness_status=PaperReadinessStatus.ABORTED,
                    evaluated_state=self._state,
                    timestamp=now,
                    abort_issues=(
                        self._issue(
                            "future_ingest_quote_timestamp",
                            "Paper quote events must not arrive from the future relative to ingestion time.",
                            PaperReadinessStatus.ABORTED,
                            event_type=event.envelope.event_type,
                        ),
                    ),
                )
            if now - event.envelope.effective_timestamp > self._max_quote_age:
                return self._manual_result(
                    readiness_status=PaperReadinessStatus.ABORTED,
                    evaluated_state=self._state,
                    timestamp=now,
                    abort_issues=(
                        self._issue(
                            "stale_ingest_quote",
                            "Paper quote event exceeded the allowed freshness window at ingestion time.",
                            PaperReadinessStatus.ABORTED,
                            event_type=event.envelope.event_type,
                        ),
                    ),
                )

        return None

    def _event_type_already_seen(self, event_type: PaperEventType) -> bool:
        return any(event.envelope.event_type is event_type for event in self._accepted_events)

    def _source_ids(self) -> dict[PaperEventType, str]:
        source_ids: dict[PaperEventType, str] = {}
        for event in self._accepted_events:
            source_ids.setdefault(event.envelope.event_type, event.envelope.source_id)
        return source_ids

    def _store_event(self, event: PaperEvent) -> None:
        if isinstance(event, CalendarContextEvent):
            self._calendar_context = event
        elif isinstance(event, MonthlyStatusInputEvent):
            self._monthly_status_input = event
        elif isinstance(event, PaperSessionConfigEvent):
            self._paper_config = event
        elif isinstance(event, CostSlippageSettingsEvent):
            self._cost_settings = event
        elif isinstance(event, UnderlyingQuoteEvent):
            self._underlying_quote = event
        elif isinstance(event, OptionChainSnapshotEvent):
            self._option_chain_snapshot = event
        elif isinstance(event, SelectedContractQuoteEvent):
            self._selected_contract_quote = event
        elif isinstance(event, PaperTradePlanEvent):
            self._trade_plan_input = event
        elif isinstance(event, UnderlyingSnapshotEvent):
            self._snapshots[event.snapshot_label] = event
        elif isinstance(event, SelectedContractBarEvent):
            self._selected_contract_bars[(event.symbol, event.bar_start, event.bar_end)] = event
        else:
            raise TypeError(f"Unsupported paper event type: {type(event)!r}")

    def _advance_state(
        self,
        *,
        now: datetime,
        trigger_event_type: PaperEventType | None,
    ) -> None:
        while self._state not in _TERMINAL_STATES:
            target_state, reason, validation_result, terminal_code = self._determine_transition(now=now)
            if target_state is None or target_state is self._state:
                break
            self._transition(
                target_state,
                timestamp=now,
                event_type=trigger_event_type,
                reason=reason,
                validation_result=validation_result,
                terminal_code=terminal_code,
            )

    def _determine_transition(
        self,
        *,
        now: datetime,
    ) -> tuple[
        PaperSessionState | None,
        str,
        PaperValidationResult | None,
        str | None,
    ]:
        if not self._has_pre_market_inputs():
            return None, "", None, None

        if self._paper_config is not None and not self._paper_config.same_day_square_off_only:
            result = self._manual_result(
                readiness_status=PaperReadinessStatus.ABORTED,
                evaluated_state=PaperSessionState.PRE_MARKET_READY,
                timestamp=now,
                abort_issues=(
                    self._issue(
                        "unsupported_continuation_path",
                        "Next-day continuation is blocked for the first S23 paper rollout.",
                        PaperReadinessStatus.ABORTED,
                        field_name="same_day_square_off_only",
                        event_type=PaperEventType.PAPER_SESSION_CONFIG,
                    ),
                ),
            )
            return (
                PaperSessionState.ABORTED,
                "unsupported_continuation_path",
                result,
                "unsupported_continuation_path",
            )

        if self._calendar_context is not None and self._calendar_context.is_holiday:
            result = self._manual_result(
                readiness_status=PaperReadinessStatus.NO_TRADE,
                evaluated_state=PaperSessionState.PRE_MARKET_READY,
                timestamp=now,
                no_trade_issues=(
                    self._issue(
                        "holiday_session_blocked",
                        "Holiday sessions must not trade.",
                        PaperReadinessStatus.NO_TRADE,
                        event_type=PaperEventType.CALENDAR_CONTEXT,
                    ),
                ),
            )
            return (
                PaperSessionState.NO_TRADE,
                "holiday_session_blocked",
                result,
                "holiday_session_blocked",
            )

        if (
            self._monthly_status_input is not None
            and self._monthly_status_input.monthly_status is MonthlyStatus.UNKNOWN
        ):
            result = self._manual_result(
                readiness_status=PaperReadinessStatus.NO_TRADE,
                evaluated_state=PaperSessionState.PRE_MARKET_READY,
                timestamp=now,
                no_trade_issues=(
                    self._issue(
                        "monthly_status_unknown",
                        "Monthly status UNKNOWN must result in NO_TRADE.",
                        PaperReadinessStatus.NO_TRADE,
                        event_type=PaperEventType.MONTHLY_STATUS_INPUT,
                    ),
                ),
            )
            return (
                PaperSessionState.NO_TRADE,
                "monthly_status_unknown",
                result,
                "monthly_status_unknown",
            )

        required_labels = self._required_snapshot_labels()
        if self._state is PaperSessionState.NOT_STARTED:
            result = self._manual_result(
                readiness_status=PaperReadinessStatus.READY,
                evaluated_state=PaperSessionState.PRE_MARKET_READY,
                timestamp=now,
                required_snapshot_labels=required_labels,
                missing_snapshot_labels=self._missing_snapshot_labels(required_labels),
            )
            return PaperSessionState.PRE_MARKET_READY, "pre_market_inputs_ready", result, None

        if (
            SnapshotLabel.AT_0915 in required_labels
            and SnapshotLabel.AT_0915 not in self._snapshots
        ):
            if self._state is not PaperSessionState.WAITING_FOR_0915:
                result = self._manual_result(
                    readiness_status=PaperReadinessStatus.READY,
                    evaluated_state=PaperSessionState.WAITING_FOR_0915,
                    timestamp=now,
                    required_snapshot_labels=required_labels,
                    missing_snapshot_labels=self._missing_snapshot_labels(required_labels),
                )
                return (
                    PaperSessionState.WAITING_FOR_0915,
                    "awaiting_0915_snapshot",
                    result,
                    None,
                )
            return None, "", None, None

        if SnapshotLabel.ORPT in required_labels and SnapshotLabel.ORPT not in self._snapshots:
            if self._state is not PaperSessionState.WAITING_FOR_ORPT:
                result = self._manual_result(
                    readiness_status=PaperReadinessStatus.READY,
                    evaluated_state=PaperSessionState.WAITING_FOR_ORPT,
                    timestamp=now,
                    required_snapshot_labels=required_labels,
                    missing_snapshot_labels=self._missing_snapshot_labels(required_labels),
                )
                return (
                    PaperSessionState.WAITING_FOR_ORPT,
                    "awaiting_orpt_snapshot",
                    result,
                    None,
                )
            return None, "", None, None

        if SnapshotLabel.RC in required_labels and SnapshotLabel.RC not in self._snapshots:
            if self._state is not PaperSessionState.WAITING_FOR_RC:
                result = self._manual_result(
                    readiness_status=PaperReadinessStatus.READY,
                    evaluated_state=PaperSessionState.WAITING_FOR_RC,
                    timestamp=now,
                    required_snapshot_labels=required_labels,
                    missing_snapshot_labels=self._missing_snapshot_labels(required_labels),
                )
                return (
                    PaperSessionState.WAITING_FOR_RC,
                    "awaiting_rc_snapshot",
                    result,
                    None,
                )
            return None, "", None, None

        if not self._has_decision_inputs():
            return None, "", None, None

        readiness_result = self._build_readiness_result(now=now)
        if readiness_result.readiness_status is PaperReadinessStatus.ABORTED:
            return (
                PaperSessionState.ABORTED,
                "session_readiness_aborted",
                readiness_result,
                readiness_result.abort_reasons[0]
                if readiness_result.abort_reasons
                else "session_readiness_aborted",
            )
        if readiness_result.readiness_status is PaperReadinessStatus.NO_TRADE:
            return (
                PaperSessionState.NO_TRADE,
                "session_readiness_no_trade",
                readiness_result,
                readiness_result.no_trade_reasons[0]
                if readiness_result.no_trade_reasons
                else "session_readiness_no_trade",
            )
        if self._state is not PaperSessionState.DECISION_READY:
            return PaperSessionState.DECISION_READY, "planning_inputs_ready", readiness_result, None
        return None, "", None, None

    def _build_readiness_result(self, *, now: datetime) -> PaperValidationResult:
        if not self._has_pre_market_inputs():
            return self._manual_result(
                readiness_status=PaperReadinessStatus.ABORTED,
                evaluated_state=self._state,
                timestamp=now,
                abort_issues=(
                    self._issue(
                        "session_missing_pre_market_inputs",
                        "S23 paper-session readiness requires calendar, status, config, and cost inputs.",
                        PaperReadinessStatus.ABORTED,
                    ),
                ),
            )

        required_labels = self._required_snapshot_labels()
        if self._underlying_quote is None:
            return self._manual_result(
                readiness_status=PaperReadinessStatus.NO_TRADE,
                evaluated_state=self._state,
                timestamp=now,
                required_snapshot_labels=required_labels,
                missing_snapshot_labels=self._missing_snapshot_labels(required_labels),
                no_trade_issues=(
                    self._issue(
                        "missing_underlying_quote",
                        "Decision-ready paper sessions require an underlying quote.",
                        PaperReadinessStatus.NO_TRADE,
                        event_type=PaperEventType.UNDERLYING_QUOTE,
                    ),
                ),
            )

        return self._validator.validate_session_readiness(
            calendar_context=self._calendar_context,
            monthly_status_input=self._monthly_status_input,
            paper_config=self._paper_config,
            cost_settings=self._cost_settings,
            underlying_quote=self._underlying_quote,
            snapshots=tuple(self._ordered_snapshots()),
            option_chain_snapshot=self._option_chain_snapshot,
            selected_contract_quote=self._selected_contract_quote,
            now=now,
            max_quote_age=self._max_quote_age,
            required_snapshot_labels=required_labels,
        )

    def _build_order_plan(self, *, now: datetime) -> S23PaperOrderPlan:
        assert self._paper_config is not None
        assert self._monthly_status_input is not None
        assert self._selected_contract_quote is not None
        assert self._selected_contract_quote.option_type is not None
        assert self._selected_contract_quote.expiry is not None
        assert self._selected_contract_quote.ltp is not None

        overlays: list[str] = []
        if self._paper_config.allow_recalculation:
            overlays.append("S23_RECALCULATION")
        if self._paper_config.allow_current_day_fsl_trp:
            overlays.append("S23_CURRENT_DAY_FSL_TRP")

        return S23PaperOrderPlan(
            strategy_code=self._paper_config.strategy_code,
            session_date=self._paper_config.envelope.session_date,
            selected_contract_symbol=self._selected_contract_quote.symbol,
            selected_contract_option_type=self._selected_contract_quote.option_type,
            selected_contract_expiry=self._selected_contract_quote.expiry,
            selected_contract_ltp=self._selected_contract_quote.ltp,
            monthly_status=self._monthly_status_input.monthly_status,
            overlays_enabled=tuple(overlays),
            required_snapshot_labels=self._required_snapshot_labels(),
            planning_timestamp=now,
            strategy_branch=(
                self._trade_plan_input.strategy_branch
                if self._trade_plan_input is not None
                else None
            ),
            order_side=(
                self._trade_plan_input.order_side
                if self._trade_plan_input is not None
                else None
            ),
            lots=(self._trade_plan_input.lots if self._trade_plan_input is not None else None),
            quantity=(self._trade_plan_input.quantity if self._trade_plan_input is not None else None),
            planned_entry_price=(
                self._trade_plan_input.planned_entry_price
                if self._trade_plan_input is not None
                else None
            ),
            target_price=(
                self._trade_plan_input.target_price
                if self._trade_plan_input is not None
                else None
            ),
            stoploss_price=(
                self._trade_plan_input.stoploss_price
                if self._trade_plan_input is not None
                else None
            ),
            start_strike=(
                self._trade_plan_input.start_strike
                if self._trade_plan_input is not None
                else None
            ),
            end_strike=(
                self._trade_plan_input.end_strike
                if self._trade_plan_input is not None
                else None
            ),
            ideal_premium=(
                self._trade_plan_input.ideal_premium
                if self._trade_plan_input is not None
                else None
            ),
            minimum_premium=(
                self._trade_plan_input.minimum_premium
                if self._trade_plan_input is not None
                else None
            ),
            fsl_price=(
                self._trade_plan_input.fsl_price
                if self._trade_plan_input is not None
                else None
            ),
            order_reference_time=(
                self._trade_plan_input.order_reference_time
                if self._trade_plan_input is not None
                else None
            ),
            order_reference_label=(
                self._trade_plan_input.order_reference_label
                if self._trade_plan_input is not None
                else None
            ),
            source_workbook_rule=(
                self._trade_plan_input.source_workbook_rule
                if self._trade_plan_input is not None
                else None
            ),
            workbook_row_number=(
                self._trade_plan_input.workbook_row_number
                if self._trade_plan_input is not None
                else None
            ),
        )

    def _transition(
        self,
        new_state: PaperSessionState,
        *,
        timestamp: datetime,
        event_type: PaperEventType | None,
        reason: str,
        validation_result: PaperValidationResult | None = None,
        terminal_code: str | None = None,
        guardrail_decision: PaperGuardrailDecision | None = None,
    ) -> None:
        previous_state = self._state
        self._state = new_state
        if validation_result is not None:
            self._latest_validation_result = validation_result

        resolved_guardrail = guardrail_decision
        if new_state is PaperSessionState.ORDER_PLANNED:
            self._latest_guardrail_decision = None
        elif new_state in {PaperSessionState.NO_TRADE, PaperSessionState.ABORTED}:
            if resolved_guardrail is None:
                resolved_guardrail = self._guardrail_evaluator.classify_validation_block(
                    validation_result,
                    source_ids=self._source_ids(),
                )
            self._latest_guardrail_decision = resolved_guardrail

        self._refresh_manifest(timestamp)
        self._record_audit(
            timestamp=timestamp,
            previous_state=previous_state,
            new_state=new_state,
            event_type=event_type,
            reason=reason,
            validation_result=validation_result,
            terminal_code=terminal_code,
            guardrail_decision=resolved_guardrail,
        )

    def _record_audit(
        self,
        *,
        timestamp: datetime,
        previous_state: PaperSessionState,
        new_state: PaperSessionState,
        event_type: PaperEventType | None,
        reason: str,
        validation_result: PaperValidationResult | None = None,
        terminal_code: str | None = None,
        guardrail_decision: PaperGuardrailDecision | None = None,
    ) -> None:
        self._audit_events.append(
            PaperAuditTrailEntry(
                timestamp=timestamp,
                previous_state=previous_state,
                new_state=new_state,
                event_type=event_type,
                reason=reason,
                validation_result=validation_result,
                terminal_code=terminal_code,
                guardrail_code=guardrail_decision.code if guardrail_decision is not None else None,
                guardrail_message=guardrail_decision.message if guardrail_decision is not None else None,
                blocking_event_type=(
                    guardrail_decision.blocking_event_type
                    if guardrail_decision is not None
                    else None
                ),
                blocking_source_id=(
                    guardrail_decision.blocking_source_id
                    if guardrail_decision is not None
                    else None
                ),
                operator_action_required=(
                    guardrail_decision.operator_action_required
                    if guardrail_decision is not None
                    else None
                ),
            )
        )

    def _refresh_manifest(self, generated_at: datetime) -> None:
        if (
            self._paper_config is None
            or self._cost_settings is None
            or self._latest_validation_result is None
        ):
            return
        self._manifest = self._manifest_builder.build(
            paper_config=self._paper_config,
            cost_settings=self._cost_settings,
            validation_result=self._latest_validation_result,
            events=tuple(self._accepted_events),
            generated_at=generated_at,
        )

    def _has_pre_market_inputs(self) -> bool:
        return (
            self._calendar_context is not None
            and self._monthly_status_input is not None
            and self._paper_config is not None
            and self._cost_settings is not None
        )

    def _has_decision_inputs(self) -> bool:
        return (
            self._underlying_quote is not None
            and self._option_chain_snapshot is not None
            and self._selected_contract_quote is not None
        )

    def _required_snapshot_labels(self) -> tuple[SnapshotLabel, ...]:
        if self._paper_config is None:
            return ()
        return required_snapshot_labels_for_config(self._paper_config)

    def _missing_snapshot_labels(
        self,
        required_labels: tuple[SnapshotLabel, ...],
    ) -> tuple[SnapshotLabel, ...]:
        return tuple(label for label in required_labels if label not in self._snapshots)

    def _ordered_snapshots(self) -> tuple[UnderlyingSnapshotEvent, ...]:
        return tuple(
            snapshot
            for _, snapshot in sorted(
                self._snapshots.items(),
                key=lambda item: _SNAPSHOT_ORDER[item[0]],
            )
        )

    def _issue(
        self,
        code: str,
        message: str,
        readiness_status: PaperReadinessStatus,
        *,
        field_name: str | None = None,
        event_type: PaperEventType | None = None,
    ) -> PaperValidationIssue:
        return PaperValidationIssue(
            code=code,
            message=message,
            readiness_status=readiness_status,
            field_name=field_name,
            event_type=event_type,
        )

    def _manual_result(
        self,
        *,
        readiness_status: PaperReadinessStatus,
        evaluated_state: PaperSessionState,
        timestamp: datetime,
        required_snapshot_labels: tuple[SnapshotLabel, ...] = (),
        missing_snapshot_labels: tuple[SnapshotLabel, ...] = (),
        warnings: tuple[str, ...] = (),
        no_trade_issues: tuple[PaperValidationIssue, ...] = (),
        abort_issues: tuple[PaperValidationIssue, ...] = (),
    ) -> PaperValidationResult:
        issues = tuple(no_trade_issues) + tuple(abort_issues)
        return PaperValidationResult(
            readiness_status=readiness_status,
            issues=issues,
            evaluated_state=evaluated_state,
            validated_at=timestamp,
            required_snapshot_labels=required_snapshot_labels,
            missing_snapshot_labels=missing_snapshot_labels,
            warnings=warnings,
            no_trade_reasons=tuple(issue.code for issue in no_trade_issues),
            abort_reasons=tuple(issue.code for issue in abort_issues),
        )
