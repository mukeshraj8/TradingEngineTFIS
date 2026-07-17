from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from .guardrails import (
    PaperGuardrailDecision,
    S23PaperGuardrailEvaluator,
    S23PaperGuardrailSettings,
)
from .models import (
    PaperReadinessStatus,
    PaperSessionState,
    SelectedContractBarEvent,
    SelectedContractQuoteEvent,
)
from .replay_bundle import S23PaperReplayBundleManager
from .review import S23PaperReviewError, S23PaperSessionReviewer
from .runtime_contract import PaperTradeShellContract
from .validation import DEFAULT_MAX_QUOTE_AGE

_ARTIFACT_VERSION = 1
_PENDING_EVENT_TYPE = "PAPER_ORDER_PENDING"
_FILLED_EVENT_TYPE = "PAPER_ORDER_FILLED"
_NOT_FILLED_EVENT_TYPE = "PAPER_ORDER_NOT_FILLED"
_ABORTED_EVENT_TYPE = "PAPER_FILL_ABORTED"
_PHASE1_FILL_DISCLAIMER = (
    "No broker order was placed, no real-money order was routed, no live "
    "position was opened, and no target/SL lifecycle monitoring occurred yet; "
    "this artifact covers Phase 1 fill or no-fill simulation only."
)
_SUPPORTED_INPUT_TERMINAL_STATES = frozenset({PaperSessionState.ORDER_PLANNED})
_FINAL_FILL_STATUSES = frozenset(
    {
        _FILLED_EVENT_TYPE,
        _NOT_FILLED_EVENT_TYPE,
        _ABORTED_EVENT_TYPE,
    }
)


class S23PaperFillStatus(str, Enum):
    PAPER_ORDER_PENDING = _PENDING_EVENT_TYPE
    PAPER_ORDER_FILLED = _FILLED_EVENT_TYPE
    PAPER_ORDER_NOT_FILLED = _NOT_FILLED_EVENT_TYPE
    PAPER_FILL_ABORTED = _ABORTED_EVENT_TYPE


