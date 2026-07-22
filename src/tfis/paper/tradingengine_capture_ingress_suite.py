from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tfis.domain.enums import MonthlyStatus, OptionType

from .artifacts import S23PaperSessionArtifactWriter
from .ingress_dry_run import (
    PaperIngressDryRunArtifactSet,
    PaperIngressDryRunRunner,
    PaperIngressDryRunThresholds,
)
from .models import PaperSessionState
from .tradingengine_capture_adapter import (
    TradingEngineCaptureAdapterError,
    TradingEngineCaptureAuditSummary,
    build_capture_audit,
    convert_capture_to_normalized_market_events,
    discover_context_session_dir,
    infer_option_quotes_path,
    normalize_tradingengine_option_symbol,
)

_ARTIFACT_VERSION = 1
_IST = ZoneInfo("Asia/Kolkata")
_DEFAULT_OUT_ROOT = Path("tmp/s23_tradingengine_capture_dry_runs")
_DEFAULT_DATES = (
    "2026-05-15",
    "2026-05-20",
    "2026-05-22",
    "2026-05-25",
    "2026-05-26",
    "2026-05-27",
)
_RC_TIME = time(9, 29, 59)
_COMMON_REQUIRED_ARTIFACTS = (
    "session_manifest.json",
    "audit_events.jsonl",
    "decision_summary.json",
    "execution_summary.json",
    "replay_bundle_manifest.json",
    "paper_session_review.json",
    "paper_session_review.md",
    "ingress_health_metrics.json",
    "orpt_rc_timing_audit.json",
    "selected_contract_audit.json",
    "s23_live_paper_dry_run.json",
    "s23_live_paper_dry_run.md",
)
_UNEXPECTED_POST_PLANNING_ARTIFACTS = (
    "paper_fill.json",
    "paper_no_fill.json",
    "paper_position.json",
    "lifecycle_events.jsonl",
    "paper_exit.json",
    "paper_pnl_summary.json",
)


