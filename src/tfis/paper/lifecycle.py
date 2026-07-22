from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from .guardrails import (
    PaperGuardrailDecision,
    S23PaperGuardrailEvaluator,
    S23PaperGuardrailSettings,
)
from .models import PaperSessionState, SelectedContractBarEvent, SelectedContractQuoteEvent
from .replay_bundle import S23PaperReplayBundleManager
from .review import PaperReviewError, PaperSessionReviewer
from .validation import DEFAULT_MAX_QUOTE_AGE


_ARTIFACT_VERSION = 1
_OPEN_EVENT_TYPE = "PAPER_POSITION_OPEN"
_EXIT_PENDING_EVENT_TYPE = "PAPER_EXIT_PENDING"
_CLOSED_EVENT_TYPE = "PAPER_POSITION_CLOSED"
_EOD_EVENT_TYPE = "PAPER_EOD_SQUARE_OFF"
_ABORTED_EVENT_TYPE = "PAPER_LIFECYCLE_ABORTED"
_PHASE2_LIFECYCLE_DISCLAIMER = (
    "No broker order was placed, no real-money order was routed, and no live "
    "position existed; this artifact covers only same-day paper fill-to-exit "
    "lifecycle simulation."
)


class S23PaperLifecycleStatus(str, Enum):
    PAPER_POSITION_OPEN = _OPEN_EVENT_TYPE
    PAPER_EXIT_PENDING = _EXIT_PENDING_EVENT_TYPE
    PAPER_POSITION_CLOSED = _CLOSED_EVENT_TYPE
    PAPER_EOD_SQUARE_OFF = _EOD_EVENT_TYPE
    PAPER_LIFECYCLE_ABORTED = _ABORTED_EVENT_TYPE


class S23PaperLifecycleError(RuntimeError):
    """Raised when S23 Phase 2 paper lifecycle simulation cannot proceed safely."""


@dataclass(frozen=True, slots=True)
class S23PaperPosition:
    artifact_version: int
    session_id: str
    session_date: date
    strategy_code: str
    status: S23PaperLifecycleStatus
    selected_contract_symbol: str
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    side: str
    lots: int
    quantity: int
    entry_price: float
    target_price: float
    stoploss_price: float | None
    fsl_price: float | None
    effective_stop_price: float
    entry_timestamp: datetime
    source_branch: str | None
    source_workbook_rule: str | None
    workbook_row_number: int | None
    provenance_source_kind: str | None
    provenance_source_type: str | None
    provenance_source_id: str | None
    disclaimer: str


@dataclass(frozen=True, slots=True)
class S23PaperLifecycleDecision:
    artifact_version: int
    session_id: str
    session_date: date
    strategy_code: str
    status: S23PaperLifecycleStatus
    selected_contract_symbol: str
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    side: str
    lots: int
    quantity: int
    entry_price: float
    target_price: float
    stoploss_price: float | None
    fsl_price: float | None
    effective_stop_price: float
    entry_timestamp: datetime
    exit_price: float | None
    exit_timestamp: datetime | None
    exit_reason_code: str
    message: str
    source_kind: str | None
    source_type: str | None
    source_id: str | None
    source_effective_timestamp: datetime | None
    quote_bid: float | None
    quote_ask: float | None
    quote_ltp: float | None
    bar_open: float | None
    bar_high: float | None
    bar_low: float | None
    bar_close: float | None
    gross_pnl_rupees: float | None
    brokerage_rupees: float | None
    net_pnl_rupees: float | None
    guardrail_code: str | None
    guardrail_message: str | None
    blocking_source_id: str | None
    operator_action_required: str | None
    warning_flags: tuple[str, ...]
    disclaimer: str


@dataclass(frozen=True, slots=True)
class S23PaperLifecycleArtifactSet:
    session_directory: Path
    paper_position_path: Path | None
    lifecycle_events_path: Path
    paper_exit_path: Path | None
    paper_pnl_summary_path: Path | None
    execution_journal_path: Path
    execution_summary_path: Path


@dataclass(frozen=True, slots=True)
class _LifecycleContext:
    session_directory: Path
    session_id: str
    session_date: date
    strategy_code: str
    selected_contract_symbol: str | None
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    side: str
    lots: int
    quantity: int
    entry_price: float | None
    target_price: float | None
    stoploss_price: float | None
    fsl_price: float | None
    effective_stop_price: float | None
    fill_timestamp: datetime | None
    fill_source_kind: str | None
    fill_source_type: str | None
    fill_source_id: str | None
    fill_selected_contract_symbol: str | None
    source_branch: str | None
    source_workbook_rule: str | None
    workbook_row_number: int | None
    brokerage_per_lot: float
    slippage_exit_points: float
    runtime_fill_status: str | None
    execution_summary_payload: dict[str, Any]
    execution_journal_rows: tuple[dict[str, Any], ...]
    replay_bundle_valid: bool | None
    replay_bundle_validation_performed: bool
    replay_bundle_errors: tuple[str, ...]


