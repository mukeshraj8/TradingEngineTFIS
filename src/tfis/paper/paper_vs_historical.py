from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from tfis.backtest.report_comparison import (
    ComparisonLimits,
    NormalizedTradeSummary,
    load_and_summarize_backtest_report,
)

from .models import PaperSessionState
from .review import S23PaperReviewError, S23PaperReviewSummary, S23PaperSessionReviewer


_ARTIFACT_VERSION = 1
_NO_EXECUTION_DISCLAIMER = (
    "No order was placed, no fill was simulated, no position was opened, and "
    "no lifecycle monitoring occurred yet; this comparison only checks whether "
    "the persisted paper intent aligns with the expected historical trade-plan "
    "output."
)
_PHASE1_FILL_DISCLAIMER = (
    "No broker order was placed, no real-money order was routed, no live "
    "position was opened, and no lifecycle monitoring occurred yet; this "
    "comparison includes Phase 1 fill or no-fill status only."
)
_PHASE2_LIFECYCLE_DISCLAIMER = (
    "No broker order was placed, no real-money order was routed, and no live "
    "position existed; this comparison includes same-day paper-only fill-to-exit "
    "lifecycle status only."
)
_SAME_DAY_ONLY_STATEMENT = (
    "This parity policy applies only to same-day S23 paper lifecycle sessions. "
    "Next-day continuation is unsupported and any carry-style outcome is a no-go."
)
_ACCEPTABLE_FILL_PRICE_DRIFT_POINTS = 2.0
_ACCEPTABLE_EXIT_PRICE_DRIFT_POINTS = 2.0
_ACCEPTABLE_EXIT_TIMESTAMP_DRIFT_SECONDS = 60.0


class PaperHistoricalComparisonStatus(str, Enum):
    MATCH = "MATCH"
    MATCH_WITH_ACCEPTABLE_DRIFT = "MATCH_WITH_ACCEPTABLE_DRIFT"
    MISMATCH = "MISMATCH"
    PARTIAL_MATCH = "PARTIAL_MATCH"
    UNCOMPARABLE = "UNCOMPARABLE"


class PaperHistoricalMismatchSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    BLOCKER = "blocker"


class S23PaperHistoricalComparisonError(RuntimeError):
    """Raised when a paper-vs-historical comparison request is invalid."""


@dataclass(frozen=True, slots=True)
class S23PaperHistoricalFieldComparison:
    field_name: str
    paper_value: Any
    historical_value: Any
    matched: bool
    acceptable_drift: bool
    severity: PaperHistoricalMismatchSeverity
    tolerance: float | None
    message: str


@dataclass(frozen=True, slots=True)
class S23PaperHistoricalComparisonSummary:
    artifact_version: int
    status: PaperHistoricalComparisonStatus
    go_no_go: str
    comparison_reason: str
    session_directory: str
    bundle_directory: str | None
    historical_report_path: str
    session_id: str
    session_date: date
    strategy_code: str
    paper_terminal_state: PaperSessionState
    paper_intent_status: str | None
    paper_execution_shell_status: str | None
    paper_dispatch_shell_status: str | None
    paper_handoff_shell_status: str | None
    paper_fill_status: str | None
    paper_fill_price: float | None
    paper_fill_timestamp: str | None
    paper_fill_reason_code: str | None
    paper_fill_message: str | None
    paper_lifecycle_status: str | None
    paper_exit_reason_code: str | None
    paper_exit_price: float | None
    paper_exit_timestamp: str | None
    paper_gross_pnl_rupees: float | None
    paper_net_pnl_rupees: float | None
    historical_entry_price: float | None
    historical_exit_reason_code: str | None
    historical_exit_price: float | None
    historical_exit_timestamp: str | None
    historical_exit_outcome: str | None
    historical_net_pnl_rupees: float | None
    execution_shell_reason_code: str | None
    execution_shell_guardrail_code: str | None
    execution_shell_guardrail_message: str | None
    execution_shell_operator_action_required: str | None
    historical_comparison_status_used: str | None
    historical_comparison_go_no_go_used: str | None
    historical_comparison_reason_used: str | None
    matched_historical_trade_key: str | None
    matched_historical_trade_timestamp: str | None
    bundle_validation_performed: bool
    bundle_valid: bool | None
    matched_field_count: int
    mismatched_field_count: int
    partial_field_count: int
    acceptable_drift_field_count: int
    field_comparisons: tuple[S23PaperHistoricalFieldComparison, ...]
    lifecycle_comparable: bool
    lifecycle_parity_reason: str | None
    lifecycle_exact_match_count: int
    lifecycle_acceptable_drift_count: int
    lifecycle_mismatch_count: int
    lifecycle_partial_count: int
    lifecycle_field_comparisons: tuple[S23PaperHistoricalFieldComparison, ...]
    paper_provenance: dict[str, Any]
    historical_provenance: dict[str, Any]
    warnings: tuple[str, ...]
    no_execution_disclaimer: str


@dataclass(frozen=True, slots=True)
class _PaperComparisonContext:
    session_directory: Path
    bundle_directory: Path | None
    review_summary: S23PaperReviewSummary
    decision_summary: dict[str, Any]
    session_manifest: dict[str, Any]
    order_plan_payload: dict[str, Any] | None
    order_plan: dict[str, Any]
    order_intent_payload: dict[str, Any] | None
    execution_summary_payload: dict[str, Any] | None
    execution_arm_summary_payload: dict[str, Any] | None
    execution_block_summary_payload: dict[str, Any] | None
    intent_dispatch_summary_payload: dict[str, Any] | None
    execution_handoff_summary_payload: dict[str, Any] | None
    paper_fill_payload: dict[str, Any] | None
    paper_no_fill_payload: dict[str, Any] | None
    paper_fill_abort_summary_payload: dict[str, Any] | None
    paper_position_payload: dict[str, Any] | None
    paper_exit_payload: dict[str, Any] | None
    paper_pnl_summary_payload: dict[str, Any] | None
    execution_journal_rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class _FieldSpec:
    field_name: str
    severity: PaperHistoricalMismatchSeverity
    tolerance: float | None = None


@dataclass(frozen=True, slots=True)
class _LifecycleParityResult:
    comparable: bool
    reason: str | None
    field_comparisons: tuple[S23PaperHistoricalFieldComparison, ...]
    exact_match_count: int
    acceptable_drift_count: int
    mismatch_count: int
    partial_count: int
    historical_exit_reason_code: str | None
    historical_exit_timestamp: str | None
    historical_exit_outcome: str | None


