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
from .models import PaperSessionState
from .paper_vs_historical import PaperHistoricalComparisonStatus
from .replay_bundle import (
    S23PaperReplayBundleManager,
    S23PaperReplayBundleValidationResult,
)
from .review import (
    S23PaperReviewError,
    S23PaperReviewSummary,
    S23PaperSessionReviewer,
)
from .validation import DEFAULT_MAX_QUOTE_AGE


_ARTIFACT_VERSION = 1
_INTENT_EVENT_TYPE = "INTENT_CREATED"
_BLOCKED_EVENT_TYPE = "INTENT_BLOCKED"
_ABORTED_EVENT_TYPE = "INTENT_ABORTED"
_SKIPPED_EVENT_TYPE = "INTENT_SKIPPED"
_EXECUTION_ARMED_EVENT_TYPE = "EXECUTION_ARMED"
_EXECUTION_BLOCKED_EVENT_TYPE = "EXECUTION_BLOCKED"
_EXECUTION_ABORTED_EVENT_TYPE = "EXECUTION_ABORTED"
_EXECUTION_SKIPPED_EVENT_TYPE = "EXECUTION_SKIPPED"
_DISPATCH_READY_EVENT_TYPE = "ORDER_INTENT_DISPATCH_READY"
_DISPATCHED_EVENT_TYPE = "ORDER_INTENT_DISPATCHED"
_DISPATCH_BLOCKED_EVENT_TYPE = "ORDER_INTENT_DISPATCH_BLOCKED"
_DISPATCH_CANCELLED_EVENT_TYPE = "ORDER_INTENT_CANCELLED"
_DISPATCH_SKIPPED_EVENT_TYPE = "ORDER_INTENT_DISPATCH_SKIPPED"
_HANDOFF_READY_EVENT_TYPE = "PAPER_EXECUTION_HANDOFF_READY"
_HANDOFF_BLOCKED_EVENT_TYPE = "PAPER_EXECUTION_HANDOFF_BLOCKED"
_HANDOFF_ABORTED_EVENT_TYPE = "PAPER_EXECUTION_HANDOFF_ABORTED"
_HANDOFF_SKIPPED_EVENT_TYPE = "PAPER_EXECUTION_HANDOFF_SKIPPED"
_NO_EXECUTION_DISCLAIMER = (
    "No order was placed, no fill was simulated, no position was opened, and "
    "no lifecycle monitoring occurred yet; this is a pre-execution paper-shell "
    "journal."
)
_SUPPORTED_TERMINAL_STATES = frozenset(
    {
        PaperSessionState.ORDER_PLANNED,
        PaperSessionState.NO_TRADE,
        PaperSessionState.ABORTED,
    }
)


class S23PaperExecutionJournalError(RuntimeError):
    """Raised when paper execution-journal artifacts cannot be produced safely."""


class S23PaperIntentPhaseStatus(str, Enum):
    INTENT_READY = "INTENT_READY"
    INTENT_BLOCKED = "INTENT_BLOCKED"
    INTENT_ABORTED = "INTENT_ABORTED"
    INTENT_SKIPPED = "INTENT_SKIPPED"


class S23PaperExecutionShellStatus(str, Enum):
    EXECUTION_ARMED = "EXECUTION_ARMED"
    EXECUTION_BLOCKED = "EXECUTION_BLOCKED"
    EXECUTION_ABORTED = "EXECUTION_ABORTED"
    EXECUTION_SKIPPED = "EXECUTION_SKIPPED"


class S23PaperDispatchShellStatus(str, Enum):
    ORDER_INTENT_DISPATCH_READY = "ORDER_INTENT_DISPATCH_READY"
    ORDER_INTENT_DISPATCHED = "ORDER_INTENT_DISPATCHED"
    ORDER_INTENT_DISPATCH_BLOCKED = "ORDER_INTENT_DISPATCH_BLOCKED"
    ORDER_INTENT_CANCELLED = "ORDER_INTENT_CANCELLED"
    ORDER_INTENT_DISPATCH_SKIPPED = "ORDER_INTENT_DISPATCH_SKIPPED"


class S23PaperHandoffShellStatus(str, Enum):
    PAPER_EXECUTION_HANDOFF_READY = "PAPER_EXECUTION_HANDOFF_READY"
    PAPER_EXECUTION_HANDOFF_BLOCKED = "PAPER_EXECUTION_HANDOFF_BLOCKED"
    PAPER_EXECUTION_HANDOFF_ABORTED = "PAPER_EXECUTION_HANDOFF_ABORTED"
    PAPER_EXECUTION_HANDOFF_SKIPPED = "PAPER_EXECUTION_HANDOFF_SKIPPED"


@dataclass(frozen=True, slots=True)
class S23PaperOrderIntent:
    artifact_version: int
    session_id: str
    session_date: date
    strategy_code: str
    terminal_state: PaperSessionState
    status: str
    selected_contract_symbol: str
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    selected_contract_ltp: float | None
    side: str
    lots: int
    quantity: int
    planned_entry_price: float
    target_price: float
    stoploss_price: float
    fsl_price: float | None
    order_reference_time: datetime
    order_reference_label: str
    source_branch: str
    source_workbook_rule: str | None
    workbook_row_number: int | None
    data_source_count: int
    data_source_ids: tuple[str, ...]
    data_source_types: tuple[str, ...]
    synthetic_fixture_used: bool
    bundle_validation_performed: bool
    bundle_valid: bool | None
    disclaimer: str


@dataclass(frozen=True, slots=True)
class S23PaperOrderIntentValidationResult:
    is_valid: bool
    can_create_intent: bool
    status: S23PaperIntentPhaseStatus
    terminal_state: PaperSessionState
    reason_code: str | None
    message: str
    errors: tuple[str, ...]
    operator_action_required: str | None
    bundle_validation_performed: bool
    bundle_valid: bool | None
    guardrail_decision: PaperGuardrailDecision | None = None


@dataclass(frozen=True, slots=True)
class S23PaperExecutionShellValidationResult:
    is_valid: bool
    can_arm_execution: bool
    status: S23PaperExecutionShellStatus
    terminal_state: PaperSessionState
    reason_code: str | None
    message: str
    operator_action_required: str | None
    bundle_validation_performed: bool
    bundle_valid: bool | None
    historical_comparison_status: str | None
    historical_comparison_reason: str | None
    historical_comparison_go_no_go: str | None
    guardrail_decision: PaperGuardrailDecision | None = None


@dataclass(frozen=True, slots=True)
class S23PaperDispatchShellValidationResult:
    is_valid: bool
    can_dispatch_intent: bool
    status: S23PaperDispatchShellStatus
    terminal_state: PaperSessionState
    reason_code: str | None
    message: str
    operator_action_required: str | None
    bundle_validation_performed: bool
    bundle_valid: bool | None
    historical_comparison_status: str | None
    historical_comparison_reason: str | None
    historical_comparison_go_no_go: str | None
    guardrail_decision: PaperGuardrailDecision | None = None


@dataclass(frozen=True, slots=True)
class S23PaperHandoffShellValidationResult:
    is_valid: bool
    can_handoff_execution: bool
    status: S23PaperHandoffShellStatus
    terminal_state: PaperSessionState
    reason_code: str | None
    message: str
    operator_action_required: str | None
    bundle_validation_performed: bool
    bundle_valid: bool | None
    historical_comparison_status: str | None
    historical_comparison_reason: str | None
    historical_comparison_go_no_go: str | None
    guardrail_decision: PaperGuardrailDecision | None = None


@dataclass(frozen=True, slots=True)
class S23PaperExecutionJournalEvent:
    timestamp: datetime
    event_type: str
    session_id: str
    strategy_code: str
    terminal_state: PaperSessionState
    status: str
    reason_code: str | None
    message: str
    selected_contract_symbol: str | None
    guardrail_code: str | None
    guardrail_message: str | None
    blocking_event_type: str | None
    blocking_source_id: str | None
    operator_action_required: str | None
    bundle_validation_performed: bool
    bundle_valid: bool | None
    disclaimer: str


@dataclass(frozen=True, slots=True)
class S23PaperExecutionJournalSummary:
    artifact_version: int
    session_id: str
    session_date: date
    strategy_code: str
    terminal_state: PaperSessionState
    status: str
    intent_status: str | None
    execution_shell_status: str | None
    dispatch_shell_status: str | None
    handoff_shell_status: str | None
    created_order_intent: bool
    intent_dispatched: bool
    order_placed: bool
    fill_simulated: bool
    position_opened: bool
    future_fill_simulation_eligible: bool
    terminal_reason_code: str | None
    message: str
    selected_contract_symbol: str | None
    guardrail_code: str | None
    guardrail_message: str | None
    blocking_event_type: str | None
    blocking_source_id: str | None
    operator_action_required: str | None
    bundle_validation_performed: bool
    bundle_valid: bool | None
    historical_comparison_status: str | None
    historical_comparison_reason: str | None
    historical_comparison_go_no_go: str | None
    journal_event_count: int
    disclaimer: str


@dataclass(frozen=True, slots=True)
class S23PaperExecutionJournalArtifactSet:
    session_directory: Path
    paper_order_intent_path: Path | None
    execution_journal_path: Path
    execution_summary_path: Path
    intent_block_summary_path: Path | None
    execution_arm_summary_path: Path | None = None
    execution_block_summary_path: Path | None = None
    intent_dispatch_summary_path: Path | None = None
    execution_handoff_summary_path: Path | None = None


@dataclass(frozen=True, slots=True)
class _PostPlanningContext:
    session_directory: Path
    session_id: str
    session_date: date
    strategy_code: str
    terminal_state: PaperSessionState
    selected_contract_symbol: str | None
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    selected_contract_ltp: float | None
    selected_contract_effective_timestamp: datetime | None
    data_source_count: int
    data_source_ids: tuple[str, ...]
    data_source_types: tuple[str, ...]
    synthetic_fixture_used: bool
    order_plan_selected_contract_symbol: str | None
    existing_journal_rows: tuple[dict[str, Any], ...]
    execution_summary_payload: dict[str, Any] | None
    intent_dispatch_summary_payload: dict[str, Any] | None
    execution_handoff_summary_payload: dict[str, Any] | None
    replay_validation: S23PaperReplayBundleValidationResult | None
    intent_payload: dict[str, Any] | None
    intent_artifact_issue: str | None