class S23TradingEngineCaptureIngressSuiteError(RuntimeError):
    """Raised when a TradingEngine capture ingress suite cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class _PreludeTemplate:
    operator_id: str = "tradingengine-capture-suite"
    brokerage_per_lot: float = 20.0
    slippage_entry_points: float = 1.0
    slippage_exit_points: float = 1.0
    spread_buffer_policy: str = "bid_ask_guard"
    version_label: str = "capture-suite-cost-v1"
    lots: int = 1
    quantity: int = 100
    allow_current_day_fsl_trp: bool = True
    same_day_square_off_only: bool = True
    paper_mode_enabled: bool = True
    allow_recalculation: bool = False
    kill_switch_enabled: bool = False
    monthly_status: str | None = None
    strategy_branch: str | None = None
    selected_contract_symbol: str | None = None
    source_workbook_rule: str = "TRADINGENGINE_CAPTURE_VALIDATION_PRELUDE"
    workbook_row_number: int = 0


@dataclass(frozen=True, slots=True)
class S23TradingEngineCaptureDryRunResult:
    artifact_version: int
    session_date: str
    session_id: str
    conversion_status: str
    context_session_dir: str
    option_quotes_path: str
    capture_audit_path: str
    prelude_jsonl_path: str | None
    market_events_jsonl_path: str | None
    combined_events_jsonl_path: str | None
    selected_contract_symbol: str | None
    normalized_selected_contract_symbol: str | None
    selected_contract_selection_source: str | None
    terminal_state: str | None
    readiness_status: str | None
    operational_classification: str
    orpt_arrival_lag_seconds: float | None
    rc_arrival_lag_seconds: float | None
    stale_events: int | None
    late_events: int | None
    missing_chain: int | None
    missing_selected_contract: int | None
    timezone_mismatches: int | None
    unsupported_continuation: int | None
    no_trade_reasons: tuple[str, ...]
    abort_reasons: tuple[str, ...]
    fill_or_lifecycle_artifacts_present: bool
    review_md_path: str | None
    summary_json_path: str | None
    summary_md_path: str | None
    warning_messages: tuple[str, ...]
    go_no_go: str


@dataclass(frozen=True, slots=True)
class S23TradingEngineCaptureIngressSuiteSummary:
    artifact_version: int
    data_root: str
    out_root: str
    dates: tuple[str, ...]
    total_sessions: int
    pass_count: int
    warning_count: int
    no_go_count: int
    pass_rate: float
    warning_rate: float
    no_go_rate: float
    max_orpt_lag_seconds: float | None
    max_rc_lag_seconds: float | None
    total_stale_events: int
    total_late_events: int
    total_missing_chain: int
    total_missing_selected_contract: int
    total_timezone_mismatches: int
    total_unsupported_continuation: int
    selected_contract_availability_rate: float
    sessions: tuple[S23TradingEngineCaptureDryRunResult, ...]
    acceptance_thresholds: dict[str, Any]
    rollout_recommendation: str


class S23TradingEngineCaptureIngressSuiteRunner:
    def __init__(
        self,
        *,
        out_root: str | Path = _DEFAULT_OUT_ROOT,
        thresholds: PaperIngressDryRunThresholds | None = None,
    ) -> None:
        self._out_root = Path(out_root)
        self._thresholds = thresholds or PaperIngressDryRunThresholds()

    def run(
        self,
        *,
        data_root: str | Path,
        dates: tuple[str, ...] | list[str] | None = None,
        prelude_template_path: str | Path | None = None,
        audit_only: bool = False,
    ) -> S23TradingEngineCaptureIngressSuiteSummary:
        target_dates = tuple(dates or _DEFAULT_DATES)
        template = self._load_template(prelude_template_path)
        results: list[S23TradingEngineCaptureDryRunResult] = []
        for index, session_date in enumerate(target_dates):
            result = self._run_one(
                data_root=Path(data_root),
                session_date=session_date,
                template=template,
                audit_only=audit_only,
                session_index=index,
            )
            results.append(result)
        summary = self._build_summary(
            data_root=Path(data_root),
            dates=target_dates,
            results=tuple(results),
        )
        self._write_summary_files(summary)
        return summary

    def render_json(self, summary: S23TradingEngineCaptureIngressSuiteSummary) -> str:
        return json.dumps(_normalize(summary), indent=2, sort_keys=True) + "\n"

    def render_markdown(self, summary: S23TradingEngineCaptureIngressSuiteSummary) -> str:
        lines = [
            "# S23 TradingEngine Capture Ingress Dry-Run Suite",
            "",
            f"- data root: `{summary.data_root}`",
            f"- out root: `{summary.out_root}`",
            f"- total sessions: `{summary.total_sessions}`",
            f"- PASS: `{summary.pass_count}`",
            f"- WARNING: `{summary.warning_count}`",
            f"- NO_GO: `{summary.no_go_count}`",
            f"- pass rate: `{summary.pass_rate:.1%}`",
            f"- selected-contract availability rate: `{summary.selected_contract_availability_rate:.1%}`",
            f"- max ORPT lag: `{summary.max_orpt_lag_seconds if summary.max_orpt_lag_seconds is not None else 'n/a'}`",
            f"- max RC lag: `{summary.max_rc_lag_seconds if summary.max_rc_lag_seconds is not None else 'n/a'}`",
            f"- rollout recommendation: `{summary.rollout_recommendation}`",
            "",
            "## Per Session",
            "",
        ]
        for session in summary.sessions:
            lines.extend(
                [
                    f"### {session.session_date} / {session.session_id}",
                    "",
                    f"- conversion status: `{session.conversion_status}`",
                    f"- input session folder: `{session.context_session_dir}`",
                    f"- option quote file: `{session.option_quotes_path}`",
                    f"- classification: `{session.operational_classification}`",
                    f"- terminal state: `{session.terminal_state or 'n/a'}`",
                    f"- selected contract: `{session.normalized_selected_contract_symbol or 'n/a'}`",
                    f"- selected contract source: `{session.selected_contract_selection_source or 'n/a'}`",
                    f"- ORPT lag: `{session.orpt_arrival_lag_seconds if session.orpt_arrival_lag_seconds is not None else 'n/a'}`",
                    f"- RC lag: `{session.rc_arrival_lag_seconds if session.rc_arrival_lag_seconds is not None else 'n/a'}`",
                    f"- stale events: `{session.stale_events if session.stale_events is not None else 'n/a'}`",
                    f"- late events: `{session.late_events if session.late_events is not None else 'n/a'}`",
                    f"- missing chain: `{session.missing_chain if session.missing_chain is not None else 'n/a'}`",
                    f"- missing selected contract: `{session.missing_selected_contract if session.missing_selected_contract is not None else 'n/a'}`",
                    f"- timezone mismatches: `{session.timezone_mismatches if session.timezone_mismatches is not None else 'n/a'}`",
                    f"- unsupported continuation: `{session.unsupported_continuation if session.unsupported_continuation is not None else 'n/a'}`",
                    f"- no fill/lifecycle artifacts present: `{session.fill_or_lifecycle_artifacts_present}`",
                    f"- go/no-go interpretation: `{session.go_no_go}`",
                ]
            )
            if session.warning_messages:
                lines.append("- warnings:")
                lines.extend(f"  - {message}" for message in session.warning_messages)
            if session.no_trade_reasons:
                lines.append(f"- no-trade reasons: `{', '.join(session.no_trade_reasons)}`")
            if session.abort_reasons:
                lines.append(f"- abort reasons: `{', '.join(session.abort_reasons)}`")
            lines.append("")
        lines.extend(
            [
                "## Acceptance Thresholds",
                "",
                f"- minimum PASS rate: `{summary.acceptance_thresholds['minimum_pass_rate']:.0%}`",
                f"- maximum WARNING count: `{summary.acceptance_thresholds['maximum_warning_count']}`",
                f"- maximum NO_GO count: `{summary.acceptance_thresholds['maximum_no_go_count']}`",
                f"- hard blockers: `{', '.join(summary.acceptance_thresholds['hard_blockers'])}`",
                "",
            ]
        )
        return "\n".join(lines).rstrip() + "\n"

    def _run_one(
        self,
        *,
        data_root: Path,
        session_date: str,
        template: dict[str, Any],
        audit_only: bool,
        session_index: int,
    ) -> S23TradingEngineCaptureDryRunResult:
        context_session_dir = discover_context_session_dir(
            tradingdata_root=data_root,
            session_date=session_date,
        )
        option_quotes_path = infer_option_quotes_path(
            tradingdata_root=data_root,
            session_date=session_date,
        )
        audit = build_capture_audit(
            context_session_dir=context_session_dir,
            option_quotes_path=option_quotes_path,
        )
        working_dir = self._out_root / session_date / context_session_dir.name
        working_dir.mkdir(parents=True, exist_ok=True)
        capture_audit_path = working_dir / "capture_audit.json"
        capture_audit_path.write_text(
            json.dumps(_normalize(audit), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if audit_only or audit.recommendation == "not_usable":
            return S23TradingEngineCaptureDryRunResult(
                artifact_version=_ARTIFACT_VERSION,
                session_date=session_date,
                session_id=context_session_dir.name,
                conversion_status="AUDIT_ONLY" if audit_only else "NOT_USABLE",
                context_session_dir=str(context_session_dir),
                option_quotes_path=str(option_quotes_path),
                capture_audit_path=str(capture_audit_path),
                prelude_jsonl_path=None,
                market_events_jsonl_path=None,
                combined_events_jsonl_path=None,
                selected_contract_symbol=None,
                normalized_selected_contract_symbol=None,
                selected_contract_selection_source=None,
                terminal_state=None,
                readiness_status=None,
                operational_classification="NO_GO" if audit.recommendation == "not_usable" else "WARNING",
                orpt_arrival_lag_seconds=None,
                rc_arrival_lag_seconds=None,
                stale_events=None,
                late_events=None,
                missing_chain=None,
                missing_selected_contract=None,
                timezone_mismatches=None,
                unsupported_continuation=None,
                no_trade_reasons=(),
                abort_reasons=(),
                fill_or_lifecycle_artifacts_present=False,
                review_md_path=None,
                summary_json_path=None,
                summary_md_path=None,
                warning_messages=audit.warnings,
                go_no_go=(
                    "NO_GO: the capture session does not safely cover the S23 decision window."
                    if audit.recommendation == "not_usable"
                    else "WARNING: audit-only mode did not run the ingress dry run."
                ),
            )

        selection = self._choose_selected_contract(
            option_quotes_path=option_quotes_path,
            session_date=date.fromisoformat(session_date),
            preferred_option_type=OptionType.PUT if session_index % 2 == 0 else OptionType.CALL,
            template=template,
        )
        market_events_path = working_dir / "market_events.jsonl"
        converted = convert_capture_to_normalized_market_events(
            context_session_dir=context_session_dir,
            option_quotes_path=option_quotes_path,
            selected_contract_symbol=selection["raw_symbol"],
            output_jsonl_path=market_events_path,
        )
        prelude_path = working_dir / "prelude.jsonl"
        prelude_lines = self._build_validation_prelude(
            session_date=date.fromisoformat(session_date),
            selection=selection,
            template=template,
        )
        prelude_path.write_text("\n".join(prelude_lines) + "\n", encoding="utf-8")
        combined_path = working_dir / "combined_ingress.jsonl"
        combined_path.write_text(
            prelude_path.read_text(encoding="utf-8")
            + market_events_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        runner = PaperIngressDryRunRunner(
            artifact_writer=S23PaperSessionArtifactWriter(self._out_root),
            thresholds=self._thresholds,
            source_mode="tradingengine_capture_plus_tfis_prelude_jsonl",
        )
        artifact_set = runner.run_jsonl(
            combined_path,
            session_id=context_session_dir.name,
        )
        classification, warnings = self._classify_session(artifact_set)
        return S23TradingEngineCaptureDryRunResult(
            artifact_version=_ARTIFACT_VERSION,
            session_date=session_date,
            session_id=context_session_dir.name,
            conversion_status="SUCCESS",
            context_session_dir=str(context_session_dir),
            option_quotes_path=str(option_quotes_path),
            capture_audit_path=str(capture_audit_path),
            prelude_jsonl_path=str(prelude_path),
            market_events_jsonl_path=str(market_events_path),
            combined_events_jsonl_path=str(combined_path),
            selected_contract_symbol=selection["raw_symbol"],
            normalized_selected_contract_symbol=selection["normalized_symbol"],
            selected_contract_selection_source=selection["source"],
            terminal_state=artifact_set.summary.terminal_state.value,
            readiness_status=(
                artifact_set.summary.readiness_status.value
                if artifact_set.summary.readiness_status is not None
                else None
            ),
            operational_classification=classification,
            orpt_arrival_lag_seconds=self._timing_value(artifact_set, "ORPT"),
            rc_arrival_lag_seconds=self._timing_value(artifact_set, "RC"),
            stale_events=artifact_set.summary.ingress_health_metrics.stale_event_count,
            late_events=artifact_set.summary.ingress_health_metrics.late_event_count,
            missing_chain=artifact_set.summary.ingress_health_metrics.missing_option_chain_count,
            missing_selected_contract=artifact_set.summary.ingress_health_metrics.missing_selected_contract_count,
            timezone_mismatches=artifact_set.summary.ingress_health_metrics.timezone_mismatch_count,
            unsupported_continuation=artifact_set.summary.ingress_health_metrics.unsupported_continuation_count,
            no_trade_reasons=artifact_set.summary.no_trade_reasons,
            abort_reasons=artifact_set.summary.abort_reasons,
            fill_or_lifecycle_artifacts_present=self._unexpected_artifacts_present(
                artifact_set.session_directory
            ),
            review_md_path=str(artifact_set.review_md_path),
            summary_json_path=str(artifact_set.dry_run_summary_json_path),
            summary_md_path=str(artifact_set.dry_run_summary_md_path),
            warning_messages=tuple(warnings),
            go_no_go=artifact_set.summary.go_no_go,
        )

    def _classify_session(
        self,
        artifact_set: PaperIngressDryRunArtifactSet,
    ) -> tuple[str, list[str]]:
        summary = artifact_set.summary
        warnings: list[str] = []
        required_missing = [
            name
            for name in self._required_artifacts_for_terminal_state(summary.terminal_state)
            if not (artifact_set.session_directory / name).exists()
        ]
        if required_missing:
            return "NO_GO", [f"Missing required artifacts: {', '.join(required_missing)}"]
        if self._unexpected_artifacts_present(artifact_set.session_directory):
            return "NO_GO", [
                "Unexpected fill or lifecycle artifacts were created during an ingress-only run."
            ]
        if summary.terminal_state is not PaperSessionState.ORDER_PLANNED:
            return "NO_GO", ["Terminal state is not ORDER_PLANNED."]
        if summary.readiness_status is None or summary.readiness_status.value != "READY":
            return "NO_GO", ["Readiness status is not READY."]
        metrics = summary.ingress_health_metrics
        if (
            metrics.stale_event_count > 0
            or metrics.late_event_count > 0
            or metrics.missing_option_chain_count > 0
            or metrics.missing_selected_contract_count > 0
            or metrics.timezone_mismatch_count > 0
            or metrics.unsupported_continuation_count > 0
        ):
            return "NO_GO", ["Hard ingress health blockers were recorded."]
        if summary.no_trade_reasons or summary.abort_reasons:
            return "NO_GO", ["No-trade or abort reasons were recorded."]
        selected = summary.selected_contract_audit
        if not selected.selected_contract_quote_present:
            return "NO_GO", ["Selected contract quote is missing."]
        if not selected.present_in_option_chain:
            return "NO_GO", ["Selected contract is not present in the option chain."]
        if selected.quote_fresh_at_finalize is not True:
            return "NO_GO", ["Selected contract quote is not fresh at finalize."]
        lags = {
            entry.snapshot_label: entry.arrival_lag_seconds
            for entry in summary.timing_audit
            if entry.snapshot_label in {"ORPT", "RC"}
        }
        if any(lag is None for lag in lags.values()) or "ORPT" not in lags or "RC" not in lags:
            return "NO_GO", ["ORPT or RC timing entries are missing."]
        if any(lag > self._thresholds.max_timing_drift_seconds for lag in lags.values()):
            return "NO_GO", ["ORPT or RC arrival lag exceeded the configured threshold."]
        if any(lag > 2.5 for lag in lags.values()):
            warnings.append("ORPT or RC arrival lag exceeded the clean PASS threshold but stayed within tolerance.")
            return "WARNING", warnings
        return "PASS", warnings

    def _required_artifacts_for_terminal_state(
        self,
        terminal_state: PaperSessionState,
    ) -> tuple[str, ...]:
        if terminal_state is PaperSessionState.ORDER_PLANNED:
            return _COMMON_REQUIRED_ARTIFACTS + (
                "paper_order_plan.json",
                "paper_order_intent.json",
            )
        if terminal_state is PaperSessionState.NO_TRADE:
            return _COMMON_REQUIRED_ARTIFACTS + ("no_trade_summary.json",)
        if terminal_state is PaperSessionState.ABORTED:
            return _COMMON_REQUIRED_ARTIFACTS + ("abort_summary.json",)
        return _COMMON_REQUIRED_ARTIFACTS

    def _build_summary(
        self,
        *,
        data_root: Path,
        dates: tuple[str, ...],
        results: tuple[S23TradingEngineCaptureDryRunResult, ...],
    ) -> S23TradingEngineCaptureIngressSuiteSummary:
        pass_count = sum(1 for result in results if result.operational_classification == "PASS")
        warning_count = sum(
            1 for result in results if result.operational_classification == "WARNING"
        )
        no_go_count = sum(
            1 for result in results if result.operational_classification == "NO_GO"
        )
        selected_contract_ok = sum(
            1
            for result in results
            if result.selected_contract_symbol is not None
            and (
                result.operational_classification in {"PASS", "WARNING"}
                or result.missing_selected_contract == 0
            )
        )
        total_sessions = len(results)
        aggregate_ok = (
            total_sessions > 0
            and pass_count / total_sessions >= 0.8
            and warning_count <= 1
            and no_go_count == 0
        )
        if aggregate_ok and warning_count == 0:
            recommendation = "GO_FOR_CONTROLLED_PAPER"
        elif aggregate_ok:
            recommendation = "LIMITED_GO"
        else:
            recommendation = "NO_GO"
        return S23TradingEngineCaptureIngressSuiteSummary(
            artifact_version=_ARTIFACT_VERSION,
            data_root=str(data_root),
            out_root=str(self._out_root),
            dates=dates,
            total_sessions=total_sessions,
            pass_count=pass_count,
            warning_count=warning_count,
            no_go_count=no_go_count,
            pass_rate=pass_count / total_sessions if total_sessions else 0.0,
            warning_rate=warning_count / total_sessions if total_sessions else 0.0,
            no_go_rate=no_go_count / total_sessions if total_sessions else 0.0,
            max_orpt_lag_seconds=_max_defined(
                result.orpt_arrival_lag_seconds for result in results
            ),
            max_rc_lag_seconds=_max_defined(
                result.rc_arrival_lag_seconds for result in results
            ),
            total_stale_events=sum(result.stale_events or 0 for result in results),
            total_late_events=sum(result.late_events or 0 for result in results),
            total_missing_chain=sum(result.missing_chain or 0 for result in results),
            total_missing_selected_contract=sum(
                result.missing_selected_contract or 0 for result in results
            ),
            total_timezone_mismatches=sum(
                result.timezone_mismatches or 0 for result in results
            ),
            total_unsupported_continuation=sum(
                result.unsupported_continuation or 0 for result in results
            ),
            selected_contract_availability_rate=(
                selected_contract_ok / total_sessions if total_sessions else 0.0
            ),
            sessions=results,
            acceptance_thresholds={
                "minimum_pass_rate": 0.8,
                "maximum_warning_count": 1,
                "maximum_no_go_count": 0,
                "hard_blockers": [
                    "timezone_mismatch",
                    "unsupported_continuation",
                    "missing_selected_contract",
                    "stale_event",
                    "late_event",
                    "missing_option_chain",
                    "orpt_or_rc_lag_above_threshold",
                    "unexpected_fill_or_lifecycle_artifact",
                ],
            },
            rollout_recommendation=recommendation,
        )

    def _write_summary_files(
        self,
        summary: S23TradingEngineCaptureIngressSuiteSummary,
    ) -> None:
        self._out_root.mkdir(parents=True, exist_ok=True)
        (self._out_root / "summary.json").write_text(
            self.render_json(summary),
            encoding="utf-8",
        )
        (self._out_root / "summary.md").write_text(
            self.render_markdown(summary),
            encoding="utf-8",
        )

    def _timing_value(
        self,
        artifact_set: PaperIngressDryRunArtifactSet,
        label: str,
    ) -> float | None:
        for entry in artifact_set.summary.timing_audit:
            if entry.snapshot_label == label:
                return entry.arrival_lag_seconds
        return None

    def _unexpected_artifacts_present(self, session_directory: Path) -> bool:
        return any((session_directory / name).exists() for name in _UNEXPECTED_POST_PLANNING_ARTIFACTS)

    def _build_validation_prelude(
        self,
        *,
        session_date: date,
        selection: dict[str, Any],
        template: dict[str, Any],
    ) -> list[str]:
        defaults = _PreludeTemplate(**template.get("defaults", {}))
        overrides = template.get("dates", {}).get(session_date.isoformat(), {})
        defaults = _PreludeTemplate(**(asdict(defaults) | overrides))
        monthly_status, strategy_branch = self._resolve_branching(defaults, selection)
        effective_rc = datetime.combine(session_date, _RC_TIME, tzinfo=_IST)
        spread = max(0.05, (selection["ask"] or selection["ltp"]) - (selection["bid"] or selection["ltp"]))
        planned_entry = round(selection["bid"] or selection["ltp"] or selection["ask"], 2)
        target = round(max(0.05, planned_entry - max(1.0, spread * 2)), 2)
        stoploss = round((selection["ask"] or planned_entry) + max(1.0, spread * 2), 2)
        payloads = [
            {
                "event_type": "CALENDAR_CONTEXT",
                "session_date": session_date.isoformat(),
                "effective_timestamp": datetime.combine(session_date, time(9, 0), tzinfo=_IST).isoformat(),
                "captured_at": datetime.combine(session_date, time(9, 0, 1), tzinfo=_IST).isoformat(),
                "timezone": "Asia/Kolkata",
                "source_type": "tfis_validation_prelude",
                "source_id": f"validation_calendar:{session_date.isoformat()}",
                "synthetic_fixture": False,
                "normalized_by": "tradingengine-capture-suite-v1",
                "source_sequence": 1,
                "data_quality_flags": [],
                "payload": {
                    "is_holiday": False,
                    "is_expiry_day": False,
                    "weekly_expiry": selection["expiry"],
                    "market_open": "09:15:00",
                    "market_close": "15:30:00",
                },
            },
            {
                "event_type": "MONTHLY_STATUS_INPUT",
                "session_date": session_date.isoformat(),
                "effective_timestamp": datetime.combine(session_date, time(9, 0, 30), tzinfo=_IST).isoformat(),
                "captured_at": datetime.combine(session_date, time(9, 0, 31), tzinfo=_IST).isoformat(),
                "timezone": "Asia/Kolkata",
                "source_type": "tfis_validation_prelude",
                "source_id": f"validation_monthly_status:{session_date.isoformat()}",
                "synthetic_fixture": False,
                "normalized_by": "tradingengine-capture-suite-v1",
                "source_sequence": 2,
                "data_quality_flags": ["synthetic_validation_prelude"],
                "payload": {
                    "monthly_status": monthly_status.value,
                    "status_source": "capture_validation_template",
                    "reference_date": session_date.isoformat(),
                    "threshold_version": "capture-suite-v1",
                },
            },
            {
                "event_type": "PAPER_SESSION_CONFIG",
                "session_date": session_date.isoformat(),
                "effective_timestamp": datetime.combine(session_date, time(9, 0, 40), tzinfo=_IST).isoformat(),
                "captured_at": datetime.combine(session_date, time(9, 0, 41), tzinfo=_IST).isoformat(),
                "timezone": "Asia/Kolkata",
                "source_type": "tfis_validation_prelude",
                "source_id": f"validation_paper_config:{session_date.isoformat()}",
                "synthetic_fixture": False,
                "normalized_by": "tradingengine-capture-suite-v1",
                "source_sequence": 3,
                "data_quality_flags": ["synthetic_validation_prelude"],
                "payload": {
                    "strategy_code": "S23",
                    "paper_mode_enabled": defaults.paper_mode_enabled,
                    "same_day_square_off_only": defaults.same_day_square_off_only,
                    "allow_recalculation": defaults.allow_recalculation,
                    "allow_current_day_fsl_trp": defaults.allow_current_day_fsl_trp,
                    "kill_switch_enabled": defaults.kill_switch_enabled,
                    "operator_id": defaults.operator_id,
                    "symbol": "NIFTY",
                    "contract_cycle": "WEEKLY",
                    "mode": "paper",
                },
            },
            {
                "event_type": "COST_SLIPPAGE_SETTINGS",
                "session_date": session_date.isoformat(),
                "effective_timestamp": datetime.combine(session_date, time(9, 0, 50), tzinfo=_IST).isoformat(),
                "captured_at": datetime.combine(session_date, time(9, 0, 51), tzinfo=_IST).isoformat(),
                "timezone": "Asia/Kolkata",
                "source_type": "tfis_validation_prelude",
                "source_id": f"validation_costs:{session_date.isoformat()}",
                "synthetic_fixture": False,
                "normalized_by": "tradingengine-capture-suite-v1",
                "source_sequence": 4,
                "data_quality_flags": ["synthetic_validation_prelude"],
                "payload": {
                    "brokerage_per_lot": defaults.brokerage_per_lot,
                    "slippage_entry_points": defaults.slippage_entry_points,
                    "slippage_exit_points": defaults.slippage_exit_points,
                    "spread_buffer_policy": defaults.spread_buffer_policy,
                    "version_label": defaults.version_label,
                },
            },
            {
                "event_type": "TRADE_PLAN_INPUT",
                "session_date": session_date.isoformat(),
                "effective_timestamp": effective_rc.isoformat(),
                "captured_at": (effective_rc + timedelta(seconds=3)).isoformat(),
                "timezone": "Asia/Kolkata",
                "source_type": "tfis_validation_prelude",
                "source_id": f"validation_trade_plan:{session_date.isoformat()}",
                "synthetic_fixture": False,
                "normalized_by": "tradingengine-capture-suite-v1",
                "source_sequence": 5,
                "data_quality_flags": ["synthetic_validation_prelude"],
                "payload": {
                    "strategy_branch": strategy_branch,
                    "order_side": "SELL",
                    "lots": defaults.lots,
                    "quantity": defaults.quantity,
                    "planned_entry_price": planned_entry,
                    "target_price": target,
                    "stoploss_price": stoploss,
                    "order_reference_time": effective_rc.isoformat(),
                    "order_reference_label": "RC",
                    "start_strike": selection["strike"],
                    "end_strike": selection["strike"],
                    "ideal_premium": planned_entry,
                    "minimum_premium": round(max(0.05, planned_entry - max(0.5, spread)), 2),
                    "source_workbook_rule": defaults.source_workbook_rule,
                    "workbook_row_number": defaults.workbook_row_number,
                    "fsl_price": stoploss,
                },
            },
        ]
        return [json.dumps(payload, sort_keys=True) for payload in payloads]

    def _resolve_branching(
        self,
        defaults: _PreludeTemplate,
        selection: dict[str, Any],
    ) -> tuple[MonthlyStatus, str]:
        if defaults.monthly_status and defaults.strategy_branch:
            return MonthlyStatus(defaults.monthly_status), defaults.strategy_branch
        if selection["option_type"] is OptionType.PUT:
            return (
                MonthlyStatus.BEAR_CF,
                "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
            )
        return (
            MonthlyStatus.BEAR,
            "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        )

    def _choose_selected_contract(
        self,
        *,
        option_quotes_path: Path,
        session_date: date,
        preferred_option_type: OptionType,
        template: dict[str, Any],
    ) -> dict[str, Any]:
        override = template.get("dates", {}).get(session_date.isoformat(), {})
        override_symbol = override.get("selected_contract_symbol") or template.get("defaults", {}).get("selected_contract_symbol")
        latest_rows: dict[str, dict[str, Any]] = {}
        rc_time = datetime.combine(session_date, _RC_TIME, tzinfo=_IST)
        with option_quotes_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw in reader:
                symbol = (raw.get("option_symbol") or "").strip()
                timestamp_text = (raw.get("timestamp") or "").strip()
                if not symbol or not timestamp_text:
                    continue
                timestamp = datetime.fromisoformat(timestamp_text)
                if timestamp > rc_time or (rc_time - timestamp).total_seconds() > 60:
                    continue
                row = {
                    "raw_symbol": symbol,
                    "timestamp": timestamp,
                    "strike": _optional_float(raw.get("strike")),
                    "option_type": _raw_option_type(raw.get("option_type")),
                    "expiry": _decode_expiry_value(raw.get("expiry")),
                    "ltp": _optional_float(raw.get("ltp")),
                    "bid": _optional_float(raw.get("bid")),
                    "ask": _optional_float(raw.get("ask")),
                    "volume": _optional_float(raw.get("volume")),
                    "oi": _optional_float(raw.get("oi")),
                }
                current = latest_rows.get(symbol)
                if current is None or timestamp > current["timestamp"]:
                    latest_rows[symbol] = row
        if not latest_rows:
            raise S23TradingEngineCaptureIngressSuiteError(
                f"No RC-adjacent option quotes were found in {option_quotes_path}."
            )
        if override_symbol:
            chosen = latest_rows.get(str(override_symbol))
            if chosen is None:
                raise S23TradingEngineCaptureIngressSuiteError(
                    f"Configured selected contract override {override_symbol} was not found near RC."
                )
            source = "template_override"
        else:
            candidates = [
                row
                for row in latest_rows.values()
                if row["bid"] is not None
                and row["ask"] is not None
                and row["ltp"] is not None
                and row["option_type"] is preferred_option_type
            ]
            if not candidates:
                candidates = [
                    row
                    for row in latest_rows.values()
                    if row["bid"] is not None and row["ask"] is not None and row["ltp"] is not None
                ]
            if not candidates:
                raise S23TradingEngineCaptureIngressSuiteError(
                    f"No tradable RC-adjacent option quotes were found in {option_quotes_path}."
                )
            chosen = min(
                candidates,
                key=lambda row: (
                    (row["ask"] - row["bid"]) if row["ask"] is not None and row["bid"] is not None else float("inf"),
                    -(row["volume"] or 0.0),
                    row["strike"] if row["strike"] is not None else float("inf"),
                ),
            )
            source = "auto_min_spread"
        chosen["normalized_symbol"] = normalize_tradingengine_option_symbol(
            chosen["raw_symbol"],
            expiry=chosen["expiry"],
            strike=chosen["strike"],
            option_type=chosen["option_type"],
        )
        chosen["source"] = source
        return chosen

    def _load_template(self, path: str | Path | None) -> dict[str, Any]:
        if path is None:
            return {"defaults": {}, "dates": {}}
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise S23TradingEngineCaptureIngressSuiteError(
                f"Prelude template must be a JSON object: {path}"
            )
        return payload


def _normalize(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _normalize(val) for key, val in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, OptionType):
        return value.value
    if isinstance(value, MonthlyStatus):
        return value.value
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return float(text)


def _raw_option_type(value: Any) -> OptionType | None:
    text = str(value or "").strip().upper()
    if text == "CE":
        return OptionType.CALL
    if text == "PE":
        return OptionType.PUT
    return None


def _decode_expiry_value(value: Any) -> str | None:
    from .tradingengine_capture_adapter import _decode_expiry_code as _internal_decode_expiry_code  # type: ignore[attr-defined]

    parsed = _internal_decode_expiry_code(str(value) if value is not None else None)
    return parsed.isoformat() if parsed is not None else None


def _max_defined(values: Any) -> float | None:
    resolved = [value for value in values if value is not None]
    return max(resolved) if resolved else None
