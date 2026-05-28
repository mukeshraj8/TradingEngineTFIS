from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .models import (
    OptionChainSnapshotEvent,
    PaperEventType,
    PaperReadinessStatus,
    PaperSessionConfigEvent,
    PaperSessionState,
    PaperValidationIssue,
    PaperValidationResult,
    SelectedContractQuoteEvent,
    SnapshotLabel,
)


@dataclass(frozen=True, slots=True)
class S23PaperGuardrailSettings:
    global_paper_trading_enabled: bool = True
    s23_paper_enabled: bool = True
    manual_operator_abort: bool = False
    manual_abort_reason: str | None = None
    max_planned_orders_per_session: int = 1
    enforce_selected_contract_liquidity_checks: bool = False
    min_selected_contract_oi: float | None = None
    max_selected_contract_spread_points: float | None = None
    global_paper_execution_enabled: bool = True
    s23_paper_execution_enabled: bool = True
    manual_operator_abort_after_planning: bool = False
    manual_abort_after_planning_reason: str | None = None
    require_operator_review_completed_before_execution: bool = False
    operator_review_completed: bool = True
    require_historical_comparison_before_execution: bool = True
    acceptable_historical_comparison_statuses: tuple[str, ...] = ("MATCH", "PARTIAL_MATCH")
    require_replay_bundle_validation_before_execution: bool = True
    require_same_day_only_policy_confirmation_before_execution: bool = True
    same_day_only_policy_confirmed: bool = True
    manual_operator_abort_before_dispatch: bool = False
    manual_abort_before_dispatch_reason: str | None = None
    manual_operator_abort_before_handoff: bool = False
    manual_abort_before_handoff_reason: str | None = None
    manual_operator_abort_before_fill: bool = False
    manual_abort_before_fill_reason: str | None = None
    manual_operator_abort_during_lifecycle: bool = False
    manual_abort_during_lifecycle_reason: str | None = None


@dataclass(frozen=True, slots=True)
class PaperGuardrailDecision:
    code: str
    message: str
    readiness_status: PaperReadinessStatus
    blocking_event_type: PaperEventType | None = None
    blocking_source_id: str | None = None
    operator_action_required: str | None = None

    @property
    def terminal_state(self) -> PaperSessionState:
        if self.readiness_status is PaperReadinessStatus.ABORTED:
            return PaperSessionState.ABORTED
        return PaperSessionState.NO_TRADE


