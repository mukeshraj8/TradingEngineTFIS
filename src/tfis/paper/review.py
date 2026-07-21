from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from .models import PaperReadinessStatus, PaperSessionState
from .replay_bundle import S23PaperReplayBundleManager
from .runtime_contract import (
    PaperTradeFillContract,
    PaperTradeIntentContract,
    PaperTradeLifecycleContract,
    PaperTradeShellContract,
)


_NO_EXECUTION_DISCLAIMER = (
    "No order was placed, no fill was simulated, no position was opened, and "
    "no lifecycle monitoring occurred yet; this review covers planning and "
    "fillless pre-execution shell artifacts only."
)
_PHASE1_FILL_DISCLAIMER = (
    "No broker order was placed, no real-money order was routed, no live "
    "position was opened, and no target/SL lifecycle monitoring occurred yet; "
    "this review covers only Phase 1 fill or no-fill artifacts."
)
_PHASE2_LIFECYCLE_DISCLAIMER = (
    "No broker order was placed, no real-money order was routed, and no live "
    "position existed; this review includes same-day paper-only fill-to-exit "
    "lifecycle simulation artifacts."
)
_TERMINAL_ARTIFACTS = {
    PaperSessionState.ORDER_PLANNED: "paper_order_plan.json",
    PaperSessionState.NO_TRADE: "no_trade_summary.json",
    PaperSessionState.ABORTED: "abort_summary.json",
}