class S23PaperFillSimulatorError(RuntimeError):
    """Raised when Phase 1 S23 paper fill simulation cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class S23PaperFillDecision:
    artifact_version: int
    session_id: str
    session_date: date
    strategy_code: str
    status: S23PaperFillStatus
    planned_entry_price: float
    selected_contract_symbol: str
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    order_reference_time: datetime | None
    order_reference_label: str | None
    handoff_boundary_timestamp: datetime
    fill_price: float | None
    fill_timestamp: datetime | None
    source_kind: str | None
    source_type: str | None
    source_id: str | None
    source_effective_timestamp: datetime | None
    spread_points: float | None
    slippage_entry_points: float | None
    quote_bid: float | None
    quote_ask: float | None
    quote_ltp: float | None
    bar_high: float | None
    bar_low: float | None
    market_event_count: int
    reason_code: str
    message: str
    no_fill_reason: str | None
    operator_action_required: str | None
    guardrail_code: str | None
    guardrail_message: str | None
    blocking_source_id: str | None
    disclaimer: str


@dataclass(frozen=True, slots=True)
class S23PaperFillArtifactSet:
    session_directory: Path
    paper_order_pending_path: Path | None
    paper_fill_path: Path | None
    paper_no_fill_path: Path | None
    paper_fill_abort_summary_path: Path | None
    execution_journal_path: Path
    execution_summary_path: Path


@dataclass(frozen=True, slots=True)
class _FillContext:
    session_directory: Path
    session_id: str
    session_date: date
    strategy_code: str
    terminal_state: PaperSessionState
    selected_contract_symbol: str
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    selected_contract_effective_timestamp: datetime | None
    planned_entry_price: float
    order_reference_time: datetime | None
    order_reference_label: str | None
    slippage_entry_points: float
    execution_summary_payload: dict[str, Any]
    execution_journal_rows: tuple[dict[str, Any], ...]
    replay_bundle_valid: bool | None
    replay_bundle_validation_performed: bool
    replay_bundle_errors: tuple[str, ...]
    handoff_boundary_timestamp: datetime
    runtime_shell: PaperTradeShellContract | None


class S23PaperFillSimulator:
    def __init__(
        self,
        *,
        reviewer: S23PaperSessionReviewer | None = None,
        replay_bundle_manager: S23PaperReplayBundleManager | None = None,
        guardrail_settings: S23PaperGuardrailSettings | None = None,
        guardrail_evaluator: S23PaperGuardrailEvaluator | None = None,
        max_selected_contract_age: timedelta = DEFAULT_MAX_QUOTE_AGE,
    ) -> None:
        self._reviewer = reviewer or S23PaperSessionReviewer()
        self._replay_bundle_manager = (
            replay_bundle_manager or S23PaperReplayBundleManager()
        )
        self._guardrail_settings = guardrail_settings or S23PaperGuardrailSettings()
        self._guardrail_evaluator = guardrail_evaluator or S23PaperGuardrailEvaluator(
            self._guardrail_settings
        )
        self._max_selected_contract_age = max_selected_contract_age

    def simulate_from_session(
        self,
        session_directory: str | Path,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        bundle_directory: str | Path | None = None,
        created_at: datetime | None = None,
    ) -> S23PaperFillArtifactSet:
        context = self._load_context(
            session_directory=session_directory,
            bundle_directory=bundle_directory,
        )
        evaluation_timestamp = self._derive_evaluation_timestamp(
            created_at=created_at,
            market_events=market_events,
            fallback=context.handoff_boundary_timestamp,
        )

        duplicate_fill_attempt = self._existing_fill_attempt(context.session_directory)
        guardrail = self._guardrail_evaluator.evaluate_fill_phase(
            evaluation_timestamp=evaluation_timestamp,
            max_selected_contract_age=self._max_selected_contract_age,
            replay_bundle_validation_performed=context.replay_bundle_validation_performed,
            replay_bundle_valid=context.replay_bundle_valid,
            replay_bundle_errors=context.replay_bundle_errors,
            handoff_shell_status=self._handoff_shell_status(context),
            selected_contract_symbol=context.selected_contract_symbol,
            order_plan_selected_contract_symbol=context.selected_contract_symbol,
            intent_selected_contract_symbol=context.selected_contract_symbol,
            execution_summary_selected_contract_symbol=(
                self._execution_summary_selected_contract_symbol(context)
                or context.selected_contract_symbol
            ),
            handoff_summary_selected_contract_symbol=self._load_optional_summary_symbol(
                context.session_directory / "execution_handoff_summary.json"
            ),
            historical_comparison_performed=(
                self._historical_comparison_status(context) is not None
            ),
            historical_comparison_status=self._historical_comparison_status(context),
            execution_shell_status=self._execution_shell_status(context),
            dispatch_shell_status=self._dispatch_shell_status(context),
            duplicate_fill_attempt=duplicate_fill_attempt,
        )
        if guardrail is not None:
            decision = self._build_abort_decision(
                context=context,
                evaluation_timestamp=evaluation_timestamp,
                guardrail=guardrail,
                market_event_count=len(market_events),
            )
            return self._persist_fill_decision(context, decision, append_pending=False)

        pending_decision = self._build_pending_decision(
            context=context,
            evaluation_timestamp=evaluation_timestamp,
            market_event_count=len(market_events),
        )
        self._write_json(
            context.session_directory / "paper_order_pending.json",
            pending_decision,
        )

        final_decision = self._evaluate_market_events(
            context=context,
            market_events=market_events,
        )
        return self._persist_fill_decision(context, final_decision, append_pending=True)

    def _load_context(
        self,
        *,
        session_directory: str | Path,
        bundle_directory: str | Path | None,
    ) -> _FillContext:
        session_dir = Path(session_directory)
        if not session_dir.exists():
            raise S23PaperFillSimulatorError(
                f"S23 paper session directory does not exist: {session_dir}"
            )

        effective_bundle = (
            Path(bundle_directory)
            if bundle_directory is not None
            else (session_dir if (session_dir / "replay_bundle_manifest.json").exists() else None)
        )
        try:
            review_summary = self._reviewer.review_session(
                session_dir,
                bundle_directory=effective_bundle,
            )
        except S23PaperReviewError as exc:
            raise S23PaperFillSimulatorError(str(exc)) from exc

        if review_summary.strategy_code != "S23":
            raise S23PaperFillSimulatorError(
                f"Unsupported strategy for S23 Phase 1 fill simulation: "
                f"{review_summary.strategy_code or 'unknown'}"
            )
        if review_summary.terminal_state not in _SUPPORTED_INPUT_TERMINAL_STATES:
            raise S23PaperFillSimulatorError(
                "S23 Phase 1 fill simulation requires an ORDER_PLANNED paper session."
            )
        if review_summary.order_intent is None:
            raise S23PaperFillSimulatorError(
                "S23 Phase 1 fill simulation requires a persisted paper order intent."
            )
        if review_summary.order_plan is None:
            raise S23PaperFillSimulatorError(
                "S23 Phase 1 fill simulation requires a persisted paper order plan."
            )
        handoff_shell_status = (
            review_summary.runtime_contracts.shell.handoff_shell_status
            if review_summary.runtime_contracts.shell is not None
            else review_summary.order_intent.handoff_shell_status
        )
        if handoff_shell_status != "PAPER_EXECUTION_HANDOFF_READY":
            raise S23PaperFillSimulatorError(
                "S23 Phase 1 fill simulation requires PAPER_EXECUTION_HANDOFF_READY."
            )
        intent_contract = review_summary.runtime_contracts.intent
        planned_entry_price = (
            intent_contract.planned_entry_price
            if intent_contract is not None
            else review_summary.order_intent.planned_entry_price
        )
        order_reference_time = (
            intent_contract.order_reference_time
            if intent_contract is not None
            else review_summary.order_intent.order_reference_time
        )
        order_reference_label = (
            intent_contract.order_reference_label
            if intent_contract is not None
            else review_summary.order_intent.order_reference_label
        )
        if planned_entry_price is None:
            raise S23PaperFillSimulatorError(
                "Planned entry price is missing from the S23 paper order intent."
            )
        if not review_summary.selected_contract.symbol:
            raise S23PaperFillSimulatorError(
                "Selected contract symbol is missing from the persisted S23 paper session."
            )

        manifest = self._load_json_required(session_dir / "session_manifest.json")
        execution_summary = self._load_json_required(session_dir / "execution_summary.json")
        execution_journal_rows = self._load_jsonl_optional(
            session_dir / "execution_journal.jsonl"
        )

        replay_validation_performed = review_summary.replay_bundle.validation_performed
        replay_valid = review_summary.replay_bundle.is_valid
        replay_errors = review_summary.replay_bundle.errors

        return _FillContext(
            session_directory=session_dir,
            session_id=review_summary.session_id,
            session_date=review_summary.session_date,
            strategy_code=review_summary.strategy_code,
            terminal_state=review_summary.terminal_state,
            selected_contract_symbol=review_summary.selected_contract.symbol,
            selected_contract_option_type=review_summary.selected_contract.option_type,
            selected_contract_expiry=review_summary.selected_contract.expiry,
            selected_contract_effective_timestamp=review_summary.selected_contract.effective_timestamp,
            planned_entry_price=planned_entry_price,
            order_reference_time=order_reference_time,
            order_reference_label=order_reference_label,
            slippage_entry_points=float(manifest.get("slippage_entry_points") or 0.0),
            execution_summary_payload=execution_summary,
            execution_journal_rows=execution_journal_rows,
            replay_bundle_valid=replay_valid,
            replay_bundle_validation_performed=replay_validation_performed,
            replay_bundle_errors=replay_errors,
            handoff_boundary_timestamp=self._handoff_boundary_timestamp(
                execution_journal_rows=execution_journal_rows,
                order_reference_time=order_reference_time,
            ),
            runtime_shell=review_summary.runtime_contracts.shell,
        )

    def _handoff_shell_status(self, context: _FillContext) -> str | None:
        if context.runtime_shell is not None and context.runtime_shell.handoff_shell_status is not None:
            return self._text_or_none(context.runtime_shell.handoff_shell_status)
        return self._text_or_none(context.execution_summary_payload.get("handoff_shell_status"))

    def _execution_shell_status(self, context: _FillContext) -> str | None:
        if context.runtime_shell is not None and context.runtime_shell.execution_shell_status is not None:
            return self._text_or_none(context.runtime_shell.execution_shell_status)
        return self._text_or_none(context.execution_summary_payload.get("execution_shell_status"))

    def _dispatch_shell_status(self, context: _FillContext) -> str | None:
        if context.runtime_shell is not None and context.runtime_shell.dispatch_shell_status is not None:
            return self._text_or_none(context.runtime_shell.dispatch_shell_status)
        return self._text_or_none(context.execution_summary_payload.get("dispatch_shell_status"))

    def _historical_comparison_status(self, context: _FillContext) -> str | None:
        if context.runtime_shell is not None and context.runtime_shell.historical_comparison_status is not None:
            return self._text_or_none(context.runtime_shell.historical_comparison_status)
        return self._text_or_none(context.execution_summary_payload.get("historical_comparison_status"))

    def _execution_summary_selected_contract_symbol(self, context: _FillContext) -> str | None:
        if context.runtime_shell is not None and context.runtime_shell.selected_contract_symbol is not None:
            return self._text_or_none(context.runtime_shell.selected_contract_symbol)
        return self._text_or_none(context.execution_summary_payload.get("selected_contract_symbol"))

    def _evaluate_market_events(
        self,
        *,
        context: _FillContext,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> S23PaperFillDecision:
        if not market_events:
            return self._build_no_fill_decision(
                context=context,
                reason_code="missing_selected_contract_market_data",
                message=(
                    "No selected-contract quote or bar data was supplied after the "
                    "final handoff boundary, so the paper order was not filled."
                ),
                no_fill_reason="missing_selected_contract_market_data",
                evaluation_timestamp=context.handoff_boundary_timestamp,
                market_event_count=0,
            )

        last_reason_code = "planned_entry_not_tradable"
        last_message = (
            "The supplied selected-contract market data never proved the planned "
            "sell entry was tradable at or above the planned entry price."
        )
        last_event_timestamp = context.handoff_boundary_timestamp

        for event in self._sorted_market_events(market_events):
            if event.symbol != context.selected_contract_symbol:
                return self._build_abort_decision(
                    context=context,
                    evaluation_timestamp=event.envelope.captured_at,
                    guardrail=PaperGuardrailDecision(
                        code="selected_contract_mismatch_before_fill",
                        message=(
                            "Selected-contract market data does not match the persisted "
                            "S23 order intent."
                        ),
                        readiness_status=PaperReadinessStatus.ABORTED,
                        blocking_source_id=event.envelope.source_id,
                    ),
                    market_event_count=len(market_events),
                )

            if event.envelope.effective_timestamp < context.handoff_boundary_timestamp:
                last_reason_code = "market_data_before_handoff_boundary"
                last_message = (
                    "Selected-contract market data arrived before the final handoff "
                    "boundary, so it cannot prove a Phase 1 paper fill."
                )
                last_event_timestamp = event.envelope.effective_timestamp
                continue

            if (
                event.envelope.captured_at - event.envelope.effective_timestamp
                > self._max_selected_contract_age
            ):
                last_reason_code = "selected_contract_quote_stale_before_fill"
                last_message = (
                    "Selected-contract market data was stale at the point of fill "
                    "evaluation, so the paper order was not filled."
                )
                last_event_timestamp = event.envelope.effective_timestamp
                continue

            if isinstance(event, SelectedContractQuoteEvent):
                decision = self._evaluate_quote_event(
                    context=context,
                    event=event,
                    market_event_count=len(market_events),
                )
            else:
                decision = self._evaluate_bar_event(
                    context=context,
                    event=event,
                    market_event_count=len(market_events),
                )

            if decision is None:
                continue
            if decision.status is S23PaperFillStatus.PAPER_ORDER_FILLED:
                return decision
            last_reason_code = decision.reason_code
            last_message = decision.message
            last_event_timestamp = (
                decision.source_effective_timestamp
                or decision.fill_timestamp
                or context.handoff_boundary_timestamp
            )

        return self._build_no_fill_decision(
            context=context,
            reason_code=last_reason_code,
            message=last_message,
            no_fill_reason=last_reason_code,
            evaluation_timestamp=last_event_timestamp,
            market_event_count=len(market_events),
        )

    def _evaluate_quote_event(
        self,
        *,
        context: _FillContext,
        event: SelectedContractQuoteEvent,
        market_event_count: int,
    ) -> S23PaperFillDecision | None:
        spread = None
        if event.bid is not None and event.ask is not None:
            spread = float(event.ask) - float(event.bid)

        if event.bid is None:
            return self._build_no_fill_decision(
                context=context,
                reason_code="missing_selected_contract_bid",
                message=(
                    "Selected-contract quote did not include a usable bid, so the "
                    "sell order was not filled."
                ),
                no_fill_reason="missing_selected_contract_bid",
                evaluation_timestamp=event.envelope.effective_timestamp,
                market_event_count=market_event_count,
                source_kind="selected_contract_quote",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                spread_points=spread,
                quote_bid=event.bid,
                quote_ask=event.ask,
                quote_ltp=event.ltp,
            )

        if (
            self._guardrail_settings.max_selected_contract_spread_points is not None
            and spread is not None
            and spread > self._guardrail_settings.max_selected_contract_spread_points
        ):
            return self._build_no_fill_decision(
                context=context,
                reason_code="selected_contract_spread_too_wide_before_fill",
                message=(
                    "Selected-contract spread exceeded the configured paper-fill "
                    "threshold, so the order was not filled."
                ),
                no_fill_reason="selected_contract_spread_too_wide_before_fill",
                evaluation_timestamp=event.envelope.effective_timestamp,
                market_event_count=market_event_count,
                source_kind="selected_contract_quote",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                spread_points=spread,
                quote_bid=event.bid,
                quote_ask=event.ask,
                quote_ltp=event.ltp,
            )

        effective_sell_price = float(event.bid) - context.slippage_entry_points
        if effective_sell_price < context.planned_entry_price:
            return self._build_no_fill_decision(
                context=context,
                reason_code="planned_entry_not_tradable_on_quote",
                message=(
                    "Selected-contract quote never proved a conservative sell fill "
                    "at or above the planned entry price."
                ),
                no_fill_reason="planned_entry_not_tradable_on_quote",
                evaluation_timestamp=event.envelope.effective_timestamp,
                market_event_count=market_event_count,
                source_kind="selected_contract_quote",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                spread_points=spread,
                quote_bid=event.bid,
                quote_ask=event.ask,
                quote_ltp=event.ltp,
            )

        return S23PaperFillDecision(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=S23PaperFillStatus.PAPER_ORDER_FILLED,
            planned_entry_price=context.planned_entry_price,
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            order_reference_time=context.order_reference_time,
            order_reference_label=context.order_reference_label,
            handoff_boundary_timestamp=context.handoff_boundary_timestamp,
            fill_price=effective_sell_price,
            fill_timestamp=event.envelope.effective_timestamp,
            source_kind="selected_contract_quote",
            source_type=event.envelope.source_type,
            source_id=event.envelope.source_id,
            source_effective_timestamp=event.envelope.effective_timestamp,
            spread_points=spread,
            slippage_entry_points=context.slippage_entry_points,
            quote_bid=event.bid,
            quote_ask=event.ask,
            quote_ltp=event.ltp,
            bar_high=None,
            bar_low=None,
            market_event_count=market_event_count,
            reason_code="paper_order_filled_from_quote",
            message=(
                "A fresh selected-contract quote proved a conservative sell fill at "
                "or above the planned entry price."
            ),
            no_fill_reason=None,
            operator_action_required=None,
            guardrail_code=None,
            guardrail_message=None,
            blocking_source_id=None,
            disclaimer=_PHASE1_FILL_DISCLAIMER,
        )

    def _evaluate_bar_event(
        self,
        *,
        context: _FillContext,
        event: SelectedContractBarEvent,
        market_event_count: int,
    ) -> S23PaperFillDecision | None:
        if event.high is None:
            return self._build_no_fill_decision(
                context=context,
                reason_code="selected_contract_bar_incomplete",
                message=(
                    "Selected-contract OHLC data was incomplete, so the paper order "
                    "was not filled."
                ),
                no_fill_reason="selected_contract_bar_incomplete",
                evaluation_timestamp=event.bar_end,
                market_event_count=market_event_count,
                source_kind="selected_contract_bar",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                bar_high=event.high,
                bar_low=event.low,
            )

        threshold = context.planned_entry_price + context.slippage_entry_points
        if float(event.high) < threshold:
            return self._build_no_fill_decision(
                context=context,
                reason_code="planned_entry_not_reached_on_bar",
                message=(
                    "Selected-contract OHLC data never proved the planned sell entry "
                    "was reached conservatively after the handoff boundary."
                ),
                no_fill_reason="planned_entry_not_reached_on_bar",
                evaluation_timestamp=event.bar_end,
                market_event_count=market_event_count,
                source_kind="selected_contract_bar",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                bar_high=event.high,
                bar_low=event.low,
            )

        return S23PaperFillDecision(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=S23PaperFillStatus.PAPER_ORDER_FILLED,
            planned_entry_price=context.planned_entry_price,
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            order_reference_time=context.order_reference_time,
            order_reference_label=context.order_reference_label,
            handoff_boundary_timestamp=context.handoff_boundary_timestamp,
            fill_price=context.planned_entry_price,
            fill_timestamp=event.bar_end,
            source_kind="selected_contract_bar",
            source_type=event.envelope.source_type,
            source_id=event.envelope.source_id,
            source_effective_timestamp=event.envelope.effective_timestamp,
            spread_points=None,
            slippage_entry_points=context.slippage_entry_points,
            quote_bid=None,
            quote_ask=None,
            quote_ltp=None,
            bar_high=event.high,
            bar_low=event.low,
            market_event_count=market_event_count,
            reason_code="paper_order_filled_from_bar",
            message=(
                "Selected-contract OHLC data proved the planned sell entry was "
                "reached conservatively after the handoff boundary."
            ),
            no_fill_reason=None,
            operator_action_required=None,
            guardrail_code=None,
            guardrail_message=None,
            blocking_source_id=None,
            disclaimer=_PHASE1_FILL_DISCLAIMER,
        )

    def _persist_fill_decision(
        self,
        context: _FillContext,
        decision: S23PaperFillDecision,
        *,
        append_pending: bool,
    ) -> S23PaperFillArtifactSet:
        session_dir = context.session_directory
        pending_path = session_dir / "paper_order_pending.json"
        fill_path = session_dir / "paper_fill.json"
        no_fill_path = session_dir / "paper_no_fill.json"
        abort_path = session_dir / "paper_fill_abort_summary.json"
        execution_journal_path = session_dir / "execution_journal.jsonl"
        execution_summary_path = session_dir / "execution_summary.json"

        journal_rows = list(context.execution_journal_rows)
        if decision.status is S23PaperFillStatus.PAPER_ORDER_PENDING:
            event_type = _PENDING_EVENT_TYPE
        elif decision.status is S23PaperFillStatus.PAPER_ORDER_FILLED:
            event_type = _FILLED_EVENT_TYPE
        elif decision.status is S23PaperFillStatus.PAPER_ORDER_NOT_FILLED:
            event_type = _NOT_FILLED_EVENT_TYPE
        else:
            event_type = _ABORTED_EVENT_TYPE

        if append_pending and (
            not journal_rows or journal_rows[-1].get("event_type") != _PENDING_EVENT_TYPE
        ):
            journal_rows.append(
                self._journal_event_payload(
                    timestamp=decision.handoff_boundary_timestamp,
                    event_type=_PENDING_EVENT_TYPE,
                    session_id=context.session_id,
                    strategy_code=context.strategy_code,
                    terminal_state=context.terminal_state,
                    status=_PENDING_EVENT_TYPE,
                    reason_code="paper_order_pending",
                    message=(
                        "Phase 1 paper fill simulation started after the final handoff boundary."
                    ),
                    selected_contract_symbol=context.selected_contract_symbol,
                    guardrail_code=None,
                    guardrail_message=None,
                    blocking_source_id=None,
                )
            )

        journal_rows.append(
            self._journal_event_payload(
                timestamp=(
                    decision.fill_timestamp
                    or decision.source_effective_timestamp
                    or decision.handoff_boundary_timestamp
                ),
                event_type=event_type,
                session_id=context.session_id,
                strategy_code=context.strategy_code,
                terminal_state=context.terminal_state,
                status=decision.status.value,
                reason_code=decision.reason_code,
                message=decision.message,
                selected_contract_symbol=decision.selected_contract_symbol,
                guardrail_code=decision.guardrail_code,
                guardrail_message=decision.guardrail_message,
                blocking_source_id=decision.blocking_source_id,
                operator_action_required=decision.operator_action_required,
            )
        )
        self._write_jsonl(execution_journal_path, tuple(journal_rows))

        execution_summary_payload = dict(context.execution_summary_payload)
        execution_summary_payload.update(
            {
                "status": decision.status.value,
                "fill_status": decision.status.value,
                "fill_reason_code": decision.reason_code,
                "fill_message": decision.message,
                "fill_price": decision.fill_price,
                "fill_timestamp": (
                    decision.fill_timestamp.isoformat()
                    if decision.fill_timestamp is not None
                    else None
                ),
                "fill_source_kind": decision.source_kind,
                "fill_source_type": decision.source_type,
                "fill_source_id": decision.source_id,
                "fill_source_effective_timestamp": (
                    decision.source_effective_timestamp.isoformat()
                    if decision.source_effective_timestamp is not None
                    else None
                ),
                "fill_spread_points": decision.spread_points,
                "fill_slippage_entry_points": decision.slippage_entry_points,
                "fill_quote_bid": decision.quote_bid,
                "fill_quote_ask": decision.quote_ask,
                "fill_quote_ltp": decision.quote_ltp,
                "fill_bar_high": decision.bar_high,
                "fill_bar_low": decision.bar_low,
                "fill_simulated": decision.status is S23PaperFillStatus.PAPER_ORDER_FILLED,
                "order_placed": False,
                "position_opened": False,
                "future_fill_simulation_eligible": False,
                "terminal_reason_code": decision.reason_code,
                "message": decision.message,
                "guardrail_code": decision.guardrail_code,
                "guardrail_message": decision.guardrail_message,
                "blocking_source_id": decision.blocking_source_id,
                "operator_action_required": decision.operator_action_required,
                "disclaimer": decision.disclaimer,
            }
        )
        self._write_json(execution_summary_path, execution_summary_payload)

        if decision.status is S23PaperFillStatus.PAPER_ORDER_FILLED:
            self._write_json(fill_path, decision)
            self._cleanup_optional_file(no_fill_path)
            self._cleanup_optional_file(abort_path)
            result = S23PaperFillArtifactSet(
                session_directory=session_dir,
                paper_order_pending_path=pending_path if pending_path.exists() else None,
                paper_fill_path=fill_path,
                paper_no_fill_path=None,
                paper_fill_abort_summary_path=None,
                execution_journal_path=execution_journal_path,
                execution_summary_path=execution_summary_path,
            )
        elif decision.status is S23PaperFillStatus.PAPER_ORDER_NOT_FILLED:
            self._write_json(no_fill_path, decision)
            self._cleanup_optional_file(fill_path)
            self._cleanup_optional_file(abort_path)
            result = S23PaperFillArtifactSet(
                session_directory=session_dir,
                paper_order_pending_path=pending_path if pending_path.exists() else None,
                paper_fill_path=None,
                paper_no_fill_path=no_fill_path,
                paper_fill_abort_summary_path=None,
                execution_journal_path=execution_journal_path,
                execution_summary_path=execution_summary_path,
            )
        else:
            self._write_json(abort_path, decision)
            self._cleanup_optional_file(fill_path)
            self._cleanup_optional_file(no_fill_path)
            result = S23PaperFillArtifactSet(
                session_directory=session_dir,
                paper_order_pending_path=(
                    pending_path if pending_path.exists() else None
                ),
                paper_fill_path=None,
                paper_no_fill_path=None,
                paper_fill_abort_summary_path=abort_path,
                execution_journal_path=execution_journal_path,
                execution_summary_path=execution_summary_path,
            )
        return result

    def _build_pending_decision(
        self,
        *,
        context: _FillContext,
        evaluation_timestamp: datetime,
        market_event_count: int,
    ) -> S23PaperFillDecision:
        return S23PaperFillDecision(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=S23PaperFillStatus.PAPER_ORDER_PENDING,
            planned_entry_price=context.planned_entry_price,
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            order_reference_time=context.order_reference_time,
            order_reference_label=context.order_reference_label,
            handoff_boundary_timestamp=context.handoff_boundary_timestamp,
            fill_price=None,
            fill_timestamp=evaluation_timestamp,
            source_kind=None,
            source_type=None,
            source_id=None,
            source_effective_timestamp=None,
            spread_points=None,
            slippage_entry_points=context.slippage_entry_points,
            quote_bid=None,
            quote_ask=None,
            quote_ltp=None,
            bar_high=None,
            bar_low=None,
            market_event_count=market_event_count,
            reason_code="paper_order_pending",
            message=(
                "Phase 1 paper fill simulation is evaluating selected-contract market "
                "data after the final handoff boundary."
            ),
            no_fill_reason=None,
            operator_action_required=None,
            guardrail_code=None,
            guardrail_message=None,
            blocking_source_id=None,
            disclaimer=_PHASE1_FILL_DISCLAIMER,
        )

    def _build_no_fill_decision(
        self,
        *,
        context: _FillContext,
        reason_code: str,
        message: str,
        no_fill_reason: str,
        evaluation_timestamp: datetime,
        market_event_count: int,
        source_kind: str | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        source_effective_timestamp: datetime | None = None,
        spread_points: float | None = None,
        quote_bid: float | None = None,
        quote_ask: float | None = None,
        quote_ltp: float | None = None,
        bar_high: float | None = None,
        bar_low: float | None = None,
    ) -> S23PaperFillDecision:
        return S23PaperFillDecision(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=S23PaperFillStatus.PAPER_ORDER_NOT_FILLED,
            planned_entry_price=context.planned_entry_price,
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            order_reference_time=context.order_reference_time,
            order_reference_label=context.order_reference_label,
            handoff_boundary_timestamp=context.handoff_boundary_timestamp,
            fill_price=None,
            fill_timestamp=None,
            source_kind=source_kind,
            source_type=source_type,
            source_id=source_id,
            source_effective_timestamp=source_effective_timestamp,
            spread_points=spread_points,
            slippage_entry_points=context.slippage_entry_points,
            quote_bid=quote_bid,
            quote_ask=quote_ask,
            quote_ltp=quote_ltp,
            bar_high=bar_high,
            bar_low=bar_low,
            market_event_count=market_event_count,
            reason_code=reason_code,
            message=message,
            no_fill_reason=no_fill_reason,
            operator_action_required=(
                "Review selected-contract market quality before retrying the paper fill simulator."
            ),
            guardrail_code=reason_code,
            guardrail_message=message,
            blocking_source_id=source_id,
            disclaimer=_PHASE1_FILL_DISCLAIMER,
        )

    def _build_abort_decision(
        self,
        *,
        context: _FillContext,
        evaluation_timestamp: datetime,
        guardrail: PaperGuardrailDecision,
        market_event_count: int,
    ) -> S23PaperFillDecision:
        return S23PaperFillDecision(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=S23PaperFillStatus.PAPER_FILL_ABORTED,
            planned_entry_price=context.planned_entry_price,
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            order_reference_time=context.order_reference_time,
            order_reference_label=context.order_reference_label,
            handoff_boundary_timestamp=context.handoff_boundary_timestamp,
            fill_price=None,
            fill_timestamp=evaluation_timestamp,
            source_kind=None,
            source_type=None,
            source_id=None,
            source_effective_timestamp=None,
            spread_points=None,
            slippage_entry_points=context.slippage_entry_points,
            quote_bid=None,
            quote_ask=None,
            quote_ltp=None,
            bar_high=None,
            bar_low=None,
            market_event_count=market_event_count,
            reason_code=guardrail.code,
            message=guardrail.message,
            no_fill_reason=guardrail.code,
            operator_action_required=guardrail.operator_action_required,
            guardrail_code=guardrail.code,
            guardrail_message=guardrail.message,
            blocking_source_id=guardrail.blocking_source_id,
            disclaimer=_PHASE1_FILL_DISCLAIMER,
        )

    def _sorted_market_events(
        self,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...]:
        def _key(
            event: SelectedContractQuoteEvent | SelectedContractBarEvent,
        ) -> tuple[datetime, datetime, int]:
            event_order = 0 if isinstance(event, SelectedContractQuoteEvent) else 1
            return (
                event.envelope.effective_timestamp,
                event.envelope.captured_at,
                event_order,
            )

        return tuple(sorted(market_events, key=_key))

    def _existing_fill_attempt(self, session_directory: Path) -> bool:
        return any(
            (session_directory / filename).exists()
            for filename in (
                "paper_fill.json",
                "paper_no_fill.json",
                "paper_fill_abort_summary.json",
            )
        )

    def _handoff_boundary_timestamp(
        self,
        *,
        execution_journal_rows: tuple[dict[str, Any], ...],
        order_reference_time: datetime | None,
    ) -> datetime:
        candidate = order_reference_time
        for row in execution_journal_rows:
            if row.get("event_type") == "PAPER_EXECUTION_HANDOFF_READY":
                timestamp = self._optional_datetime(row.get("timestamp"))
                if timestamp is not None and (candidate is None or timestamp > candidate):
                    candidate = timestamp
        if candidate is None:
            raise S23PaperFillSimulatorError(
                "Cannot derive a handoff boundary timestamp for Phase 1 fill simulation."
            )
        return candidate

    def _derive_evaluation_timestamp(
        self,
        *,
        created_at: datetime | None,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        fallback: datetime,
    ) -> datetime:
        if created_at is not None:
            return created_at
        latest = fallback
        for event in market_events:
            if event.envelope.captured_at > latest:
                latest = event.envelope.captured_at
        return latest

    def _journal_event_payload(
        self,
        *,
        timestamp: datetime,
        event_type: str,
        session_id: str,
        strategy_code: str,
        terminal_state: PaperSessionState,
        status: str,
        reason_code: str | None,
        message: str,
        selected_contract_symbol: str | None,
        guardrail_code: str | None,
        guardrail_message: str | None,
        blocking_source_id: str | None,
        operator_action_required: str | None = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "session_id": session_id,
            "strategy_code": strategy_code,
            "terminal_state": terminal_state.value,
            "status": status,
            "reason_code": reason_code,
            "message": message,
            "selected_contract_symbol": selected_contract_symbol,
            "guardrail_code": guardrail_code,
            "guardrail_message": guardrail_message,
            "blocking_source_id": blocking_source_id,
            "operator_action_required": operator_action_required,
            "disclaimer": _PHASE1_FILL_DISCLAIMER,
        }

    def _load_json_required(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise S23PaperFillSimulatorError(
                f"Missing required Phase 1 fill artifact: {path}"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise S23PaperFillSimulatorError(
                f"Corrupt JSON artifact: {path} ({exc.msg})"
            ) from exc
        if not isinstance(payload, dict):
            raise S23PaperFillSimulatorError(
                f"Phase 1 fill artifact must be a JSON object: {path}"
            )
        return payload

    def _load_jsonl_optional(self, path: Path) -> tuple[dict[str, Any], ...]:
        if not path.exists():
            return ()
        rows: list[dict[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise S23PaperFillSimulatorError(
                    f"Corrupt JSONL artifact: {path} line {index} ({exc.msg})"
                ) from exc
            if not isinstance(row, dict):
                raise S23PaperFillSimulatorError(
                    f"Phase 1 fill journal row must be a JSON object: {path} line {index}"
                )
            rows.append(row)
        return tuple(rows)

    def _load_optional_summary_symbol(self, path: Path) -> str | None:
        payload = self._load_optional_json(path)
        if payload is None:
            return None
        return self._text_or_none(payload.get("selected_contract_symbol"))

    def _load_optional_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return self._load_json_required(path)

    def _write_json(self, path: Path, payload: Any) -> None:
        rendered = json.dumps(self._normalize(payload), indent=2, sort_keys=True) + "\n"
        self._atomic_write_text(path, rendered)

    def _write_jsonl(self, path: Path, rows: tuple[Any, ...]) -> None:
        rendered = "".join(
            json.dumps(self._normalize(row), sort_keys=True) + "\n" for row in rows
        )
        self._atomic_write_text(path, rendered)

    def _atomic_write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.parent / f".{path.name}.tmp"
        try:
            with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _cleanup_optional_file(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return {
                field.name: self._normalize(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, dict):
            return {
                str(key): self._normalize(value[key])
                for key in sorted(value, key=lambda item: str(item))
            }
        if isinstance(value, tuple | list):
            return [self._normalize(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date | time):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _text_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        rendered = str(value).strip()
        return rendered or None