class S23PaperExecutionJournalWriter:
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
        self._replay_bundle_manager = replay_bundle_manager or S23PaperReplayBundleManager()
        self._guardrail_evaluator = guardrail_evaluator or S23PaperGuardrailEvaluator(
            guardrail_settings
        )
        self._max_selected_contract_age = max_selected_contract_age

    def write_from_session(
        self,
        session_directory: str | Path,
        *,
        bundle_directory: str | Path | None = None,
        created_at: datetime | None = None,
    ) -> S23PaperExecutionJournalArtifactSet:
        session_dir = Path(session_directory)
        if self._has_post_planning_shell(session_dir):
            return self._write_post_planning_from_session(
                session_dir,
                bundle_directory=bundle_directory,
                created_at=created_at,
            )

        summary = self._reviewer.review_session(
            session_directory,
            bundle_directory=bundle_directory,
        )
        return self.write_from_review(summary, created_at=created_at)

    def arm_execution_from_session(
        self,
        session_directory: str | Path,
        *,
        bundle_directory: str | Path | None = None,
        historical_comparison_path: str | Path | None = None,
        created_at: datetime | None = None,
    ) -> S23PaperExecutionJournalArtifactSet:
        session_dir = Path(session_directory)
        if not self._has_post_planning_shell(session_dir):
            raise S23PaperExecutionJournalError(
                "S23 execution-shell arming requires an existing intent shell. "
                "Create the paper order intent first."
            )

        context = self._load_post_planning_context(
            session_dir,
            bundle_directory=bundle_directory,
        )
        event_timestamp = created_at or datetime.now().astimezone()
        comparison_payload, comparison_issue = self._load_historical_comparison_payload(
            historical_comparison_path
        )
        return self._arm_execution_from_context(
            context,
            timestamp=event_timestamp,
            comparison_payload=comparison_payload,
            comparison_issue=comparison_issue,
        )

    def dispatch_order_intent_from_session(
        self,
        session_directory: str | Path,
        *,
        bundle_directory: str | Path | None = None,
        created_at: datetime | None = None,
    ) -> S23PaperExecutionJournalArtifactSet:
        session_dir = Path(session_directory)
        if not self._has_post_planning_shell(session_dir):
            raise S23PaperExecutionJournalError(
                "S23 fillless dispatch requires an existing intent shell. "
                "Create the paper order intent first."
            )

        context = self._load_post_planning_context(
            session_dir,
            bundle_directory=bundle_directory,
        )
        event_timestamp = created_at or datetime.now().astimezone()
        return self._dispatch_order_intent_from_context(
            context,
            timestamp=event_timestamp,
        )

    def mark_execution_handoff_ready_from_session(
        self,
        session_directory: str | Path,
        *,
        bundle_directory: str | Path | None = None,
        created_at: datetime | None = None,
    ) -> S23PaperExecutionJournalArtifactSet:
        session_dir = Path(session_directory)
        if not self._has_post_planning_shell(session_dir):
            raise S23PaperExecutionJournalError(
                "S23 execution handoff requires an existing fillless intent shell. "
                "Create the paper order intent first."
            )

        context = self._load_post_planning_context(
            session_dir,
            bundle_directory=bundle_directory,
        )
        event_timestamp = created_at or datetime.now().astimezone()
        return self._mark_execution_handoff_ready_from_context(
            context,
            timestamp=event_timestamp,
        )

    def write_from_review(
        self,
        summary: S23PaperReviewSummary,
        *,
        created_at: datetime | None = None,
    ) -> S23PaperExecutionJournalArtifactSet:
        validation = self.validate_review(summary)
        if not validation.is_valid:
            raise S23PaperExecutionJournalError(
                "S23 paper execution journal cannot be created: "
                + ", ".join(validation.errors)
            )

        session_directory = Path(summary.session_directory)
        session_directory.mkdir(parents=True, exist_ok=True)
        event_timestamp = created_at or self._derive_event_timestamp(summary)

        status = validation.status
        guardrail = self._evaluate_post_planning_from_review(
            summary,
            validation=validation,
            evaluation_timestamp=event_timestamp,
        )
        if guardrail is not None:
            validation = self._validation_with_guardrail(
                validation,
                status=self._status_from_guardrail(guardrail),
                reason_code=guardrail.code,
                message=guardrail.message,
                operator_action_required=guardrail.operator_action_required,
                guardrail_decision=guardrail,
            )
            status = validation.status

        intent = None
        if validation.can_create_intent and status is S23PaperIntentPhaseStatus.INTENT_READY:
            intent = self._build_order_intent(summary, validation)

        journal_event = self._build_journal_event(
            session_id=summary.session_id,
            strategy_code=summary.strategy_code,
            terminal_state=summary.terminal_state,
            selected_contract_symbol=summary.selected_contract.symbol,
            validation=validation,
            timestamp=event_timestamp,
            intent_created=intent is not None,
        )
        execution_summary = self._build_execution_summary(
            session_id=summary.session_id,
            session_date=summary.session_date,
            strategy_code=summary.strategy_code,
            terminal_state=summary.terminal_state,
            selected_contract_symbol=summary.selected_contract.symbol,
            validation=validation,
            created_order_intent=intent is not None,
            journal_event_count=1,
            intent_status=validation.status.value,
            execution_shell_status=None,
            dispatch_shell_status=None,
            handoff_shell_status=None,
            intent_dispatched=False,
            future_fill_simulation_eligible=False,
            historical_comparison_status=None,
            historical_comparison_reason=None,
            historical_comparison_go_no_go=None,
        )

        paper_order_intent_path: Path | None = None
        if intent is not None:
            paper_order_intent_path = session_directory / "paper_order_intent.json"
            self._write_json(paper_order_intent_path, intent)

        execution_journal_path = session_directory / "execution_journal.jsonl"
        execution_summary_path = session_directory / "execution_summary.json"
        self._write_jsonl(execution_journal_path, (journal_event,))
        self._write_json(execution_summary_path, execution_summary)

        intent_block_summary_path: Path | None = None
        if status in {
            S23PaperIntentPhaseStatus.INTENT_BLOCKED,
            S23PaperIntentPhaseStatus.INTENT_ABORTED,
        }:
            intent_block_summary_path = session_directory / "intent_block_summary.json"
            self._write_json(intent_block_summary_path, execution_summary)

        return S23PaperExecutionJournalArtifactSet(
            session_directory=session_directory,
            paper_order_intent_path=paper_order_intent_path,
            execution_journal_path=execution_journal_path,
            execution_summary_path=execution_summary_path,
            intent_block_summary_path=intent_block_summary_path,
            execution_arm_summary_path=None,
            execution_block_summary_path=None,
            intent_dispatch_summary_path=None,
        )

    def validate_review(
        self,
        summary: S23PaperReviewSummary,
    ) -> S23PaperOrderIntentValidationResult:
        errors: list[str] = []
        bundle_validation_performed = summary.replay_bundle.validation_performed
        bundle_valid = summary.replay_bundle.is_valid

        if summary.strategy_code != "S23":
            errors.append("unsupported_strategy")

        if summary.terminal_state not in _SUPPORTED_TERMINAL_STATES:
            errors.append("unsupported_terminal_state")

        if summary.terminal_state is PaperSessionState.ORDER_PLANNED:
            order_plan = summary.order_plan
            selected_contract_path = Path(summary.session_directory) / "selected_contract.json"
            if order_plan is None:
                errors.append("missing_order_plan")
            if (
                not summary.selected_contract.available
                or not summary.selected_contract.symbol
                or not selected_contract_path.exists()
            ):
                errors.append("missing_selected_contract")

            if order_plan is not None:
                if order_plan.order_side != "SELL":
                    errors.append("unsupported_order_side")
                if order_plan.lots is None:
                    errors.append("missing_lots")
                if order_plan.quantity is None:
                    errors.append("missing_quantity")
                if order_plan.planned_entry_price is None:
                    errors.append("missing_planned_entry_price")
                if order_plan.target_price is None:
                    errors.append("missing_target_price")
                if order_plan.stoploss_price is None:
                    errors.append("missing_stoploss_price")
                if order_plan.order_reference_time is None:
                    errors.append("missing_order_reference_time")
                if not order_plan.order_reference_label:
                    errors.append("missing_order_reference_label")
                if not order_plan.strategy_branch:
                    errors.append("missing_strategy_branch")

            if errors:
                return S23PaperOrderIntentValidationResult(
                    is_valid=False,
                    can_create_intent=False,
                    status=S23PaperIntentPhaseStatus.INTENT_BLOCKED,
                    terminal_state=summary.terminal_state,
                    reason_code="order_plan_incomplete",
                    message="ORDER_PLANNED session is missing required intent fields.",
                    errors=tuple(errors),
                    operator_action_required="Review paper planning inputs before creating an execution journal.",
                    bundle_validation_performed=bundle_validation_performed,
                    bundle_valid=bundle_valid,
                )

            return S23PaperOrderIntentValidationResult(
                is_valid=True,
                can_create_intent=True,
                status=S23PaperIntentPhaseStatus.INTENT_READY,
                terminal_state=summary.terminal_state,
                reason_code=summary.terminal_reason_code or "order_planned",
                message="Paper order intent is ready from an ORDER_PLANNED S23 session. No order was placed or simulated.",
                errors=(),
                operator_action_required=None,
                bundle_validation_performed=bundle_validation_performed,
                bundle_valid=bundle_valid,
            )

        terminal_label = summary.terminal_state.value
        return S23PaperOrderIntentValidationResult(
            is_valid=True,
            can_create_intent=False,
            status=S23PaperIntentPhaseStatus.INTENT_SKIPPED,
            terminal_state=summary.terminal_state,
            reason_code=summary.terminal_reason_code,
            message=f"No paper order intent created because the S23 paper session ended in {terminal_label}.",
            errors=(),
            operator_action_required=summary.guardrail.operator_action_required,
            bundle_validation_performed=bundle_validation_performed,
            bundle_valid=bundle_valid,
        )

    def _write_post_planning_from_session(
        self,
        session_directory: Path,
        *,
        bundle_directory: str | Path | None,
        created_at: datetime | None,
    ) -> S23PaperExecutionJournalArtifactSet:
        context = self._load_post_planning_context(
            session_directory,
            bundle_directory=bundle_directory,
        )
        event_timestamp = created_at or datetime.now().astimezone()

        if context.strategy_code != "S23":
            raise S23PaperExecutionJournalError(
                "S23 paper execution journal cannot continue from a non-S23 session."
            )

        if context.terminal_state is not PaperSessionState.ORDER_PLANNED:
            validation = S23PaperOrderIntentValidationResult(
                is_valid=True,
                can_create_intent=False,
                status=S23PaperIntentPhaseStatus.INTENT_SKIPPED,
                terminal_state=context.terminal_state,
                reason_code=context.terminal_state.value.lower(),
                message=(
                    f"No paper order intent is available because the session terminal state is "
                    f"{context.terminal_state.value}."
                ),
                errors=(),
                operator_action_required=None,
                bundle_validation_performed=(
                    context.replay_validation is not None
                    and context.replay_validation.manifest is not None
                ),
                bundle_valid=(
                    context.replay_validation.is_valid
                    if context.replay_validation is not None
                    else None
                ),
            )
            return self._persist_post_planning_outcome(
                context=context,
                validation=validation,
                timestamp=event_timestamp,
            )

        if context.intent_artifact_issue == "corrupt_order_intent_artifact":
            validation = self._validation_from_decision(
                context,
                self._guardrail_evaluator.evaluate_post_planning(
                    evaluation_timestamp=event_timestamp,
                    max_selected_contract_age=self._max_selected_contract_age,
                    replay_bundle_validation_performed=(
                        context.replay_validation is not None
                        and context.replay_validation.manifest is not None
                    ),
                    replay_bundle_valid=(
                        context.replay_validation.is_valid
                        if context.replay_validation is not None
                        else None
                    ),
                    replay_bundle_errors=(
                        context.replay_validation.errors
                        if context.replay_validation is not None
                        else ()
                    ),
                    selected_contract_symbol=context.selected_contract_symbol,
                    selected_contract_effective_timestamp=context.selected_contract_effective_timestamp,
                    order_plan_selected_contract_symbol=context.order_plan_selected_contract_symbol,
                    intent_selected_contract_symbol=None,
                    require_intent_artifact=True,
                    intent_exists=False,
                    intent_artifact_issue="corrupt_order_intent_artifact",
                    duplicate_intent_generation_attempt=False,
                ),
            )
            return self._persist_post_planning_outcome(
                context=context,
                validation=validation,
                timestamp=event_timestamp,
            )

        decision = self._guardrail_evaluator.evaluate_post_planning(
            evaluation_timestamp=event_timestamp,
            max_selected_contract_age=self._max_selected_contract_age,
            replay_bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            replay_bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            replay_bundle_errors=(
                context.replay_validation.errors
                if context.replay_validation is not None
                else ()
            ),
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_effective_timestamp=context.selected_contract_effective_timestamp,
            order_plan_selected_contract_symbol=context.order_plan_selected_contract_symbol,
            intent_selected_contract_symbol=(
                self._optional_text(context.intent_payload.get("selected_contract_symbol"))
                if context.intent_payload is not None
                else None
            ),
            require_intent_artifact=True,
            intent_exists=context.intent_payload is not None,
            intent_artifact_issue=context.intent_artifact_issue,
            duplicate_intent_generation_attempt=context.intent_payload is not None,
        )
        validation = self._validation_from_decision(context, decision)
        return self._persist_post_planning_outcome(
            context=context,
            validation=validation,
            timestamp=event_timestamp,
        )

    def _arm_execution_from_context(
        self,
        context: _PostPlanningContext,
        *,
        timestamp: datetime,
        comparison_payload: dict[str, Any] | None,
        comparison_issue: tuple[str, str] | None,
    ) -> S23PaperExecutionJournalArtifactSet:
        if context.strategy_code != "S23":
            raise S23PaperExecutionJournalError(
                "S23 execution-shell arming cannot continue from a non-S23 session."
            )

        if context.terminal_state is not PaperSessionState.ORDER_PLANNED:
            validation = S23PaperExecutionShellValidationResult(
                is_valid=True,
                can_arm_execution=False,
                status=S23PaperExecutionShellStatus.EXECUTION_SKIPPED,
                terminal_state=context.terminal_state,
                reason_code=context.terminal_state.value.lower(),
                message=(
                    "Execution-shell arming was skipped because the paper session "
                    f"ended in {context.terminal_state.value}."
                ),
                operator_action_required=None,
                bundle_validation_performed=(
                    context.replay_validation is not None
                    and context.replay_validation.manifest is not None
                ),
                bundle_valid=(
                    context.replay_validation.is_valid
                    if context.replay_validation is not None
                    else None
                ),
                historical_comparison_status=self._comparison_status(comparison_payload),
                historical_comparison_reason=self._comparison_reason(comparison_payload),
                historical_comparison_go_no_go=self._comparison_go_no_go(comparison_payload),
            )
            return self._persist_execution_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
            )

        intent_status = self._current_intent_status(context)
        if intent_status != S23PaperIntentPhaseStatus.INTENT_READY.value:
            validation = S23PaperExecutionShellValidationResult(
                is_valid=True,
                can_arm_execution=False,
                status=S23PaperExecutionShellStatus.EXECUTION_SKIPPED,
                terminal_state=context.terminal_state,
                reason_code="paper_intent_not_ready_for_execution_shell",
                message=(
                    "Execution-shell arming was skipped because the paper order "
                    "intent is not INTENT_READY."
                ),
                operator_action_required="Review or regenerate the paper order intent before arming execution.",
                bundle_validation_performed=(
                    context.replay_validation is not None
                    and context.replay_validation.manifest is not None
                ),
                bundle_valid=(
                    context.replay_validation.is_valid
                    if context.replay_validation is not None
                    else None
                ),
                historical_comparison_status=self._comparison_status(comparison_payload),
                historical_comparison_reason=self._comparison_reason(comparison_payload),
                historical_comparison_go_no_go=self._comparison_go_no_go(comparison_payload),
            )
            return self._persist_execution_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
            )

        if comparison_issue is not None:
            code, message = comparison_issue
            validation = S23PaperExecutionShellValidationResult(
                is_valid=True,
                can_arm_execution=False,
                status=S23PaperExecutionShellStatus.EXECUTION_BLOCKED,
                terminal_state=context.terminal_state,
                reason_code=code,
                message=message,
                operator_action_required="Repair or regenerate the historical comparison artifact before arming execution.",
                bundle_validation_performed=(
                    context.replay_validation is not None
                    and context.replay_validation.manifest is not None
                ),
                bundle_valid=(
                    context.replay_validation.is_valid
                    if context.replay_validation is not None
                    else None
                ),
                historical_comparison_status=None,
                historical_comparison_reason=None,
                historical_comparison_go_no_go=None,
            )
            return self._persist_execution_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
            )

        decision = self._guardrail_evaluator.evaluate_execution_shell(
            evaluation_timestamp=timestamp,
            max_selected_contract_age=self._max_selected_contract_age,
            replay_bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            replay_bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            replay_bundle_errors=(
                context.replay_validation.errors
                if context.replay_validation is not None
                else ()
            ),
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_effective_timestamp=context.selected_contract_effective_timestamp,
            order_plan_selected_contract_symbol=context.order_plan_selected_contract_symbol,
            intent_selected_contract_symbol=(
                self._optional_text(context.intent_payload.get("selected_contract_symbol"))
                if context.intent_payload is not None
                else None
            ),
            intent_exists=context.intent_payload is not None,
            intent_artifact_issue=context.intent_artifact_issue,
            historical_comparison_performed=comparison_payload is not None,
            historical_comparison_status=self._comparison_status(comparison_payload),
            duplicate_execution_arming_attempt=self._has_existing_execution_shell_outcome(
                context
            ),
        )
        if decision is not None:
            validation = self._execution_validation_from_decision(
                context,
                decision,
                comparison_payload=comparison_payload,
            )
            return self._persist_execution_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
            )

        validation = S23PaperExecutionShellValidationResult(
            is_valid=True,
            can_arm_execution=True,
            status=S23PaperExecutionShellStatus.EXECUTION_ARMED,
            terminal_state=context.terminal_state,
            reason_code="execution_shell_armed",
            message=(
                "Execution shell armed successfully. No order was placed, no fill "
                "was simulated, and no lifecycle monitoring started."
            ),
            operator_action_required=None,
            bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            historical_comparison_status=self._comparison_status(comparison_payload),
            historical_comparison_reason=self._comparison_reason(comparison_payload),
            historical_comparison_go_no_go=self._comparison_go_no_go(comparison_payload),
        )
        return self._persist_execution_shell_outcome(
            context=context,
            validation=validation,
            timestamp=timestamp,
        )

    def _dispatch_order_intent_from_context(
        self,
        context: _PostPlanningContext,
        *,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalArtifactSet:
        if context.strategy_code != "S23":
            raise S23PaperExecutionJournalError(
                "S23 fillless dispatch cannot continue from a non-S23 session."
            )

        if context.terminal_state is not PaperSessionState.ORDER_PLANNED:
            validation = S23PaperDispatchShellValidationResult(
                is_valid=True,
                can_dispatch_intent=False,
                status=S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_SKIPPED,
                terminal_state=context.terminal_state,
                reason_code=context.terminal_state.value.lower(),
                message=(
                    "Intent dispatch was skipped because the paper session "
                    f"ended in {context.terminal_state.value}."
                ),
                operator_action_required=None,
                bundle_validation_performed=(
                    context.replay_validation is not None
                    and context.replay_validation.manifest is not None
                ),
                bundle_valid=(
                    context.replay_validation.is_valid
                    if context.replay_validation is not None
                    else None
                ),
                historical_comparison_status=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_status")
                ),
                historical_comparison_reason=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_reason")
                ),
                historical_comparison_go_no_go=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
                ),
            )
            return self._persist_dispatch_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
                emit_ready_event=False,
            )

        intent_status = self._current_intent_status(context)
        if intent_status != S23PaperIntentPhaseStatus.INTENT_READY.value:
            validation = S23PaperDispatchShellValidationResult(
                is_valid=True,
                can_dispatch_intent=False,
                status=S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_SKIPPED,
                terminal_state=context.terminal_state,
                reason_code="paper_intent_not_ready_for_dispatch",
                message=(
                    "Intent dispatch was skipped because the persisted paper "
                    "order intent is not INTENT_READY."
                ),
                operator_action_required="Review or regenerate the paper order intent before dispatch.",
                bundle_validation_performed=(
                    context.replay_validation is not None
                    and context.replay_validation.manifest is not None
                ),
                bundle_valid=(
                    context.replay_validation.is_valid
                    if context.replay_validation is not None
                    else None
                ),
                historical_comparison_status=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_status")
                ),
                historical_comparison_reason=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_reason")
                ),
                historical_comparison_go_no_go=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
                ),
            )
            return self._persist_dispatch_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
                emit_ready_event=False,
            )

        decision = self._guardrail_evaluator.evaluate_dispatch_shell(
            evaluation_timestamp=timestamp,
            max_selected_contract_age=self._max_selected_contract_age,
            replay_bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            replay_bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            replay_bundle_errors=(
                context.replay_validation.errors
                if context.replay_validation is not None
                else ()
            ),
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_effective_timestamp=context.selected_contract_effective_timestamp,
            order_plan_selected_contract_symbol=context.order_plan_selected_contract_symbol,
            intent_selected_contract_symbol=(
                self._optional_text(context.intent_payload.get("selected_contract_symbol"))
                if context.intent_payload is not None
                else None
            ),
            execution_summary_selected_contract_symbol=self._optional_text(
                (context.execution_summary_payload or {}).get("selected_contract_symbol")
            ),
            intent_exists=context.intent_payload is not None,
            intent_artifact_issue=context.intent_artifact_issue,
            historical_comparison_performed=(
                self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_status")
                )
                is not None
            ),
            historical_comparison_status=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_status")
            ),
            execution_shell_status=self._optional_text(
                (context.execution_summary_payload or {}).get("execution_shell_status")
            ),
            duplicate_dispatch_attempt=self._has_existing_dispatch_outcome(context),
        )
        if decision is not None:
            validation = self._dispatch_validation_from_decision(context, decision)
            return self._persist_dispatch_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
                emit_ready_event=False,
            )

        validation = S23PaperDispatchShellValidationResult(
            is_valid=True,
            can_dispatch_intent=True,
            status=S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCHED,
            terminal_state=context.terminal_state,
            reason_code="order_intent_dispatched",
            message=(
                "Order intent marked as dispatched to the future paper-execution "
                "handoff shell. No order was placed, no fill was simulated, and "
                "no position was opened."
            ),
            operator_action_required=None,
            bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            historical_comparison_status=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_status")
            ),
            historical_comparison_reason=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_reason")
            ),
            historical_comparison_go_no_go=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
            ),
        )
        return self._persist_dispatch_shell_outcome(
            context=context,
            validation=validation,
            timestamp=timestamp,
            emit_ready_event=True,
        )

    def _mark_execution_handoff_ready_from_context(
        self,
        context: _PostPlanningContext,
        *,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalArtifactSet:
        if self._current_intent_status(context) != S23PaperIntentPhaseStatus.INTENT_READY.value:
            validation = S23PaperHandoffShellValidationResult(
                is_valid=True,
                can_handoff_execution=False,
                status=S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_SKIPPED,
                terminal_state=context.terminal_state,
                reason_code="paper_intent_not_ready_for_handoff",
                message=(
                    "Execution handoff was skipped because the persisted paper "
                    "order intent is not INTENT_READY."
                ),
                operator_action_required=(
                    "Review or regenerate the paper order intent before marking "
                    "execution handoff readiness."
                ),
                bundle_validation_performed=(
                    context.replay_validation is not None
                    and context.replay_validation.manifest is not None
                ),
                bundle_valid=(
                    context.replay_validation.is_valid
                    if context.replay_validation is not None
                    else None
                ),
                historical_comparison_status=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_status")
                ),
                historical_comparison_reason=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_reason")
                ),
                historical_comparison_go_no_go=self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
                ),
            )
            return self._persist_handoff_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
            )

        decision = self._guardrail_evaluator.evaluate_handoff_shell(
            evaluation_timestamp=timestamp,
            max_selected_contract_age=self._max_selected_contract_age,
            replay_bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            replay_bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            replay_bundle_errors=(
                context.replay_validation.errors
                if context.replay_validation is not None
                else ()
            ),
            selected_contract_symbol=context.selected_contract_symbol,
            selected_contract_effective_timestamp=context.selected_contract_effective_timestamp,
            order_plan_selected_contract_symbol=context.order_plan_selected_contract_symbol,
            intent_selected_contract_symbol=(
                self._optional_text(context.intent_payload.get("selected_contract_symbol"))
                if context.intent_payload is not None
                else None
            ),
            execution_summary_selected_contract_symbol=self._optional_text(
                (context.execution_summary_payload or {}).get("selected_contract_symbol")
            ),
            dispatch_summary_selected_contract_symbol=self._optional_text(
                (context.intent_dispatch_summary_payload or {}).get("selected_contract_symbol")
            ),
            intent_exists=context.intent_payload is not None,
            intent_artifact_issue=context.intent_artifact_issue,
            historical_comparison_performed=(
                self._optional_text(
                    (context.execution_summary_payload or {}).get("historical_comparison_status")
                )
                is not None
            ),
            historical_comparison_status=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_status")
            ),
            execution_shell_status=self._optional_text(
                (context.execution_summary_payload or {}).get("execution_shell_status")
            ),
            dispatch_shell_status=self._current_dispatch_status(context),
            duplicate_handoff_attempt=self._has_existing_handoff_outcome(context),
        )
        if decision is not None:
            validation = self._handoff_validation_from_decision(context, decision)
            return self._persist_handoff_shell_outcome(
                context=context,
                validation=validation,
                timestamp=timestamp,
            )

        validation = S23PaperHandoffShellValidationResult(
            is_valid=True,
            can_handoff_execution=True,
            status=S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_READY,
            terminal_state=context.terminal_state,
            reason_code="paper_execution_handoff_ready",
            message=(
                "Paper execution handoff is ready for a future fill simulator. "
                "No order was placed, no fill was simulated, and no position "
                "was opened."
            ),
            operator_action_required=None,
            bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            historical_comparison_status=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_status")
            ),
            historical_comparison_reason=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_reason")
            ),
            historical_comparison_go_no_go=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
            ),
        )
        return self._persist_handoff_shell_outcome(
            context=context,
            validation=validation,
            timestamp=timestamp,
        )

    def _persist_post_planning_outcome(
        self,
        *,
        context: _PostPlanningContext,
        validation: S23PaperOrderIntentValidationResult,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalArtifactSet:
        journal_event = self._build_journal_event(
            session_id=context.session_id,
            strategy_code=context.strategy_code,
            terminal_state=context.terminal_state,
            selected_contract_symbol=context.selected_contract_symbol,
            validation=validation,
            timestamp=timestamp,
            intent_created=False,
        )
        total_rows = context.existing_journal_rows + (journal_event,)
        execution_summary = self._build_execution_summary(
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            terminal_state=context.terminal_state,
            selected_contract_symbol=context.selected_contract_symbol,
            validation=validation,
            created_order_intent=context.intent_payload is not None,
            journal_event_count=len(total_rows),
            intent_status=validation.status.value,
            execution_shell_status=None,
            dispatch_shell_status=None,
            handoff_shell_status=None,
            intent_dispatched=False,
            future_fill_simulation_eligible=False,
            historical_comparison_status=None,
            historical_comparison_reason=None,
            historical_comparison_go_no_go=None,
        )

        execution_journal_path = context.session_directory / "execution_journal.jsonl"
        execution_summary_path = context.session_directory / "execution_summary.json"
        self._write_jsonl(execution_journal_path, total_rows)
        self._write_json(execution_summary_path, execution_summary)

        intent_block_summary_path: Path | None = None
        execution_arm_summary_path: Path | None = None
        execution_block_summary_path: Path | None = None
        if validation.status in {
            S23PaperIntentPhaseStatus.INTENT_BLOCKED,
            S23PaperIntentPhaseStatus.INTENT_ABORTED,
        }:
            intent_block_summary_path = context.session_directory / "intent_block_summary.json"
            self._write_json(intent_block_summary_path, execution_summary)
        self._cleanup_optional_file(context.session_directory / "execution_arm_summary.json")
        self._cleanup_optional_file(context.session_directory / "execution_block_summary.json")
        self._cleanup_optional_file(context.session_directory / "intent_dispatch_summary.json")
        self._cleanup_optional_file(context.session_directory / "execution_handoff_summary.json")

        return S23PaperExecutionJournalArtifactSet(
            session_directory=context.session_directory,
            paper_order_intent_path=(
                context.session_directory / "paper_order_intent.json"
                if context.intent_payload is not None
                else None
            ),
            execution_journal_path=execution_journal_path,
            execution_summary_path=execution_summary_path,
            intent_block_summary_path=intent_block_summary_path,
            execution_arm_summary_path=execution_arm_summary_path,
            execution_block_summary_path=execution_block_summary_path,
            intent_dispatch_summary_path=(
                context.session_directory / "intent_dispatch_summary.json"
                if (context.session_directory / "intent_dispatch_summary.json").exists()
                else None
            ),
            execution_handoff_summary_path=(
                context.session_directory / "execution_handoff_summary.json"
                if (context.session_directory / "execution_handoff_summary.json").exists()
                else None
            ),
        )

    def _persist_execution_shell_outcome(
        self,
        *,
        context: _PostPlanningContext,
        validation: S23PaperExecutionShellValidationResult,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalArtifactSet:
        journal_event = self._build_execution_shell_journal_event(
            session_id=context.session_id,
            strategy_code=context.strategy_code,
            terminal_state=context.terminal_state,
            selected_contract_symbol=context.selected_contract_symbol,
            validation=validation,
            timestamp=timestamp,
        )
        total_rows = context.existing_journal_rows + (journal_event,)
        execution_summary = self._build_execution_shell_summary(
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            terminal_state=context.terminal_state,
            selected_contract_symbol=context.selected_contract_symbol,
            validation=validation,
            created_order_intent=context.intent_payload is not None,
            journal_event_count=len(total_rows),
            intent_status=self._current_intent_status(context),
        )

        execution_journal_path = context.session_directory / "execution_journal.jsonl"
        execution_summary_path = context.session_directory / "execution_summary.json"
        self._write_jsonl(execution_journal_path, total_rows)
        self._write_json(execution_summary_path, execution_summary)

        execution_arm_summary_path: Path | None = None
        execution_block_summary_path: Path | None = None
        if validation.status is S23PaperExecutionShellStatus.EXECUTION_ARMED:
            execution_arm_summary_path = context.session_directory / "execution_arm_summary.json"
            self._write_json(execution_arm_summary_path, execution_summary)
            self._cleanup_optional_file(context.session_directory / "execution_block_summary.json")
        elif validation.status in {
            S23PaperExecutionShellStatus.EXECUTION_BLOCKED,
            S23PaperExecutionShellStatus.EXECUTION_ABORTED,
        }:
            execution_block_summary_path = context.session_directory / "execution_block_summary.json"
            self._write_json(execution_block_summary_path, execution_summary)
            self._cleanup_optional_file(context.session_directory / "execution_arm_summary.json")
        self._cleanup_optional_file(context.session_directory / "intent_dispatch_summary.json")
        self._cleanup_optional_file(context.session_directory / "execution_handoff_summary.json")

        return S23PaperExecutionJournalArtifactSet(
            session_directory=context.session_directory,
            paper_order_intent_path=(
                context.session_directory / "paper_order_intent.json"
                if context.intent_payload is not None
                else None
            ),
            execution_journal_path=execution_journal_path,
            execution_summary_path=execution_summary_path,
            intent_block_summary_path=(
                context.session_directory / "intent_block_summary.json"
                if (context.session_directory / "intent_block_summary.json").exists()
                else None
            ),
            execution_arm_summary_path=execution_arm_summary_path,
            execution_block_summary_path=execution_block_summary_path,
            intent_dispatch_summary_path=(
                context.session_directory / "intent_dispatch_summary.json"
                if (context.session_directory / "intent_dispatch_summary.json").exists()
                else None
            ),
            execution_handoff_summary_path=(
                context.session_directory / "execution_handoff_summary.json"
                if (context.session_directory / "execution_handoff_summary.json").exists()
                else None
            ),
        )

    def _persist_dispatch_shell_outcome(
        self,
        *,
        context: _PostPlanningContext,
        validation: S23PaperDispatchShellValidationResult,
        timestamp: datetime,
        emit_ready_event: bool,
    ) -> S23PaperExecutionJournalArtifactSet:
        new_rows: list[S23PaperExecutionJournalEvent] = []
        if emit_ready_event:
            new_rows.append(
                self._build_dispatch_ready_journal_event(
                    session_id=context.session_id,
                    strategy_code=context.strategy_code,
                    terminal_state=context.terminal_state,
                    selected_contract_symbol=context.selected_contract_symbol,
                    validation=validation,
                    timestamp=timestamp,
                )
            )
        new_rows.append(
            self._build_dispatch_shell_journal_event(
                session_id=context.session_id,
                strategy_code=context.strategy_code,
                terminal_state=context.terminal_state,
                selected_contract_symbol=context.selected_contract_symbol,
                validation=validation,
                timestamp=timestamp,
            )
        )
        total_rows = context.existing_journal_rows + tuple(new_rows)
        execution_summary = self._build_dispatch_shell_summary(
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            terminal_state=context.terminal_state,
            selected_contract_symbol=context.selected_contract_symbol,
            validation=validation,
            created_order_intent=context.intent_payload is not None,
            journal_event_count=len(total_rows),
            intent_status=self._current_intent_status(context),
            execution_shell_status=self._optional_text(
                (context.execution_summary_payload or {}).get("execution_shell_status")
            ),
        )

        execution_journal_path = context.session_directory / "execution_journal.jsonl"
        execution_summary_path = context.session_directory / "execution_summary.json"
        intent_dispatch_summary_path = context.session_directory / "intent_dispatch_summary.json"
        self._write_jsonl(execution_journal_path, total_rows)
        self._write_json(execution_summary_path, execution_summary)
        self._write_json(intent_dispatch_summary_path, execution_summary)
        self._cleanup_optional_file(context.session_directory / "execution_handoff_summary.json")

        return S23PaperExecutionJournalArtifactSet(
            session_directory=context.session_directory,
            paper_order_intent_path=(
                context.session_directory / "paper_order_intent.json"
                if context.intent_payload is not None
                else None
            ),
            execution_journal_path=execution_journal_path,
            execution_summary_path=execution_summary_path,
            intent_block_summary_path=(
                context.session_directory / "intent_block_summary.json"
                if (context.session_directory / "intent_block_summary.json").exists()
                else None
            ),
            execution_arm_summary_path=(
                context.session_directory / "execution_arm_summary.json"
                if (context.session_directory / "execution_arm_summary.json").exists()
                else None
            ),
            execution_block_summary_path=(
                context.session_directory / "execution_block_summary.json"
                if (context.session_directory / "execution_block_summary.json").exists()
                else None
            ),
            intent_dispatch_summary_path=intent_dispatch_summary_path,
            execution_handoff_summary_path=(
                context.session_directory / "execution_handoff_summary.json"
                if (context.session_directory / "execution_handoff_summary.json").exists()
                else None
            ),
        )

    def _persist_handoff_shell_outcome(
        self,
        *,
        context: _PostPlanningContext,
        validation: S23PaperHandoffShellValidationResult,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalArtifactSet:
        journal_event = self._build_handoff_shell_journal_event(
            session_id=context.session_id,
            strategy_code=context.strategy_code,
            terminal_state=context.terminal_state,
            selected_contract_symbol=context.selected_contract_symbol,
            validation=validation,
            timestamp=timestamp,
        )
        total_rows = context.existing_journal_rows + (journal_event,)
        execution_summary = self._build_handoff_shell_summary(
            session_id=context.session_id,
            session_date=context.session_date,
            strategy_code=context.strategy_code,
            terminal_state=context.terminal_state,
            selected_contract_symbol=context.selected_contract_symbol,
            validation=validation,
            created_order_intent=context.intent_payload is not None,
            journal_event_count=len(total_rows),
            intent_status=self._current_intent_status(context),
            execution_shell_status=self._optional_text(
                (context.execution_summary_payload or {}).get("execution_shell_status")
            ),
            dispatch_shell_status=self._current_dispatch_status(context),
        )

        execution_journal_path = context.session_directory / "execution_journal.jsonl"
        execution_summary_path = context.session_directory / "execution_summary.json"
        execution_handoff_summary_path = (
            context.session_directory / "execution_handoff_summary.json"
        )
        self._write_jsonl(execution_journal_path, total_rows)
        self._write_json(execution_summary_path, execution_summary)
        self._write_json(execution_handoff_summary_path, execution_summary)

        return S23PaperExecutionJournalArtifactSet(
            session_directory=context.session_directory,
            paper_order_intent_path=(
                context.session_directory / "paper_order_intent.json"
                if context.intent_payload is not None
                else None
            ),
            execution_journal_path=execution_journal_path,
            execution_summary_path=execution_summary_path,
            intent_block_summary_path=(
                context.session_directory / "intent_block_summary.json"
                if (context.session_directory / "intent_block_summary.json").exists()
                else None
            ),
            execution_arm_summary_path=(
                context.session_directory / "execution_arm_summary.json"
                if (context.session_directory / "execution_arm_summary.json").exists()
                else None
            ),
            execution_block_summary_path=(
                context.session_directory / "execution_block_summary.json"
                if (context.session_directory / "execution_block_summary.json").exists()
                else None
            ),
            intent_dispatch_summary_path=(
                context.session_directory / "intent_dispatch_summary.json"
                if (context.session_directory / "intent_dispatch_summary.json").exists()
                else None
            ),
            execution_handoff_summary_path=execution_handoff_summary_path,
        )

    def _load_historical_comparison_payload(
        self,
        historical_comparison_path: str | Path | None,
    ) -> tuple[dict[str, Any] | None, tuple[str, str] | None]:
        if historical_comparison_path is None:
            return None, None

        comparison_path = Path(historical_comparison_path)
        if not comparison_path.exists():
            return None, (
                "missing_historical_comparison",
                "Paper-vs-historical comparison artifact is missing, so execution-shell arming is blocked.",
            )
        try:
            payload = self._load_json_required(comparison_path)
        except S23PaperExecutionJournalError:
            return None, (
                "invalid_historical_comparison_artifact",
                "Paper-vs-historical comparison artifact is corrupt and blocks execution-shell arming.",
            )
        if self._optional_text(payload.get("strategy_code")) not in {None, "S23"}:
            return None, (
                "invalid_historical_comparison_artifact",
                "Paper-vs-historical comparison artifact is not for S23 and blocks execution-shell arming.",
            )
        status = self._optional_text(payload.get("status"))
        if status is not None:
            try:
                PaperHistoricalComparisonStatus(status)
            except ValueError:
                return None, (
                    "invalid_historical_comparison_artifact",
                    "Paper-vs-historical comparison artifact contains an invalid comparison status.",
                )
        return payload, None

    def _current_intent_status(self, context: _PostPlanningContext) -> str | None:
        if context.execution_summary_payload is None:
            return None
        return self._optional_text(
            context.execution_summary_payload.get("intent_status")
        ) or self._optional_text(context.execution_summary_payload.get("status"))

    def _current_dispatch_status(self, context: _PostPlanningContext) -> str | None:
        if context.execution_summary_payload is None:
            return None
        explicit = self._optional_text(
            context.execution_summary_payload.get("dispatch_shell_status")
        )
        if explicit is not None:
            return explicit
        status = self._optional_text(context.execution_summary_payload.get("status"))
        if status in {
            S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_READY.value,
            S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCHED.value,
            S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_BLOCKED.value,
            S23PaperDispatchShellStatus.ORDER_INTENT_CANCELLED.value,
            S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_SKIPPED.value,
        }:
            return status
        return None

    def _current_handoff_status(self, context: _PostPlanningContext) -> str | None:
        if context.execution_summary_payload is None:
            return None
        explicit = self._optional_text(
            context.execution_summary_payload.get("handoff_shell_status")
        )
        if explicit is not None:
            return explicit
        status = self._optional_text(context.execution_summary_payload.get("status"))
        if status in {
            S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_READY.value,
            S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_BLOCKED.value,
            S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_ABORTED.value,
            S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_SKIPPED.value,
        }:
            return status
        return None

    def _has_existing_execution_shell_outcome(self, context: _PostPlanningContext) -> bool:
        if context.execution_summary_payload is None:
            return False
        status = self._optional_text(context.execution_summary_payload.get("execution_shell_status"))
        return status == S23PaperExecutionShellStatus.EXECUTION_ARMED.value

    def _has_existing_dispatch_outcome(self, context: _PostPlanningContext) -> bool:
        status = self._current_dispatch_status(context)
        return status in {
            S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_READY.value,
            S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCHED.value,
            S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_BLOCKED.value,
            S23PaperDispatchShellStatus.ORDER_INTENT_CANCELLED.value,
        }

    def _has_existing_handoff_outcome(self, context: _PostPlanningContext) -> bool:
        status = self._current_handoff_status(context)
        return status in {
            S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_READY.value,
            S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_BLOCKED.value,
            S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_ABORTED.value,
        }

    def _comparison_status(self, payload: dict[str, Any] | None) -> str | None:
        return self._optional_text(payload.get("status")) if payload is not None else None

    def _comparison_reason(self, payload: dict[str, Any] | None) -> str | None:
        return self._optional_text(payload.get("comparison_reason")) if payload is not None else None

    def _comparison_go_no_go(self, payload: dict[str, Any] | None) -> str | None:
        return self._optional_text(payload.get("go_no_go")) if payload is not None else None

    def _load_post_planning_context(
        self,
        session_directory: Path,
        *,
        bundle_directory: str | Path | None,
    ) -> _PostPlanningContext:
        decision = self._load_json_required(session_directory / "decision_summary.json")
        manifest = self._load_json_required(session_directory / "session_manifest.json")
        terminal_state = self._parse_state_required(decision.get("state"), "decision_summary.json")

        selected_contract_payload = self._load_optional_json(session_directory / "selected_contract.json")
        order_plan_payload = self._load_optional_json(session_directory / "paper_order_plan.json")
        if terminal_state is PaperSessionState.ORDER_PLANNED and order_plan_payload is None:
            raise S23PaperExecutionJournalError(
                "S23 paper execution journal requires paper_order_plan.json for an ORDER_PLANNED session."
            )

        journal_path = session_directory / "execution_journal.jsonl"
        existing_journal_rows = (
            self._load_jsonl_optional(journal_path)
            if journal_path.exists()
            else ()
        )
        execution_summary_payload = self._load_optional_json(
            session_directory / "execution_summary.json"
        )
        intent_dispatch_summary_payload = self._load_optional_json(
            session_directory / "intent_dispatch_summary.json"
        )
        execution_handoff_summary_payload = self._load_optional_json(
            session_directory / "execution_handoff_summary.json"
        )

        intent_payload = None
        intent_artifact_issue = None
        intent_path = session_directory / "paper_order_intent.json"
        if intent_path.exists():
            try:
                intent_payload = self._load_json_required(intent_path)
            except S23PaperExecutionJournalError:
                intent_artifact_issue = "corrupt_order_intent_artifact"
        else:
            intent_artifact_issue = "missing_order_intent_artifact"

        replay_validation = None
        if bundle_directory is not None:
            replay_validation = self._replay_bundle_manager.validate_bundle(bundle_directory)

        selected_contract_envelope = selected_contract_payload.get("envelope", {}) if selected_contract_payload is not None else {}
        order_plan = order_plan_payload.get("order_plan", {}) if order_plan_payload is not None else {}
        data_sources = tuple(
            item for item in manifest.get("data_sources", ()) if isinstance(item, dict)
        )
        return _PostPlanningContext(
            session_directory=session_directory,
            session_id=str(decision["session_id"]),
            session_date=self._parse_date_required(decision["session_date"], "decision_summary.json"),
            strategy_code=str(decision["strategy_code"]),
            terminal_state=terminal_state,
            selected_contract_symbol=self._optional_text(
                selected_contract_payload.get("symbol") if selected_contract_payload is not None else decision.get("selected_contract_symbol")
            ),
            selected_contract_option_type=self._optional_text(
                selected_contract_payload.get("option_type") if selected_contract_payload is not None else None
            ),
            selected_contract_expiry=self._optional_date(
                selected_contract_payload.get("expiry") if selected_contract_payload is not None else None
            ),
            selected_contract_ltp=self._optional_float(
                selected_contract_payload.get("ltp") if selected_contract_payload is not None else None
            ),
            selected_contract_effective_timestamp=self._optional_datetime(
                selected_contract_envelope.get("effective_timestamp")
            ),
            data_source_count=len(data_sources),
            data_source_ids=tuple(
                sorted(
                    {
                        str(item.get("source_id"))
                        for item in data_sources
                        if item.get("source_id") is not None
                    }
                )
            ),
            data_source_types=tuple(
                sorted(
                    {
                        str(item.get("source_type"))
                        for item in data_sources
                        if item.get("source_type") is not None
                    }
                )
            ),
            synthetic_fixture_used=bool(manifest.get("synthetic_fixture_used", False)),
            order_plan_selected_contract_symbol=self._optional_text(
                order_plan.get("selected_contract_symbol")
            ),
            existing_journal_rows=existing_journal_rows,
            execution_summary_payload=execution_summary_payload,
            intent_dispatch_summary_payload=intent_dispatch_summary_payload,
            execution_handoff_summary_payload=execution_handoff_summary_payload,
            replay_validation=replay_validation,
            intent_payload=intent_payload,
            intent_artifact_issue=intent_artifact_issue,
        )

    def _evaluate_post_planning_from_review(
        self,
        summary: S23PaperReviewSummary,
        *,
        validation: S23PaperOrderIntentValidationResult,
        evaluation_timestamp: datetime,
    ) -> PaperGuardrailDecision | None:
        if summary.terminal_state is not PaperSessionState.ORDER_PLANNED:
            return None
        return self._guardrail_evaluator.evaluate_post_planning(
            evaluation_timestamp=evaluation_timestamp,
            max_selected_contract_age=self._max_selected_contract_age,
            replay_bundle_validation_performed=summary.replay_bundle.validation_performed,
            replay_bundle_valid=summary.replay_bundle.is_valid,
            replay_bundle_errors=summary.replay_bundle.errors,
            selected_contract_symbol=summary.selected_contract.symbol,
            selected_contract_effective_timestamp=summary.selected_contract.effective_timestamp,
            order_plan_selected_contract_symbol=(
                summary.order_plan.selected_contract_symbol if summary.order_plan is not None else None
            ),
            intent_selected_contract_symbol=None,
            require_intent_artifact=False,
            intent_exists=False,
            intent_artifact_issue=None,
            duplicate_intent_generation_attempt=False,
        )

    def _validation_from_decision(
        self,
        context: _PostPlanningContext,
        decision: PaperGuardrailDecision | None,
    ) -> S23PaperOrderIntentValidationResult:
        if decision is None:
            raise S23PaperExecutionJournalError(
                "Post-planning execution-journal checks expected a guardrail decision but none was returned."
            )
        return S23PaperOrderIntentValidationResult(
            is_valid=True,
            can_create_intent=False,
            status=self._status_from_guardrail(decision),
            terminal_state=context.terminal_state,
            reason_code=decision.code,
            message=decision.message,
            errors=(),
            operator_action_required=decision.operator_action_required,
            bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            guardrail_decision=decision,
        )

    def _validation_with_guardrail(
        self,
        validation: S23PaperOrderIntentValidationResult,
        *,
        status: S23PaperIntentPhaseStatus,
        reason_code: str,
        message: str,
        operator_action_required: str | None,
        guardrail_decision: PaperGuardrailDecision,
    ) -> S23PaperOrderIntentValidationResult:
        return S23PaperOrderIntentValidationResult(
            is_valid=validation.is_valid,
            can_create_intent=False,
            status=status,
            terminal_state=validation.terminal_state,
            reason_code=reason_code,
            message=message,
            errors=validation.errors,
            operator_action_required=operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            guardrail_decision=guardrail_decision,
        )

    def _execution_validation_from_decision(
        self,
        context: _PostPlanningContext,
        decision: PaperGuardrailDecision | None,
        *,
        comparison_payload: dict[str, Any] | None,
    ) -> S23PaperExecutionShellValidationResult:
        if decision is None:
            raise S23PaperExecutionJournalError(
                "Execution-shell checks expected a guardrail decision but none was returned."
            )
        return S23PaperExecutionShellValidationResult(
            is_valid=True,
            can_arm_execution=False,
            status=self._execution_status_from_guardrail(decision),
            terminal_state=context.terminal_state,
            reason_code=decision.code,
            message=decision.message,
            operator_action_required=decision.operator_action_required,
            bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            historical_comparison_status=self._comparison_status(comparison_payload),
            historical_comparison_reason=self._comparison_reason(comparison_payload),
            historical_comparison_go_no_go=self._comparison_go_no_go(comparison_payload),
            guardrail_decision=decision,
        )

    def _dispatch_validation_from_decision(
        self,
        context: _PostPlanningContext,
        decision: PaperGuardrailDecision | None,
    ) -> S23PaperDispatchShellValidationResult:
        if decision is None:
            raise S23PaperExecutionJournalError(
                "Dispatch-shell checks expected a guardrail decision but none was returned."
            )
        return S23PaperDispatchShellValidationResult(
            is_valid=True,
            can_dispatch_intent=False,
            status=self._dispatch_status_from_guardrail(decision),
            terminal_state=context.terminal_state,
            reason_code=decision.code,
            message=decision.message,
            operator_action_required=decision.operator_action_required,
            bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            historical_comparison_status=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_status")
            ),
            historical_comparison_reason=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_reason")
            ),
            historical_comparison_go_no_go=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
            ),
            guardrail_decision=decision,
        )

    def _handoff_validation_from_decision(
        self,
        context: _PostPlanningContext,
        decision: PaperGuardrailDecision | None,
    ) -> S23PaperHandoffShellValidationResult:
        if decision is None:
            raise S23PaperExecutionJournalError(
                "Handoff-shell checks expected a guardrail decision but none was returned."
            )
        return S23PaperHandoffShellValidationResult(
            is_valid=True,
            can_handoff_execution=False,
            status=self._handoff_status_from_guardrail(decision),
            terminal_state=context.terminal_state,
            reason_code=decision.code,
            message=decision.message,
            operator_action_required=decision.operator_action_required,
            bundle_validation_performed=(
                context.replay_validation is not None
                and context.replay_validation.manifest is not None
            ),
            bundle_valid=(
                context.replay_validation.is_valid
                if context.replay_validation is not None
                else None
            ),
            historical_comparison_status=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_status")
            ),
            historical_comparison_reason=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_reason")
            ),
            historical_comparison_go_no_go=self._optional_text(
                (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
            ),
            guardrail_decision=decision,
        )

    def _status_from_guardrail(
        self,
        decision: PaperGuardrailDecision,
    ) -> S23PaperIntentPhaseStatus:
        if decision.readiness_status.value == "ABORTED":
            return S23PaperIntentPhaseStatus.INTENT_ABORTED
        return S23PaperIntentPhaseStatus.INTENT_BLOCKED

    def _execution_status_from_guardrail(
        self,
        decision: PaperGuardrailDecision,
    ) -> S23PaperExecutionShellStatus:
        if decision.readiness_status.value == "ABORTED":
            return S23PaperExecutionShellStatus.EXECUTION_ABORTED
        return S23PaperExecutionShellStatus.EXECUTION_BLOCKED

    def _dispatch_status_from_guardrail(
        self,
        decision: PaperGuardrailDecision,
    ) -> S23PaperDispatchShellStatus:
        if decision.readiness_status.value == "ABORTED":
            return S23PaperDispatchShellStatus.ORDER_INTENT_CANCELLED
        return S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_BLOCKED

    def _handoff_status_from_guardrail(
        self,
        decision: PaperGuardrailDecision,
    ) -> S23PaperHandoffShellStatus:
        if decision.readiness_status.value == "ABORTED":
            return S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_ABORTED
        return S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_BLOCKED

    def _build_order_intent(
        self,
        summary: S23PaperReviewSummary,
        validation: S23PaperOrderIntentValidationResult,
    ) -> S23PaperOrderIntent:
        assert summary.order_plan is not None
        assert summary.selected_contract.symbol is not None
        assert summary.order_plan.lots is not None
        assert summary.order_plan.quantity is not None
        assert summary.order_plan.planned_entry_price is not None
        assert summary.order_plan.target_price is not None
        assert summary.order_plan.stoploss_price is not None
        assert summary.order_plan.order_reference_time is not None
        assert summary.order_plan.strategy_branch is not None
        return S23PaperOrderIntent(
            artifact_version=_ARTIFACT_VERSION,
            session_id=summary.session_id,
            session_date=summary.session_date,
            strategy_code=summary.strategy_code,
            terminal_state=summary.terminal_state,
            status="INTENT_ONLY",
            selected_contract_symbol=summary.selected_contract.symbol,
            selected_contract_option_type=summary.selected_contract.option_type,
            selected_contract_expiry=summary.selected_contract.expiry,
            selected_contract_ltp=summary.selected_contract.ltp,
            side=summary.order_plan.order_side or "SELL",
            lots=summary.order_plan.lots,
            quantity=summary.order_plan.quantity,
            planned_entry_price=summary.order_plan.planned_entry_price,
            target_price=summary.order_plan.target_price,
            stoploss_price=summary.order_plan.stoploss_price,
            fsl_price=summary.order_plan.fsl_price,
            order_reference_time=summary.order_plan.order_reference_time,
            order_reference_label=summary.order_plan.order_reference_label or "",
            source_branch=summary.order_plan.strategy_branch,
            source_workbook_rule=summary.order_plan.source_workbook_rule,
            workbook_row_number=summary.order_plan.workbook_row_number,
            data_source_count=summary.data_provenance.data_source_count,
            data_source_ids=summary.data_provenance.source_ids,
            data_source_types=summary.data_provenance.source_types,
            synthetic_fixture_used=summary.data_provenance.synthetic_fixture_used,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_journal_event(
        self,
        *,
        session_id: str,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperOrderIntentValidationResult,
        timestamp: datetime,
        intent_created: bool,
    ) -> S23PaperExecutionJournalEvent:
        event_type = _SKIPPED_EVENT_TYPE
        if validation.status is S23PaperIntentPhaseStatus.INTENT_READY and intent_created:
            event_type = _INTENT_EVENT_TYPE
        elif validation.status is S23PaperIntentPhaseStatus.INTENT_BLOCKED:
            event_type = _BLOCKED_EVENT_TYPE
        elif validation.status is S23PaperIntentPhaseStatus.INTENT_ABORTED:
            event_type = _ABORTED_EVENT_TYPE

        guardrail = validation.guardrail_decision
        return S23PaperExecutionJournalEvent(
            timestamp=timestamp,
            event_type=event_type,
            session_id=session_id,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=validation.status.value,
            reason_code=validation.reason_code,
            message=validation.message,
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=guardrail.code if guardrail is not None else None,
            guardrail_message=guardrail.message if guardrail is not None else None,
            blocking_event_type=(
                guardrail.blocking_event_type.value
                if guardrail is not None and guardrail.blocking_event_type is not None
                else None
            ),
            blocking_source_id=(
                guardrail.blocking_source_id if guardrail is not None else None
            ),
            operator_action_required=validation.operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_execution_shell_journal_event(
        self,
        *,
        session_id: str,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperExecutionShellValidationResult,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalEvent:
        event_type = _EXECUTION_SKIPPED_EVENT_TYPE
        if validation.status is S23PaperExecutionShellStatus.EXECUTION_ARMED:
            event_type = _EXECUTION_ARMED_EVENT_TYPE
        elif validation.status is S23PaperExecutionShellStatus.EXECUTION_BLOCKED:
            event_type = _EXECUTION_BLOCKED_EVENT_TYPE
        elif validation.status is S23PaperExecutionShellStatus.EXECUTION_ABORTED:
            event_type = _EXECUTION_ABORTED_EVENT_TYPE

        guardrail = validation.guardrail_decision
        return S23PaperExecutionJournalEvent(
            timestamp=timestamp,
            event_type=event_type,
            session_id=session_id,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=validation.status.value,
            reason_code=validation.reason_code,
            message=validation.message,
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=guardrail.code if guardrail is not None else None,
            guardrail_message=guardrail.message if guardrail is not None else None,
            blocking_event_type=(
                guardrail.blocking_event_type.value
                if guardrail is not None and guardrail.blocking_event_type is not None
                else None
            ),
            blocking_source_id=(
                guardrail.blocking_source_id if guardrail is not None else None
            ),
            operator_action_required=validation.operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_dispatch_ready_journal_event(
        self,
        *,
        session_id: str,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperDispatchShellValidationResult,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalEvent:
        return S23PaperExecutionJournalEvent(
            timestamp=timestamp,
            event_type=_DISPATCH_READY_EVENT_TYPE,
            session_id=session_id,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_READY.value,
            reason_code="order_intent_dispatch_ready",
            message=(
                "Order intent is dispatch-ready for the future paper execution "
                "handoff shell. No order was placed, no fill was simulated, "
                "and no position was opened."
            ),
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=None,
            guardrail_message=None,
            blocking_event_type=None,
            blocking_source_id=None,
            operator_action_required=None,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_dispatch_shell_journal_event(
        self,
        *,
        session_id: str,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperDispatchShellValidationResult,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalEvent:
        event_type = _DISPATCH_SKIPPED_EVENT_TYPE
        if validation.status is S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCHED:
            event_type = _DISPATCHED_EVENT_TYPE
        elif validation.status is S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCH_BLOCKED:
            event_type = _DISPATCH_BLOCKED_EVENT_TYPE
        elif validation.status is S23PaperDispatchShellStatus.ORDER_INTENT_CANCELLED:
            event_type = _DISPATCH_CANCELLED_EVENT_TYPE

        guardrail = validation.guardrail_decision
        return S23PaperExecutionJournalEvent(
            timestamp=timestamp,
            event_type=event_type,
            session_id=session_id,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=validation.status.value,
            reason_code=validation.reason_code,
            message=validation.message,
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=guardrail.code if guardrail is not None else None,
            guardrail_message=guardrail.message if guardrail is not None else None,
            blocking_event_type=(
                guardrail.blocking_event_type.value
                if guardrail is not None and guardrail.blocking_event_type is not None
                else None
            ),
            blocking_source_id=(
                guardrail.blocking_source_id if guardrail is not None else None
            ),
            operator_action_required=validation.operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_handoff_shell_journal_event(
        self,
        *,
        session_id: str,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperHandoffShellValidationResult,
        timestamp: datetime,
    ) -> S23PaperExecutionJournalEvent:
        event_type = _HANDOFF_SKIPPED_EVENT_TYPE
        if validation.status is S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_READY:
            event_type = _HANDOFF_READY_EVENT_TYPE
        elif validation.status is S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_BLOCKED:
            event_type = _HANDOFF_BLOCKED_EVENT_TYPE
        elif validation.status is S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_ABORTED:
            event_type = _HANDOFF_ABORTED_EVENT_TYPE

        guardrail = validation.guardrail_decision
        return S23PaperExecutionJournalEvent(
            timestamp=timestamp,
            event_type=event_type,
            session_id=session_id,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=validation.status.value,
            reason_code=validation.reason_code,
            message=validation.message,
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=guardrail.code if guardrail is not None else None,
            guardrail_message=guardrail.message if guardrail is not None else None,
            blocking_event_type=(
                guardrail.blocking_event_type.value
                if guardrail is not None and guardrail.blocking_event_type is not None
                else None
            ),
            blocking_source_id=(
                guardrail.blocking_source_id if guardrail is not None else None
            ),
            operator_action_required=validation.operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_execution_summary(
        self,
        *,
        session_id: str,
        session_date: date,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperOrderIntentValidationResult,
        created_order_intent: bool,
        journal_event_count: int,
        intent_status: str | None,
        execution_shell_status: str | None,
        dispatch_shell_status: str | None,
        handoff_shell_status: str | None,
        intent_dispatched: bool,
        future_fill_simulation_eligible: bool,
        historical_comparison_status: str | None,
        historical_comparison_reason: str | None,
        historical_comparison_go_no_go: str | None,
    ) -> S23PaperExecutionJournalSummary:
        guardrail = validation.guardrail_decision
        return S23PaperExecutionJournalSummary(
            artifact_version=_ARTIFACT_VERSION,
            session_id=session_id,
            session_date=session_date,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=validation.status.value,
            intent_status=intent_status,
            execution_shell_status=execution_shell_status,
            dispatch_shell_status=dispatch_shell_status,
            handoff_shell_status=handoff_shell_status,
            created_order_intent=created_order_intent,
            intent_dispatched=intent_dispatched,
            order_placed=False,
            fill_simulated=False,
            position_opened=False,
            future_fill_simulation_eligible=future_fill_simulation_eligible,
            terminal_reason_code=validation.reason_code,
            message=validation.message,
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=guardrail.code if guardrail is not None else None,
            guardrail_message=guardrail.message if guardrail is not None else None,
            blocking_event_type=(
                guardrail.blocking_event_type.value
                if guardrail is not None and guardrail.blocking_event_type is not None
                else None
            ),
            blocking_source_id=(
                guardrail.blocking_source_id if guardrail is not None else None
            ),
            operator_action_required=validation.operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            historical_comparison_status=historical_comparison_status,
            historical_comparison_reason=historical_comparison_reason,
            historical_comparison_go_no_go=historical_comparison_go_no_go,
            journal_event_count=journal_event_count,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_execution_shell_summary(
        self,
        *,
        session_id: str,
        session_date: date,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperExecutionShellValidationResult,
        created_order_intent: bool,
        journal_event_count: int,
        intent_status: str | None,
    ) -> S23PaperExecutionJournalSummary:
        guardrail = validation.guardrail_decision
        return S23PaperExecutionJournalSummary(
            artifact_version=_ARTIFACT_VERSION,
            session_id=session_id,
            session_date=session_date,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=validation.status.value,
            intent_status=intent_status,
            execution_shell_status=validation.status.value,
            dispatch_shell_status=None,
            handoff_shell_status=None,
            created_order_intent=created_order_intent,
            intent_dispatched=False,
            order_placed=False,
            fill_simulated=False,
            position_opened=False,
            future_fill_simulation_eligible=False,
            terminal_reason_code=validation.reason_code,
            message=validation.message,
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=guardrail.code if guardrail is not None else None,
            guardrail_message=guardrail.message if guardrail is not None else None,
            blocking_event_type=(
                guardrail.blocking_event_type.value
                if guardrail is not None and guardrail.blocking_event_type is not None
                else None
            ),
            blocking_source_id=(
                guardrail.blocking_source_id if guardrail is not None else None
            ),
            operator_action_required=validation.operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            historical_comparison_status=validation.historical_comparison_status,
            historical_comparison_reason=validation.historical_comparison_reason,
            historical_comparison_go_no_go=validation.historical_comparison_go_no_go,
            journal_event_count=journal_event_count,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_dispatch_shell_summary(
        self,
        *,
        session_id: str,
        session_date: date,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperDispatchShellValidationResult,
        created_order_intent: bool,
        journal_event_count: int,
        intent_status: str | None,
        execution_shell_status: str | None,
    ) -> S23PaperExecutionJournalSummary:
        guardrail = validation.guardrail_decision
        return S23PaperExecutionJournalSummary(
            artifact_version=_ARTIFACT_VERSION,
            session_id=session_id,
            session_date=session_date,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=validation.status.value,
            intent_status=intent_status,
            execution_shell_status=execution_shell_status,
            dispatch_shell_status=validation.status.value,
            handoff_shell_status=None,
            created_order_intent=created_order_intent,
            intent_dispatched=(
                validation.status
                is S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCHED
            ),
            order_placed=False,
            fill_simulated=False,
            position_opened=False,
            future_fill_simulation_eligible=False,
            terminal_reason_code=validation.reason_code,
            message=validation.message,
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=guardrail.code if guardrail is not None else None,
            guardrail_message=guardrail.message if guardrail is not None else None,
            blocking_event_type=(
                guardrail.blocking_event_type.value
                if guardrail is not None and guardrail.blocking_event_type is not None
                else None
            ),
            blocking_source_id=(
                guardrail.blocking_source_id if guardrail is not None else None
            ),
            operator_action_required=validation.operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            historical_comparison_status=validation.historical_comparison_status,
            historical_comparison_reason=validation.historical_comparison_reason,
            historical_comparison_go_no_go=validation.historical_comparison_go_no_go,
            journal_event_count=journal_event_count,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _build_handoff_shell_summary(
        self,
        *,
        session_id: str,
        session_date: date,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        validation: S23PaperHandoffShellValidationResult,
        created_order_intent: bool,
        journal_event_count: int,
        intent_status: str | None,
        execution_shell_status: str | None,
        dispatch_shell_status: str | None,
    ) -> S23PaperExecutionJournalSummary:
        guardrail = validation.guardrail_decision
        return S23PaperExecutionJournalSummary(
            artifact_version=_ARTIFACT_VERSION,
            session_id=session_id,
            session_date=session_date,
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            status=validation.status.value,
            intent_status=intent_status,
            execution_shell_status=execution_shell_status,
            dispatch_shell_status=dispatch_shell_status,
            handoff_shell_status=validation.status.value,
            created_order_intent=created_order_intent,
            intent_dispatched=dispatch_shell_status
            == S23PaperDispatchShellStatus.ORDER_INTENT_DISPATCHED.value,
            order_placed=False,
            fill_simulated=False,
            position_opened=False,
            future_fill_simulation_eligible=(
                validation.status
                is S23PaperHandoffShellStatus.PAPER_EXECUTION_HANDOFF_READY
            ),
            terminal_reason_code=validation.reason_code,
            message=validation.message,
            selected_contract_symbol=selected_contract_symbol,
            guardrail_code=guardrail.code if guardrail is not None else None,
            guardrail_message=guardrail.message if guardrail is not None else None,
            blocking_event_type=(
                guardrail.blocking_event_type.value
                if guardrail is not None and guardrail.blocking_event_type is not None
                else None
            ),
            blocking_source_id=(
                guardrail.blocking_source_id if guardrail is not None else None
            ),
            operator_action_required=validation.operator_action_required,
            bundle_validation_performed=validation.bundle_validation_performed,
            bundle_valid=validation.bundle_valid,
            historical_comparison_status=validation.historical_comparison_status,
            historical_comparison_reason=validation.historical_comparison_reason,
            historical_comparison_go_no_go=validation.historical_comparison_go_no_go,
            journal_event_count=journal_event_count,
            disclaimer=_NO_EXECUTION_DISCLAIMER,
        )

    def _derive_event_timestamp(self, summary: S23PaperReviewSummary) -> datetime:
        if summary.audit_transitions:
            return summary.audit_transitions[-1].timestamp
        if summary.order_plan is not None and summary.order_plan.planning_timestamp is not None:
            return summary.order_plan.planning_timestamp
        raise S23PaperExecutionJournalError(
            "Cannot derive a deterministic execution-journal timestamp from the paper session review."
        )

    def _has_post_planning_shell(self, session_directory: Path) -> bool:
        return any(
            (session_directory / filename).exists()
            for filename in (
                "paper_order_intent.json",
                "execution_summary.json",
                "execution_journal.jsonl",
                "intent_block_summary.json",
                "intent_dispatch_summary.json",
                "execution_handoff_summary.json",
            )
        )

    def _load_json_required(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise S23PaperExecutionJournalError(
                f"Missing required S23 paper artifact: {path}"
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise S23PaperExecutionJournalError(
                f"Corrupt JSON artifact: {path} ({exc.msg})"
            ) from exc

    def _load_optional_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return self._load_json_required(path)

    def _load_jsonl_optional(self, path: Path) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise S23PaperExecutionJournalError(
                    f"Corrupt JSONL artifact: {path} line {index} ({exc.msg})"
                ) from exc
        return tuple(rows)

    def _parse_state_required(self, value: Any, artifact_name: str) -> PaperSessionState:
        try:
            return PaperSessionState(str(value))
        except ValueError as exc:
            raise S23PaperExecutionJournalError(
                f"Invalid terminal state in {artifact_name}: {value!r}"
            ) from exc

    def _parse_date_required(self, value: Any, artifact_name: str) -> date:
        try:
            return date.fromisoformat(str(value))
        except ValueError as exc:
            raise S23PaperExecutionJournalError(
                f"Invalid date in {artifact_name}: {value!r}"
            ) from exc

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        rendered = str(value)
        return rendered if rendered else None

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _optional_date(self, value: Any) -> date | None:
        if value is None:
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    def _write_json(self, path: Path, payload: Any) -> None:
        rendered = json.dumps(
            self._normalize(payload),
            indent=2,
            sort_keys=True,
        ) + "\n"
        self._atomic_write_text(path, rendered)

    def _write_jsonl(self, path: Path, rows: tuple[Any, ...]) -> None:
        rendered = "".join(
            json.dumps(self._normalize(row), sort_keys=True) + "\n"
            for row in rows
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