_FIELD_SPECS = (
    _FieldSpec("strategy_code", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("symbol", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("option_type", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("selected_contract_symbol", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("source_branch_unique_code", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("workbook_row_number", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("source_rule", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("entry_price", PaperHistoricalMismatchSeverity.BLOCKER, tolerance=0.01),
    _FieldSpec("target_price", PaperHistoricalMismatchSeverity.BLOCKER, tolerance=0.01),
    _FieldSpec("stoploss_price", PaperHistoricalMismatchSeverity.BLOCKER, tolerance=0.01),
    _FieldSpec("fsl_price", PaperHistoricalMismatchSeverity.WARN, tolerance=0.01),
    _FieldSpec("start_strike", PaperHistoricalMismatchSeverity.WARN, tolerance=0.01),
    _FieldSpec("end_strike", PaperHistoricalMismatchSeverity.WARN, tolerance=0.01),
    _FieldSpec("ideal_premium", PaperHistoricalMismatchSeverity.WARN, tolerance=0.01),
    _FieldSpec("minimum_premium", PaperHistoricalMismatchSeverity.WARN, tolerance=0.01),
    _FieldSpec(
        "current_day_fsl_trp_overlay_enabled",
        PaperHistoricalMismatchSeverity.BLOCKER,
    ),
    _FieldSpec("recalculation_overlay_enabled", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("option_chain_selected", PaperHistoricalMismatchSeverity.BLOCKER),
    _FieldSpec("slippage_entry_points", PaperHistoricalMismatchSeverity.WARN, tolerance=0.01),
    _FieldSpec("slippage_exit_points", PaperHistoricalMismatchSeverity.WARN, tolerance=0.01),
)


def compare_paper_session_to_historical(
    session_directory: str | Path,
    historical_report_path: str | Path,
    *,
    bundle_directory: str | Path | None = None,
    historical_trade_key: str | None = None,
    session_date: str | date | None = None,
    numeric_tolerance: float = 0.01,
    reviewer: S23PaperSessionReviewer | None = None,
    comparison_limits: ComparisonLimits | None = None,
) -> S23PaperHistoricalComparisonSummary:
    context = _load_paper_context(
        session_directory=session_directory,
        bundle_directory=bundle_directory,
        reviewer=reviewer,
    )
    effective_bundle = context.bundle_directory
    review_summary = context.review_summary

    if review_summary.strategy_code != "S23":
        raise S23PaperHistoricalComparisonError(
            f"Unsupported strategy for S23 paper-vs-historical comparison: "
            f"{review_summary.strategy_code or 'unknown'}"
        )

    bundle_validation_performed = review_summary.replay_bundle.validation_performed
    bundle_valid = review_summary.replay_bundle.is_valid
    warnings: list[str] = []
    execution_shell_status = _paper_execution_shell_status(context)
    dispatch_shell_status = _paper_dispatch_shell_status(context)
    handoff_shell_status = _paper_handoff_shell_status(context)
    fill_status = _paper_fill_status(context)
    fill_reason_code = _paper_fill_reason_code(context)
    fill_message = _paper_fill_message(context)
    lifecycle_status = _paper_lifecycle_status(context)
    exit_reason_code = _paper_exit_reason_code(context)
    exit_price = _paper_exit_price(context)
    exit_timestamp = _paper_exit_timestamp(context)
    gross_pnl_rupees = _paper_gross_pnl_rupees(context)
    net_pnl_rupees = _paper_net_pnl_rupees(context)
    execution_guardrail_code = _execution_guardrail_code(context)
    execution_guardrail_message = _execution_guardrail_message(context)
    execution_operator_action = _execution_operator_action(context)
    historical_comparison_status_used = _text_or_none(
        (context.execution_summary_payload or {}).get("historical_comparison_status")
    )
    historical_comparison_go_no_go_used = _text_or_none(
        (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
    )
    historical_comparison_reason_used = _text_or_none(
        (context.execution_summary_payload or {}).get("historical_comparison_reason")
    )

    if (
        effective_bundle is not None
        and bundle_validation_performed
        and bundle_valid is False
    ):
        return _terminal_uncomparable_summary(
            context=context,
            historical_report_path=historical_report_path,
            reason=(
                "Replay bundle validation failed, so the persisted paper session "
                "cannot be trusted for historical parity checks."
            ),
            warnings=tuple(review_summary.replay_bundle.errors),
        )

    if review_summary.terminal_state is not PaperSessionState.ORDER_PLANNED:
        return _terminal_uncomparable_summary(
            context=context,
            historical_report_path=historical_report_path,
            reason=(
                "Paper session is not in ORDER_PLANNED state, so there is no "
                "paper decision intent to compare against historical output."
            ),
        )

    if context.execution_summary_payload is None:
        return _terminal_uncomparable_summary(
            context=context,
            historical_report_path=historical_report_path,
            reason=(
                "Execution summary is missing, so the paper session is not "
                "trustworthy enough for historical parity comparison."
            ),
            warnings=("missing_execution_summary",),
        )

    paper_intent_status = _paper_intent_status(context)
    if paper_intent_status != "INTENT_READY":
        return _terminal_uncomparable_summary(
            context=context,
            historical_report_path=historical_report_path,
            reason=(
                "Paper order intent is not INTENT_READY, so the planned paper "
                "decision is not comparable to historical output."
            ),
            warnings=(f"paper_intent_status={paper_intent_status or 'missing'}",),
        )

    if execution_shell_status is None:
        return _terminal_uncomparable_summary(
            context=context,
            historical_report_path=historical_report_path,
            reason=(
                "Execution-shell readiness has not been evaluated for this paper "
                "session yet."
            ),
            warnings=("missing_execution_shell_status",),
        )

    execution_artifact_issue = _execution_shell_artifact_issue(context)
    if execution_artifact_issue is not None:
        return _terminal_uncomparable_summary(
            context=context,
            historical_report_path=historical_report_path,
            reason=execution_artifact_issue,
            warnings=("incomplete_execution_shell_artifacts",),
        )

    historical_summary = load_and_summarize_backtest_report(
        label="historical",
        path=historical_report_path,
        limits=comparison_limits or ComparisonLimits(),
    )
    matched_trade, match_warning = _select_historical_trade(
        context,
        historical_summary=historical_summary,
        historical_trade_key=historical_trade_key,
        session_date=session_date,
    )
    if match_warning is not None:
        warnings.append(match_warning)
    if matched_trade is None:
        return _terminal_uncomparable_summary(
            context=context,
            historical_report_path=historical_report_path,
            reason=(
                "No unique historical trade matched the persisted paper intent "
                "for the requested session context."
            ),
            warnings=tuple(warnings),
            historical_summary=historical_summary,
        )

    historical_report_payload = _load_json_report(Path(historical_report_path))
    historical_evaluation = _select_historical_evaluation_payload(
        report_payload=historical_report_payload,
        matched_trade=matched_trade,
    )
    paper_values = _paper_values(context)
    historical_values = _historical_values(historical_summary, matched_trade)
    field_comparisons = _build_field_comparisons(
        paper_values=paper_values,
        historical_values=historical_values,
        numeric_tolerance=numeric_tolerance,
    )
    lifecycle_parity = _build_lifecycle_parity_result(
        context=context,
        matched_trade=matched_trade,
        historical_evaluation=historical_evaluation,
    )

    blocker_mismatches = [
        item
        for item in field_comparisons
        if not item.matched and item.severity is PaperHistoricalMismatchSeverity.BLOCKER
    ]
    lifecycle_blocker_mismatches = [
        item
        for item in lifecycle_parity.field_comparisons
        if not item.matched and item.severity is PaperHistoricalMismatchSeverity.BLOCKER
    ]
    partial_mismatches = [
        item
        for item in field_comparisons
        if not item.matched and item.severity is not PaperHistoricalMismatchSeverity.BLOCKER
    ]
    lifecycle_partial_mismatches = [
        item
        for item in lifecycle_parity.field_comparisons
        if (
            not item.matched
            and item.severity is not PaperHistoricalMismatchSeverity.BLOCKER
            and not item.acceptable_drift
        )
    ]

    if blocker_mismatches or lifecycle_blocker_mismatches:
        status = PaperHistoricalComparisonStatus.MISMATCH
        comparison_reason = (
            "One or more blocker-level planning or lifecycle fields diverged "
            "between the paper session and the expected historical result."
        )
        go_no_go = (
            "NO-GO: the persisted paper session does not match the expected "
            "historical trade-plan or same-day lifecycle result."
        )
    elif not lifecycle_parity.comparable:
        status = PaperHistoricalComparisonStatus.UNCOMPARABLE
        comparison_reason = lifecycle_parity.reason or (
            "Same-day lifecycle parity could not be established from the "
            "available paper or historical artifacts."
        )
        go_no_go = (
            "NO-GO: the paper session cannot be judged for same-day lifecycle "
            "parity because one side does not expose enough lifecycle detail."
        )
    else:
        status, comparison_reason, go_no_go = _classify_execution_shell_result(
            execution_shell_status=execution_shell_status,
            dispatch_shell_status=dispatch_shell_status,
            handoff_shell_status=handoff_shell_status,
            fill_status=fill_status,
            fill_reason_code=fill_reason_code,
            fill_message=fill_message,
            lifecycle_status=lifecycle_status,
            lifecycle_reason_code=exit_reason_code,
            partial_mismatches=partial_mismatches,
            lifecycle_partial_mismatches=lifecycle_partial_mismatches,
            lifecycle_has_acceptable_drift=(
                lifecycle_parity.acceptable_drift_count > 0
            ),
            execution_guardrail_code=execution_guardrail_code,
            execution_guardrail_message=execution_guardrail_message,
        )

    paper_provenance = _paper_provenance(context)
    historical_provenance = _historical_provenance(historical_summary)

    return S23PaperHistoricalComparisonSummary(
        artifact_version=_ARTIFACT_VERSION,
        status=status,
        go_no_go=go_no_go,
        comparison_reason=comparison_reason,
        session_directory=str(context.session_directory),
        bundle_directory=str(effective_bundle) if effective_bundle is not None else None,
        historical_report_path=str(Path(historical_report_path)),
        session_id=review_summary.session_id,
        session_date=review_summary.session_date,
        strategy_code=review_summary.strategy_code,
        paper_terminal_state=review_summary.terminal_state,
        paper_intent_status=paper_intent_status,
        paper_execution_shell_status=execution_shell_status,
        paper_dispatch_shell_status=dispatch_shell_status,
        paper_handoff_shell_status=handoff_shell_status,
        paper_fill_status=fill_status,
        paper_fill_price=_paper_fill_price(context),
        paper_fill_timestamp=_paper_fill_timestamp(context),
        paper_fill_reason_code=fill_reason_code,
        paper_fill_message=fill_message,
        paper_lifecycle_status=lifecycle_status,
        paper_exit_reason_code=exit_reason_code,
        paper_exit_price=exit_price,
        paper_exit_timestamp=exit_timestamp,
        paper_gross_pnl_rupees=gross_pnl_rupees,
        paper_net_pnl_rupees=net_pnl_rupees,
        historical_entry_price=matched_trade.entry_price,
        historical_exit_reason_code=lifecycle_parity.historical_exit_reason_code,
        historical_exit_price=matched_trade.exit_price,
        historical_exit_timestamp=lifecycle_parity.historical_exit_timestamp,
        historical_exit_outcome=lifecycle_parity.historical_exit_outcome,
        historical_net_pnl_rupees=matched_trade.net_pnl_rupees,
        execution_shell_reason_code=_text_or_none(
            (context.execution_summary_payload or {}).get("terminal_reason_code")
        ),
        execution_shell_guardrail_code=execution_guardrail_code,
        execution_shell_guardrail_message=execution_guardrail_message,
        execution_shell_operator_action_required=execution_operator_action,
        historical_comparison_status_used=historical_comparison_status_used,
        historical_comparison_go_no_go_used=historical_comparison_go_no_go_used,
        historical_comparison_reason_used=historical_comparison_reason_used,
        matched_historical_trade_key=matched_trade.trade_key,
        matched_historical_trade_timestamp=matched_trade.timestamp,
        bundle_validation_performed=bundle_validation_performed,
        bundle_valid=bundle_valid,
        matched_field_count=sum(1 for item in field_comparisons if item.matched),
        mismatched_field_count=len(blocker_mismatches) + len(lifecycle_blocker_mismatches),
        partial_field_count=len(partial_mismatches) + len(lifecycle_partial_mismatches),
        acceptable_drift_field_count=sum(
            1 for item in field_comparisons if item.acceptable_drift
        ) + lifecycle_parity.acceptable_drift_count,
        field_comparisons=field_comparisons,
        lifecycle_comparable=lifecycle_parity.comparable,
        lifecycle_parity_reason=lifecycle_parity.reason,
        lifecycle_exact_match_count=lifecycle_parity.exact_match_count,
        lifecycle_acceptable_drift_count=lifecycle_parity.acceptable_drift_count,
        lifecycle_mismatch_count=lifecycle_parity.mismatch_count,
        lifecycle_partial_count=lifecycle_parity.partial_count,
        lifecycle_field_comparisons=lifecycle_parity.field_comparisons,
        paper_provenance=paper_provenance,
        historical_provenance=historical_provenance,
        warnings=tuple(sorted(set(warnings))),
        no_execution_disclaimer=(
            _PHASE2_LIFECYCLE_DISCLAIMER
            if lifecycle_status is not None
            else (_PHASE1_FILL_DISCLAIMER if fill_status is not None else _NO_EXECUTION_DISCLAIMER)
        ),
    )


def compare_paper_bundle_to_historical(
    bundle_directory: str | Path,
    historical_report_path: str | Path,
    *,
    historical_trade_key: str | None = None,
    session_date: str | date | None = None,
    numeric_tolerance: float = 0.01,
    reviewer: S23PaperSessionReviewer | None = None,
    comparison_limits: ComparisonLimits | None = None,
) -> S23PaperHistoricalComparisonSummary:
    return compare_paper_session_to_historical(
        bundle_directory,
        historical_report_path,
        bundle_directory=bundle_directory,
        historical_trade_key=historical_trade_key,
        session_date=session_date,
        numeric_tolerance=numeric_tolerance,
        reviewer=reviewer,
        comparison_limits=comparison_limits,
    )


def render_paper_historical_comparison_json(
    summary: S23PaperHistoricalComparisonSummary,
) -> str:
    return json.dumps(_normalize(summary), indent=2, sort_keys=True) + "\n"


def render_paper_historical_comparison_markdown(
    summary: S23PaperHistoricalComparisonSummary,
) -> str:
    lines = [
        "# S23 Paper vs Historical Comparison",
        "",
        "## Summary",
        "",
        f"- Status: `{summary.status.value}`",
        f"- Go / No-Go: {summary.go_no_go}",
        f"- Reason: {summary.comparison_reason}",
        f"- Session ID: `{summary.session_id}`",
        f"- Session Date: `{summary.session_date.isoformat()}`",
        f"- Strategy: `{summary.strategy_code}`",
        f"- Paper Terminal State: `{summary.paper_terminal_state.value}`",
        f"- Paper Intent Status: `{summary.paper_intent_status or 'n/a'}`",
        f"- Execution Shell Status: `{summary.paper_execution_shell_status or 'n/a'}`",
        f"- Dispatch Shell Status: `{summary.paper_dispatch_shell_status or 'n/a'}`",
        f"- Handoff Shell Status: `{summary.paper_handoff_shell_status or 'n/a'}`",
        f"- Fill Status: `{summary.paper_fill_status or 'n/a'}`",
        f"- Fill Reason Code: `{summary.paper_fill_reason_code or 'n/a'}`",
        f"- Fill Price: `{summary.paper_fill_price if summary.paper_fill_price is not None else 'n/a'}`",
        f"- Fill Timestamp: `{summary.paper_fill_timestamp or 'n/a'}`",
        f"- Lifecycle Status: `{summary.paper_lifecycle_status or 'n/a'}`",
        f"- Exit Reason Code: `{summary.paper_exit_reason_code or 'n/a'}`",
        f"- Historical Trade Key: `{summary.matched_historical_trade_key or 'n/a'}`",
        f"- Historical Timestamp: `{summary.matched_historical_trade_timestamp or 'n/a'}`",
        f"- Bundle Validation Performed: `{summary.bundle_validation_performed}`",
        f"- Bundle Valid: `{summary.bundle_valid if summary.bundle_valid is not None else 'n/a'}`",
        f"- Lifecycle Comparable: `{summary.lifecycle_comparable}`",
        f"- Same-Day Policy: {_SAME_DAY_ONLY_STATEMENT}",
        "",
        "## Planning Comparison",
        "",
        "| Field | Paper | Historical | Matched | Severity | Notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in summary.field_comparisons:
        lines.append(
            "| "
            f"`{item.field_name}` | "
            f"{_markdown_value(item.paper_value)} | "
            f"{_markdown_value(item.historical_value)} | "
            f"`{item.matched}` | "
            f"`{item.severity.value}` | "
            f"{item.message} |"
        )

    lines.extend(
        [
            "",
            "## Execution-Shell Readiness",
            "",
            f"- Intent Status: `{summary.paper_intent_status or 'n/a'}`",
            f"- Execution Shell Status: `{summary.paper_execution_shell_status or 'n/a'}`",
            f"- Dispatch Shell Status: `{summary.paper_dispatch_shell_status or 'n/a'}`",
            f"- Handoff Shell Status: `{summary.paper_handoff_shell_status or 'n/a'}`",
            f"- Fill Status: `{summary.paper_fill_status or 'n/a'}`",
            f"- Fill Reason Code: `{summary.paper_fill_reason_code or 'n/a'}`",
            f"- Fill Message: {summary.paper_fill_message or 'n/a'}",
            f"- Lifecycle Status: `{summary.paper_lifecycle_status or 'n/a'}`",
            f"- Exit Reason Code: `{summary.paper_exit_reason_code or 'n/a'}`",
            f"- Exit Price: `{summary.paper_exit_price if summary.paper_exit_price is not None else 'n/a'}`",
            f"- Exit Timestamp: `{summary.paper_exit_timestamp or 'n/a'}`",
            f"- Gross P&L (Rupees): `{summary.paper_gross_pnl_rupees if summary.paper_gross_pnl_rupees is not None else 'n/a'}`",
            f"- Net P&L (Rupees): `{summary.paper_net_pnl_rupees if summary.paper_net_pnl_rupees is not None else 'n/a'}`",
            f"- Historical Exit Price: `{summary.historical_exit_price if summary.historical_exit_price is not None else 'n/a'}`",
            f"- Historical Net P&L (Rupees): `{summary.historical_net_pnl_rupees if summary.historical_net_pnl_rupees is not None else 'n/a'}`",
            f"- Execution Reason Code: `{summary.execution_shell_reason_code or 'n/a'}`",
            f"- Guardrail Code: `{summary.execution_shell_guardrail_code or 'n/a'}`",
            f"- Guardrail Message: {summary.execution_shell_guardrail_message or 'n/a'}",
            f"- Operator Action Required: {summary.execution_shell_operator_action_required or 'n/a'}",
            f"- Historical Comparison Status Used For Arming: `{summary.historical_comparison_status_used or 'n/a'}`",
            f"- Historical Comparison Go / No-Go Used For Arming: {summary.historical_comparison_go_no_go_used or 'n/a'}",
            f"- Historical Comparison Reason Used For Arming: {summary.historical_comparison_reason_used or 'n/a'}",
            "",
            "## Lifecycle Parity",
            "",
            f"- Comparable: `{summary.lifecycle_comparable}`",
            f"- Parity Reason: {summary.lifecycle_parity_reason or 'n/a'}",
            f"- Lifecycle Status: `{summary.paper_lifecycle_status or 'n/a'}`",
            f"- Exit Reason Code: `{summary.paper_exit_reason_code or 'n/a'}`",
            f"- Historical Exit Reason Code: `{summary.historical_exit_reason_code or 'n/a'}`",
            f"- Historical Exit Outcome: `{summary.historical_exit_outcome or 'n/a'}`",
            f"- Exit Price: `{summary.paper_exit_price if summary.paper_exit_price is not None else 'n/a'}`",
            f"- Historical Exit Price: `{summary.historical_exit_price if summary.historical_exit_price is not None else 'n/a'}`",
            f"- Exit Timestamp: `{summary.paper_exit_timestamp or 'n/a'}`",
            f"- Historical Exit Timestamp: `{summary.historical_exit_timestamp or 'n/a'}`",
            f"- Exact Lifecycle Matches: `{summary.lifecycle_exact_match_count}`",
            f"- Acceptable Drift Fields: `{summary.lifecycle_acceptable_drift_count}`",
            f"- Lifecycle Mismatches: `{summary.lifecycle_mismatch_count}`",
            f"- Lifecycle Partial Fields: `{summary.lifecycle_partial_count}`",
            "",
            "| Field | Paper | Historical | Matched | Acceptable Drift | Severity | Tolerance | Explanation |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if summary.lifecycle_field_comparisons:
        for item in summary.lifecycle_field_comparisons:
            lines.append(
                "| "
                f"`{item.field_name}` | "
                f"{_markdown_value(item.paper_value)} | "
                f"{_markdown_value(item.historical_value)} | "
                f"`{item.matched}` | "
                f"`{item.acceptable_drift}` | "
                f"`{item.severity.value}` | "
                f"{_markdown_value(item.tolerance)} | "
                f"{item.message} |"
            )
    else:
        lines.append("| `n/a` | n/a | n/a | `False` | `False` | `info` | n/a | No lifecycle parity fields were applicable for this session. |")

    pnl_delta = None
    if (
        summary.paper_net_pnl_rupees is not None
        and summary.historical_net_pnl_rupees is not None
    ):
        pnl_delta = summary.paper_net_pnl_rupees - summary.historical_net_pnl_rupees
    lines.extend(
        [
            "",
            "## P&L Drift",
            "",
            f"- Paper Gross P&L (Rupees): `{summary.paper_gross_pnl_rupees if summary.paper_gross_pnl_rupees is not None else 'n/a'}`",
            f"- Paper Net P&L (Rupees): `{summary.paper_net_pnl_rupees if summary.paper_net_pnl_rupees is not None else 'n/a'}`",
            f"- Historical Net P&L (Rupees): `{summary.historical_net_pnl_rupees if summary.historical_net_pnl_rupees is not None else 'n/a'}`",
            f"- Net P&L Drift (Paper - Historical): `{pnl_delta if pnl_delta is not None else 'n/a'}`",
            f"- Acceptable Drift Fields Count: `{summary.acceptable_drift_field_count}`",
            f"- Go / No-Go Interpretation: {summary.go_no_go}",
            f"- Same-Day Only Policy: {_SAME_DAY_ONLY_STATEMENT}",
            "",
            "## Provenance",
            "",
            f"- Paper Session Directory: `{summary.session_directory}`",
            f"- Replay Bundle Directory: `{summary.bundle_directory or 'n/a'}`",
            f"- Historical Report: `{summary.historical_report_path}`",
            f"- Paper Synthetic Fixture Used: `{summary.paper_provenance.get('synthetic_fixture_used')}`",
            f"- Historical Synthetic Fixture Used: `{summary.historical_provenance.get('synthetic_fixture_used')}`",
            f"- Paper Cost Version: `{summary.paper_provenance.get('cost_slippage_version') or 'n/a'}`",
            f"- Historical Cost Model: `{summary.historical_provenance.get('cost_model')}`",
            "",
            "## Warnings",
            "",
        ]
    )
    if summary.warnings:
        lines.extend(f"- {warning}" for warning in summary.warnings)
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Disclaimer",
            "",
            f"- {summary.no_execution_disclaimer}",
            "- No real broker order was placed, no real-money position was opened, and no lifecycle monitoring occurred outside the same-day paper-only simulator; this output validates planning parity, execution shell readiness, and same-day-only paper lifecycle drift policy.",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_paper_context(
    *,
    session_directory: str | Path,
    bundle_directory: str | Path | None,
    reviewer: S23PaperSessionReviewer | None,
) -> _PaperComparisonContext:
    session_dir = Path(session_directory)
    if not session_dir.exists():
        raise S23PaperHistoricalComparisonError(
            f"S23 paper session directory does not exist: {session_dir}"
        )

    effective_bundle = (
        Path(bundle_directory)
        if bundle_directory is not None
        else (session_dir if (session_dir / "replay_bundle_manifest.json").exists() else None)
    )
    active_reviewer = reviewer or S23PaperSessionReviewer()
    try:
        review_summary = active_reviewer.review_session(
            session_dir,
            bundle_directory=effective_bundle,
        )
    except S23PaperReviewError as exc:
        raise S23PaperHistoricalComparisonError(str(exc)) from exc

    decision_summary = _load_json_required(session_dir / "decision_summary.json")
    session_manifest = _load_json_required(session_dir / "session_manifest.json")
    order_plan_payload = _load_json_optional(session_dir / "paper_order_plan.json")
    order_plan = (
        order_plan_payload.get("order_plan", {})
        if isinstance(order_plan_payload, dict)
        else {}
    )
    order_plan = order_plan if isinstance(order_plan, dict) else {}
    execution_summary_payload = _load_json_optional(session_dir / "execution_summary.json")
    return _PaperComparisonContext(
        session_directory=session_dir,
        bundle_directory=effective_bundle,
        review_summary=review_summary,
        decision_summary=decision_summary,
        session_manifest=session_manifest,
        order_plan_payload=order_plan_payload,
        order_plan=order_plan,
        order_intent_payload=_load_json_optional(session_dir / "paper_order_intent.json"),
        execution_summary_payload=execution_summary_payload,
        execution_arm_summary_payload=_load_json_optional(session_dir / "execution_arm_summary.json"),
        execution_block_summary_payload=_load_json_optional(session_dir / "execution_block_summary.json"),
        intent_dispatch_summary_payload=_load_json_optional(session_dir / "intent_dispatch_summary.json"),
        execution_handoff_summary_payload=_load_json_optional(session_dir / "execution_handoff_summary.json"),
        paper_fill_payload=_load_json_optional(session_dir / "paper_fill.json"),
        paper_no_fill_payload=_load_json_optional(session_dir / "paper_no_fill.json"),
        paper_fill_abort_summary_payload=_load_json_optional(session_dir / "paper_fill_abort_summary.json"),
        paper_position_payload=_load_json_optional(session_dir / "paper_position.json"),
        paper_exit_payload=_load_json_optional(session_dir / "paper_exit.json"),
        paper_pnl_summary_payload=_load_json_optional(session_dir / "paper_pnl_summary.json"),
        execution_journal_rows=_load_jsonl_optional(session_dir / "execution_journal.jsonl"),
    )


def _load_json_required(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise S23PaperHistoricalComparisonError(
            f"Required paper artifact is missing: {path.name}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise S23PaperHistoricalComparisonError(
            f"Paper artifact '{path.name}' is not valid JSON: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})."
        ) from exc
    if not isinstance(payload, dict):
        raise S23PaperHistoricalComparisonError(
            f"Paper artifact '{path.name}' must be a JSON object."
        )
    return payload


def _load_json_optional(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _load_json_required(path)


def _load_jsonl_optional(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        return ()
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise S23PaperHistoricalComparisonError(
                f"Paper artifact '{path.name}' is not valid JSONL: {exc.msg} "
                f"(line {index})."
            ) from exc
        if not isinstance(payload, dict):
            raise S23PaperHistoricalComparisonError(
                f"Paper artifact '{path.name}' must contain JSON objects only."
            )
        rows.append(payload)
    return tuple(rows)


def _select_historical_trade(
    context: _PaperComparisonContext,
    *,
    historical_summary: Any,
    historical_trade_key: str | None,
    session_date: str | date | None,
) -> tuple[NormalizedTradeSummary | None, str | None]:
    trades = list(historical_summary.normalized_trades)
    if historical_trade_key is not None:
        for trade in trades:
            if trade.trade_key == historical_trade_key:
                return trade, None
        return None, f"historical_trade_key_not_found:{historical_trade_key}"

    expected_trade_date = (
        session_date.isoformat()
        if isinstance(session_date, date)
        else session_date or context.review_summary.session_date.isoformat()
    )
    day_candidates = [
        trade
        for trade in trades
        if trade.trade_date == expected_trade_date
        and trade.strategy_code == context.review_summary.strategy_code
        and trade.accepted
    ]
    if not day_candidates:
        return None, f"no_accepted_historical_trade_for_date:{expected_trade_date}"

    paper_branch = _text_or_none(context.order_plan.get("strategy_branch"))
    paper_option_type = _paper_option_type(context)
    paper_selected_contract = _text_or_none(
        (context.order_intent_payload or {}).get("selected_contract_symbol")
        or context.order_plan.get("selected_contract_symbol")
        or context.decision_summary.get("selected_contract_symbol")
    )
    paper_source_rule = _text_or_none(
        (context.order_intent_payload or {}).get("source_workbook_rule")
        or context.order_plan.get("source_workbook_rule")
    )
    paper_row = _int_or_none(
        (context.order_intent_payload or {}).get("workbook_row_number")
        or context.order_plan.get("workbook_row_number")
    )

    scored: list[tuple[int, NormalizedTradeSummary]] = []
    for trade in day_candidates:
        score = 0
        if paper_branch and trade.source_branch_unique_code == paper_branch:
            score += 4
        if paper_option_type and trade.option_type == paper_option_type:
            score += 3
        if paper_selected_contract and trade.selected_contract_symbol == paper_selected_contract:
            score += 2
        if paper_source_rule and trade.source_rule == paper_source_rule:
            score += 1
        if paper_row is not None and trade.workbook_row_number == paper_row:
            score += 1
        scored.append((score, trade))

    if not scored:
        return None, "no_scored_historical_candidates"

    scored.sort(key=lambda item: (-item[0], item[1].trade_key))
    top_score = scored[0][0]
    if top_score <= 0:
        return None, "historical_candidates_exist_but_no_matching_signals"

    top_candidates = [trade for score, trade in scored if score == top_score]
    if len(top_candidates) != 1:
        return None, (
            "ambiguous_historical_trade_match:"
            + ",".join(item.trade_key for item in sorted(top_candidates, key=lambda t: t.trade_key))
        )
    return top_candidates[0], None


def _paper_values(context: _PaperComparisonContext) -> dict[str, Any]:
    decision = context.decision_summary
    order_plan = context.order_plan
    order_intent = context.order_intent_payload or {}
    manifest = context.session_manifest
    overlays = {
        str(item)
        for item in decision.get("overlays_enabled", ())
        if isinstance(item, str)
    }
    return {
        "strategy_code": _text_or_none(decision.get("strategy_code")),
        "symbol": _text_or_none(decision.get("symbol")),
        "option_type": _paper_option_type(context),
        "selected_contract_symbol": _text_or_none(
            order_intent.get("selected_contract_symbol")
            or order_plan.get("selected_contract_symbol")
            or decision.get("selected_contract_symbol")
        ),
        "source_branch_unique_code": _text_or_none(
            order_intent.get("source_branch") or order_plan.get("strategy_branch")
        ),
        "workbook_row_number": _int_or_none(
            order_intent.get("workbook_row_number")
            or order_plan.get("workbook_row_number")
        ),
        "source_rule": _text_or_none(
            order_intent.get("source_workbook_rule")
            or order_plan.get("source_workbook_rule")
        ),
        "entry_price": _float_or_none(order_intent.get("planned_entry_price")),
        "target_price": _float_or_none(order_intent.get("target_price")),
        "stoploss_price": _float_or_none(order_intent.get("stoploss_price")),
        "fsl_price": _float_or_none(order_intent.get("fsl_price")),
        "start_strike": _float_or_none(order_plan.get("start_strike")),
        "end_strike": _float_or_none(order_plan.get("end_strike")),
        "ideal_premium": _float_or_none(order_plan.get("ideal_premium")),
        "minimum_premium": _float_or_none(order_plan.get("minimum_premium")),
        "current_day_fsl_trp_overlay_enabled": "S23_CURRENT_DAY_FSL_TRP" in overlays,
        "recalculation_overlay_enabled": "S23_RECALCULATION" in overlays,
        "option_chain_selected": bool(decision.get("selected_contract_available", False)),
        "slippage_entry_points": _float_or_none(manifest.get("slippage_entry_points")),
        "slippage_exit_points": _float_or_none(manifest.get("slippage_exit_points")),
    }


def _paper_intent_status(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("intent_status"))
    if explicit is not None:
        return explicit
    status = _text_or_none(execution_summary.get("status"))
    if status in {
        "PAPER_ORDER_PENDING",
        "PAPER_ORDER_FILLED",
        "PAPER_ORDER_NOT_FILLED",
        "PAPER_FILL_ABORTED",
    }:
        return None
    return status


def _paper_execution_shell_status(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("execution_shell_status"))
    if explicit is not None:
        return explicit
    status = _text_or_none(execution_summary.get("status"))
    if status in {
        "EXECUTION_ARMED",
        "EXECUTION_BLOCKED",
        "EXECUTION_ABORTED",
        "EXECUTION_SKIPPED",
    }:
        return status
    return None


def _paper_dispatch_shell_status(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("dispatch_shell_status"))
    if explicit is not None:
        return explicit
    status = _text_or_none(execution_summary.get("status"))
    if status in {
        "ORDER_INTENT_DISPATCH_READY",
        "ORDER_INTENT_DISPATCHED",
        "ORDER_INTENT_DISPATCH_BLOCKED",
        "ORDER_INTENT_CANCELLED",
        "ORDER_INTENT_DISPATCH_SKIPPED",
    }:
        return status
    return None


def _paper_handoff_shell_status(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("handoff_shell_status"))
    if explicit is not None:
        return explicit
    status = _text_or_none(execution_summary.get("status"))
    if status in {
        "PAPER_EXECUTION_HANDOFF_READY",
        "PAPER_EXECUTION_HANDOFF_BLOCKED",
        "PAPER_EXECUTION_HANDOFF_ABORTED",
        "PAPER_EXECUTION_HANDOFF_SKIPPED",
    }:
        return status
    return None


def _paper_fill_status(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("fill_status"))
    if explicit is not None:
        return explicit
    status = _text_or_none(execution_summary.get("status"))
    if status in {
        "PAPER_ORDER_PENDING",
        "PAPER_ORDER_FILLED",
        "PAPER_ORDER_NOT_FILLED",
        "PAPER_FILL_ABORTED",
    }:
        return status
    for payload in (
        context.paper_fill_payload,
        context.paper_no_fill_payload,
        context.paper_fill_abort_summary_payload,
    ):
        if payload is None:
            continue
        payload_status = _text_or_none(payload.get("status"))
        if payload_status is not None:
            return payload_status
    return None


def _paper_fill_reason_code(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("fill_reason_code"))
    if explicit is not None:
        return explicit
    for payload in (
        context.paper_fill_payload,
        context.paper_no_fill_payload,
        context.paper_fill_abort_summary_payload,
    ):
        if payload is None:
            continue
        reason = _text_or_none(payload.get("reason_code"))
        if reason is not None:
            return reason
    return None


def _paper_fill_message(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("fill_message"))
    if explicit is not None:
        return explicit
    for payload in (
        context.paper_fill_payload,
        context.paper_no_fill_payload,
        context.paper_fill_abort_summary_payload,
    ):
        if payload is None:
            continue
        message = _text_or_none(payload.get("message"))
        if message is not None:
            return message
    return None


def _paper_fill_price(context: _PaperComparisonContext) -> float | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = execution_summary.get("fill_price")
    if explicit is not None:
        return _float_or_none(explicit)
    return _float_or_none((context.paper_fill_payload or {}).get("fill_price"))


def _paper_fill_timestamp(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("fill_timestamp"))
    if explicit is not None:
        return explicit
    return _text_or_none((context.paper_fill_payload or {}).get("fill_timestamp"))


def _paper_lifecycle_status(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("lifecycle_status"))
    if explicit is not None:
        return explicit
    payload = context.paper_exit_payload or context.paper_pnl_summary_payload or context.paper_position_payload
    if payload is None:
        return None
    return _text_or_none(payload.get("status"))


def _paper_exit_reason_code(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("exit_reason_code"))
    if explicit is not None:
        return explicit
    return _text_or_none((context.paper_exit_payload or {}).get("exit_reason_code"))


def _paper_exit_price(context: _PaperComparisonContext) -> float | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = execution_summary.get("exit_price")
    if explicit is not None:
        return _float_or_none(explicit)
    payload = context.paper_exit_payload or context.paper_pnl_summary_payload or {}
    return _float_or_none(payload.get("exit_price"))


def _paper_exit_timestamp(context: _PaperComparisonContext) -> str | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = _text_or_none(execution_summary.get("exit_timestamp"))
    if explicit is not None:
        return explicit
    return _text_or_none((context.paper_exit_payload or {}).get("exit_timestamp"))


def _paper_gross_pnl_rupees(context: _PaperComparisonContext) -> float | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = execution_summary.get("gross_pnl_rupees")
    if explicit is not None:
        return _float_or_none(explicit)
    payload = context.paper_pnl_summary_payload or context.paper_exit_payload or {}
    return _float_or_none(payload.get("gross_pnl_rupees"))


def _paper_net_pnl_rupees(context: _PaperComparisonContext) -> float | None:
    execution_summary = context.execution_summary_payload or {}
    explicit = execution_summary.get("net_pnl_rupees")
    if explicit is not None:
        return _float_or_none(explicit)
    payload = context.paper_pnl_summary_payload or context.paper_exit_payload or {}
    return _float_or_none(payload.get("net_pnl_rupees"))


def _paper_quantity(context: _PaperComparisonContext) -> int:
    order_intent = context.order_intent_payload or {}
    order_plan = context.order_plan
    return _int_or_none(order_intent.get("quantity") or order_plan.get("quantity")) or 0


def _paper_target_price(context: _PaperComparisonContext) -> float | None:
    order_intent = context.order_intent_payload or {}
    return _float_or_none(order_intent.get("target_price"))


def _paper_stoploss_price(context: _PaperComparisonContext) -> float | None:
    order_intent = context.order_intent_payload or {}
    return _float_or_none(order_intent.get("stoploss_price") or order_intent.get("fsl_price"))


def _execution_guardrail_code(context: _PaperComparisonContext) -> str | None:
    payload = (
        context.execution_handoff_summary_payload
        or context.intent_dispatch_summary_payload
        or context.execution_block_summary_payload
        or context.execution_arm_summary_payload
        or context.execution_summary_payload
        or {}
    )
    return _text_or_none(payload.get("guardrail_code"))


def _execution_guardrail_message(context: _PaperComparisonContext) -> str | None:
    payload = (
        context.execution_handoff_summary_payload
        or context.intent_dispatch_summary_payload
        or context.execution_block_summary_payload
        or context.execution_arm_summary_payload
        or context.execution_summary_payload
        or {}
    )
    return _text_or_none(payload.get("guardrail_message"))


def _execution_operator_action(context: _PaperComparisonContext) -> str | None:
    payload = (
        context.execution_handoff_summary_payload
        or context.intent_dispatch_summary_payload
        or context.execution_block_summary_payload
        or context.execution_arm_summary_payload
        or context.execution_summary_payload
        or {}
    )
    return _text_or_none(payload.get("operator_action_required"))


def _execution_shell_artifact_issue(context: _PaperComparisonContext) -> str | None:
    status = _paper_execution_shell_status(context)
    dispatch_status = _paper_dispatch_shell_status(context)
    handoff_status = _paper_handoff_shell_status(context)
    if status is None:
        return None
    if not context.execution_journal_rows:
        return "Execution journal is missing, so execution-shell readiness cannot be verified."
    if status == "EXECUTION_ARMED" and context.execution_arm_summary_payload is None:
        return "Execution shell is marked armed but execution_arm_summary.json is missing."
    if status in {"EXECUTION_BLOCKED", "EXECUTION_ABORTED"} and context.execution_block_summary_payload is None:
        return "Execution shell is blocked or aborted but execution_block_summary.json is missing."
    if dispatch_status is not None and context.intent_dispatch_summary_payload is None:
        return "Dispatch shell status is recorded but intent_dispatch_summary.json is missing."
    if handoff_status is not None and dispatch_status is None:
        return "Handoff shell status is recorded but dispatch shell status is missing."
    if handoff_status is not None and context.execution_handoff_summary_payload is None:
        return "Handoff shell status is recorded but execution_handoff_summary.json is missing."
    return None


def _classify_execution_shell_result(
    *,
    execution_shell_status: str,
    dispatch_shell_status: str | None,
    handoff_shell_status: str | None,
    fill_status: str | None,
    fill_reason_code: str | None,
    fill_message: str | None,
    lifecycle_status: str | None,
    lifecycle_reason_code: str | None,
    partial_mismatches: list[S23PaperHistoricalFieldComparison],
    lifecycle_partial_mismatches: list[S23PaperHistoricalFieldComparison],
    lifecycle_has_acceptable_drift: bool,
    execution_guardrail_code: str | None,
    execution_guardrail_message: str | None,
) -> tuple[PaperHistoricalComparisonStatus, str, str]:
    if lifecycle_status in {"PAPER_POSITION_CLOSED", "PAPER_EOD_SQUARE_OFF"}:
        if partial_mismatches or lifecycle_partial_mismatches:
            return (
                PaperHistoricalComparisonStatus.PARTIAL_MATCH,
                "Core planning fields matched and the paper session reached a same-day lifecycle exit, but one or more non-blocking planning or lifecycle fields remained partial.",
                "CONDITIONAL GO: planning parity holds and the same-day paper lifecycle completed, but some non-blocking planning or lifecycle fields remain partial.",
            )
        if lifecycle_has_acceptable_drift:
            return (
                PaperHistoricalComparisonStatus.MATCH_WITH_ACCEPTABLE_DRIFT,
                "Core planning fields matched and the same-day paper lifecycle completed with only bounded acceptable drift versus the historical result.",
                "GO WITH DRIFT: the paper session is acceptable for same-day parity, but fill, exit, timestamp, or P&L drift should be monitored.",
            )
        return (
            PaperHistoricalComparisonStatus.MATCH,
            "All compared planning fields matched and the paper session reached an acceptable same-day lifecycle exit.",
            "GO: the persisted paper intent matches the expected historical trade-plan decision and the same-day paper lifecycle outcome is acceptable.",
        )

    if lifecycle_status == "PAPER_LIFECYCLE_ABORTED":
        if lifecycle_reason_code in {
            "selected_contract_mismatch_before_lifecycle",
            "duplicate_lifecycle_start",
            "invalid_replay_bundle",
            "session_artifact_hash_mismatch",
            "missing_fill_artifact_for_lifecycle",
        }:
            return (
                PaperHistoricalComparisonStatus.UNCOMPARABLE,
                "The same-day paper lifecycle aborted because session or artifact integrity failed.",
                "NO-GO: the paper lifecycle outcome is not trustworthy enough for parity comparison.",
            )
        return (
            PaperHistoricalComparisonStatus.PARTIAL_MATCH,
            "Planning fields matched, but the same-day paper lifecycle aborted for a non-strategy safety or market-data reason.",
            "CONDITIONAL GO: planning matched historical output, but the paper lifecycle could not complete under the configured safety gates.",
        )

    if fill_status == "PAPER_ORDER_PENDING":
        return (
            PaperHistoricalComparisonStatus.UNCOMPARABLE,
            "Phase 1 paper fill simulation has started but has not produced a terminal fill or no-fill outcome yet.",
            "NO-GO: the paper session is mid-fill-simulation and not ready for a terminal parity judgment.",
        )

    if fill_status == "PAPER_ORDER_FILLED":
        if partial_mismatches or lifecycle_partial_mismatches:
            return (
                PaperHistoricalComparisonStatus.PARTIAL_MATCH,
                "Core planning fields matched, the execution shell reached a filled Phase 1 paper outcome, but one or more non-blocking comparison fields were partial.",
                "CONDITIONAL GO: planning parity holds and the Phase 1 paper fill succeeded, but some non-blocking comparison fields remain partial.",
            )
        if lifecycle_has_acceptable_drift:
            return (
                PaperHistoricalComparisonStatus.MATCH_WITH_ACCEPTABLE_DRIFT,
                "Planning fields matched and the Phase 1 paper fill drift stayed within acceptable same-day tolerance versus the historical entry benchmark.",
                "GO WITH DRIFT: the paper fill is acceptable, but entry or early parity drift should be monitored.",
            )
        return (
            PaperHistoricalComparisonStatus.MATCH,
            "All compared planning fields matched and the session reached a Phase 1 paper filled outcome.",
            "GO: the persisted paper intent matches the expected historical trade-plan decision and the Phase 1 paper fill outcome is acceptable.",
        )

    if fill_status == "PAPER_ORDER_NOT_FILLED":
        return (
            PaperHistoricalComparisonStatus.PARTIAL_MATCH,
            fill_message
            or "Planning fields matched, but the Phase 1 paper fill simulator produced a no-fill outcome for a non-strategy safety or market-quality reason.",
            "CONDITIONAL GO: planning matched historical output, but the Phase 1 paper fill did not occur under the configured paper execution gates.",
        )

    if fill_status == "PAPER_FILL_ABORTED":
        if fill_reason_code in {
            "selected_contract_mismatch_before_fill",
            "execution_handoff_not_ready_for_fill",
            "duplicate_fill_attempt",
            "session_artifact_hash_mismatch",
            "invalid_replay_bundle",
        }:
            return (
                PaperHistoricalComparisonStatus.UNCOMPARABLE,
                fill_message
                or "The Phase 1 paper fill simulator aborted because artifact or session integrity failed.",
                "NO-GO: the Phase 1 paper fill outcome is not trustworthy enough for parity comparison.",
            )
        return (
            PaperHistoricalComparisonStatus.PARTIAL_MATCH,
            fill_message
            or "Planning fields matched, but the Phase 1 paper fill simulator aborted for a non-strategy safety reason.",
            "CONDITIONAL GO: planning matched historical output, but the Phase 1 paper fill simulator aborted before any lifecycle phase could begin.",
        )

    if (
        execution_shell_status == "EXECUTION_ARMED"
        and dispatch_shell_status == "ORDER_INTENT_DISPATCHED"
        and handoff_shell_status == "PAPER_EXECUTION_HANDOFF_READY"
    ):
        if partial_mismatches or lifecycle_partial_mismatches:
            return (
                PaperHistoricalComparisonStatus.PARTIAL_MATCH,
                "Core planning fields matched and the execution, dispatch, and handoff shells are acceptable, but one or more non-blocking fields were unavailable or differed.",
                "CONDITIONAL GO: the core paper decision aligns with historical output and the execution, dispatch, and handoff shells are acceptable, but some non-blocking comparison fields are partial.",
            )
        if lifecycle_has_acceptable_drift:
            return (
                PaperHistoricalComparisonStatus.MATCH_WITH_ACCEPTABLE_DRIFT,
                "Core planning fields matched and the execution shells are acceptable, with only bounded same-day drift in the paper outcome fields available so far.",
                "GO WITH DRIFT: the core paper decision aligns with historical output and only acceptable same-day drift is present.",
            )
        return (
            PaperHistoricalComparisonStatus.MATCH,
            "All compared planning fields matched and the execution, dispatch, and handoff shells are acceptable.",
            "GO: the persisted paper intent matches the expected historical trade-plan decision and the execution, dispatch, and handoff shells are acceptable.",
        )

    if execution_shell_status == "EXECUTION_ARMED" and dispatch_shell_status is None:
        return (
            PaperHistoricalComparisonStatus.UNCOMPARABLE,
            "Execution-shell arming exists, but dispatch and handoff readiness have not been evaluated yet.",
            "NO-GO: the paper session is not ready enough for a full no-fill parity comparison beyond execution arming.",
        )

    if dispatch_shell_status in {
        "ORDER_INTENT_DISPATCH_READY",
        "ORDER_INTENT_DISPATCHED",
    } and handoff_shell_status is None:
        return (
            PaperHistoricalComparisonStatus.UNCOMPARABLE,
            "Dispatch-shell readiness exists, but final handoff readiness has not been evaluated yet.",
            "NO-GO: the paper session has not crossed the final no-fill handoff boundary required for trusted later-phase parity checks.",
        )

    if (
        execution_shell_status == "EXECUTION_SKIPPED"
        or dispatch_shell_status == "ORDER_INTENT_DISPATCH_SKIPPED"
        or handoff_shell_status == "PAPER_EXECUTION_HANDOFF_SKIPPED"
    ):
        return (
            PaperHistoricalComparisonStatus.UNCOMPARABLE,
            "Execution, dispatch, or handoff shell readiness was skipped, so later-phase parity cannot be verified.",
            "NO-GO: execution, dispatch, or handoff shell readiness was not evaluated, so later-phase parity is incomplete.",
        )

    if execution_guardrail_code in {
        "invalid_replay_bundle",
        "session_artifact_hash_mismatch",
        "missing_order_intent_artifact",
        "corrupt_order_intent_artifact",
        "selected_contract_mismatch_between_order_plan_and_intent",
        "missing_historical_comparison",
        "invalid_historical_comparison_artifact",
        "historical_comparison_uncomparable",
        "execution_shell_not_armed_for_dispatch",
        "session_artifact_mismatch_before_dispatch",
        "dispatch_shell_not_ready_for_handoff",
        "session_artifact_mismatch_before_handoff",
    }:
        return (
            PaperHistoricalComparisonStatus.UNCOMPARABLE,
            execution_guardrail_message
            or "Execution, dispatch, or handoff shell readiness is not trustworthy enough for parity comparison.",
            "NO-GO: execution, dispatch, or handoff shell artifacts are incomplete or invalid for trusted replay comparison.",
        )

    if execution_guardrail_code in {
        "historical_comparison_mismatch",
        "historical_comparison_not_acceptable",
    }:
        return (
            PaperHistoricalComparisonStatus.MISMATCH,
            execution_guardrail_message
            or "Execution shell is blocked because historical parity was not acceptable.",
            "NO-GO: planning matched partially, but the execution shell is blocked for a historical-parity mismatch reason.",
        )

    return (
        PaperHistoricalComparisonStatus.PARTIAL_MATCH,
        execution_guardrail_message
        or "Planning fields matched, but execution, dispatch, or handoff shell readiness was blocked or cancelled for a non-strategy safety reason.",
        "CONDITIONAL GO: planning matched historical output, but execution, dispatch, or handoff shell readiness is blocked for a safety or operator reason.",
    )


def _historical_values(historical_summary: Any, trade: NormalizedTradeSummary) -> dict[str, Any]:
    cost_model = dict(historical_summary.cost_model)
    return {
        "strategy_code": trade.strategy_code,
        "symbol": trade.symbol,
        "option_type": trade.option_type,
        "selected_contract_symbol": trade.selected_contract_symbol,
        "source_branch_unique_code": trade.source_branch_unique_code,
        "workbook_row_number": trade.workbook_row_number,
        "source_rule": trade.source_rule,
        "entry_price": trade.entry_price,
        "target_price": trade.target_price,
        "stoploss_price": trade.stoploss_price,
        "fsl_price": None,
        "start_strike": trade.start_strike,
        "end_strike": trade.end_strike,
        "ideal_premium": trade.ideal_premium,
        "minimum_premium": trade.minimum_premium,
        "current_day_fsl_trp_overlay_enabled": historical_summary.enable_s23_current_day_fsl_trp,
        "recalculation_overlay_enabled": historical_summary.enable_s23_recalculation,
        "option_chain_selected": trade.option_chain_selected,
        "slippage_entry_points": _float_or_none(cost_model.get("slippage_points_per_side")),
        "slippage_exit_points": _float_or_none(cost_model.get("slippage_points_per_side")),
    }


def _load_json_report(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise S23PaperHistoricalComparisonError(
            f"Historical report payload must be a JSON object: {path}"
        )
    return raw


def _select_historical_evaluation_payload(
    *,
    report_payload: dict[str, Any],
    matched_trade: NormalizedTradeSummary,
) -> dict[str, Any] | None:
    evaluations = report_payload.get("evaluations")
    if not isinstance(evaluations, list):
        return None

    candidates: list[dict[str, Any]] = []
    for item in evaluations:
        if not isinstance(item, dict):
            continue
        if _text_or_none(item.get("timestamp")) != matched_trade.timestamp:
            continue
        branches = item.get("selected_branch_unique_codes")
        if (
            matched_trade.source_branch_unique_code is not None
            and isinstance(branches, list)
            and matched_trade.source_branch_unique_code not in branches
        ):
            continue
        candidates.append(item)

    if len(candidates) == 1:
        return candidates[0]
    return None


def _build_lifecycle_parity_result(
    *,
    context: _PaperComparisonContext,
    matched_trade: NormalizedTradeSummary,
    historical_evaluation: dict[str, Any] | None,
) -> _LifecycleParityResult:
    paper_fill_status = _paper_fill_status(context)
    paper_lifecycle_status = _paper_lifecycle_status(context)
    if paper_fill_status is None and paper_lifecycle_status is None:
        return _LifecycleParityResult(
            comparable=True,
            reason="No fill or lifecycle parity fields are applicable yet.",
            field_comparisons=(),
            exact_match_count=0,
            acceptable_drift_count=0,
            mismatch_count=0,
            partial_count=0,
            historical_exit_reason_code=None,
            historical_exit_timestamp=None,
            historical_exit_outcome=None,
        )

    lifecycle_payload = (
        historical_evaluation.get("lifecycle_result", {})
        if isinstance(historical_evaluation, dict)
        and isinstance(historical_evaluation.get("lifecycle_result"), dict)
        else {}
    )
    historical_exit_reason_code = _text_or_none(lifecycle_payload.get("exit_reason_code"))
    historical_exit_timestamp = _text_or_none(lifecycle_payload.get("exit_timestamp"))
    historical_exit_outcome = (
        _derive_exit_outcome(
            exit_reason_code=historical_exit_reason_code,
            outcome=_text_or_none(lifecycle_payload.get("outcome")),
            exit_price=_float_or_none(lifecycle_payload.get("exit_price")),
            target_price=matched_trade.target_price,
            stoploss_price=matched_trade.stoploss_price,
        )
    )

    paper_has_lifecycle_artifacts = (
        paper_lifecycle_status is not None
        or _paper_exit_price(context) is not None
        or _paper_net_pnl_rupees(context) is not None
        or _paper_fill_price(context) is not None
    )
    historical_has_lifecycle_artifacts = any(
        value is not None
        for value in (
            matched_trade.exit_price,
            matched_trade.net_pnl_rupees,
            historical_exit_reason_code,
            historical_exit_timestamp,
            historical_exit_outcome,
        )
    )
    if paper_has_lifecycle_artifacts and not historical_has_lifecycle_artifacts:
        return _LifecycleParityResult(
            comparable=False,
            reason=(
                "Paper lifecycle artifacts exist, but the matched historical report "
                "does not expose enough lifecycle detail for same-day parity."
            ),
            field_comparisons=(),
            exact_match_count=0,
            acceptable_drift_count=0,
            mismatch_count=0,
            partial_count=0,
            historical_exit_reason_code=historical_exit_reason_code,
            historical_exit_timestamp=historical_exit_timestamp,
            historical_exit_outcome=historical_exit_outcome,
        )

    quantity = _paper_quantity(context)
    pnl_tolerance = _derive_pnl_tolerance(quantity)
    comparisons: list[S23PaperHistoricalFieldComparison] = []
    comparisons.append(
        _build_lifecycle_field_comparison(
            field_name="fill_price_vs_historical_entry_price",
            paper_value=_paper_fill_price(context),
            historical_value=matched_trade.entry_price,
            severity=PaperHistoricalMismatchSeverity.WARN,
            tolerance=_ACCEPTABLE_FILL_PRICE_DRIFT_POINTS,
            explanation_if_missing=(
                "Historical lifecycle parity uses historical entry price as the "
                "fill benchmark because historical reports do not expose a "
                "separate simulated fill artifact."
            ),
        )
    )
    comparisons.append(
        _build_lifecycle_field_comparison(
            field_name="exit_price",
            paper_value=_paper_exit_price(context),
            historical_value=matched_trade.exit_price,
            severity=PaperHistoricalMismatchSeverity.WARN,
            tolerance=_ACCEPTABLE_EXIT_PRICE_DRIFT_POINTS,
            explanation_if_missing=(
                "One side does not expose a same-day exit price, so exit-price "
                "drift could not be evaluated."
            ),
        )
    )
    comparisons.append(
        _build_lifecycle_field_comparison(
            field_name="exit_timestamp",
            paper_value=_paper_exit_timestamp(context),
            historical_value=historical_exit_timestamp,
            severity=PaperHistoricalMismatchSeverity.WARN,
            tolerance=_ACCEPTABLE_EXIT_TIMESTAMP_DRIFT_SECONDS,
            explanation_if_missing=(
                "Historical reports do not always expose exit timestamps; when "
                "they are absent, lifecycle-time drift is only partially auditable."
            ),
        )
    )
    comparisons.append(
        _build_lifecycle_field_comparison(
            field_name="exit_reason_code",
            paper_value=_paper_exit_reason_code(context),
            historical_value=historical_exit_reason_code,
            severity=PaperHistoricalMismatchSeverity.BLOCKER,
            tolerance=None,
            explanation_if_missing=(
                "Exact exit-reason parity is enforced only when both paper and "
                "historical artifacts expose an explicit exit reason code."
            ),
        )
    )
    comparisons.append(
        _build_lifecycle_field_comparison(
            field_name="exit_outcome",
            paper_value=_derive_exit_outcome(
                exit_reason_code=_paper_exit_reason_code(context),
                outcome=None,
                exit_price=_paper_exit_price(context),
                target_price=_paper_target_price(context),
                stoploss_price=_paper_stoploss_price(context),
            ),
            historical_value=historical_exit_outcome,
            severity=PaperHistoricalMismatchSeverity.BLOCKER,
            tolerance=None,
            explanation_if_missing=(
                "Outcome parity can be checked only when the historical artifact "
                "exposes an outcome or enough price context to derive one."
            ),
        )
    )
    comparisons.append(
        _build_lifecycle_field_comparison(
            field_name="net_pnl_rupees",
            paper_value=_paper_net_pnl_rupees(context),
            historical_value=matched_trade.net_pnl_rupees,
            severity=PaperHistoricalMismatchSeverity.WARN,
            tolerance=pnl_tolerance,
            explanation_if_missing=(
                "One side is missing net P&L, so same-day lifecycle P&L drift "
                "cannot be fully verified."
            ),
        )
    )

    exact_match_count = sum(
        1 for item in comparisons if item.matched and not item.acceptable_drift
    )
    acceptable_drift_count = sum(1 for item in comparisons if item.acceptable_drift)
    mismatch_count = sum(
        1
        for item in comparisons
        if not item.matched and item.severity is PaperHistoricalMismatchSeverity.BLOCKER
    )
    partial_count = sum(
        1
        for item in comparisons
        if (
            not item.matched
            and item.severity is not PaperHistoricalMismatchSeverity.BLOCKER
            and not item.acceptable_drift
        )
    )
    return _LifecycleParityResult(
        comparable=True,
        reason=(
            "Same-day lifecycle parity uses exact contract and outcome matching, "
            "with bounded drift allowances on fill price, exit price, exit time, "
            "and net P&L."
        ),
        field_comparisons=tuple(comparisons),
        exact_match_count=exact_match_count,
        acceptable_drift_count=acceptable_drift_count,
        mismatch_count=mismatch_count,
        partial_count=partial_count,
        historical_exit_reason_code=historical_exit_reason_code,
        historical_exit_timestamp=historical_exit_timestamp,
        historical_exit_outcome=historical_exit_outcome,
    )


def _build_lifecycle_field_comparison(
    *,
    field_name: str,
    paper_value: Any,
    historical_value: Any,
    severity: PaperHistoricalMismatchSeverity,
    tolerance: float | None,
    explanation_if_missing: str,
) -> S23PaperHistoricalFieldComparison:
    if paper_value is None and historical_value is None:
        return S23PaperHistoricalFieldComparison(
            field_name=field_name,
            paper_value=paper_value,
            historical_value=historical_value,
            matched=False,
            acceptable_drift=False,
            severity=PaperHistoricalMismatchSeverity.INFO,
            tolerance=tolerance,
            message=explanation_if_missing,
        )
    if paper_value is None or historical_value is None:
        return S23PaperHistoricalFieldComparison(
            field_name=field_name,
            paper_value=paper_value,
            historical_value=historical_value,
            matched=False,
            acceptable_drift=False,
            severity=PaperHistoricalMismatchSeverity.INFO,
            tolerance=tolerance,
            message=explanation_if_missing,
        )
    if tolerance is not None:
        if field_name == "exit_timestamp":
            paper_dt = _parse_datetime_or_none(paper_value)
            historical_dt = _parse_datetime_or_none(historical_value)
            if paper_dt is not None and historical_dt is not None:
                delta = abs((paper_dt - historical_dt).total_seconds())
                if delta == 0:
                    return S23PaperHistoricalFieldComparison(
                        field_name=field_name,
                        paper_value=paper_value,
                        historical_value=historical_value,
                        matched=True,
                        acceptable_drift=False,
                        severity=severity,
                        tolerance=tolerance,
                        message="Exit timestamps matched exactly.",
                    )
                if delta <= tolerance:
                    return S23PaperHistoricalFieldComparison(
                        field_name=field_name,
                        paper_value=paper_value,
                        historical_value=historical_value,
                        matched=True,
                        acceptable_drift=True,
                        severity=severity,
                        tolerance=tolerance,
                        message=(
                            f"Exit timestamps differed by {delta:.0f} seconds, "
                            f"within acceptable same-day drift tolerance "
                            f"{tolerance:.0f}s."
                        ),
                    )
                return S23PaperHistoricalFieldComparison(
                    field_name=field_name,
                    paper_value=paper_value,
                    historical_value=historical_value,
                    matched=False,
                    acceptable_drift=False,
                    severity=severity,
                    tolerance=tolerance,
                    message=(
                        f"Exit timestamps differed by {delta:.0f} seconds, above "
                        f"acceptable same-day drift tolerance {tolerance:.0f}s."
                    ),
                )
        if isinstance(paper_value, (int, float)) and isinstance(historical_value, (int, float)):
            delta = abs(float(paper_value) - float(historical_value))
            if delta == 0:
                return S23PaperHistoricalFieldComparison(
                    field_name=field_name,
                    paper_value=paper_value,
                    historical_value=historical_value,
                    matched=True,
                    acceptable_drift=False,
                    severity=severity,
                    tolerance=tolerance,
                    message="Lifecycle values matched exactly.",
                )
            if delta <= tolerance:
                return S23PaperHistoricalFieldComparison(
                    field_name=field_name,
                    paper_value=paper_value,
                    historical_value=historical_value,
                    matched=True,
                    acceptable_drift=True,
                    severity=severity,
                    tolerance=tolerance,
                    message=(
                        f"Lifecycle drift was {delta:.4f}, within acceptable "
                        f"same-day tolerance {tolerance:.4f}."
                    ),
                )
            return S23PaperHistoricalFieldComparison(
                field_name=field_name,
                paper_value=paper_value,
                historical_value=historical_value,
                matched=False,
                acceptable_drift=False,
                severity=severity,
                tolerance=tolerance,
                message=(
                    f"Lifecycle drift was {delta:.4f}, above acceptable "
                    f"same-day tolerance {tolerance:.4f}."
                ),
            )
    matched = paper_value == historical_value
    return S23PaperHistoricalFieldComparison(
        field_name=field_name,
        paper_value=paper_value,
        historical_value=historical_value,
        matched=matched,
        acceptable_drift=False,
        severity=severity,
        tolerance=tolerance,
        message="Lifecycle values matched exactly." if matched else "Lifecycle values differed.",
    )


def _build_field_comparisons(
    *,
    paper_values: dict[str, Any],
    historical_values: dict[str, Any],
    numeric_tolerance: float,
) -> tuple[S23PaperHistoricalFieldComparison, ...]:
    results: list[S23PaperHistoricalFieldComparison] = []
    for spec in _FIELD_SPECS:
        paper_value = paper_values.get(spec.field_name)
        historical_value = historical_values.get(spec.field_name)
        tolerance = spec.tolerance if spec.tolerance is not None else None
        matched, message = _compare_values(
            field_name=spec.field_name,
            paper_value=paper_value,
            historical_value=historical_value,
            tolerance=(tolerance if tolerance is not None else numeric_tolerance),
            severity=spec.severity,
        )
        results.append(
            S23PaperHistoricalFieldComparison(
                field_name=spec.field_name,
                paper_value=paper_value,
                historical_value=historical_value,
                matched=matched,
                acceptable_drift=False,
                severity=spec.severity,
                tolerance=(tolerance if isinstance(paper_value, (int, float)) or isinstance(historical_value, (int, float)) else None),
                message=message,
            )
        )
    return tuple(results)


def _compare_values(
    *,
    field_name: str,
    paper_value: Any,
    historical_value: Any,
    tolerance: float,
    severity: PaperHistoricalMismatchSeverity,
) -> tuple[bool, str]:
    if paper_value is None and historical_value is None:
        return True, "Both paper and historical values are unavailable."
    if paper_value is None or historical_value is None:
        return (
            False,
            "One side is missing this comparison field; this is treated as partial "
            "unless a blocker severity is configured."
            if severity is not PaperHistoricalMismatchSeverity.BLOCKER
            else "One side is missing this blocker-level comparison field.",
        )
    if isinstance(paper_value, bool) or isinstance(historical_value, bool):
        return (
            paper_value == historical_value,
            "Boolean field matched."
            if paper_value == historical_value
            else "Boolean field differed.",
        )
    if isinstance(paper_value, (int, float)) and isinstance(historical_value, (int, float)):
        delta = abs(float(paper_value) - float(historical_value))
        return (
            delta <= tolerance,
            f"Numeric fields matched within tolerance {tolerance:.4f}."
            if delta <= tolerance
            else f"Numeric fields differed by {delta:.4f}, above tolerance {tolerance:.4f}.",
        )
    return (
        paper_value == historical_value,
        "Values matched."
        if paper_value == historical_value
        else "Values differed.",
    )


def _paper_option_type(context: _PaperComparisonContext) -> str | None:
    order_intent = context.order_intent_payload or {}
    order_plan = context.order_plan
    return _text_or_none(
        order_intent.get("selected_contract_option_type")
        or order_plan.get("selected_contract_option_type")
    )


def _paper_provenance(context: _PaperComparisonContext) -> dict[str, Any]:
    manifest = context.session_manifest
    data_sources = tuple(
        item for item in manifest.get("data_sources", ()) if isinstance(item, dict)
    )
    return {
        "cost_slippage_version": _text_or_none(manifest.get("cost_slippage_version")),
        "brokerage_per_lot": _float_or_none(manifest.get("brokerage_per_lot")),
        "slippage_entry_points": _float_or_none(manifest.get("slippage_entry_points")),
        "slippage_exit_points": _float_or_none(manifest.get("slippage_exit_points")),
        "spread_buffer_policy": _text_or_none(manifest.get("spread_buffer_policy")),
        "synthetic_fixture_used": bool(manifest.get("synthetic_fixture_used", False)),
        "data_source_count": len(data_sources),
        "source_types": tuple(
            sorted(
                {
                    str(item.get("source_type"))
                    for item in data_sources
                    if item.get("source_type") is not None
                }
            )
        ),
        "source_ids": tuple(
            sorted(
                {
                    str(item.get("source_id"))
                    for item in data_sources
                    if item.get("source_id") is not None
                }
            )
        ),
    }


def _historical_provenance(historical_summary: Any) -> dict[str, Any]:
    return {
        "mode": historical_summary.mode,
        "strategy_path": historical_summary.strategy_path,
        "strategy_root": historical_summary.strategy_root,
        "shared_data_root": historical_summary.shared_data_root,
        "cost_model": dict(historical_summary.cost_model),
        "synthetic_fixture_used": historical_summary.synthetic_fixture_data_used,
        "project_fixture_used": historical_summary.project_fixture_data_used,
        "input_datasets": tuple(
            {
                "name": dataset.name,
                "path": dataset.path,
                "provided": dataset.provided,
                "used": dataset.used,
                "fallback_behavior": dataset.fallback_behavior,
                "project_fixture": dataset.project_fixture,
                "synthetic_fixture": dataset.synthetic_fixture,
            }
            for dataset in historical_summary.input_datasets
        ),
    }


def _terminal_uncomparable_summary(
    *,
    context: _PaperComparisonContext,
    historical_report_path: str | Path,
    reason: str,
    warnings: tuple[str, ...] = (),
    historical_summary: Any | None = None,
) -> S23PaperHistoricalComparisonSummary:
    review_summary = context.review_summary
    return S23PaperHistoricalComparisonSummary(
        artifact_version=_ARTIFACT_VERSION,
        status=PaperHistoricalComparisonStatus.UNCOMPARABLE,
        go_no_go=(
            "NO-GO: the persisted paper session is not in a trustworthy intent-ready "
            "state for historical parity comparison."
        ),
        comparison_reason=reason,
        session_directory=str(context.session_directory),
        bundle_directory=(
            str(context.bundle_directory) if context.bundle_directory is not None else None
        ),
        historical_report_path=str(Path(historical_report_path)),
        session_id=review_summary.session_id,
        session_date=review_summary.session_date,
        strategy_code=review_summary.strategy_code,
        paper_terminal_state=review_summary.terminal_state,
        paper_intent_status=_paper_intent_status(context),
        paper_execution_shell_status=_paper_execution_shell_status(context),
        paper_dispatch_shell_status=_paper_dispatch_shell_status(context),
        paper_handoff_shell_status=_paper_handoff_shell_status(context),
        paper_fill_status=_paper_fill_status(context),
        paper_fill_price=_paper_fill_price(context),
        paper_fill_timestamp=_paper_fill_timestamp(context),
        paper_fill_reason_code=_paper_fill_reason_code(context),
        paper_fill_message=_paper_fill_message(context),
        paper_lifecycle_status=_paper_lifecycle_status(context),
        paper_exit_reason_code=_paper_exit_reason_code(context),
        paper_exit_price=_paper_exit_price(context),
        paper_exit_timestamp=_paper_exit_timestamp(context),
        paper_gross_pnl_rupees=_paper_gross_pnl_rupees(context),
        paper_net_pnl_rupees=_paper_net_pnl_rupees(context),
        historical_entry_price=None,
        historical_exit_reason_code=None,
        historical_exit_price=None,
        historical_exit_timestamp=None,
        historical_exit_outcome=None,
        historical_net_pnl_rupees=None,
        execution_shell_reason_code=_text_or_none(
            (context.execution_summary_payload or {}).get("terminal_reason_code")
        ),
        execution_shell_guardrail_code=_execution_guardrail_code(context),
        execution_shell_guardrail_message=_execution_guardrail_message(context),
        execution_shell_operator_action_required=_execution_operator_action(context),
        historical_comparison_status_used=_text_or_none(
            (context.execution_summary_payload or {}).get("historical_comparison_status")
        ),
        historical_comparison_go_no_go_used=_text_or_none(
            (context.execution_summary_payload or {}).get("historical_comparison_go_no_go")
        ),
        historical_comparison_reason_used=_text_or_none(
            (context.execution_summary_payload or {}).get("historical_comparison_reason")
        ),
        matched_historical_trade_key=None,
        matched_historical_trade_timestamp=None,
        bundle_validation_performed=review_summary.replay_bundle.validation_performed,
        bundle_valid=review_summary.replay_bundle.is_valid,
        matched_field_count=0,
        mismatched_field_count=0,
        partial_field_count=0,
        acceptable_drift_field_count=0,
        field_comparisons=(),
        lifecycle_comparable=False,
        lifecycle_parity_reason=reason,
        lifecycle_exact_match_count=0,
        lifecycle_acceptable_drift_count=0,
        lifecycle_mismatch_count=0,
        lifecycle_partial_count=0,
        lifecycle_field_comparisons=(),
        paper_provenance=_paper_provenance(context),
        historical_provenance=(
            _historical_provenance(historical_summary) if historical_summary is not None else {}
        ),
        warnings=tuple(sorted(set(warnings))),
        no_execution_disclaimer=(
            _PHASE2_LIFECYCLE_DISCLAIMER
            if _paper_lifecycle_status(context) is not None
            else (_PHASE1_FILL_DISCLAIMER if _paper_fill_status(context) is not None else _NO_EXECUTION_DISCLAIMER)
        ),
    )


def _derive_pnl_tolerance(quantity: int) -> float:
    effective_quantity = max(quantity, 1)
    return (_ACCEPTABLE_FILL_PRICE_DRIFT_POINTS + _ACCEPTABLE_EXIT_PRICE_DRIFT_POINTS) * effective_quantity


def _derive_exit_outcome(
    *,
    exit_reason_code: str | None,
    outcome: str | None,
    exit_price: float | None,
    target_price: float | None,
    stoploss_price: float | None,
) -> str | None:
    explicit = _text_or_none(outcome)
    if explicit is not None:
        return explicit
    reason = _text_or_none(exit_reason_code)
    if reason is not None:
        if reason == "target_hit":
            return "TARGET_HIT"
        if reason in {"stoploss_or_fsl_hit", "same_bar_target_stop_conflict_stoploss_wins"}:
            return "STOPLOSS_OR_FSL_HIT"
        if reason == "eod_square_off":
            return "EOD_SQUARE_OFF"
        if reason == "manual_kill_switch_forced_close":
            return "MANUAL_CLOSE"
    if exit_price is not None and target_price is not None and exit_price <= target_price:
        return "TARGET_HIT"
    if exit_price is not None and stoploss_price is not None and exit_price >= stoploss_price:
        return "STOPLOSS_OR_FSL_HIT"
    return None


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in value.items()}
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    return value


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = _text_or_none(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _markdown_value(value: Any) -> str:
    if value is None:
        return "`n/a`"
    if isinstance(value, bool):
        return f"`{value}`"
    if isinstance(value, float):
        return f"`{value:.4f}`"
    if isinstance(value, int):
        return f"`{value}`"
    return f"`{value}`"