class S23PaperLifecycleSimulator:
    def __init__(
        self,
        *,
        reviewer: PaperSessionReviewer | None = None,
        replay_bundle_manager: S23PaperReplayBundleManager | None = None,
        guardrail_settings: S23PaperGuardrailSettings | None = None,
        guardrail_evaluator: S23PaperGuardrailEvaluator | None = None,
        max_selected_contract_age: timedelta = DEFAULT_MAX_QUOTE_AGE,
        eod_cutoff: time = time(15, 30),
        eod_price_age_window: timedelta = timedelta(minutes=5),
    ) -> None:
        self._reviewer = reviewer or PaperSessionReviewer()
        self._replay_bundle_manager = (
            replay_bundle_manager or S23PaperReplayBundleManager()
        )
        self._guardrail_settings = guardrail_settings or S23PaperGuardrailSettings()
        self._guardrail_evaluator = guardrail_evaluator or S23PaperGuardrailEvaluator(
            self._guardrail_settings
        )
        self._max_selected_contract_age = max_selected_contract_age
        self._eod_cutoff = eod_cutoff
        self._eod_price_age_window = eod_price_age_window

    def simulate_from_session(
        self,
        session_directory: str | Path,
        *,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        bundle_directory: str | Path | None = None,
        created_at: datetime | None = None,
    ) -> S23PaperLifecycleArtifactSet:
        context = self._load_context(
            session_directory=session_directory,
            bundle_directory=bundle_directory,
        )
        evaluation_timestamp = self._derive_evaluation_timestamp(
            created_at=created_at,
            market_events=market_events,
            fallback=context.fill_timestamp,
        )

        guardrail = self._guardrail_evaluator.evaluate_lifecycle_phase(
            replay_bundle_validation_performed=context.replay_bundle_validation_performed,
            replay_bundle_valid=context.replay_bundle_valid,
            replay_bundle_errors=context.replay_bundle_errors,
            fill_status=(
                context.runtime_fill_status
                or self._text_or_none(context.execution_summary_payload.get("fill_status"))
            ),
            selected_contract_symbol=context.selected_contract_symbol,
            fill_selected_contract_symbol=context.fill_selected_contract_symbol,
            target_price_available=context.target_price is not None,
            stoploss_or_fsl_available=context.effective_stop_price is not None,
            duplicate_lifecycle_attempt=self._existing_lifecycle_attempt(
                context.session_directory
            ),
            same_day_only_policy_confirmed=(
                self._guardrail_settings.same_day_only_policy_confirmed
            ),
        )
        if guardrail is not None:
            decision = self._build_abort_decision(
                context=context,
                evaluation_timestamp=evaluation_timestamp,
                guardrail=guardrail,
                warning_flags=(),
            )
            return self._persist_lifecycle_outcome(
                context=context,
                position=None,
                decision=decision,
                lifecycle_events=(
                    self._lifecycle_event(
                        timestamp=evaluation_timestamp,
                        event_type=_ABORTED_EVENT_TYPE,
                        context=context,
                        decision=decision,
                    ),
                ),
            )

        position = self._build_position(context)
        lifecycle_rows: list[dict[str, Any]] = [
            self._lifecycle_event(
                timestamp=position.entry_timestamp,
                event_type=_OPEN_EVENT_TYPE,
                context=context,
                decision=None,
            ),
            self._lifecycle_event(
                timestamp=position.entry_timestamp,
                event_type=_EXIT_PENDING_EVENT_TYPE,
                context=context,
                decision=None,
                reason_code="same_day_lifecycle_monitoring_started",
                message=(
                    "Phase 2 same-day lifecycle monitoring started after the paper fill."
                ),
            ),
        ]

        if self._guardrail_settings.manual_operator_abort_during_lifecycle:
            decision = self._manual_abort_decision(context=context, market_events=market_events)
            lifecycle_rows.append(
                self._lifecycle_event(
                    timestamp=decision.exit_timestamp or evaluation_timestamp,
                    event_type=decision.status.value,
                    context=context,
                    decision=decision,
                )
            )
            return self._persist_lifecycle_outcome(
                context=context,
                position=position,
                decision=decision,
                lifecycle_events=tuple(lifecycle_rows),
            )

        decision = self._evaluate_market_events(
            context=context,
            market_events=market_events,
        )
        lifecycle_rows.append(
            self._lifecycle_event(
                timestamp=decision.exit_timestamp or evaluation_timestamp,
                event_type=decision.status.value,
                context=context,
                decision=decision,
            )
        )
        return self._persist_lifecycle_outcome(
            context=context,
            position=position,
            decision=decision,
            lifecycle_events=tuple(lifecycle_rows),
        )

    def _load_context(
        self,
        *,
        session_directory: str | Path,
        bundle_directory: str | Path | None,
    ) -> _LifecycleContext:
        session_dir = Path(session_directory)
        if not session_dir.exists():
            raise S23PaperLifecycleError(
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
        except PaperReviewError as exc:
            raise S23PaperLifecycleError(str(exc)) from exc

        if review_summary.strategy_code != "S23":
            raise S23PaperLifecycleError(
                f"Unsupported strategy for S23 Phase 2 lifecycle simulation: "
                f"{review_summary.strategy_code or 'unknown'}"
            )
        if review_summary.terminal_state is not PaperSessionState.ORDER_PLANNED:
            raise S23PaperLifecycleError(
                "S23 Phase 2 lifecycle simulation requires an ORDER_PLANNED paper session."
            )
        if review_summary.order_intent is None or review_summary.order_plan is None:
            raise S23PaperLifecycleError(
                "S23 Phase 2 lifecycle simulation requires persisted paper order plan and intent artifacts."
            )
        intent_contract = review_summary.runtime_contracts.intent
        fill_contract = review_summary.runtime_contracts.fill

        manifest = self._load_json_required(session_dir / "session_manifest.json")
        execution_summary = self._load_json_required(session_dir / "execution_summary.json")
        execution_journal_rows = self._load_jsonl_optional(
            session_dir / "execution_journal.jsonl"
        )
        paper_fill_payload = self._load_optional_json(session_dir / "paper_fill.json")
        replay_valid = review_summary.replay_bundle.is_valid
        replay_errors = review_summary.replay_bundle.errors

        stoploss_price = (
            intent_contract.stoploss_price
            if intent_contract is not None
            else review_summary.order_intent.stoploss_price
        )
        fsl_price = (
            intent_contract.fsl_price
            if intent_contract is not None
            else review_summary.order_intent.fsl_price
        )
        effective_stop_price = self._effective_stop_price(stoploss_price, fsl_price)

        return _LifecycleContext(
            session_directory=session_dir,
            session_id=review_summary.session_id,
            session_date=review_summary.session_date,
            strategy_code=review_summary.strategy_code,
            selected_contract_symbol=review_summary.selected_contract.symbol,
            selected_contract_option_type=review_summary.selected_contract.option_type,
            selected_contract_expiry=review_summary.selected_contract.expiry,
            side=(
                intent_contract.side if intent_contract is not None else review_summary.order_intent.order_side
            ) or "SELL",
            lots=int(
                intent_contract.lots if intent_contract is not None else (review_summary.order_intent.lots or 0)
            ),
            quantity=int(
                intent_contract.quantity
                if intent_contract is not None
                else (review_summary.order_intent.quantity or 0)
            ),
            entry_price=(
                fill_contract.fill_price
                if fill_contract is not None
                else (review_summary.fill_phase.fill_price if review_summary.fill_phase else None)
            ),
            target_price=(
                intent_contract.target_price
                if intent_contract is not None
                else review_summary.order_intent.target_price
            ),
            stoploss_price=stoploss_price,
            fsl_price=fsl_price,
            effective_stop_price=effective_stop_price,
            fill_timestamp=(
                fill_contract.fill_timestamp
                if fill_contract is not None
                else review_summary.fill_phase.fill_timestamp
                if review_summary.fill_phase is not None
                else None
            ),
            fill_source_kind=(
                fill_contract.source_kind
                if fill_contract is not None
                else review_summary.fill_phase.source_kind
                if review_summary.fill_phase is not None
                else None
            ),
            fill_source_type=(
                fill_contract.source_type
                if fill_contract is not None
                else review_summary.fill_phase.source_type
                if review_summary.fill_phase is not None
                else self._text_or_none(execution_summary.get("fill_source_type"))
            ),
            fill_source_id=(
                fill_contract.source_id
                if fill_contract is not None
                else review_summary.fill_phase.source_id
                if review_summary.fill_phase is not None
                else self._text_or_none(execution_summary.get("fill_source_id"))
            ),
            fill_selected_contract_symbol=(
                fill_contract.selected_contract_symbol
                if fill_contract is not None
                else self._text_or_none(paper_fill_payload.get("selected_contract_symbol"))
                if paper_fill_payload is not None
                else None
            ),
            source_branch=(
                intent_contract.source_branch
                if intent_contract is not None
                else review_summary.order_intent.source_branch
            ),
            source_workbook_rule=(
                intent_contract.source_workbook_rule
                if intent_contract is not None
                else review_summary.order_intent.source_workbook_rule
            ),
            workbook_row_number=(
                intent_contract.workbook_row_number
                if intent_contract is not None
                else review_summary.order_intent.workbook_row_number
            ),
            brokerage_per_lot=float(manifest.get("brokerage_per_lot") or 0.0),
            slippage_exit_points=float(manifest.get("slippage_exit_points") or 0.0),
            runtime_fill_status=(
                fill_contract.status if fill_contract is not None else None
            ),
            execution_summary_payload=execution_summary,
            execution_journal_rows=execution_journal_rows,
            replay_bundle_valid=replay_valid,
            replay_bundle_validation_performed=review_summary.replay_bundle.validation_performed,
            replay_bundle_errors=replay_errors,
        )

    def _evaluate_market_events(
        self,
        *,
        context: _LifecycleContext,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> S23PaperLifecycleDecision:
        if context.fill_timestamp is None or context.entry_price is None:
            cutoff = self._fallback_session_cutoff(context)
            return self._build_abort_decision_from_reason(
                context=context,
                evaluation_timestamp=cutoff,
                reason_code="missing_fill_artifact_for_lifecycle",
                message=(
                    "The persisted Phase 1 fill artifact is incomplete, so the paper lifecycle loop cannot start."
                ),
                warning_flags=(),
            )

        if not market_events:
            return self._build_abort_decision_from_reason(
                context=context,
                evaluation_timestamp=context.fill_timestamp,
                reason_code="missing_selected_contract_lifecycle_market_data",
                message=(
                    "No selected-contract market data was supplied after the paper fill, so the same-day lifecycle loop cannot determine an exit."
                ),
                warning_flags=("missing_selected_contract_lifecycle_market_data",),
            )

        last_usable_event: SelectedContractQuoteEvent | SelectedContractBarEvent | None = None
        stale_seen = False
        stale_reason = "selected_contract_lifecycle_data_stale"

        for event in self._sorted_market_events(market_events):
            if event.symbol != context.selected_contract_symbol:
                return self._build_abort_decision_from_reason(
                    context=context,
                    evaluation_timestamp=self._event_effective_timestamp(event),
                    reason_code="selected_contract_mismatch_before_lifecycle",
                    message=(
                        "Selected-contract lifecycle market data does not match the persisted paper fill symbol."
                    ),
                    warning_flags=(),
                    blocking_source_id=event.envelope.source_id,
                )

            event_timestamp = self._event_effective_timestamp(event)
            if context.fill_timestamp is not None and event_timestamp < context.fill_timestamp:
                continue
            if event_timestamp.date() != context.session_date:
                continue
            if event_timestamp > self._session_cutoff(context):
                continue
            if event.envelope.captured_at - event.envelope.effective_timestamp > self._max_selected_contract_age:
                stale_seen = True
                continue

            if isinstance(event, SelectedContractQuoteEvent):
                decision = self._evaluate_quote_event(context=context, event=event)
            else:
                decision = self._evaluate_bar_event(context=context, event=event)
            last_usable_event = event
            if decision is not None:
                if stale_seen:
                    decision = self._with_warning(
                        decision,
                        stale_reason,
                    )
                return decision

        if last_usable_event is not None and self._is_usable_for_eod(context, last_usable_event):
            decision = self._build_eod_square_off_decision(
                context=context,
                event=last_usable_event,
                warning_flags=((stale_reason,) if stale_seen else ()),
            )
            return decision

        if stale_seen:
            return self._build_abort_decision_from_reason(
                context=context,
                evaluation_timestamp=self._session_cutoff(context),
                reason_code=stale_reason,
                message=(
                    "Selected-contract lifecycle data became stale before a target, stoploss, or EOD square-off could be priced safely."
                ),
                warning_flags=(stale_reason,),
            )

        return self._build_abort_decision_from_reason(
            context=context,
            evaluation_timestamp=self._session_cutoff(context),
            reason_code="missing_eod_selected_contract_price",
            message=(
                "No target or stoploss was hit and no fresh selected-contract price was available near the same-day EOD cutoff."
            ),
            warning_flags=("missing_eod_selected_contract_price",),
        )

    def _evaluate_quote_event(
        self,
        *,
        context: _LifecycleContext,
        event: SelectedContractQuoteEvent,
    ) -> S23PaperLifecycleDecision | None:
        exit_reference = (
            float(event.ask)
            if event.ask is not None
            else (float(event.ltp) if event.ltp is not None else None)
        )
        if exit_reference is None:
            return None

        if (
            self._guardrail_settings.max_selected_contract_spread_points is not None
            and event.bid is not None
            and event.ask is not None
            and float(event.ask) - float(event.bid)
            > self._guardrail_settings.max_selected_contract_spread_points
        ):
            return None

        target_price = context.target_price
        stop_price = context.effective_stop_price
        if target_price is None or stop_price is None:
            return None

        if exit_reference >= stop_price:
            base_exit = max(stop_price, exit_reference)
            return self._build_exit_decision(
                context=context,
                status=S23PaperLifecycleStatus.PAPER_POSITION_CLOSED,
                exit_reason_code="stoploss_or_fsl_hit",
                message=(
                    "A fresh selected-contract quote breached the stoploss/FSL threshold, so the same-day paper position was closed conservatively."
                ),
                exit_price=base_exit + context.slippage_exit_points,
                exit_timestamp=event.envelope.effective_timestamp,
                source_kind="selected_contract_quote",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                quote_bid=event.bid,
                quote_ask=event.ask,
                quote_ltp=event.ltp,
            )

        if exit_reference <= target_price:
            base_exit = max(target_price, exit_reference)
            return self._build_exit_decision(
                context=context,
                status=S23PaperLifecycleStatus.PAPER_POSITION_CLOSED,
                exit_reason_code="target_hit",
                message=(
                    "A fresh selected-contract quote proved the target was hit for the same-day paper position."
                ),
                exit_price=base_exit + context.slippage_exit_points,
                exit_timestamp=event.envelope.effective_timestamp,
                source_kind="selected_contract_quote",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                quote_bid=event.bid,
                quote_ask=event.ask,
                quote_ltp=event.ltp,
            )

        return None

    def _evaluate_bar_event(
        self,
        *,
        context: _LifecycleContext,
        event: SelectedContractBarEvent,
    ) -> S23PaperLifecycleDecision | None:
        if event.high is None or event.low is None or event.close is None:
            return None

        target_price = context.target_price
        stop_price = context.effective_stop_price
        if target_price is None or stop_price is None:
            return None

        low = float(event.low)
        high = float(event.high)
        if high >= stop_price and low <= target_price:
            return self._build_exit_decision(
                context=context,
                status=S23PaperLifecycleStatus.PAPER_POSITION_CLOSED,
                exit_reason_code="same_bar_target_stop_conflict_stoploss_wins",
                message=(
                    "Target and stoploss/FSL were both possible in the same selected-contract bar, so the conservative stoploss outcome was chosen."
                ),
                exit_price=stop_price + context.slippage_exit_points,
                exit_timestamp=event.bar_end,
                source_kind="selected_contract_bar",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                bar_open=event.open,
                bar_high=event.high,
                bar_low=event.low,
                bar_close=event.close,
                warning_flags=("same_bar_target_stop_conflict_stoploss_wins",),
            )

        if high >= stop_price:
            return self._build_exit_decision(
                context=context,
                status=S23PaperLifecycleStatus.PAPER_POSITION_CLOSED,
                exit_reason_code="stoploss_or_fsl_hit",
                message=(
                    "Selected-contract OHLC data breached the stoploss/FSL threshold, so the same-day paper position was closed conservatively."
                ),
                exit_price=stop_price + context.slippage_exit_points,
                exit_timestamp=event.bar_end,
                source_kind="selected_contract_bar",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                bar_open=event.open,
                bar_high=event.high,
                bar_low=event.low,
                bar_close=event.close,
            )

        if low <= target_price:
            return self._build_exit_decision(
                context=context,
                status=S23PaperLifecycleStatus.PAPER_POSITION_CLOSED,
                exit_reason_code="target_hit",
                message=(
                    "Selected-contract OHLC data proved the target was hit for the same-day paper position."
                ),
                exit_price=target_price + context.slippage_exit_points,
                exit_timestamp=event.bar_end,
                source_kind="selected_contract_bar",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                bar_open=event.open,
                bar_high=event.high,
                bar_low=event.low,
                bar_close=event.close,
            )

        return None

    def _manual_abort_decision(
        self,
        *,
        context: _LifecycleContext,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> S23PaperLifecycleDecision:
        for event in self._sorted_market_events(market_events):
            if event.symbol != context.selected_contract_symbol:
                continue
            event_timestamp = self._event_effective_timestamp(event)
            if context.fill_timestamp is not None and event_timestamp < context.fill_timestamp:
                continue
            if event_timestamp.date() != context.session_date:
                continue
            if event_timestamp > self._session_cutoff(context):
                continue
            if event.envelope.captured_at - event.envelope.effective_timestamp > self._max_selected_contract_age:
                continue
            exit_price = self._conservative_exit_price_for_manual_close(
                context=context,
                event=event,
            )
            if exit_price is None:
                continue
            return self._build_exit_decision(
                context=context,
                status=S23PaperLifecycleStatus.PAPER_POSITION_CLOSED,
                exit_reason_code="manual_operator_abort_during_open_position",
                message=(
                    self._guardrail_settings.manual_abort_during_lifecycle_reason
                    or "An operator aborted the S23 same-day lifecycle loop after the paper position opened, so the paper position was closed conservatively."
                ),
                exit_price=exit_price,
                exit_timestamp=self._event_effective_timestamp(event),
                source_kind=(
                    "selected_contract_quote"
                    if isinstance(event, SelectedContractQuoteEvent)
                    else "selected_contract_bar"
                ),
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                quote_bid=(event.bid if isinstance(event, SelectedContractQuoteEvent) else None),
                quote_ask=(event.ask if isinstance(event, SelectedContractQuoteEvent) else None),
                quote_ltp=(event.ltp if isinstance(event, SelectedContractQuoteEvent) else None),
                bar_open=(event.open if isinstance(event, SelectedContractBarEvent) else None),
                bar_high=(event.high if isinstance(event, SelectedContractBarEvent) else None),
                bar_low=(event.low if isinstance(event, SelectedContractBarEvent) else None),
                bar_close=(event.close if isinstance(event, SelectedContractBarEvent) else None),
            )

        return self._build_abort_decision_from_reason(
            context=context,
            evaluation_timestamp=context.fill_timestamp or self._session_cutoff(context),
            reason_code="manual_operator_abort_during_open_position",
            message=(
                self._guardrail_settings.manual_abort_during_lifecycle_reason
                or "An operator aborted the S23 same-day lifecycle loop, but no fresh selected-contract price was available to close the paper position conservatively."
            ),
            warning_flags=("manual_operator_abort_during_open_position",),
        )

    def _build_eod_square_off_decision(
        self,
        *,
        context: _LifecycleContext,
        event: SelectedContractQuoteEvent | SelectedContractBarEvent,
        warning_flags: tuple[str, ...],
    ) -> S23PaperLifecycleDecision:
        if isinstance(event, SelectedContractQuoteEvent):
            exit_reference = (
                float(event.ask)
                if event.ask is not None
                else (float(event.ltp) if event.ltp is not None else None)
            )
            if exit_reference is None:
                return self._build_abort_decision_from_reason(
                    context=context,
                    evaluation_timestamp=self._event_effective_timestamp(event),
                    reason_code="missing_eod_selected_contract_price",
                    message=(
                        "No usable selected-contract quote was available to square off the same-day paper position at EOD."
                    ),
                    warning_flags=warning_flags or ("missing_eod_selected_contract_price",),
                )
            return self._build_exit_decision(
                context=context,
                status=S23PaperLifecycleStatus.PAPER_EOD_SQUARE_OFF,
                exit_reason_code="eod_square_off",
                message=(
                    "No target or stoploss/FSL was hit before the same-day cutoff, so the paper position was squared off at the last available selected-contract price."
                ),
                exit_price=exit_reference + context.slippage_exit_points,
                exit_timestamp=event.envelope.effective_timestamp,
                source_kind="selected_contract_quote",
                source_type=event.envelope.source_type,
                source_id=event.envelope.source_id,
                source_effective_timestamp=event.envelope.effective_timestamp,
                quote_bid=event.bid,
                quote_ask=event.ask,
                quote_ltp=event.ltp,
                warning_flags=warning_flags,
            )

        if event.close is None:
            return self._build_abort_decision_from_reason(
                context=context,
                evaluation_timestamp=event.bar_end,
                reason_code="missing_eod_selected_contract_price",
                message=(
                    "No usable selected-contract close was available to square off the same-day paper position at EOD."
                ),
                warning_flags=warning_flags or ("missing_eod_selected_contract_price",),
            )
        return self._build_exit_decision(
            context=context,
            status=S23PaperLifecycleStatus.PAPER_EOD_SQUARE_OFF,
            exit_reason_code="eod_square_off",
            message=(
                "No target or stoploss/FSL was hit before the same-day cutoff, so the paper position was squared off at the last available selected-contract close."
            ),
            exit_price=float(event.close) + context.slippage_exit_points,
            exit_timestamp=event.bar_end,
            source_kind="selected_contract_bar",
            source_type=event.envelope.source_type,
            source_id=event.envelope.source_id,
            source_effective_timestamp=event.envelope.effective_timestamp,
            bar_open=event.open,
            bar_high=event.high,
            bar_low=event.low,
            bar_close=event.close,
            warning_flags=warning_flags,
        )

    def _persist_lifecycle_outcome(
        self,
        *,
        context: _LifecycleContext,
        position: S23PaperPosition | None,
        decision: S23PaperLifecycleDecision,
        lifecycle_events: tuple[dict[str, Any], ...],
    ) -> S23PaperLifecycleArtifactSet:
        session_dir = context.session_directory
        paper_position_path = session_dir / "paper_position.json"
        lifecycle_events_path = session_dir / "lifecycle_events.jsonl"
        paper_exit_path = session_dir / "paper_exit.json"
        paper_pnl_summary_path = session_dir / "paper_pnl_summary.json"
        execution_journal_path = session_dir / "execution_journal.jsonl"
        execution_summary_path = session_dir / "execution_summary.json"

        if position is not None:
            self._write_json(paper_position_path, position)
        self._write_jsonl(lifecycle_events_path, lifecycle_events)
        self._write_json(paper_exit_path, decision)

        if decision.gross_pnl_rupees is not None:
            pnl_summary = {
                "artifact_version": _ARTIFACT_VERSION,
                "session_id": context.session_id,
                "session_date": context.session_date.isoformat(),
                "strategy_code": context.strategy_code,
                "status": decision.status.value,
                "selected_contract_symbol": context.selected_contract_symbol,
                "entry_price": context.entry_price,
                "exit_price": decision.exit_price,
                "quantity": context.quantity,
                "lots": context.lots,
                "gross_pnl_rupees": decision.gross_pnl_rupees,
                "brokerage_rupees": decision.brokerage_rupees,
                "net_pnl_rupees": decision.net_pnl_rupees,
                "costs_applied": True,
                "disclaimer": decision.disclaimer,
            }
            self._write_json(paper_pnl_summary_path, pnl_summary)
            pnl_path: Path | None = paper_pnl_summary_path
        else:
            self._cleanup_optional_file(paper_pnl_summary_path)
            pnl_path = None

        journal_rows = list(context.execution_journal_rows)
        for row in lifecycle_events:
            journal_rows.append(
                self._journal_event_payload(
                    timestamp=self._optional_datetime(row.get("timestamp"))
                    or context.fill_timestamp
                    or self._session_cutoff(context),
                    event_type=str(row.get("event_type")),
                    session_id=context.session_id,
                    strategy_code=context.strategy_code,
                    terminal_state=PaperSessionState.ORDER_PLANNED,
                    status=str(row.get("status")),
                    reason_code=self._text_or_none(row.get("reason_code")),
                    message=str(row.get("message") or ""),
                    selected_contract_symbol=context.selected_contract_symbol,
                    guardrail_code=self._text_or_none(row.get("guardrail_code")),
                    guardrail_message=self._text_or_none(row.get("guardrail_message")),
                    blocking_source_id=self._text_or_none(row.get("blocking_source_id")),
                    operator_action_required=self._text_or_none(
                        row.get("operator_action_required")
                    ),
                )
            )
        self._write_jsonl(execution_journal_path, tuple(journal_rows))

        execution_summary_payload = dict(context.execution_summary_payload)
        execution_summary_payload.update(
            {
                "status": decision.status.value,
                "lifecycle_status": decision.status.value,
                "lifecycle_reason_code": decision.exit_reason_code,
                "lifecycle_message": decision.message,
                "position_opened": position is not None,
                "position_closed": decision.status
                in {
                    S23PaperLifecycleStatus.PAPER_POSITION_CLOSED,
                    S23PaperLifecycleStatus.PAPER_EOD_SQUARE_OFF,
                },
                "order_placed": False,
                "fill_simulated": True,
                "lifecycle_simulated": True,
                "future_fill_simulation_eligible": False,
                "exit_price": decision.exit_price,
                "exit_timestamp": (
                    decision.exit_timestamp.isoformat()
                    if decision.exit_timestamp is not None
                    else None
                ),
                "exit_reason_code": decision.exit_reason_code,
                "gross_pnl_rupees": decision.gross_pnl_rupees,
                "brokerage_rupees": decision.brokerage_rupees,
                "net_pnl_rupees": decision.net_pnl_rupees,
                "lifecycle_warning_flags": list(decision.warning_flags),
                "terminal_reason_code": decision.exit_reason_code,
                "message": decision.message,
                "guardrail_code": decision.guardrail_code,
                "guardrail_message": decision.guardrail_message,
                "blocking_source_id": decision.blocking_source_id,
                "operator_action_required": decision.operator_action_required,
                "disclaimer": decision.disclaimer,
            }
        )
        self._write_json(execution_summary_path, execution_summary_payload)

        return S23PaperLifecycleArtifactSet(
            session_directory=session_dir,
            paper_position_path=paper_position_path if paper_position_path.exists() else None,
            lifecycle_events_path=lifecycle_events_path,
            paper_exit_path=paper_exit_path,
            paper_pnl_summary_path=pnl_path,
            execution_journal_path=execution_journal_path,
            execution_summary_path=execution_summary_path,
        )

    def _build_position(self, context: _LifecycleContext) -> S23PaperPosition:
        if (
            context.selected_contract_symbol is None
            or context.entry_price is None
            or context.target_price is None
            or context.effective_stop_price is None
            or context.fill_timestamp is None
        ):
            raise S23PaperLifecycleError(
                "S23 Phase 2 lifecycle simulation context is missing required position fields."
            )
        return S23PaperPosition(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=S23PaperLifecycleStatus.PAPER_POSITION_OPEN,
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            side=context.side,
            lots=context.lots,
            quantity=context.quantity,
            entry_price=context.entry_price,
            target_price=context.target_price,
            stoploss_price=context.stoploss_price,
            fsl_price=context.fsl_price,
            effective_stop_price=context.effective_stop_price,
            entry_timestamp=context.fill_timestamp,
            source_branch=context.source_branch,
            source_workbook_rule=context.source_workbook_rule,
            workbook_row_number=context.workbook_row_number,
            provenance_source_kind=context.fill_source_kind,
            provenance_source_type=context.fill_source_type,
            provenance_source_id=context.fill_source_id,
            disclaimer=_PHASE2_LIFECYCLE_DISCLAIMER,
        )

    def _build_exit_decision(
        self,
        *,
        context: _LifecycleContext,
        status: S23PaperLifecycleStatus,
        exit_reason_code: str,
        message: str,
        exit_price: float,
        exit_timestamp: datetime,
        source_kind: str,
        source_type: str,
        source_id: str,
        source_effective_timestamp: datetime,
        quote_bid: float | None = None,
        quote_ask: float | None = None,
        quote_ltp: float | None = None,
        bar_open: float | None = None,
        bar_high: float | None = None,
        bar_low: float | None = None,
        bar_close: float | None = None,
        warning_flags: tuple[str, ...] = (),
    ) -> S23PaperLifecycleDecision:
        if context.entry_price is None:
            raise S23PaperLifecycleError("Lifecycle entry price is missing.")
        gross_pnl = round((context.entry_price - exit_price) * context.quantity, 6)
        brokerage = round(context.brokerage_per_lot * context.lots, 6)
        net_pnl = round(gross_pnl - brokerage, 6)
        return S23PaperLifecycleDecision(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=status,
            selected_contract_symbol=context.selected_contract_symbol or "",
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            side=context.side,
            lots=context.lots,
            quantity=context.quantity,
            entry_price=context.entry_price,
            target_price=context.target_price or 0.0,
            stoploss_price=context.stoploss_price,
            fsl_price=context.fsl_price,
            effective_stop_price=context.effective_stop_price or 0.0,
            entry_timestamp=context.fill_timestamp or exit_timestamp,
            exit_price=round(exit_price, 6),
            exit_timestamp=exit_timestamp,
            exit_reason_code=exit_reason_code,
            message=message,
            source_kind=source_kind,
            source_type=source_type,
            source_id=source_id,
            source_effective_timestamp=source_effective_timestamp,
            quote_bid=quote_bid,
            quote_ask=quote_ask,
            quote_ltp=quote_ltp,
            bar_open=bar_open,
            bar_high=bar_high,
            bar_low=bar_low,
            bar_close=bar_close,
            gross_pnl_rupees=gross_pnl,
            brokerage_rupees=brokerage,
            net_pnl_rupees=net_pnl,
            guardrail_code=None,
            guardrail_message=None,
            blocking_source_id=None,
            operator_action_required=None,
            warning_flags=tuple(sorted(set(warning_flags))),
            disclaimer=_PHASE2_LIFECYCLE_DISCLAIMER,
        )

    def _build_abort_decision(
        self,
        *,
        context: _LifecycleContext,
        evaluation_timestamp: datetime | None,
        guardrail: PaperGuardrailDecision,
        warning_flags: tuple[str, ...],
    ) -> S23PaperLifecycleDecision:
        return S23PaperLifecycleDecision(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=S23PaperLifecycleStatus.PAPER_LIFECYCLE_ABORTED,
            selected_contract_symbol=context.selected_contract_symbol or "",
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            side=context.side,
            lots=context.lots,
            quantity=context.quantity,
            entry_price=context.entry_price or 0.0,
            target_price=context.target_price or 0.0,
            stoploss_price=context.stoploss_price,
            fsl_price=context.fsl_price,
            effective_stop_price=context.effective_stop_price or 0.0,
            entry_timestamp=context.fill_timestamp or evaluation_timestamp or self._session_cutoff(context),
            exit_price=None,
            exit_timestamp=evaluation_timestamp,
            exit_reason_code=guardrail.code,
            message=guardrail.message,
            source_kind=None,
            source_type=None,
            source_id=None,
            source_effective_timestamp=None,
            quote_bid=None,
            quote_ask=None,
            quote_ltp=None,
            bar_open=None,
            bar_high=None,
            bar_low=None,
            bar_close=None,
            gross_pnl_rupees=None,
            brokerage_rupees=None,
            net_pnl_rupees=None,
            guardrail_code=guardrail.code,
            guardrail_message=guardrail.message,
            blocking_source_id=guardrail.blocking_source_id,
            operator_action_required=guardrail.operator_action_required,
            warning_flags=tuple(sorted(set(warning_flags))),
            disclaimer=_PHASE2_LIFECYCLE_DISCLAIMER,
        )

    def _build_abort_decision_from_reason(
        self,
        *,
        context: _LifecycleContext,
        evaluation_timestamp: datetime,
        reason_code: str,
        message: str,
        warning_flags: tuple[str, ...],
        blocking_source_id: str | None = None,
    ) -> S23PaperLifecycleDecision:
        return S23PaperLifecycleDecision(
            artifact_version=_ARTIFACT_VERSION,
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            status=S23PaperLifecycleStatus.PAPER_LIFECYCLE_ABORTED,
            selected_contract_symbol=context.selected_contract_symbol or "",
            selected_contract_option_type=context.selected_contract_option_type,
            selected_contract_expiry=context.selected_contract_expiry,
            side=context.side,
            lots=context.lots,
            quantity=context.quantity,
            entry_price=context.entry_price or 0.0,
            target_price=context.target_price or 0.0,
            stoploss_price=context.stoploss_price,
            fsl_price=context.fsl_price,
            effective_stop_price=context.effective_stop_price or 0.0,
            entry_timestamp=context.fill_timestamp or evaluation_timestamp,
            exit_price=None,
            exit_timestamp=evaluation_timestamp,
            exit_reason_code=reason_code,
            message=message,
            source_kind=None,
            source_type=None,
            source_id=None,
            source_effective_timestamp=None,
            quote_bid=None,
            quote_ask=None,
            quote_ltp=None,
            bar_open=None,
            bar_high=None,
            bar_low=None,
            bar_close=None,
            gross_pnl_rupees=None,
            brokerage_rupees=None,
            net_pnl_rupees=None,
            guardrail_code=reason_code,
            guardrail_message=message,
            blocking_source_id=blocking_source_id,
            operator_action_required=(
                "Review the selected-contract lifecycle data before retrying the same-day paper lifecycle loop."
            ),
            warning_flags=tuple(sorted(set(warning_flags))),
            disclaimer=_PHASE2_LIFECYCLE_DISCLAIMER,
        )

    def _with_warning(
        self,
        decision: S23PaperLifecycleDecision,
        warning_flag: str,
    ) -> S23PaperLifecycleDecision:
        return S23PaperLifecycleDecision(
            **{
                **asdict(decision),
                "warning_flags": tuple(sorted(set(decision.warning_flags + (warning_flag,)))),
            }
        )

    def _conservative_exit_price_for_manual_close(
        self,
        *,
        context: _LifecycleContext,
        event: SelectedContractQuoteEvent | SelectedContractBarEvent,
    ) -> float | None:
        if isinstance(event, SelectedContractQuoteEvent):
            reference = (
                float(event.ask)
                if event.ask is not None
                else (float(event.ltp) if event.ltp is not None else None)
            )
            if reference is None:
                return None
            return reference + context.slippage_exit_points
        if event.close is None:
            return None
        return float(event.close) + context.slippage_exit_points

    def _effective_stop_price(
        self,
        stoploss_price: float | None,
        fsl_price: float | None,
    ) -> float | None:
        candidates = [value for value in (stoploss_price, fsl_price) if value is not None]
        if not candidates:
            return None
        return min(float(item) for item in candidates)

    def _is_usable_for_eod(
        self,
        context: _LifecycleContext,
        event: SelectedContractQuoteEvent | SelectedContractBarEvent,
    ) -> bool:
        event_timestamp = self._event_effective_timestamp(event)
        return event_timestamp >= self._session_cutoff(context) - self._eod_price_age_window

    def _session_cutoff(self, context: _LifecycleContext) -> datetime:
        base = context.fill_timestamp
        if base is None:
            raise S23PaperLifecycleError(
                "Cannot derive a same-day lifecycle cutoff without a paper fill timestamp."
            )
        return datetime.combine(
            context.session_date,
            self._eod_cutoff,
            tzinfo=base.tzinfo,
        )

    def _fallback_session_cutoff(self, context: _LifecycleContext) -> datetime:
        base = context.fill_timestamp
        if base is not None:
            return self._session_cutoff(context)
        if context.execution_journal_rows:
            timestamp = self._optional_datetime(
                context.execution_journal_rows[-1].get("timestamp")
            )
            if timestamp is not None:
                return datetime.combine(
                    context.session_date,
                    self._eod_cutoff,
                    tzinfo=timestamp.tzinfo,
                )
        return datetime.combine(context.session_date, self._eod_cutoff)

    def _event_effective_timestamp(
        self,
        event: SelectedContractQuoteEvent | SelectedContractBarEvent,
    ) -> datetime:
        if isinstance(event, SelectedContractBarEvent):
            return event.bar_end
        return event.envelope.effective_timestamp

    def _sorted_market_events(
        self,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    ) -> tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...]:
        def _key(
            event: SelectedContractQuoteEvent | SelectedContractBarEvent,
        ) -> tuple[datetime, datetime, int]:
            event_order = 0 if isinstance(event, SelectedContractQuoteEvent) else 1
            return (
                self._event_effective_timestamp(event),
                event.envelope.captured_at,
                event_order,
            )

        return tuple(sorted(market_events, key=_key))

    def _existing_lifecycle_attempt(self, session_directory: Path) -> bool:
        return any(
            (session_directory / filename).exists()
            for filename in (
                "paper_position.json",
                "paper_exit.json",
                "paper_pnl_summary.json",
                "lifecycle_events.jsonl",
            )
        )

    def _derive_evaluation_timestamp(
        self,
        *,
        created_at: datetime | None,
        market_events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
        fallback: datetime | None,
    ) -> datetime | None:
        if created_at is not None:
            return created_at
        latest = fallback
        for event in market_events:
            captured_at = event.envelope.captured_at
            if latest is None or captured_at > latest:
                latest = captured_at
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
        }

    def _lifecycle_event(
        self,
        *,
        timestamp: datetime,
        event_type: str,
        context: _LifecycleContext,
        decision: S23PaperLifecycleDecision | None,
        reason_code: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        return {
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "status": event_type,
            "session_id": context.session_id,
            "strategy_code": context.strategy_code,
            "selected_contract_symbol": context.selected_contract_symbol,
            "reason_code": (
                decision.exit_reason_code
                if decision is not None
                else reason_code
            ),
            "message": decision.message if decision is not None else message,
            "guardrail_code": decision.guardrail_code if decision is not None else None,
            "guardrail_message": (
                decision.guardrail_message if decision is not None else None
            ),
            "blocking_source_id": (
                decision.blocking_source_id if decision is not None else None
            ),
            "operator_action_required": (
                decision.operator_action_required if decision is not None else None
            ),
            "source_kind": decision.source_kind if decision is not None else None,
            "source_type": decision.source_type if decision is not None else None,
            "source_id": decision.source_id if decision is not None else None,
        }

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized = self._normalize(payload)
        raw = json.dumps(normalized, indent=2, sort_keys=True) + "\n"
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(raw, encoding="utf-8", newline="\n")
        os.replace(tmp_path, path)

    def _write_jsonl(self, path: Path, rows: tuple[dict[str, Any], ...]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = "".join(
            json.dumps(self._normalize(item), sort_keys=True) + "\n" for item in rows
        )
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(raw, encoding="utf-8", newline="\n")
        os.replace(tmp_path, path)

    def _cleanup_optional_file(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def _load_json_required(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise S23PaperLifecycleError(f"Required lifecycle artifact is missing: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_optional_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_jsonl_optional(self, path: Path) -> tuple[dict[str, Any], ...]:
        if not path.exists():
            return ()
        rows: list[dict[str, Any]] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped:
                rows.append(json.loads(stripped))
        return tuple(rows)

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return self._normalize(asdict(value))
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, tuple):
            return [self._normalize(item) for item in value]
        if isinstance(value, list):
            return [self._normalize(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._normalize(val) for key, val in value.items()}
        return value

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def _text_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