class S23PaperGuardrailEvaluator:
    def __init__(
        self,
        settings: S23PaperGuardrailSettings | None = None,
    ) -> None:
        self._settings = settings or S23PaperGuardrailSettings()

    @property
    def settings(self) -> S23PaperGuardrailSettings:
        return self._settings

    def evaluate_pre_planning(
        self,
        *,
        paper_config: PaperSessionConfigEvent | None,
        option_chain_snapshot: OptionChainSnapshotEvent | None,
        selected_contract_quote: SelectedContractQuoteEvent | None,
        validation_result: PaperValidationResult | None,
        existing_order_plans: int,
        source_ids: dict[PaperEventType, str] | None = None,
    ) -> PaperGuardrailDecision | None:
        source_ids = source_ids or {}

        if not self._settings.global_paper_trading_enabled:
            return self._decision(
                "global_paper_trading_disabled",
                "Global paper trading is disabled, so S23 planning must abort.",
                PaperReadinessStatus.ABORTED,
                blocking_event_type=PaperEventType.PAPER_SESSION_CONFIG,
                blocking_source_id=source_ids.get(PaperEventType.PAPER_SESSION_CONFIG),
            )

        if not self._settings.s23_paper_enabled:
            return self._decision(
                "s23_paper_disabled",
                "S23 paper trading is disabled for this runtime.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.PAPER_SESSION_CONFIG,
                blocking_source_id=source_ids.get(PaperEventType.PAPER_SESSION_CONFIG),
            )

        if paper_config is not None and not paper_config.paper_mode_enabled:
            return self._decision(
                "paper_mode_disabled",
                "Paper mode is disabled in the supplied S23 session config.",
                PaperReadinessStatus.ABORTED,
                blocking_event_type=PaperEventType.PAPER_SESSION_CONFIG,
                blocking_source_id=source_ids.get(PaperEventType.PAPER_SESSION_CONFIG),
            )

        if paper_config is not None and paper_config.kill_switch_enabled:
            return self._decision(
                "session_kill_switch_enabled",
                "The S23 paper-session kill switch is engaged.",
                PaperReadinessStatus.ABORTED,
                blocking_event_type=PaperEventType.PAPER_SESSION_CONFIG,
                blocking_source_id=source_ids.get(PaperEventType.PAPER_SESSION_CONFIG),
            )

        if self._settings.manual_operator_abort:
            return self._decision(
                "manual_operator_abort",
                self._settings.manual_abort_reason
                or "An operator requested a manual S23 paper-session abort.",
                PaperReadinessStatus.ABORTED,
                blocking_source_id="manual_operator",
            )

        if existing_order_plans >= self._settings.max_planned_orders_per_session:
            return self.planning_limit_decision()

        validation_decision = self.classify_validation_block(
            validation_result,
            source_ids=source_ids,
        )
        if validation_decision is not None:
            return validation_decision

        if option_chain_snapshot is None:
            return self._decision(
                "missing_option_chain_snapshot",
                "Decision-ready S23 paper sessions require an option-chain snapshot.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.OPTION_CHAIN_SNAPSHOT,
            )

        if selected_contract_quote is None:
            return self._decision(
                "missing_selected_contract_quote",
                "Decision-ready S23 paper sessions require a selected contract quote.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            )

        liquidity_decision = self._evaluate_liquidity_placeholder(
            option_chain_snapshot=option_chain_snapshot,
            selected_contract_quote=selected_contract_quote,
            source_ids=source_ids,
        )
        if liquidity_decision is not None:
            return liquidity_decision

        return None

    def evaluate_post_planning(
        self,
        *,
        evaluation_timestamp: datetime,
        max_selected_contract_age: timedelta,
        replay_bundle_validation_performed: bool,
        replay_bundle_valid: bool | None,
        replay_bundle_errors: tuple[str, ...] = (),
        selected_contract_symbol: str | None,
        selected_contract_effective_timestamp: datetime | None,
        order_plan_selected_contract_symbol: str | None = None,
        intent_selected_contract_symbol: str | None = None,
        require_intent_artifact: bool = False,
        intent_exists: bool = False,
        intent_artifact_issue: str | None = None,
        duplicate_intent_generation_attempt: bool = False,
    ) -> PaperGuardrailDecision | None:
        if self._settings.manual_operator_abort_after_planning:
            return self._decision(
                "manual_operator_abort_after_planning",
                self._settings.manual_abort_after_planning_reason
                or "An operator aborted the S23 paper execution shell after planning.",
                PaperReadinessStatus.ABORTED,
                blocking_source_id="manual_operator",
            )

        if not self._settings.global_paper_execution_enabled:
            return self._decision(
                "global_paper_execution_disabled",
                "Global paper execution-shell readiness is disabled for S23.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.PAPER_SESSION_CONFIG,
            )

        if not self._settings.s23_paper_execution_enabled:
            return self._decision(
                "s23_paper_execution_disabled",
                "S23 paper execution-shell readiness is disabled for this runtime.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.PAPER_SESSION_CONFIG,
            )

        if (
            self._settings.require_operator_review_completed_before_execution
            and not self._settings.operator_review_completed
        ):
            return self._decision(
                "operator_review_incomplete",
                "Operator review must be completed before the S23 execution shell can be marked ready.",
                PaperReadinessStatus.NO_TRADE,
            )

        if replay_bundle_validation_performed and replay_bundle_valid is False:
            if any(
                error.startswith("hash_mismatch:")
                or error.startswith("missing_hashed_artifact:")
                for error in replay_bundle_errors
            ):
                return self._decision(
                    "session_artifact_hash_mismatch",
                    "Replay bundle validation found a paper-session artifact hash mismatch.",
                    PaperReadinessStatus.NO_TRADE,
                )
            return self._decision(
                "invalid_replay_bundle",
                "Replay bundle validation failed for the S23 paper session.",
                PaperReadinessStatus.NO_TRADE,
            )

        if intent_artifact_issue == "corrupt_order_intent_artifact":
            return self._decision(
                "corrupt_order_intent_artifact",
                "The persisted paper order-intent artifact is corrupt and blocks execution-shell readiness.",
                PaperReadinessStatus.NO_TRADE,
            )

        if require_intent_artifact and intent_artifact_issue == "missing_order_intent_artifact":
            return self._decision(
                "missing_order_intent_artifact",
                "The paper order-intent artifact is missing and execution-shell readiness is blocked.",
                PaperReadinessStatus.NO_TRADE,
            )

        if selected_contract_symbol is None or selected_contract_effective_timestamp is None:
            return self._decision(
                "missing_selected_contract_quote",
                "Selected contract quote provenance is missing for the post-planning execution shell.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            )

        if evaluation_timestamp - selected_contract_effective_timestamp > max_selected_contract_age:
            return self._decision(
                "selected_contract_stale_before_execution",
                "Selected contract quote is stale before the S23 execution shell can be marked ready.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            )

        if (
            order_plan_selected_contract_symbol
            and intent_selected_contract_symbol
            and order_plan_selected_contract_symbol != intent_selected_contract_symbol
        ):
            return self._decision(
                "selected_contract_mismatch_between_order_plan_and_intent",
                "The persisted paper order intent no longer matches the planned selected contract.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            )

        if require_intent_artifact and not intent_exists:
            return self._decision(
                "missing_order_intent_artifact",
                "The paper order-intent artifact is missing and execution-shell readiness is blocked.",
                PaperReadinessStatus.NO_TRADE,
            )

        if duplicate_intent_generation_attempt:
            return self._decision(
                "duplicate_paper_order_intent_generation",
                "Duplicate paper order-intent generation attempts are blocked for one S23 paper session.",
                PaperReadinessStatus.NO_TRADE,
            )

        return None

    def evaluate_execution_shell(
        self,
        *,
        evaluation_timestamp: datetime,
        max_selected_contract_age: timedelta,
        replay_bundle_validation_performed: bool,
        replay_bundle_valid: bool | None,
        replay_bundle_errors: tuple[str, ...] = (),
        selected_contract_symbol: str | None,
        selected_contract_effective_timestamp: datetime | None,
        order_plan_selected_contract_symbol: str | None = None,
        intent_selected_contract_symbol: str | None = None,
        intent_exists: bool = False,
        intent_artifact_issue: str | None = None,
        historical_comparison_performed: bool = False,
        historical_comparison_status: str | None = None,
        duplicate_execution_arming_attempt: bool = False,
    ) -> PaperGuardrailDecision | None:
        decision = self.evaluate_post_planning(
            evaluation_timestamp=evaluation_timestamp,
            max_selected_contract_age=max_selected_contract_age,
            replay_bundle_validation_performed=replay_bundle_validation_performed,
            replay_bundle_valid=replay_bundle_valid,
            replay_bundle_errors=replay_bundle_errors,
            selected_contract_symbol=selected_contract_symbol,
            selected_contract_effective_timestamp=selected_contract_effective_timestamp,
            order_plan_selected_contract_symbol=order_plan_selected_contract_symbol,
            intent_selected_contract_symbol=intent_selected_contract_symbol,
            require_intent_artifact=True,
            intent_exists=intent_exists,
            intent_artifact_issue=intent_artifact_issue,
            duplicate_intent_generation_attempt=False,
        )
        if decision is not None:
            return decision

        if (
            self._settings.require_replay_bundle_validation_before_execution
            and not replay_bundle_validation_performed
        ):
            return self._decision(
                "missing_replay_bundle_validation",
                "Replay bundle validation must be completed before the S23 execution shell can be armed.",
                PaperReadinessStatus.NO_TRADE,
            )

        if duplicate_execution_arming_attempt:
            return self._decision(
                "duplicate_execution_shell_arming_attempt",
                "Duplicate execution-shell arming attempts are blocked for one S23 paper session.",
                PaperReadinessStatus.NO_TRADE,
            )

        if self._settings.require_historical_comparison_before_execution:
            if not historical_comparison_performed:
                return self._decision(
                    "missing_historical_comparison",
                    "Paper-vs-historical comparison must be completed before the S23 execution shell can be armed.",
                    PaperReadinessStatus.NO_TRADE,
                )

            accepted = set(self._settings.acceptable_historical_comparison_statuses)
            if historical_comparison_status not in accepted:
                if historical_comparison_status == "MISMATCH":
                    code = "historical_comparison_mismatch"
                    message = (
                        "Paper-vs-historical comparison reported a mismatch, so the S23 execution shell cannot be armed."
                    )
                elif historical_comparison_status == "UNCOMPARABLE":
                    code = "historical_comparison_uncomparable"
                    message = (
                        "Paper-vs-historical comparison was uncomparable, so the S23 execution shell cannot be armed."
                    )
                else:
                    code = "historical_comparison_not_acceptable"
                    message = (
                        "Paper-vs-historical comparison did not produce an acceptable status for S23 execution-shell arming."
                    )
                return self._decision(
                    code,
                    message,
                    PaperReadinessStatus.NO_TRADE,
                )

        if (
            self._settings.require_same_day_only_policy_confirmation_before_execution
            and not self._settings.same_day_only_policy_confirmed
        ):
            return self._decision(
                "same_day_only_policy_not_confirmed",
                "Same-day-only policy must be confirmed before the S23 execution shell can be armed.",
                PaperReadinessStatus.NO_TRADE,
            )

        return None

    def evaluate_dispatch_shell(
        self,
        *,
        evaluation_timestamp: datetime,
        max_selected_contract_age: timedelta,
        replay_bundle_validation_performed: bool,
        replay_bundle_valid: bool | None,
        replay_bundle_errors: tuple[str, ...] = (),
        selected_contract_symbol: str | None,
        selected_contract_effective_timestamp: datetime | None,
        order_plan_selected_contract_symbol: str | None = None,
        intent_selected_contract_symbol: str | None = None,
        execution_summary_selected_contract_symbol: str | None = None,
        intent_exists: bool = False,
        intent_artifact_issue: str | None = None,
        historical_comparison_performed: bool = False,
        historical_comparison_status: str | None = None,
        execution_shell_status: str | None = None,
        duplicate_dispatch_attempt: bool = False,
    ) -> PaperGuardrailDecision | None:
        if self._settings.manual_operator_abort_before_dispatch:
            return self._decision(
                "manual_operator_abort_before_dispatch",
                self._settings.manual_abort_before_dispatch_reason
                or "An operator cancelled the S23 paper intent before dispatch.",
                PaperReadinessStatus.ABORTED,
                blocking_source_id="manual_operator",
            )

        decision = self.evaluate_execution_shell(
            evaluation_timestamp=evaluation_timestamp,
            max_selected_contract_age=max_selected_contract_age,
            replay_bundle_validation_performed=replay_bundle_validation_performed,
            replay_bundle_valid=replay_bundle_valid,
            replay_bundle_errors=replay_bundle_errors,
            selected_contract_symbol=selected_contract_symbol,
            selected_contract_effective_timestamp=selected_contract_effective_timestamp,
            order_plan_selected_contract_symbol=order_plan_selected_contract_symbol,
            intent_selected_contract_symbol=intent_selected_contract_symbol,
            intent_exists=intent_exists,
            intent_artifact_issue=intent_artifact_issue,
            historical_comparison_performed=historical_comparison_performed,
            historical_comparison_status=historical_comparison_status,
            duplicate_execution_arming_attempt=False,
        )
        if decision is not None:
            return decision

        if execution_shell_status != "EXECUTION_ARMED":
            return self._decision(
                "execution_shell_not_armed_for_dispatch",
                "The S23 execution shell must be armed before the order intent can be dispatched.",
                PaperReadinessStatus.NO_TRADE,
            )

        if (
            execution_summary_selected_contract_symbol
            and intent_selected_contract_symbol
            and execution_summary_selected_contract_symbol != intent_selected_contract_symbol
        ):
            return self._decision(
                "session_artifact_mismatch_before_dispatch",
                "Execution-shell artifacts no longer agree on the selected contract before dispatch.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            )

        if duplicate_dispatch_attempt:
            return self._decision(
                "duplicate_order_intent_dispatch_attempt",
                "Duplicate order-intent dispatch attempts are blocked for one S23 paper session.",
                PaperReadinessStatus.NO_TRADE,
            )

        return None

    def evaluate_handoff_shell(
        self,
        *,
        evaluation_timestamp: datetime,
        max_selected_contract_age: timedelta,
        replay_bundle_validation_performed: bool,
        replay_bundle_valid: bool | None,
        replay_bundle_errors: tuple[str, ...] = (),
        selected_contract_symbol: str | None,
        selected_contract_effective_timestamp: datetime | None,
        order_plan_selected_contract_symbol: str | None = None,
        intent_selected_contract_symbol: str | None = None,
        execution_summary_selected_contract_symbol: str | None = None,
        dispatch_summary_selected_contract_symbol: str | None = None,
        intent_exists: bool = False,
        intent_artifact_issue: str | None = None,
        historical_comparison_performed: bool = False,
        historical_comparison_status: str | None = None,
        execution_shell_status: str | None = None,
        dispatch_shell_status: str | None = None,
        duplicate_handoff_attempt: bool = False,
    ) -> PaperGuardrailDecision | None:
        if self._settings.manual_operator_abort_before_handoff:
            return self._decision(
                "manual_operator_abort_before_handoff",
                self._settings.manual_abort_before_handoff_reason
                or "An operator cancelled the S23 paper intent before the final no-fill handoff boundary.",
                PaperReadinessStatus.ABORTED,
                blocking_source_id="manual_operator",
            )

        decision = self.evaluate_dispatch_shell(
            evaluation_timestamp=evaluation_timestamp,
            max_selected_contract_age=max_selected_contract_age,
            replay_bundle_validation_performed=replay_bundle_validation_performed,
            replay_bundle_valid=replay_bundle_valid,
            replay_bundle_errors=replay_bundle_errors,
            selected_contract_symbol=selected_contract_symbol,
            selected_contract_effective_timestamp=selected_contract_effective_timestamp,
            order_plan_selected_contract_symbol=order_plan_selected_contract_symbol,
            intent_selected_contract_symbol=intent_selected_contract_symbol,
            execution_summary_selected_contract_symbol=execution_summary_selected_contract_symbol,
            intent_exists=intent_exists,
            intent_artifact_issue=intent_artifact_issue,
            historical_comparison_performed=historical_comparison_performed,
            historical_comparison_status=historical_comparison_status,
            execution_shell_status=execution_shell_status,
            duplicate_dispatch_attempt=False,
        )
        if decision is not None:
            return decision

        if dispatch_shell_status != "ORDER_INTENT_DISPATCHED":
            return self._decision(
                "dispatch_shell_not_ready_for_handoff",
                "The S23 paper intent must be filllessly dispatched before final execution handoff readiness can be marked.",
                PaperReadinessStatus.NO_TRADE,
            )

        symbols = {
            symbol
            for symbol in (
                order_plan_selected_contract_symbol,
                intent_selected_contract_symbol,
                execution_summary_selected_contract_symbol,
                dispatch_summary_selected_contract_symbol,
            )
            if symbol
        }
        if len(symbols) > 1:
            return self._decision(
                "session_artifact_mismatch_before_handoff",
                "Execution-shell artifacts no longer agree on the selected contract before final handoff readiness.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
            )

        if duplicate_handoff_attempt:
            return self._decision(
                "duplicate_execution_handoff_attempt",
                "Duplicate final execution-handoff attempts are blocked for one S23 paper session.",
                PaperReadinessStatus.NO_TRADE,
            )

        return None

    def evaluate_fill_phase(
        self,
        *,
        evaluation_timestamp: datetime,
        max_selected_contract_age: timedelta,
        replay_bundle_validation_performed: bool,
        replay_bundle_valid: bool | None,
        replay_bundle_errors: tuple[str, ...] = (),
        handoff_shell_status: str | None,
        selected_contract_symbol: str | None,
        order_plan_selected_contract_symbol: str | None = None,
        intent_selected_contract_symbol: str | None = None,
        execution_summary_selected_contract_symbol: str | None = None,
        handoff_summary_selected_contract_symbol: str | None = None,
        historical_comparison_performed: bool = False,
        historical_comparison_status: str | None = None,
        execution_shell_status: str | None = None,
        dispatch_shell_status: str | None = None,
        duplicate_fill_attempt: bool = False,
    ) -> PaperGuardrailDecision | None:
        if self._settings.manual_operator_abort_before_fill:
            return self._decision(
                "manual_operator_abort_before_fill",
                self._settings.manual_abort_before_fill_reason
                or "An operator aborted the S23 paper fill simulator before any paper fill was evaluated.",
                PaperReadinessStatus.ABORTED,
                blocking_source_id="manual_operator",
            )

        decision = self.evaluate_handoff_shell(
            evaluation_timestamp=evaluation_timestamp,
            max_selected_contract_age=max_selected_contract_age,
            replay_bundle_validation_performed=replay_bundle_validation_performed,
            replay_bundle_valid=replay_bundle_valid,
            replay_bundle_errors=replay_bundle_errors,
            selected_contract_symbol=selected_contract_symbol,
            selected_contract_effective_timestamp=evaluation_timestamp,
            order_plan_selected_contract_symbol=order_plan_selected_contract_symbol,
            intent_selected_contract_symbol=intent_selected_contract_symbol,
            execution_summary_selected_contract_symbol=execution_summary_selected_contract_symbol,
            dispatch_summary_selected_contract_symbol=handoff_summary_selected_contract_symbol,
            intent_exists=True,
            intent_artifact_issue=None,
            historical_comparison_performed=historical_comparison_performed,
            historical_comparison_status=historical_comparison_status,
            execution_shell_status=execution_shell_status,
            dispatch_shell_status=dispatch_shell_status,
            duplicate_handoff_attempt=False,
        )
        if decision is not None:
            if decision.code == "dispatch_shell_not_ready_for_handoff":
                return self._decision(
                    "execution_handoff_not_ready_for_fill",
                    "The S23 paper fill simulator requires PAPER_EXECUTION_HANDOFF_READY before any fill or no-fill decision can be recorded.",
                    PaperReadinessStatus.ABORTED,
                )
            return decision

        if handoff_shell_status != "PAPER_EXECUTION_HANDOFF_READY":
            return self._decision(
                "execution_handoff_not_ready_for_fill",
                "The S23 paper fill simulator requires PAPER_EXECUTION_HANDOFF_READY before any fill or no-fill decision can be recorded.",
                PaperReadinessStatus.ABORTED,
            )

        if duplicate_fill_attempt:
            return self._decision(
                "duplicate_fill_attempt",
                "Duplicate Phase 1 paper fill attempts are blocked for one S23 paper session.",
                PaperReadinessStatus.ABORTED,
            )

        return None

    def evaluate_lifecycle_phase(
        self,
        *,
        replay_bundle_validation_performed: bool,
        replay_bundle_valid: bool | None,
        replay_bundle_errors: tuple[str, ...] = (),
        fill_status: str | None,
        selected_contract_symbol: str | None,
        fill_selected_contract_symbol: str | None,
        target_price_available: bool,
        stoploss_or_fsl_available: bool,
        duplicate_lifecycle_attempt: bool,
        same_day_only_policy_confirmed: bool | None = None,
    ) -> PaperGuardrailDecision | None:
        if replay_bundle_validation_performed and replay_bundle_valid is False:
            error_text = " ".join(replay_bundle_errors).lower()
            code = (
                "session_artifact_hash_mismatch"
                if "hash mismatch" in error_text
                else "invalid_replay_bundle"
            )
            return self._decision(
                code,
                "Replay bundle validation failed, so the S23 same-day lifecycle shell cannot proceed safely.",
                PaperReadinessStatus.ABORTED,
            )

        if fill_status is None:
            return self._decision(
                "missing_fill_artifact_for_lifecycle",
                "A persisted paper fill artifact is required before starting the S23 same-day lifecycle loop.",
                PaperReadinessStatus.ABORTED,
            )
        if fill_status != "PAPER_ORDER_FILLED":
            return self._decision(
                "paper_fill_not_ready_for_lifecycle",
                "S23 same-day lifecycle simulation requires a PAPER_ORDER_FILLED outcome.",
                PaperReadinessStatus.ABORTED,
            )
        if duplicate_lifecycle_attempt:
            return self._decision(
                "duplicate_lifecycle_start",
                "S23 same-day lifecycle simulation has already been started for this paper session.",
                PaperReadinessStatus.ABORTED,
            )
        if (
            not selected_contract_symbol
            or not fill_selected_contract_symbol
            or selected_contract_symbol != fill_selected_contract_symbol
        ):
            return self._decision(
                "selected_contract_mismatch_before_lifecycle",
                "The persisted selected contract does not match the paper fill artifact, so lifecycle simulation cannot proceed safely.",
                PaperReadinessStatus.ABORTED,
            )
        if not target_price_available:
            return self._decision(
                "missing_target_price_for_lifecycle",
                "The S23 paper lifecycle loop requires a target price before a filled paper order can be monitored.",
                PaperReadinessStatus.ABORTED,
            )
        if not stoploss_or_fsl_available:
            return self._decision(
                "missing_stoploss_or_fsl_for_lifecycle",
                "The S23 paper lifecycle loop requires a stoploss or FSL threshold before a filled paper order can be monitored.",
                PaperReadinessStatus.ABORTED,
            )
        if (
            self._settings.require_same_day_only_policy_confirmation_before_execution
            and same_day_only_policy_confirmed is False
        ):
            return self._decision(
                "same_day_only_policy_not_confirmed_for_lifecycle",
                "The S23 paper lifecycle loop is restricted to same-day operation and the same-day-only policy was not confirmed.",
                PaperReadinessStatus.ABORTED,
            )

        return None

    def classify_validation_block(
        self,
        validation_result: PaperValidationResult | None,
        *,
        source_ids: dict[PaperEventType, str] | None = None,
    ) -> PaperGuardrailDecision | None:
        if validation_result is None:
            return None
        if validation_result.readiness_status is PaperReadinessStatus.READY:
            return None

        issue = self._first_terminal_issue(validation_result)
        if issue is None:
            return None

        source_id = None
        if issue.event_type is not None and source_ids is not None:
            source_id = source_ids.get(issue.event_type)

        return PaperGuardrailDecision(
            code=issue.code,
            message=issue.message,
            readiness_status=issue.readiness_status,
            blocking_event_type=issue.event_type,
            blocking_source_id=source_id,
            operator_action_required=self._operator_action_for_code(issue.code),
        )

    def decision_for_terminal_event(
        self,
        *,
        current_state: PaperSessionState,
        event_type: PaperEventType | None,
        source_id: str | None,
    ) -> PaperGuardrailDecision:
        code = "session_already_terminal"
        message = (
            "S23 paper-session input was rejected because the session is already terminal."
        )
        operator_action = self._operator_action_for_code(code)
        if current_state is PaperSessionState.ORDER_PLANNED:
            code = "max_planned_orders_per_session_exceeded"
            message = (
                "S23 paper sessions allow at most one planned order per session."
            )
            operator_action = self._operator_action_for_code(code)
        return PaperGuardrailDecision(
            code=code,
            message=message,
            readiness_status=PaperReadinessStatus.ABORTED,
            blocking_event_type=event_type,
            blocking_source_id=source_id,
            operator_action_required=operator_action,
        )

    def planning_limit_decision(self) -> PaperGuardrailDecision:
        return self._decision(
            "max_planned_orders_per_session_exceeded",
            "S23 paper sessions allow at most one planned order per session.",
            PaperReadinessStatus.ABORTED,
        )

    def build_validation_result(
        self,
        decision: PaperGuardrailDecision,
        *,
        evaluated_state: PaperSessionState,
        timestamp: datetime,
        required_snapshot_labels: tuple[SnapshotLabel, ...] = (),
        missing_snapshot_labels: tuple[SnapshotLabel, ...] = (),
    ) -> PaperValidationResult:
        issue = PaperValidationIssue(
            code=decision.code,
            message=decision.message,
            readiness_status=decision.readiness_status,
            event_type=decision.blocking_event_type,
        )
        return PaperValidationResult(
            readiness_status=decision.readiness_status,
            issues=(issue,),
            evaluated_state=evaluated_state,
            validated_at=timestamp,
            required_snapshot_labels=required_snapshot_labels,
            missing_snapshot_labels=missing_snapshot_labels,
            no_trade_reasons=(
                (decision.code,)
                if decision.readiness_status is PaperReadinessStatus.NO_TRADE
                else ()
            ),
            abort_reasons=(
                (decision.code,)
                if decision.readiness_status is PaperReadinessStatus.ABORTED
                else ()
            ),
        )

    def _evaluate_liquidity_placeholder(
        self,
        *,
        option_chain_snapshot: OptionChainSnapshotEvent,
        selected_contract_quote: SelectedContractQuoteEvent,
        source_ids: dict[PaperEventType, str],
    ) -> PaperGuardrailDecision | None:
        if not self._settings.enforce_selected_contract_liquidity_checks:
            return None

        if (
            self._settings.min_selected_contract_oi is not None
            and selected_contract_quote.oi is not None
            and selected_contract_quote.oi < self._settings.min_selected_contract_oi
        ):
            return self._decision(
                "selected_contract_oi_below_minimum",
                "Selected contract open interest is below the configured S23 paper threshold.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
                blocking_source_id=source_ids.get(PaperEventType.SELECTED_CONTRACT_QUOTE),
            )

        if (
            self._settings.max_selected_contract_spread_points is not None
            and selected_contract_quote.bid is not None
            and selected_contract_quote.ask is not None
            and (selected_contract_quote.ask - selected_contract_quote.bid)
            > self._settings.max_selected_contract_spread_points
        ):
            return self._decision(
                "selected_contract_spread_too_wide",
                "Selected contract spread exceeds the configured S23 paper threshold.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
                blocking_source_id=source_ids.get(PaperEventType.SELECTED_CONTRACT_QUOTE),
            )

        contract_symbols = {contract.symbol for contract in option_chain_snapshot.contracts}
        if selected_contract_quote.symbol not in contract_symbols:
            return self._decision(
                "selected_contract_not_in_option_chain",
                "The selected contract quote is not present in the supplied option chain.",
                PaperReadinessStatus.NO_TRADE,
                blocking_event_type=PaperEventType.SELECTED_CONTRACT_QUOTE,
                blocking_source_id=source_ids.get(PaperEventType.SELECTED_CONTRACT_QUOTE),
            )

        return None

    def _first_terminal_issue(
        self,
        validation_result: PaperValidationResult,
    ) -> PaperValidationIssue | None:
        priority_codes = validation_result.abort_reasons or validation_result.no_trade_reasons
        if priority_codes:
            for code in priority_codes:
                for issue in validation_result.issues:
                    if issue.code == code:
                        return issue
        if validation_result.issues:
            return validation_result.issues[0]
        return None

    def _decision(
        self,
        code: str,
        message: str,
        readiness_status: PaperReadinessStatus,
        *,
        blocking_event_type: PaperEventType | None = None,
        blocking_source_id: str | None = None,
    ) -> PaperGuardrailDecision:
        return PaperGuardrailDecision(
            code=code,
            message=message,
            readiness_status=readiness_status,
            blocking_event_type=blocking_event_type,
            blocking_source_id=blocking_source_id,
            operator_action_required=self._operator_action_for_code(code),
        )

    def _operator_action_for_code(self, code: str) -> str:
        if code == "global_paper_trading_disabled":
            return "Re-enable global paper trading before starting a new S23 paper session."
        if code == "s23_paper_disabled":
            return "Enable S23 paper trading or skip the S23 session for today."
        if code in {"manual_operator_abort", "session_kill_switch_enabled"}:
            return "Review the operator kill-switch state before starting another S23 paper session."
        if code == "max_planned_orders_per_session_exceeded":
            return "Start a fresh S23 paper session before planning another order."
        if code == "paper_mode_disabled":
            return "Enable paper mode in the S23 paper-session config."
        if code.startswith("missing_snapshot_"):
            return "Wait for the required normalized snapshots before planning S23."
        if code in {"missing_option_chain_snapshot", "selected_contract_not_in_option_chain"}:
            return "Refresh the option chain before attempting to plan S23."
        if code == "missing_selected_contract_quote":
            return "Refresh or reselect the chosen contract quote before continuing the S23 paper shell."
        if code in {
            "stale_underlying_quote",
            "stale_selected_contract_quote",
            "stale_ingest_quote",
            "future_ingest_quote_timestamp",
        }:
            return "Refresh the affected live-paper data source before planning S23."
        if code == "selected_contract_stale_before_execution":
            return "Refresh the selected-contract quote before marking the S23 intent ready for any future execution shell."
        if code == "unsupported_continuation_path":
            return "Keep same-day square-off enabled until the paper runtime supports multi-session carry-forward and expiry-aware continuation handling."
        if code == "monthly_status_unknown":
            return "Wait for a non-UNKNOWN monthly status before planning S23."
        if code == "holiday_session_blocked":
            return "Do not start an S23 paper session on a holiday."
        if code in {
            "selected_contract_oi_below_minimum",
            "selected_contract_spread_too_wide",
        }:
            return "Wait for better liquidity or adjust the configured paper thresholds."
        if code == "session_already_terminal":
            return "Start a new S23 paper session before accepting more paper events."
        if code == "global_paper_execution_disabled":
            return "Re-enable the global paper execution shell before handing off S23 intents."
        if code == "s23_paper_execution_disabled":
            return "Re-enable S23 paper execution-shell readiness before handing off the intent."
        if code == "manual_operator_abort_after_planning":
            return "Resolve the operator abort and review the intent shell before any future execution phase."
        if code == "operator_review_incomplete":
            return "Complete the operator review before marking the S23 intent ready."
        if code == "duplicate_paper_order_intent_generation":
            return "Do not regenerate the same S23 paper order intent; review the persisted intent and journal instead."
        if code == "duplicate_execution_shell_arming_attempt":
            return "Do not arm the same S23 execution shell more than once; review the persisted execution journal instead."
        if code == "selected_contract_mismatch_between_order_plan_and_intent":
            return "Regenerate or discard the paper intent because it no longer matches the planned selected contract."
        if code == "corrupt_order_intent_artifact":
            return "Repair or regenerate the corrupted paper order-intent artifact before continuing."
        if code == "missing_order_intent_artifact":
            return "Regenerate the missing paper order-intent artifact before continuing."
        if code in {"invalid_replay_bundle", "session_artifact_hash_mismatch"}:
            return "Rebuild and revalidate the replay bundle before continuing the S23 execution shell."
        if code == "missing_replay_bundle_validation":
            return "Create and validate a replay bundle before arming the S23 execution shell."
        if code == "missing_historical_comparison":
            return "Run paper-vs-historical comparison before arming the S23 execution shell."
        if code in {
            "historical_comparison_mismatch",
            "historical_comparison_uncomparable",
            "historical_comparison_not_acceptable",
        }:
            return "Resolve the paper-vs-historical comparison result before arming the S23 execution shell."
        if code == "same_day_only_policy_not_confirmed":
            return "Confirm same-day-only operating policy before arming the S23 execution shell."
        if code == "manual_operator_abort_before_dispatch":
            return "Resolve the operator cancel request before attempting to dispatch the S23 paper intent."
        if code == "execution_shell_not_armed_for_dispatch":
            return "Arm the S23 execution shell successfully before attempting any dispatch handoff."
        if code == "duplicate_order_intent_dispatch_attempt":
            return "Do not dispatch the same S23 paper intent twice; review the persisted dispatch summary instead."
        if code == "session_artifact_mismatch_before_dispatch":
            return "Repair or regenerate the paper execution-shell artifacts before dispatching the S23 intent."
        if code == "manual_operator_abort_before_handoff":
            return "Resolve the operator cancel request before marking the S23 intent eligible for any future fill simulator."
        if code == "dispatch_shell_not_ready_for_handoff":
            return "Dispatch the S23 intent filllessly before attempting the final execution handoff boundary."
        if code == "session_artifact_mismatch_before_handoff":
            return "Repair or regenerate the paper execution-shell artifacts before marking final handoff readiness."
        if code == "duplicate_execution_handoff_attempt":
            return "Do not mark the same S23 handoff boundary twice; review the persisted handoff summary instead."
        if code == "manual_operator_abort_before_fill":
            return "Resolve the operator cancel request before running the S23 Phase 1 paper fill simulator."
        if code == "execution_handoff_not_ready_for_fill":
            return "Do not run the paper fill simulator until the final S23 handoff boundary is ready."
        if code == "duplicate_fill_attempt":
            return "Do not run the S23 Phase 1 fill simulator twice for the same session; review the persisted fill artifacts instead."
        if code == "selected_contract_mismatch_before_fill":
            return "Supply selected-contract market data for the exact planned S23 symbol before running the fill simulator."
        if code == "missing_fill_artifact_for_lifecycle":
            return "Complete a valid Phase 1 paper fill before starting the S23 same-day lifecycle loop."
        if code == "paper_fill_not_ready_for_lifecycle":
            return "Do not start the S23 lifecycle loop until the paper fill result is PAPER_ORDER_FILLED."
        if code == "duplicate_lifecycle_start":
            return "Do not start the S23 lifecycle loop twice for the same session; review the persisted lifecycle artifacts instead."
        if code == "selected_contract_mismatch_before_lifecycle":
            return "Repair the selected-contract artifacts so the lifecycle loop uses the exact symbol that was filled."
        if code == "missing_target_price_for_lifecycle":
            return "Regenerate the paper order plan so the S23 lifecycle loop has a target price."
        if code == "missing_stoploss_or_fsl_for_lifecycle":
            return "Regenerate the paper order plan so the S23 lifecycle loop has a stoploss or FSL threshold."
        if code == "same_day_only_policy_not_confirmed_for_lifecycle":
            return "Confirm same-day-only policy before starting the S23 paper lifecycle loop."
        return "Review the recorded paper-session guardrail before retrying."