class S23PaperReviewError(RuntimeError):
    """Raised when a paper-session review cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class S23PaperReviewAuditStep:
    timestamp: datetime
    previous_state: str
    new_state: str
    event_type: str | None
    reason: str
    terminal_code: str | None
    guardrail_code: str | None


@dataclass(frozen=True, slots=True)
class S23PaperReviewGuardrail:
    code: str | None
    message: str | None
    blocking_event_type: str | None
    blocking_source_id: str | None
    operator_action_required: str | None


@dataclass(frozen=True, slots=True)
class S23PaperReviewSelectedContract:
    available: bool
    symbol: str | None
    option_type: str | None
    strike: float | None
    expiry: date | None
    bid: float | None
    ask: float | None
    ltp: float | None
    oi: float | None
    volume: float | None
    effective_timestamp: datetime | None
    captured_at: datetime | None


@dataclass(frozen=True, slots=True)
class S23PaperReviewOrderPlan:
    available: bool
    selected_contract_symbol: str | None
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    selected_contract_ltp: float | None
    monthly_status: str | None
    overlays_enabled: tuple[str, ...]
    required_snapshot_labels: tuple[str, ...]
    planning_timestamp: datetime | None
    strategy_branch: str | None
    order_side: str | None
    lots: int | None
    quantity: int | None
    planned_entry_price: float | None
    target_price: float | None
    stoploss_price: float | None
    fsl_price: float | None
    order_reference_time: datetime | None
    order_reference_label: str | None
    source_workbook_rule: str | None
    workbook_row_number: int | None


@dataclass(frozen=True, slots=True)
class S23PaperReviewOrderIntent:
    available: bool
    status: str | None
    execution_shell_status: str | None
    dispatch_shell_status: str | None
    handoff_shell_status: str | None
    reason_code: str | None
    message: str | None
    order_side: str | None
    lots: int | None
    quantity: int | None
    planned_entry_price: float | None
    target_price: float | None
    stoploss_price: float | None
    fsl_price: float | None
    order_reference_time: datetime | None
    order_reference_label: str | None
    source_branch: str | None
    source_workbook_rule: str | None
    workbook_row_number: int | None
    bundle_validated: bool | None
    historical_comparison_status: str | None
    historical_comparison_go_no_go: str | None
    historical_comparison_reason: str | None
    guardrail_code: str | None
    guardrail_message: str | None
    blocking_event_type: str | None
    blocking_source_id: str | None
    operator_action_required: str | None
    future_fill_simulation_eligible: bool | None
    disclaimer: str | None


@dataclass(frozen=True, slots=True)
class S23PaperReviewFillPhase:
    available: bool
    status: str | None
    reason_code: str | None
    message: str | None
    fill_price: float | None
    fill_timestamp: datetime | None
    selected_contract_symbol: str | None
    source_kind: str | None
    source_type: str | None
    source_id: str | None
    source_effective_timestamp: datetime | None
    spread_points: float | None
    slippage_entry_points: float | None
    no_fill_reason: str | None
    disclaimer: str | None


@dataclass(frozen=True, slots=True)
class S23PaperReviewLifecyclePhase:
    available: bool
    status: str | None
    exit_reason_code: str | None
    message: str | None
    entry_price: float | None
    entry_timestamp: datetime | None
    target_price: float | None
    stoploss_price: float | None
    fsl_price: float | None
    exit_price: float | None
    exit_timestamp: datetime | None
    gross_pnl_rupees: float | None
    net_pnl_rupees: float | None
    event_count: int
    warning_flags: tuple[str, ...]
    disclaimer: str | None


@dataclass(frozen=True, slots=True)
class S23PaperReviewDataProvenance:
    cost_slippage_version: str | None
    data_source_count: int
    source_types: tuple[str, ...]
    source_ids: tuple[str, ...]
    synthetic_fixture_used: bool


@dataclass(frozen=True, slots=True)
class S23PaperReviewFreshness:
    selected_contract_quote_present: bool
    selected_contract_effective_timestamp: datetime | None
    selected_contract_captured_at: datetime | None
    planning_timestamp: datetime | None
    selected_contract_quote_age_seconds_at_planning: float | None
    warning_flags: tuple[str, ...]
    stale_warning_present: bool


@dataclass(frozen=True, slots=True)
class S23PaperReviewBundleStatus:
    bundle_directory: str | None
    manifest_present: bool
    validation_performed: bool
    is_valid: bool | None
    terminal_state: PaperSessionState | None
    terminal_reason_code: str | None
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class S23PaperReviewRuntimeContracts:
    shell: PaperTradeShellContract | None
    intent: PaperTradeIntentContract | None
    fill: PaperTradeFillContract | None
    lifecycle: PaperTradeLifecycleContract | None


@dataclass(frozen=True, slots=True)
class S23PaperReviewSummary:
    session_directory: str
    bundle_directory: str | None
    session_id: str
    session_date: date
    strategy_code: str
    terminal_state: PaperSessionState
    readiness_status: PaperReadinessStatus
    terminal_reason_code: str | None
    terminal_reason_message: str
    guardrail: S23PaperReviewGuardrail
    selected_contract: S23PaperReviewSelectedContract
    order_plan: S23PaperReviewOrderPlan | None
    order_intent: S23PaperReviewOrderIntent | None
    fill_phase: S23PaperReviewFillPhase | None
    lifecycle_phase: S23PaperReviewLifecyclePhase | None
    audit_transition_count: int
    audit_transitions: tuple[S23PaperReviewAuditStep, ...]
    data_provenance: S23PaperReviewDataProvenance
    freshness: S23PaperReviewFreshness
    replay_bundle: S23PaperReviewBundleStatus
    runtime_contracts: S23PaperReviewRuntimeContracts
    no_execution_disclaimer: str


class S23PaperSessionReviewer:
    def __init__(
        self,
        *,
        bundle_manager: S23PaperReplayBundleManager | None = None,
    ) -> None:
        self._bundle_manager = bundle_manager or S23PaperReplayBundleManager()

    def review_session(
        self,
        session_directory: str | Path,
        *,
        bundle_directory: str | Path | None = None,
    ) -> S23PaperReviewSummary:
        session_dir = Path(session_directory)
        if not session_dir.exists():
            raise S23PaperReviewError(
                f"S23 paper session artifact directory does not exist: {session_dir}"
            )

        manifest = self._load_json_required(session_dir / "session_manifest.json")
        decision = self._load_json_required(session_dir / "decision_summary.json")
        audit_rows = self._load_jsonl_required(session_dir / "audit_events.jsonl")

        strategy_code = str(decision.get("strategy_code", ""))
        if strategy_code != "S23":
            raise S23PaperReviewError(
                f"Unsupported strategy for S23 paper review: {strategy_code or 'unknown'}"
            )

        terminal_state = self._parse_state(decision.get("state"), "decision_summary.json")
        readiness_status = self._parse_readiness(
            decision.get("readiness_status"),
            "decision_summary.json",
        )
        terminal_payload = self._load_terminal_payload(session_dir, terminal_state)
        selected_contract_payload = self._load_optional_json(
            session_dir / "selected_contract.json"
        )
        order_intent_payload = self._load_optional_json(
            session_dir / "paper_order_intent.json"
        )
        execution_summary_payload = self._load_optional_json(
            session_dir / "execution_summary.json"
        )
        pending_fill_payload = self._load_optional_json(
            session_dir / "paper_order_pending.json"
        )
        paper_fill_payload = self._load_optional_json(session_dir / "paper_fill.json")
        paper_no_fill_payload = self._load_optional_json(
            session_dir / "paper_no_fill.json"
        )
        paper_fill_abort_payload = self._load_optional_json(
            session_dir / "paper_fill_abort_summary.json"
        )
        paper_position_payload = self._load_optional_json(
            session_dir / "paper_position.json"
        )
        lifecycle_event_rows = self._load_jsonl_optional(
            session_dir / "lifecycle_events.jsonl"
        )
        paper_exit_payload = self._load_optional_json(session_dir / "paper_exit.json")
        paper_pnl_summary_payload = self._load_optional_json(
            session_dir / "paper_pnl_summary.json"
        )

        order_plan = self._build_order_plan_summary(
            terminal_state,
            terminal_payload,
        )
        guardrail = self._build_guardrail_summary(
            terminal_payload if terminal_state is not PaperSessionState.ORDER_PLANNED else decision
        )
        audit_steps = self._build_audit_steps(audit_rows)
        provenance = self._build_provenance_summary(manifest)
        freshness = self._build_freshness_summary(
            selected_contract_payload,
            order_plan,
            warnings=tuple(str(item) for item in decision.get("warning_flags", ())),
        )
        fill_phase = self._build_fill_phase_summary(
            execution_summary_payload=execution_summary_payload,
            pending_fill_payload=pending_fill_payload,
            paper_fill_payload=paper_fill_payload,
            paper_no_fill_payload=paper_no_fill_payload,
            paper_fill_abort_payload=paper_fill_abort_payload,
        )
        lifecycle_phase = self._build_lifecycle_phase_summary(
            execution_summary_payload=execution_summary_payload,
            paper_position_payload=paper_position_payload,
            lifecycle_event_rows=lifecycle_event_rows,
            paper_exit_payload=paper_exit_payload,
            paper_pnl_summary_payload=paper_pnl_summary_payload,
        )
        replay_bundle = self._build_bundle_status(
            session_dir=session_dir,
            bundle_directory=bundle_directory,
        )
        order_intent = self._build_order_intent_summary(
            order_intent_payload=order_intent_payload,
            execution_summary_payload=execution_summary_payload,
            execution_arm_summary_payload=self._load_optional_json(
                session_dir / "execution_arm_summary.json"
            ),
            intent_dispatch_summary_payload=self._load_optional_json(
                session_dir / "intent_dispatch_summary.json"
            ),
            execution_handoff_summary_payload=self._load_optional_json(
                session_dir / "execution_handoff_summary.json"
            ),
            replay_bundle_valid=replay_bundle.is_valid,
        )
        runtime_contracts = self._build_runtime_contracts(
            session_id=str(decision["session_id"]),
            session_date=self._parse_date(decision["session_date"]),
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            selected_contract_symbol=(
                self._optional_text(
                    selected_contract_payload.get("symbol")
                    if selected_contract_payload is not None
                    else decision.get("selected_contract_symbol")
                )
            ),
            order_plan=order_plan,
            order_intent=order_intent,
            fill_phase=fill_phase,
            lifecycle_phase=lifecycle_phase,
        )

        terminal_reason_code = self._resolve_terminal_reason_code(
            terminal_state,
            decision,
            terminal_payload,
        )
        terminal_reason_message = self._resolve_terminal_reason_message(
            terminal_state,
            terminal_reason_code,
            guardrail,
        )

        return S23PaperReviewSummary(
            session_directory=str(session_dir),
            bundle_directory=(
                replay_bundle.bundle_directory if replay_bundle.bundle_directory else None
            ),
            session_id=str(decision["session_id"]),
            session_date=self._parse_date(decision["session_date"]),
            strategy_code=strategy_code,
            terminal_state=terminal_state,
            readiness_status=readiness_status,
            terminal_reason_code=terminal_reason_code,
            terminal_reason_message=terminal_reason_message,
            guardrail=guardrail,
            selected_contract=self._build_selected_contract_summary(
                decision=decision,
                selected_contract_payload=selected_contract_payload,
                order_plan=order_plan,
            ),
            order_plan=order_plan,
            order_intent=order_intent,
            fill_phase=fill_phase,
            lifecycle_phase=lifecycle_phase,
            audit_transition_count=len(audit_steps),
            audit_transitions=audit_steps,
            data_provenance=provenance,
            freshness=freshness,
            replay_bundle=replay_bundle,
            runtime_contracts=runtime_contracts,
            no_execution_disclaimer=(
                lifecycle_phase.disclaimer
                if lifecycle_phase is not None and lifecycle_phase.disclaimer
                else fill_phase.disclaimer
                if fill_phase is not None and fill_phase.disclaimer
                else _NO_EXECUTION_DISCLAIMER
            ),
        )

    def _build_runtime_contracts(
        self,
        *,
        session_id: str,
        session_date: date,
        strategy_code: str,
        terminal_state: PaperSessionState,
        selected_contract_symbol: str | None,
        order_plan: S23PaperReviewOrderPlan | None,
        order_intent: S23PaperReviewOrderIntent | None,
        fill_phase: S23PaperReviewFillPhase | None,
        lifecycle_phase: S23PaperReviewLifecyclePhase | None,
    ) -> S23PaperReviewRuntimeContracts:
        shell_contract = None
        if order_intent is not None:
            shell_contract = PaperTradeShellContract(
                session_id=session_id,
                session_date=session_date,
                strategy_code=strategy_code,
                terminal_state=terminal_state,
                selected_contract_symbol=selected_contract_symbol or "n/a",
                intent_status=order_intent.status,
                execution_shell_status=order_intent.execution_shell_status,
                dispatch_shell_status=order_intent.dispatch_shell_status,
                handoff_shell_status=order_intent.handoff_shell_status,
                historical_comparison_status=order_intent.historical_comparison_status,
                historical_comparison_reason=order_intent.historical_comparison_reason,
                historical_comparison_go_no_go=order_intent.historical_comparison_go_no_go,
            )

        intent_contract = None
        if (
            (
                order_intent is not None
                and order_intent.available
                and order_intent.planned_entry_price is not None
                and order_intent.target_price is not None
                and order_intent.stoploss_price is not None
                and order_intent.order_reference_time is not None
                and order_intent.order_side is not None
                and order_intent.lots is not None
                and order_intent.quantity is not None
            )
            or (
                order_plan is not None
                and order_plan.available
                and order_plan.planned_entry_price is not None
                and order_plan.target_price is not None
                and order_plan.stoploss_price is not None
                and order_plan.order_reference_time is not None
                and order_plan.order_side is not None
                and order_plan.lots is not None
                and order_plan.quantity is not None
            )
        ):
            intent_contract = PaperTradeIntentContract(
                session_id=session_id,
                session_date=session_date,
                strategy_code=strategy_code,
                terminal_state=terminal_state,
                status=(
                    order_intent.status
                    if order_intent is not None and order_intent.status is not None
                    else terminal_state.value
                ),
                selected_contract_symbol=(
                    order_plan.selected_contract_symbol
                    if order_plan is not None and order_plan.selected_contract_symbol is not None
                    else "n/a"
                ),
                selected_contract_option_type=(
                    order_plan.selected_contract_option_type if order_plan is not None else None
                ),
                selected_contract_expiry=(
                    order_plan.selected_contract_expiry if order_plan is not None else None
                ),
                side=(
                    order_intent.order_side
                    if order_intent is not None and order_intent.order_side is not None
                    else order_plan.order_side
                ),
                lots=(
                    order_intent.lots
                    if order_intent is not None and order_intent.lots is not None
                    else order_plan.lots
                ),
                quantity=(
                    order_intent.quantity
                    if order_intent is not None and order_intent.quantity is not None
                    else order_plan.quantity
                ),
                planned_entry_price=(
                    order_intent.planned_entry_price
                    if order_intent is not None and order_intent.planned_entry_price is not None
                    else order_plan.planned_entry_price
                ),
                target_price=(
                    order_intent.target_price
                    if order_intent is not None and order_intent.target_price is not None
                    else order_plan.target_price
                ),
                stoploss_price=(
                    order_intent.stoploss_price
                    if order_intent is not None and order_intent.stoploss_price is not None
                    else order_plan.stoploss_price
                ),
                fsl_price=(
                    order_intent.fsl_price
                    if order_intent is not None
                    else order_plan.fsl_price
                ),
                order_reference_time=(
                    order_intent.order_reference_time
                    if order_intent is not None and order_intent.order_reference_time is not None
                    else order_plan.order_reference_time
                ),
                order_reference_label=(
                    order_intent.order_reference_label
                    if order_intent is not None and order_intent.order_reference_label is not None
                    else order_plan.order_reference_label or "n/a"
                ),
                source_branch=(
                    order_intent.source_branch
                    if order_intent is not None and order_intent.source_branch is not None
                    else order_plan.strategy_branch
                ),
                source_workbook_rule=(
                    order_intent.source_workbook_rule
                    if order_intent is not None and order_intent.source_workbook_rule is not None
                    else order_plan.source_workbook_rule
                ),
                workbook_row_number=(
                    order_intent.workbook_row_number
                    if order_intent is not None and order_intent.workbook_row_number is not None
                    else order_plan.workbook_row_number
                ),
            )

        fill_contract = None
        if (
            fill_phase is not None
            and fill_phase.available
            and order_intent is not None
            and order_intent.planned_entry_price is not None
            and order_intent.order_reference_time is not None
        ):
            fill_contract = PaperTradeFillContract(
                session_id=session_id,
                session_date=session_date,
                strategy_code=strategy_code,
                status=fill_phase.status or "n/a",
                selected_contract_symbol=(
                    fill_phase.selected_contract_symbol
                    or (
                        order_plan.selected_contract_symbol
                        if order_plan is not None and order_plan.selected_contract_symbol is not None
                        else "n/a"
                    )
                ),
                selected_contract_option_type=(
                    order_plan.selected_contract_option_type if order_plan is not None else None
                ),
                selected_contract_expiry=(
                    order_plan.selected_contract_expiry if order_plan is not None else None
                ),
                planned_entry_price=order_intent.planned_entry_price,
                handoff_boundary_timestamp=order_intent.order_reference_time,
                fill_price=fill_phase.fill_price,
                fill_timestamp=fill_phase.fill_timestamp,
                source_kind=fill_phase.source_kind,
                source_type=fill_phase.source_type,
                source_id=fill_phase.source_id,
                source_effective_timestamp=fill_phase.source_effective_timestamp,
                reason_code=fill_phase.reason_code or "n/a",
                message=fill_phase.message or "",
                no_fill_reason=fill_phase.no_fill_reason,
                operator_action_required=None,
            )

        lifecycle_contract = None
        if (
            lifecycle_phase is not None
            and lifecycle_phase.available
            and lifecycle_phase.entry_price is not None
            and lifecycle_phase.target_price is not None
            and lifecycle_phase.entry_timestamp is not None
        ):
            lifecycle_contract = PaperTradeLifecycleContract(
                session_id=session_id,
                session_date=session_date,
                strategy_code=strategy_code,
                status=lifecycle_phase.status or "n/a",
                selected_contract_symbol=(
                    fill_phase.selected_contract_symbol
                    if fill_phase is not None and fill_phase.selected_contract_symbol is not None
                    else (
                        order_plan.selected_contract_symbol
                        if order_plan is not None and order_plan.selected_contract_symbol is not None
                        else "n/a"
                    )
                ),
                selected_contract_option_type=(
                    order_plan.selected_contract_option_type if order_plan is not None else None
                ),
                selected_contract_expiry=(
                    order_plan.selected_contract_expiry if order_plan is not None else None
                ),
                side=order_intent.order_side if order_intent is not None and order_intent.order_side else "n/a",
                lots=order_intent.lots if order_intent is not None and order_intent.lots is not None else 0,
                quantity=order_intent.quantity if order_intent is not None and order_intent.quantity is not None else 0,
                entry_price=lifecycle_phase.entry_price,
                target_price=lifecycle_phase.target_price,
                stoploss_price=lifecycle_phase.stoploss_price,
                fsl_price=lifecycle_phase.fsl_price,
                effective_stop_price=(
                    lifecycle_phase.stoploss_price
                    if lifecycle_phase.stoploss_price is not None
                    else lifecycle_phase.entry_price
                ),
                entry_timestamp=lifecycle_phase.entry_timestamp,
                exit_price=lifecycle_phase.exit_price,
                exit_timestamp=lifecycle_phase.exit_timestamp,
                exit_reason_code=lifecycle_phase.exit_reason_code or "n/a",
                message=lifecycle_phase.message or "",
                source_kind=fill_phase.source_kind if fill_phase is not None else None,
                source_type=fill_phase.source_type if fill_phase is not None else None,
                source_id=fill_phase.source_id if fill_phase is not None else None,
                source_effective_timestamp=(
                    fill_phase.source_effective_timestamp if fill_phase is not None else None
                ),
                gross_pnl_rupees=lifecycle_phase.gross_pnl_rupees,
                brokerage_rupees=None,
                net_pnl_rupees=lifecycle_phase.net_pnl_rupees,
                operator_action_required=None,
                warning_flags=lifecycle_phase.warning_flags,
            )

        return S23PaperReviewRuntimeContracts(
            shell=shell_contract,
            intent=intent_contract,
            fill=fill_contract,
            lifecycle=lifecycle_contract,
        )

    def review_bundle(
        self,
        bundle_directory: str | Path,
    ) -> S23PaperReviewSummary:
        return self.review_session(
            bundle_directory,
            bundle_directory=bundle_directory,
        )

    def render_review_json(self, summary: S23PaperReviewSummary) -> str:
        return json.dumps(self._normalize(summary), indent=2, sort_keys=True) + "\n"

    def render_review_markdown(self, summary: S23PaperReviewSummary) -> str:
        lines = [
            "# S23 Paper Session Review",
            "",
            "## Session",
            "",
            f"- Session ID: `{summary.session_id}`",
            f"- Session Date: `{summary.session_date.isoformat()}`",
            f"- Strategy: `{summary.strategy_code}`",
            f"- Terminal State: `{summary.terminal_state.value}`",
            f"- Readiness Status: `{summary.readiness_status.value}`",
            f"- Terminal Reason Code: `{summary.terminal_reason_code or 'n/a'}`",
            f"- Terminal Reason: {summary.terminal_reason_message}",
            "",
            "## Guardrails",
            "",
            f"- Guardrail Code: `{summary.guardrail.code or 'n/a'}`",
            f"- Guardrail Message: {summary.guardrail.message or 'n/a'}",
            f"- Blocking Event Type: `{summary.guardrail.blocking_event_type or 'n/a'}`",
            f"- Blocking Source ID: `{summary.guardrail.blocking_source_id or 'n/a'}`",
            f"- Operator Action Required: {summary.guardrail.operator_action_required or 'n/a'}",
            "",
            "## Selected Contract",
            "",
            f"- Available: `{summary.selected_contract.available}`",
            f"- Symbol: `{summary.selected_contract.symbol or 'n/a'}`",
            f"- Option Type: `{summary.selected_contract.option_type or 'n/a'}`",
            f"- Strike: `{summary.selected_contract.strike if summary.selected_contract.strike is not None else 'n/a'}`",
            f"- Expiry: `{summary.selected_contract.expiry.isoformat() if summary.selected_contract.expiry is not None else 'n/a'}`",
            f"- LTP: `{summary.selected_contract.ltp if summary.selected_contract.ltp is not None else 'n/a'}`",
            "",
            "## Order Plan",
            "",
        ]

        if summary.order_plan is None:
            lines.extend(
                [
                    "- Available: `False`",
                    "- Summary: no paper order plan was created for this session.",
                ]
            )
        else:
            lines.extend(
                [
                    "- Available: `True`",
                    f"- Selected Contract Symbol: `{summary.order_plan.selected_contract_symbol or 'n/a'}`",
                    f"- Monthly Status: `{summary.order_plan.monthly_status or 'n/a'}`",
                    f"- Planning Timestamp: `{summary.order_plan.planning_timestamp.isoformat() if summary.order_plan.planning_timestamp is not None else 'n/a'}`",
                    f"- Overlays Enabled: `{', '.join(summary.order_plan.overlays_enabled) if summary.order_plan.overlays_enabled else 'none'}`",
                    f"- Required Snapshots: `{', '.join(summary.order_plan.required_snapshot_labels) if summary.order_plan.required_snapshot_labels else 'none'}`",
                ]
            )

        lines.extend(
            [
                "",
                "## Order Intent",
                "",
            ]
        )

        if summary.order_intent is None:
            lines.extend(
                [
                    "- Available: `False`",
                    "- Summary: no execution-journal intent shell is present for this session.",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Available: `{summary.order_intent.available}`",
                    f"- Status: `{summary.order_intent.status or 'n/a'}`",
                    f"- Execution Shell Status: `{summary.order_intent.execution_shell_status or 'n/a'}`",
                    f"- Dispatch Shell Status: `{summary.order_intent.dispatch_shell_status or 'n/a'}`",
                    f"- Handoff Shell Status: `{summary.order_intent.handoff_shell_status or 'n/a'}`",
                    f"- Future Fill Simulation Eligible: `{summary.order_intent.future_fill_simulation_eligible if summary.order_intent.future_fill_simulation_eligible is not None else 'n/a'}`",
                    f"- Order Side: `{summary.order_intent.order_side or 'n/a'}`",
                    f"- Lots: `{summary.order_intent.lots if summary.order_intent.lots is not None else 'n/a'}`",
                    f"- Quantity: `{summary.order_intent.quantity if summary.order_intent.quantity is not None else 'n/a'}`",
                    f"- Planned Entry Price: `{summary.order_intent.planned_entry_price if summary.order_intent.planned_entry_price is not None else 'n/a'}`",
                    f"- Target Price: `{summary.order_intent.target_price if summary.order_intent.target_price is not None else 'n/a'}`",
                    f"- Stoploss Price: `{summary.order_intent.stoploss_price if summary.order_intent.stoploss_price is not None else 'n/a'}`",
                    f"- FSL Price: `{summary.order_intent.fsl_price if summary.order_intent.fsl_price is not None else 'n/a'}`",
                    f"- Order Reference: `{summary.order_intent.order_reference_label or 'n/a'}` at `{summary.order_intent.order_reference_time.isoformat() if summary.order_intent.order_reference_time is not None else 'n/a'}`",
                    f"- Source Branch: `{summary.order_intent.source_branch or 'n/a'}`",
                    f"- Source Workbook Rule: `{summary.order_intent.source_workbook_rule or 'n/a'}`",
                    f"- Bundle Validated: `{summary.order_intent.bundle_validated if summary.order_intent.bundle_validated is not None else 'n/a'}`",
                    f"- Historical Comparison Status: `{summary.order_intent.historical_comparison_status or 'n/a'}`",
                    f"- Historical Comparison Go / No-Go: {summary.order_intent.historical_comparison_go_no_go or 'n/a'}",
                    f"- Historical Comparison Reason: {summary.order_intent.historical_comparison_reason or 'n/a'}",
                    f"- Latest Shell Guardrail Code: `{summary.order_intent.guardrail_code or 'n/a'}`",
                    f"- Latest Shell Guardrail Message: {summary.order_intent.guardrail_message or 'n/a'}",
                    f"- Blocking Event Type: `{summary.order_intent.blocking_event_type or 'n/a'}`",
                    f"- Blocking Source ID: `{summary.order_intent.blocking_source_id or 'n/a'}`",
                    f"- Operator Action Required: {summary.order_intent.operator_action_required or 'n/a'}",
                    f"- Disclaimer: {summary.order_intent.disclaimer or 'n/a'}",
                ]
            )

        lines.extend(
            [
                "",
                "## Fill Phase 1",
                "",
            ]
        )

        if summary.fill_phase is None:
            lines.extend(
                [
                    "- Available: `False`",
                    "- Summary: no Phase 1 fill or no-fill artifact is present for this session yet.",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Available: `{summary.fill_phase.available}`",
                    f"- Status: `{summary.fill_phase.status or 'n/a'}`",
                    f"- Reason Code: `{summary.fill_phase.reason_code or 'n/a'}`",
                    f"- Message: {summary.fill_phase.message or 'n/a'}",
                    f"- Fill Price: `{summary.fill_phase.fill_price if summary.fill_phase.fill_price is not None else 'n/a'}`",
                    f"- Fill Timestamp: `{summary.fill_phase.fill_timestamp.isoformat() if summary.fill_phase.fill_timestamp is not None else 'n/a'}`",
                    f"- Selected Contract Symbol: `{summary.fill_phase.selected_contract_symbol or 'n/a'}`",
                    f"- Source Kind: `{summary.fill_phase.source_kind or 'n/a'}`",
                    f"- Source Type: `{summary.fill_phase.source_type or 'n/a'}`",
                    f"- Source ID: `{summary.fill_phase.source_id or 'n/a'}`",
                    f"- Source Effective Timestamp: `{summary.fill_phase.source_effective_timestamp.isoformat() if summary.fill_phase.source_effective_timestamp is not None else 'n/a'}`",
                    f"- Spread Points: `{summary.fill_phase.spread_points if summary.fill_phase.spread_points is not None else 'n/a'}`",
                    f"- Entry Slippage Points: `{summary.fill_phase.slippage_entry_points if summary.fill_phase.slippage_entry_points is not None else 'n/a'}`",
                    f"- No-Fill Reason: `{summary.fill_phase.no_fill_reason or 'n/a'}`",
                    f"- Disclaimer: {summary.fill_phase.disclaimer or 'n/a'}",
                ]
            )

        lines.extend(
            [
                "",
                "## Lifecycle Phase 2",
                "",
            ]
        )

        if summary.lifecycle_phase is None:
            lines.extend(
                [
                    "- Available: `False`",
                    "- Summary: no Phase 2 same-day lifecycle artifact is present for this session yet.",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Available: `{summary.lifecycle_phase.available}`",
                    f"- Status: `{summary.lifecycle_phase.status or 'n/a'}`",
                    f"- Exit Reason Code: `{summary.lifecycle_phase.exit_reason_code or 'n/a'}`",
                    f"- Message: {summary.lifecycle_phase.message or 'n/a'}",
                    f"- Entry Price: `{summary.lifecycle_phase.entry_price if summary.lifecycle_phase.entry_price is not None else 'n/a'}`",
                    f"- Entry Timestamp: `{summary.lifecycle_phase.entry_timestamp.isoformat() if summary.lifecycle_phase.entry_timestamp is not None else 'n/a'}`",
                    f"- Target Price: `{summary.lifecycle_phase.target_price if summary.lifecycle_phase.target_price is not None else 'n/a'}`",
                    f"- Stoploss Price: `{summary.lifecycle_phase.stoploss_price if summary.lifecycle_phase.stoploss_price is not None else 'n/a'}`",
                    f"- FSL Price: `{summary.lifecycle_phase.fsl_price if summary.lifecycle_phase.fsl_price is not None else 'n/a'}`",
                    f"- Exit Price: `{summary.lifecycle_phase.exit_price if summary.lifecycle_phase.exit_price is not None else 'n/a'}`",
                    f"- Exit Timestamp: `{summary.lifecycle_phase.exit_timestamp.isoformat() if summary.lifecycle_phase.exit_timestamp is not None else 'n/a'}`",
                    f"- Gross P&L (Rupees): `{summary.lifecycle_phase.gross_pnl_rupees if summary.lifecycle_phase.gross_pnl_rupees is not None else 'n/a'}`",
                    f"- Net P&L (Rupees): `{summary.lifecycle_phase.net_pnl_rupees if summary.lifecycle_phase.net_pnl_rupees is not None else 'n/a'}`",
                    f"- Lifecycle Event Count: `{summary.lifecycle_phase.event_count}`",
                    f"- Warning Flags: `{', '.join(summary.lifecycle_phase.warning_flags) if summary.lifecycle_phase.warning_flags else 'none'}`",
                    f"- Disclaimer: {summary.lifecycle_phase.disclaimer or 'n/a'}",
                ]
            )

        lines.extend(
            [
                "",
                "## Provenance",
                "",
                f"- Cost/Slippage Version: `{summary.data_provenance.cost_slippage_version or 'n/a'}`",
                f"- Data Source Count: `{summary.data_provenance.data_source_count}`",
                f"- Source Types: `{', '.join(summary.data_provenance.source_types) if summary.data_provenance.source_types else 'n/a'}`",
                f"- Source IDs: `{', '.join(summary.data_provenance.source_ids) if summary.data_provenance.source_ids else 'n/a'}`",
                f"- Synthetic Fixture Used: `{summary.data_provenance.synthetic_fixture_used}`",
                "",
                "## Freshness",
                "",
                f"- Selected Contract Quote Present: `{summary.freshness.selected_contract_quote_present}`",
                f"- Quote Effective Timestamp: `{summary.freshness.selected_contract_effective_timestamp.isoformat() if summary.freshness.selected_contract_effective_timestamp is not None else 'n/a'}`",
                f"- Quote Captured Timestamp: `{summary.freshness.selected_contract_captured_at.isoformat() if summary.freshness.selected_contract_captured_at is not None else 'n/a'}`",
                f"- Planning Timestamp: `{summary.freshness.planning_timestamp.isoformat() if summary.freshness.planning_timestamp is not None else 'n/a'}`",
                f"- Quote Age Seconds At Planning: `{summary.freshness.selected_contract_quote_age_seconds_at_planning if summary.freshness.selected_contract_quote_age_seconds_at_planning is not None else 'n/a'}`",
                f"- Warning Flags: `{', '.join(summary.freshness.warning_flags) if summary.freshness.warning_flags else 'none'}`",
                f"- Stale Warning Present: `{summary.freshness.stale_warning_present}`",
                "",
                "## Replay Bundle",
                "",
                f"- Bundle Manifest Present: `{summary.replay_bundle.manifest_present}`",
                f"- Validation Performed: `{summary.replay_bundle.validation_performed}`",
                f"- Bundle Valid: `{summary.replay_bundle.is_valid if summary.replay_bundle.is_valid is not None else 'n/a'}`",
                f"- Bundle Errors: `{', '.join(summary.replay_bundle.errors) if summary.replay_bundle.errors else 'none'}`",
                f"- Bundle Warnings: `{', '.join(summary.replay_bundle.warnings) if summary.replay_bundle.warnings else 'none'}`",
                "",
                "## Audit Timeline",
                "",
            ]
        )

        if not summary.audit_transitions:
            lines.append("- No audit transitions were recorded.")
        else:
            for step in summary.audit_transitions:
                lines.append(
                    f"- `{step.timestamp.isoformat()}` `{step.previous_state}->{step.new_state}` "
                    f"`{step.event_type or 'NONE'}` reason=`{step.reason}` "
                    f"terminal=`{step.terminal_code or 'n/a'}` guardrail=`{step.guardrail_code or 'n/a'}`"
                )

        lines.extend(
            [
                "",
                "## Safety Note",
                "",
                f"- {summary.no_execution_disclaimer}",
                "",
            ]
        )
        return "\n".join(lines)

    def write_review_outputs(
        self,
        summary: S23PaperReviewSummary,
        *,
        out_json: str | Path | None = None,
        out_md: str | Path | None = None,
    ) -> None:
        if out_json is not None:
            self._atomic_write_text(Path(out_json), self.render_review_json(summary))
        if out_md is not None:
            self._atomic_write_text(Path(out_md), self.render_review_markdown(summary))

    def _build_bundle_status(
        self,
        *,
        session_dir: Path,
        bundle_directory: str | Path | None,
    ) -> S23PaperReviewBundleStatus:
        explicit_bundle = bundle_directory is not None
        target_dir = Path(bundle_directory) if bundle_directory is not None else session_dir
        manifest_path = target_dir / "replay_bundle_manifest.json"
        if not manifest_path.exists():
            if explicit_bundle:
                raise S23PaperReviewError(
                    f"Replay bundle manifest is missing: {manifest_path}"
                )
            return S23PaperReviewBundleStatus(
                bundle_directory=None,
                manifest_present=False,
                validation_performed=False,
                is_valid=None,
                terminal_state=None,
                terminal_reason_code=None,
                errors=(),
                warnings=(),
            )

        validation = self._bundle_manager.validate_bundle(target_dir)
        return S23PaperReviewBundleStatus(
            bundle_directory=str(target_dir),
            manifest_present=True,
            validation_performed=True,
            is_valid=validation.is_valid,
            terminal_state=validation.terminal_state,
            terminal_reason_code=validation.terminal_reason_code,
            errors=validation.errors,
            warnings=validation.warnings,
        )

    def _build_selected_contract_summary(
        self,
        *,
        decision: dict[str, Any],
        selected_contract_payload: dict[str, Any] | None,
        order_plan: S23PaperReviewOrderPlan | None,
    ) -> S23PaperReviewSelectedContract:
        if selected_contract_payload is None:
            return S23PaperReviewSelectedContract(
                available=bool(decision.get("selected_contract_available", False)),
                symbol=(
                    order_plan.selected_contract_symbol
                    if order_plan is not None
                    else self._optional_text(decision.get("selected_contract_symbol"))
                ),
                option_type=(
                    order_plan.selected_contract_option_type
                    if order_plan is not None
                    else None
                ),
                strike=None,
                expiry=(
                    order_plan.selected_contract_expiry
                    if order_plan is not None
                    else None
                ),
                bid=None,
                ask=None,
                ltp=order_plan.selected_contract_ltp if order_plan is not None else None,
                oi=None,
                volume=None,
                effective_timestamp=None,
                captured_at=None,
            )

        envelope = selected_contract_payload.get("envelope", {})
        return S23PaperReviewSelectedContract(
            available=True,
            symbol=self._optional_text(selected_contract_payload.get("symbol")),
            option_type=self._optional_text(selected_contract_payload.get("option_type")),
            strike=self._optional_float(selected_contract_payload.get("strike")),
            expiry=self._optional_date(selected_contract_payload.get("expiry")),
            bid=self._optional_float(selected_contract_payload.get("bid")),
            ask=self._optional_float(selected_contract_payload.get("ask")),
            ltp=self._optional_float(selected_contract_payload.get("ltp")),
            oi=self._optional_float(selected_contract_payload.get("oi")),
            volume=self._optional_float(selected_contract_payload.get("volume")),
            effective_timestamp=self._optional_datetime(
                envelope.get("effective_timestamp")
            ),
            captured_at=self._optional_datetime(envelope.get("captured_at")),
        )

    def _build_order_plan_summary(
        self,
        terminal_state: PaperSessionState,
        terminal_payload: dict[str, Any],
    ) -> S23PaperReviewOrderPlan | None:
        if terminal_state is not PaperSessionState.ORDER_PLANNED:
            return None
        plan = terminal_payload.get("order_plan")
        if not isinstance(plan, dict):
            raise S23PaperReviewError(
                "paper_order_plan.json is missing the serialized order plan payload."
            )
        return S23PaperReviewOrderPlan(
            available=True,
            selected_contract_symbol=self._optional_text(
                plan.get("selected_contract_symbol")
            ),
            selected_contract_option_type=self._optional_text(
                plan.get("selected_contract_option_type")
            ),
            selected_contract_expiry=self._optional_date(
                plan.get("selected_contract_expiry")
            ),
            selected_contract_ltp=self._optional_float(
                plan.get("selected_contract_ltp")
            ),
            monthly_status=self._optional_text(plan.get("monthly_status")),
            overlays_enabled=tuple(str(item) for item in plan.get("overlays_enabled", ())),
            required_snapshot_labels=tuple(
                str(item) for item in plan.get("required_snapshot_labels", ())
            ),
            planning_timestamp=self._optional_datetime(
                plan.get("planning_timestamp")
            ),
            strategy_branch=self._optional_text(plan.get("strategy_branch")),
            order_side=self._optional_text(plan.get("order_side")),
            lots=self._optional_int(plan.get("lots")),
            quantity=self._optional_int(plan.get("quantity")),
            planned_entry_price=self._optional_float(plan.get("planned_entry_price")),
            target_price=self._optional_float(plan.get("target_price")),
            stoploss_price=self._optional_float(plan.get("stoploss_price")),
            fsl_price=self._optional_float(plan.get("fsl_price")),
            order_reference_time=self._optional_datetime(plan.get("order_reference_time")),
            order_reference_label=self._optional_text(plan.get("order_reference_label")),
            source_workbook_rule=self._optional_text(plan.get("source_workbook_rule")),
            workbook_row_number=self._optional_int(plan.get("workbook_row_number")),
        )

    def _build_order_intent_summary(
        self,
        *,
        order_intent_payload: dict[str, Any] | None,
        execution_summary_payload: dict[str, Any] | None,
        execution_arm_summary_payload: dict[str, Any] | None,
        intent_dispatch_summary_payload: dict[str, Any] | None,
        execution_handoff_summary_payload: dict[str, Any] | None,
        replay_bundle_valid: bool | None,
    ) -> S23PaperReviewOrderIntent | None:
        if (
            order_intent_payload is None
            and execution_summary_payload is None
            and execution_arm_summary_payload is None
            and intent_dispatch_summary_payload is None
            and execution_handoff_summary_payload is None
        ):
            return None
        status_source = (
            execution_handoff_summary_payload
            or intent_dispatch_summary_payload
            or execution_arm_summary_payload
            or execution_summary_payload
            or {}
        )
        explicit_summary = execution_summary_payload or {}
        intent_status = self._optional_text(explicit_summary.get("intent_status"))
        if intent_status is None and order_intent_payload is not None:
            intent_status = "INTENT_READY"
        return S23PaperReviewOrderIntent(
            available=order_intent_payload is not None,
            status=intent_status,
            execution_shell_status=self._optional_text(
                explicit_summary.get("execution_shell_status")
            ) or self._optional_text(status_source.get("execution_shell_status")),
            dispatch_shell_status=self._optional_text(
                explicit_summary.get("dispatch_shell_status")
            ) or self._optional_text(status_source.get("dispatch_shell_status")),
            handoff_shell_status=self._optional_text(
                explicit_summary.get("handoff_shell_status")
            ) or self._optional_text(status_source.get("handoff_shell_status")),
            reason_code=self._optional_text(
                explicit_summary.get("terminal_reason_code")
            ) or self._optional_text(status_source.get("terminal_reason_code")),
            message=self._optional_text(explicit_summary.get("message"))
            or self._optional_text(status_source.get("message")),
            order_side=self._optional_text(
                order_intent_payload.get("side") if order_intent_payload is not None else None
            ),
            lots=self._optional_int(
                order_intent_payload.get("lots") if order_intent_payload is not None else None
            ),
            quantity=self._optional_int(
                order_intent_payload.get("quantity") if order_intent_payload is not None else None
            ),
            planned_entry_price=self._optional_float(
                order_intent_payload.get("planned_entry_price") if order_intent_payload is not None else None
            ),
            target_price=self._optional_float(
                order_intent_payload.get("target_price") if order_intent_payload is not None else None
            ),
            stoploss_price=self._optional_float(
                order_intent_payload.get("stoploss_price") if order_intent_payload is not None else None
            ),
            fsl_price=self._optional_float(
                order_intent_payload.get("fsl_price") if order_intent_payload is not None else None
            ),
            order_reference_time=self._optional_datetime(
                order_intent_payload.get("order_reference_time") if order_intent_payload is not None else None
            ),
            order_reference_label=self._optional_text(
                order_intent_payload.get("order_reference_label") if order_intent_payload is not None else None
            ),
            source_branch=self._optional_text(
                order_intent_payload.get("source_branch") if order_intent_payload is not None else None
            ),
            source_workbook_rule=self._optional_text(
                order_intent_payload.get("source_workbook_rule") if order_intent_payload is not None else None
            ),
            workbook_row_number=self._optional_int(
                order_intent_payload.get("workbook_row_number") if order_intent_payload is not None else None
            ),
            bundle_validated=replay_bundle_valid,
            historical_comparison_status=self._optional_text(
                explicit_summary.get("historical_comparison_status")
            ) or self._optional_text(status_source.get("historical_comparison_status")),
            historical_comparison_go_no_go=self._optional_text(
                explicit_summary.get("historical_comparison_go_no_go")
            ) or self._optional_text(status_source.get("historical_comparison_go_no_go")),
            historical_comparison_reason=self._optional_text(
                explicit_summary.get("historical_comparison_reason")
            ) or self._optional_text(status_source.get("historical_comparison_reason")),
            guardrail_code=self._optional_text(
                explicit_summary.get("guardrail_code")
            ) or self._optional_text(status_source.get("guardrail_code")),
            guardrail_message=self._optional_text(explicit_summary.get("guardrail_message"))
            or self._optional_text(status_source.get("guardrail_message")),
            blocking_event_type=self._optional_text(
                explicit_summary.get("blocking_event_type")
            ) or self._optional_text(status_source.get("blocking_event_type")),
            blocking_source_id=self._optional_text(explicit_summary.get("blocking_source_id"))
            or self._optional_text(status_source.get("blocking_source_id")),
            operator_action_required=self._optional_text(
                explicit_summary.get("operator_action_required")
            ) or self._optional_text(status_source.get("operator_action_required")),
            future_fill_simulation_eligible=self._optional_bool(
                explicit_summary.get("future_fill_simulation_eligible")
            )
            if explicit_summary.get("future_fill_simulation_eligible") is not None
            else self._optional_bool(status_source.get("future_fill_simulation_eligible")),
            disclaimer=self._optional_text(
                order_intent_payload.get("disclaimer") if order_intent_payload is not None else (
                    explicit_summary.get("disclaimer")
                )
            ) or self._optional_text(status_source.get("disclaimer")),
        )

    def _build_fill_phase_summary(
        self,
        *,
        execution_summary_payload: dict[str, Any] | None,
        pending_fill_payload: dict[str, Any] | None,
        paper_fill_payload: dict[str, Any] | None,
        paper_no_fill_payload: dict[str, Any] | None,
        paper_fill_abort_payload: dict[str, Any] | None,
    ) -> S23PaperReviewFillPhase | None:
        if (
            execution_summary_payload is None
            and pending_fill_payload is None
            and paper_fill_payload is None
            and paper_no_fill_payload is None
            and paper_fill_abort_payload is None
        ):
            return None

        explicit_status = self._optional_text(
            (execution_summary_payload or {}).get("fill_status")
        )
        if (
            explicit_status is None
            and pending_fill_payload is None
            and paper_fill_payload is None
            and paper_no_fill_payload is None
            and paper_fill_abort_payload is None
        ):
            return None

        payload = (
            paper_fill_payload
            or paper_no_fill_payload
            or paper_fill_abort_payload
            or pending_fill_payload
            or execution_summary_payload
            or {}
        )
        explicit_summary = execution_summary_payload or {}
        status = self._optional_text(
            explicit_summary.get("fill_status")
        ) or self._optional_text(payload.get("status"))
        return S23PaperReviewFillPhase(
            available=payload is not None,
            status=status,
            reason_code=self._optional_text(
                explicit_summary.get("fill_reason_code")
            ) or self._optional_text(payload.get("reason_code")),
            message=self._optional_text(
                explicit_summary.get("fill_message")
            ) or self._optional_text(payload.get("message")),
            fill_price=self._optional_float(
                explicit_summary.get("fill_price")
            ) if explicit_summary.get("fill_price") is not None else self._optional_float(payload.get("fill_price")),
            fill_timestamp=self._optional_datetime(
                explicit_summary.get("fill_timestamp")
            ) if explicit_summary.get("fill_timestamp") not in (None, "") else self._optional_datetime(payload.get("fill_timestamp")),
            selected_contract_symbol=self._optional_text(payload.get("selected_contract_symbol")),
            source_kind=self._optional_text(
                explicit_summary.get("fill_source_kind")
            ) or self._optional_text(payload.get("source_kind")),
            source_type=self._optional_text(
                explicit_summary.get("fill_source_type")
            ) or self._optional_text(payload.get("source_type")),
            source_id=self._optional_text(
                explicit_summary.get("fill_source_id")
            ) or self._optional_text(payload.get("source_id")),
            source_effective_timestamp=self._optional_datetime(
                explicit_summary.get("fill_source_effective_timestamp")
            ) if explicit_summary.get("fill_source_effective_timestamp") not in (None, "") else self._optional_datetime(payload.get("source_effective_timestamp")),
            spread_points=self._optional_float(
                explicit_summary.get("fill_spread_points")
            ) if explicit_summary.get("fill_spread_points") is not None else self._optional_float(payload.get("spread_points")),
            slippage_entry_points=self._optional_float(
                explicit_summary.get("fill_slippage_entry_points")
            ) if explicit_summary.get("fill_slippage_entry_points") is not None else self._optional_float(payload.get("slippage_entry_points")),
            no_fill_reason=self._optional_text(
                payload.get("no_fill_reason")
            ),
            disclaimer=self._optional_text(payload.get("disclaimer"))
            or self._optional_text(
                explicit_summary.get("disclaimer")
            )
            or _PHASE1_FILL_DISCLAIMER,
        )

    def _build_lifecycle_phase_summary(
        self,
        *,
        execution_summary_payload: dict[str, Any] | None,
        paper_position_payload: dict[str, Any] | None,
        lifecycle_event_rows: tuple[dict[str, Any], ...],
        paper_exit_payload: dict[str, Any] | None,
        paper_pnl_summary_payload: dict[str, Any] | None,
    ) -> S23PaperReviewLifecyclePhase | None:
        if (
            execution_summary_payload is None
            and paper_position_payload is None
            and not lifecycle_event_rows
            and paper_exit_payload is None
            and paper_pnl_summary_payload is None
        ):
            return None

        explicit_status = self._optional_text(
            (execution_summary_payload or {}).get("lifecycle_status")
        )
        payload = paper_exit_payload or paper_pnl_summary_payload or paper_position_payload or {}
        explicit_summary = execution_summary_payload or {}
        status = explicit_status or self._optional_text(payload.get("status"))
        if status is None and not lifecycle_event_rows:
            return None

        warning_flags = tuple(
            str(item)
            for item in (
                explicit_summary.get("lifecycle_warning_flags")
                or payload.get("warning_flags")
                or ()
            )
            if str(item).strip()
        )
        return S23PaperReviewLifecyclePhase(
            available=True,
            status=status,
            exit_reason_code=self._optional_text(
                explicit_summary.get("exit_reason_code")
            ) or self._optional_text(payload.get("exit_reason_code")),
            message=self._optional_text(
                explicit_summary.get("lifecycle_message")
            ) or self._optional_text(payload.get("message")),
            entry_price=self._optional_float(
                (paper_position_payload or {}).get("entry_price")
            ),
            entry_timestamp=self._optional_datetime(
                (paper_position_payload or {}).get("entry_timestamp")
            ),
            target_price=self._optional_float(
                (paper_position_payload or {}).get("target_price")
            ),
            stoploss_price=self._optional_float(
                (paper_position_payload or {}).get("stoploss_price")
            ),
            fsl_price=self._optional_float(
                (paper_position_payload or {}).get("fsl_price")
            ),
            exit_price=self._optional_float(
                explicit_summary.get("exit_price")
            ) if explicit_summary.get("exit_price") is not None else self._optional_float((paper_exit_payload or {}).get("exit_price")),
            exit_timestamp=self._optional_datetime(
                explicit_summary.get("exit_timestamp")
            ) if explicit_summary.get("exit_timestamp") not in (None, "") else self._optional_datetime((paper_exit_payload or {}).get("exit_timestamp")),
            gross_pnl_rupees=self._optional_float(
                (paper_pnl_summary_payload or {}).get("gross_pnl_rupees")
            ) if paper_pnl_summary_payload is not None else self._optional_float(
                (paper_exit_payload or {}).get("gross_pnl_rupees")
            ),
            net_pnl_rupees=self._optional_float(
                (paper_pnl_summary_payload or {}).get("net_pnl_rupees")
            ) if paper_pnl_summary_payload is not None else self._optional_float(
                (paper_exit_payload or {}).get("net_pnl_rupees")
            ),
            event_count=len(lifecycle_event_rows),
            warning_flags=warning_flags,
            disclaimer=self._optional_text((paper_exit_payload or {}).get("disclaimer"))
            or self._optional_text((paper_pnl_summary_payload or {}).get("disclaimer"))
            or self._optional_text((paper_position_payload or {}).get("disclaimer"))
            or self._optional_text(explicit_summary.get("disclaimer"))
            or _PHASE2_LIFECYCLE_DISCLAIMER,
        )

    def _build_guardrail_summary(
        self,
        payload: dict[str, Any],
    ) -> S23PaperReviewGuardrail:
        return S23PaperReviewGuardrail(
            code=self._optional_text(payload.get("guardrail_code")),
            message=self._optional_text(payload.get("guardrail_message")),
            blocking_event_type=self._optional_text(
                payload.get("blocking_event_type")
            ),
            blocking_source_id=self._optional_text(
                payload.get("blocking_source_id")
            ),
            operator_action_required=self._optional_text(
                payload.get("operator_action_required")
            ),
        )

    def _build_audit_steps(
        self,
        audit_rows: tuple[dict[str, Any], ...],
    ) -> tuple[S23PaperReviewAuditStep, ...]:
        steps: list[S23PaperReviewAuditStep] = []
        for row in audit_rows:
            steps.append(
                S23PaperReviewAuditStep(
                    timestamp=self._parse_datetime_required(
                        row.get("timestamp"),
                        "audit_events.jsonl",
                    ),
                    previous_state=str(row.get("previous_state")),
                    new_state=str(row.get("new_state")),
                    event_type=self._optional_text(row.get("event_type")),
                    reason=str(row.get("reason")),
                    terminal_code=self._optional_text(row.get("terminal_code")),
                    guardrail_code=self._optional_text(row.get("guardrail_code")),
                )
            )
        return tuple(steps)

    def _build_provenance_summary(
        self,
        manifest: dict[str, Any],
    ) -> S23PaperReviewDataProvenance:
        data_sources = tuple(
            item for item in manifest.get("data_sources", ()) if isinstance(item, dict)
        )
        return S23PaperReviewDataProvenance(
            cost_slippage_version=self._optional_text(
                manifest.get("cost_slippage_version")
            ),
            data_source_count=len(data_sources),
            source_types=tuple(
                sorted(
                    {
                        str(item.get("source_type"))
                        for item in data_sources
                        if item.get("source_type") is not None
                    }
                )
            ),
            source_ids=tuple(
                sorted(
                    {
                        str(item.get("source_id"))
                        for item in data_sources
                        if item.get("source_id") is not None
                    }
                )
            ),
            synthetic_fixture_used=bool(
                manifest.get("synthetic_fixture_used", False)
            ),
        )

    def _build_freshness_summary(
        self,
        selected_contract_payload: dict[str, Any] | None,
        order_plan: S23PaperReviewOrderPlan | None,
        *,
        warnings: tuple[str, ...],
    ) -> S23PaperReviewFreshness:
        effective_timestamp = None
        captured_at = None
        if selected_contract_payload is not None:
            envelope = selected_contract_payload.get("envelope", {})
            effective_timestamp = self._optional_datetime(
                envelope.get("effective_timestamp")
            )
            captured_at = self._optional_datetime(envelope.get("captured_at"))

        planning_timestamp = (
            order_plan.planning_timestamp if order_plan is not None else None
        )
        quote_age = None
        if planning_timestamp is not None and captured_at is not None:
            quote_age = (
                planning_timestamp - captured_at
            ).total_seconds()
        stale_warning_present = any("stale" in item.lower() for item in warnings)
        return S23PaperReviewFreshness(
            selected_contract_quote_present=selected_contract_payload is not None,
            selected_contract_effective_timestamp=effective_timestamp,
            selected_contract_captured_at=captured_at,
            planning_timestamp=planning_timestamp,
            selected_contract_quote_age_seconds_at_planning=quote_age,
            warning_flags=warnings,
            stale_warning_present=stale_warning_present,
        )

    def _resolve_terminal_reason_code(
        self,
        terminal_state: PaperSessionState,
        decision: dict[str, Any],
        terminal_payload: dict[str, Any],
    ) -> str | None:
        if terminal_state is PaperSessionState.ORDER_PLANNED:
            return "paper_order_planned"
        return self._optional_text(
            terminal_payload.get("terminal_reason_code")
        ) or self._optional_text(decision.get("terminal_reason_code"))

    def _resolve_terminal_reason_message(
        self,
        terminal_state: PaperSessionState,
        terminal_reason_code: str | None,
        guardrail: S23PaperReviewGuardrail,
    ) -> str:
        if terminal_state is PaperSessionState.ORDER_PLANNED:
            return (
                "Paper order plan created successfully; execution and fills have "
                "not started."
            )
        if guardrail.message:
            return guardrail.message
        return terminal_reason_code or "Terminal reason unavailable."

    def _load_terminal_payload(
        self,
        session_dir: Path,
        terminal_state: PaperSessionState,
    ) -> dict[str, Any]:
        terminal_path = session_dir / _TERMINAL_ARTIFACTS[terminal_state]
        return self._load_json_required(terminal_path)

    def _load_json_required(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise S23PaperReviewError(f"Missing required artifact: {path}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise S23PaperReviewError(
                f"Corrupt JSON artifact: {path} ({exc.msg})"
            ) from exc

    def _load_optional_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return self._load_json_required(path)

    def _load_jsonl_required(self, path: Path) -> tuple[dict[str, Any], ...]:
        if not path.exists():
            raise S23PaperReviewError(f"Missing required artifact: {path}")
        rows: list[dict[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise S23PaperReviewError(
                    f"Corrupt JSONL artifact: {path} line {index} ({exc.msg})"
                ) from exc
        return tuple(rows)

    def _load_jsonl_optional(self, path: Path) -> tuple[dict[str, Any], ...]:
        if not path.exists():
            return ()
        return self._load_jsonl_required(path)

    def _parse_state(self, value: Any, artifact_name: str) -> PaperSessionState:
        try:
            return PaperSessionState(str(value))
        except ValueError as exc:
            raise S23PaperReviewError(
                f"Invalid terminal state in {artifact_name}: {value!r}"
            ) from exc

    def _parse_readiness(
        self,
        value: Any,
        artifact_name: str,
    ) -> PaperReadinessStatus:
        try:
            return PaperReadinessStatus(str(value))
        except ValueError as exc:
            raise S23PaperReviewError(
                f"Invalid readiness status in {artifact_name}: {value!r}"
            ) from exc

    def _parse_datetime_required(
        self,
        value: Any,
        artifact_name: str,
    ) -> datetime:
        parsed = self._optional_datetime(value)
        if parsed is None:
            raise S23PaperReviewError(
                f"Missing or invalid datetime in {artifact_name}: {value!r}"
            )
        return parsed

    def _parse_date(self, value: Any) -> date:
        return date.fromisoformat(str(value))

    def _optional_date(self, value: Any) -> date | None:
        if value is None or value == "":
            return None
        return self._parse_date(value)

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        return datetime.fromisoformat(str(value))

    def _optional_float(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    def _optional_bool(self, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no"}:
                return False
            return None
        return bool(value)

    def _optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        rendered = str(value)
        return rendered if rendered else None

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


PaperReviewError = S23PaperReviewError
PaperReviewAuditStep = S23PaperReviewAuditStep
PaperReviewGuardrail = S23PaperReviewGuardrail
PaperReviewSelectedContract = S23PaperReviewSelectedContract
PaperReviewOrderPlan = S23PaperReviewOrderPlan
PaperReviewOrderIntent = S23PaperReviewOrderIntent
PaperReviewFillPhase = S23PaperReviewFillPhase
PaperReviewLifecyclePhase = S23PaperReviewLifecyclePhase
PaperReviewDataProvenance = S23PaperReviewDataProvenance
PaperReviewFreshness = S23PaperReviewFreshness
PaperReviewBundleStatus = S23PaperReviewBundleStatus
PaperReviewRuntimeContracts = S23PaperReviewRuntimeContracts
PaperReviewSummary = S23PaperReviewSummary
PaperSessionReviewer = S23PaperSessionReviewer
