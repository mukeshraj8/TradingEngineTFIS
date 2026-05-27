from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tfis.domain.enums import MonthlyStatus, OptionType

from .artifacts import S23PaperArtifactSet, S23PaperSessionArtifactWriter
from .execution_journal import (
    S23PaperExecutionJournalArtifactSet,
    S23PaperExecutionJournalWriter,
)
from .models import (
    CalendarContextEvent,
    CostSlippageSettingsEvent,
    EventEnvelope,
    MonthlyStatusInputEvent,
    OptionChainContract,
    OptionChainSnapshotEvent,
    PaperEventType,
    PaperReadinessStatus,
    PaperSessionConfigEvent,
    PaperSessionState,
    PaperTradePlanEvent,
    SelectedContractQuoteEvent,
    SnapshotLabel,
    UnderlyingQuoteEvent,
    UnderlyingSnapshotEvent,
)
from .orchestrator import S23PaperSessionOrchestrator, S23PaperSessionSnapshot
from .replay_bundle import S23PaperReplayBundleManager
from .review import S23PaperSessionReviewer
from .validation import DEFAULT_MAX_QUOTE_AGE, PaperEvent, S23PaperContractValidator


_ARTIFACT_VERSION = 1
_DEFAULT_ARTIFACT_ROOT = Path("tmp/s23_live_paper_dry_runs")
_DEFAULT_EVENT_LAG_THRESHOLD = timedelta(seconds=5)
_IST = ZoneInfo("Asia/Kolkata")
_EXPECTED_SNAPSHOT_TIMES = {
    SnapshotLabel.AT_0915: time(9, 15),
    SnapshotLabel.ORPT: time(9, 24, 59),
    SnapshotLabel.RC: time(9, 29, 59),
}


class S23PaperIngressDryRunError(RuntimeError):
    """Raised when a normalized S23 paper ingress dry run cannot be produced safely."""


class S23PaperIngressReadiness(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class S23PaperIngressDryRunThresholds:
    max_stale_events: int = 0
    max_timing_drift_seconds: float = 5.0
    max_missing_chains: int = 0
    required_selected_contract_availability_ratio: float = 1.0
    max_no_trade_rate: float = 0.0


@dataclass(frozen=True, slots=True)
class S23PaperSnapshotTimingAudit:
    snapshot_label: str
    expected_timestamp: datetime
    effective_timestamp: datetime
    captured_at: datetime
    effective_drift_seconds: float
    arrival_lag_seconds: float
    within_drift_threshold: bool


@dataclass(frozen=True, slots=True)
class S23PaperIngressHealthMetrics:
    total_events: int
    processed_events: int
    stale_event_count: int
    late_event_count: int
    missing_option_chain_count: int
    missing_selected_contract_count: int
    timezone_mismatch_count: int
    unsupported_continuation_count: int
    selected_contract_availability_ratio: float
    no_trade_rate: float
    max_quote_age_seconds_at_finalize: float | None
    max_snapshot_arrival_lag_seconds: float | None


@dataclass(frozen=True, slots=True)
class S23PaperSelectedContractAudit:
    symbol: str | None
    option_type: str | None
    strike: float | None
    expiry: date | None
    selected_contract_quote_present: bool
    present_in_option_chain: bool
    quote_fresh_at_finalize: bool | None
    quote_effective_timestamp: datetime | None
    quote_captured_at: datetime | None
    quote_age_seconds_at_finalize: float | None
    option_chain_source_id: str | None
    selected_contract_source_id: str | None


@dataclass(frozen=True, slots=True)
class S23PaperIngressDryRunSummary:
    artifact_version: int
    source_mode: str
    source_path: str
    session_directory: str
    session_id: str
    session_date: date
    terminal_state: PaperSessionState
    readiness_status: PaperReadinessStatus | None
    operational_readiness: S23PaperIngressReadiness
    go_no_go: str
    selected_contract_audit: S23PaperSelectedContractAudit
    ingress_health_metrics: S23PaperIngressHealthMetrics
    timing_audit: tuple[S23PaperSnapshotTimingAudit, ...]
    no_trade_reasons: tuple[str, ...]
    abort_reasons: tuple[str, ...]
    warning_flags: tuple[str, ...]
    replay_bundle_created: bool
    review_json_path: str
    review_md_path: str
    execution_summary_path: str
    thresholds: S23PaperIngressDryRunThresholds
    explicit_disclaimer: str


@dataclass(frozen=True, slots=True)
class S23PaperIngressDryRunArtifactSet:
    session_directory: Path
    session_artifacts: S23PaperArtifactSet
    execution_artifacts: S23PaperExecutionJournalArtifactSet
    replay_bundle_manifest_path: Path
    review_json_path: Path
    review_md_path: Path
    ingress_health_metrics_path: Path
    timing_audit_path: Path
    selected_contract_audit_path: Path
    dry_run_summary_json_path: Path
    dry_run_summary_md_path: Path
    summary: S23PaperIngressDryRunSummary


class S23NormalizedPaperEventLoader:
    def load_jsonl(self, path: str | Path) -> tuple[PaperEvent, ...]:
        target = Path(path)
        if not target.exists():
            raise S23PaperIngressDryRunError(
                f"Normalized paper ingress source does not exist: {target}"
            )
        events: list[PaperEvent] = []
        with target.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise S23PaperIngressDryRunError(
                        f"Malformed normalized ingress JSONL at line {line_number}: {exc}"
                    ) from exc
                try:
                    events.append(self._parse_event(payload))
                except Exception as exc:  # pragma: no cover - defensive path
                    raise S23PaperIngressDryRunError(
                        f"Invalid normalized ingress event at line {line_number}: {exc}"
                    ) from exc
        if not events:
            raise S23PaperIngressDryRunError(
                f"Normalized paper ingress source is empty: {target}"
            )
        return tuple(events)

    def _parse_event(self, payload: dict[str, Any]) -> PaperEvent:
        event_type = PaperEventType(str(payload["event_type"]))
        envelope = EventEnvelope(
            event_type=event_type,
            session_date=self._parse_date(payload["session_date"]),
            effective_timestamp=self._parse_datetime(payload["effective_timestamp"]),
            captured_at=self._parse_datetime(payload["captured_at"]),
            timezone=str(payload["timezone"]),
            source_type=str(payload["source_type"]),
            source_id=str(payload["source_id"]),
            synthetic_fixture=bool(payload["synthetic_fixture"]),
            normalized_by=str(payload["normalized_by"]),
            source_sequence=self._optional_int(payload.get("source_sequence")),
            data_quality_flags=tuple(str(flag) for flag in payload.get("data_quality_flags", ())),
            integrity_hash=self._optional_text(payload.get("integrity_hash")),
        )
        body = payload.get("payload", {})
        if not isinstance(body, dict):
            raise ValueError("payload must be an object")

        if event_type is PaperEventType.CALENDAR_CONTEXT:
            return CalendarContextEvent(
                envelope=envelope,
                is_holiday=bool(body["is_holiday"]),
                is_expiry_day=bool(body["is_expiry_day"]),
                weekly_expiry=self._optional_date(body.get("weekly_expiry")),
                market_open=self._optional_time(body.get("market_open")),
                market_close=self._optional_time(body.get("market_close")),
            )
        if event_type is PaperEventType.MONTHLY_STATUS_INPUT:
            return MonthlyStatusInputEvent(
                envelope=envelope,
                monthly_status=(
                    MonthlyStatus(str(body["monthly_status"]))
                    if body.get("monthly_status") is not None
                    else None
                ),
                status_source=str(body["status_source"]),
                reference_date=self._optional_date(body.get("reference_date")),
                threshold_version=str(body["threshold_version"]),
            )
        if event_type is PaperEventType.PAPER_SESSION_CONFIG:
            return PaperSessionConfigEvent(
                envelope=envelope,
                strategy_code=str(body["strategy_code"]),
                paper_mode_enabled=bool(body["paper_mode_enabled"]),
                same_day_square_off_only=bool(body["same_day_square_off_only"]),
                allow_recalculation=bool(body["allow_recalculation"]),
                allow_current_day_fsl_trp=bool(body["allow_current_day_fsl_trp"]),
                kill_switch_enabled=bool(body["kill_switch_enabled"]),
                operator_id=str(body["operator_id"]),
                symbol=str(body.get("symbol", "NIFTY")),
                contract_cycle=str(body.get("contract_cycle", "WEEKLY")),
                mode=str(body.get("mode", "paper")),
            )
        if event_type is PaperEventType.COST_SLIPPAGE_SETTINGS:
            return CostSlippageSettingsEvent(
                envelope=envelope,
                brokerage_per_lot=self._optional_float(body.get("brokerage_per_lot")),
                slippage_entry_points=self._optional_float(body.get("slippage_entry_points")),
                slippage_exit_points=self._optional_float(body.get("slippage_exit_points")),
                spread_buffer_policy=str(body["spread_buffer_policy"]),
                version_label=str(body["version_label"]),
            )
        if event_type is PaperEventType.UNDERLYING_SNAPSHOT:
            return UnderlyingSnapshotEvent(
                envelope=envelope,
                snapshot_label=SnapshotLabel(str(body["snapshot_label"])),
                high=self._optional_float(body.get("high")),
                low=self._optional_float(body.get("low")),
                bar_start=self._parse_datetime(body["bar_start"]),
                bar_end=self._parse_datetime(body["bar_end"]),
                complete=bool(body["complete"]),
                open=self._optional_float(body.get("open")),
                close=self._optional_float(body.get("close")),
            )
        if event_type is PaperEventType.UNDERLYING_QUOTE:
            return UnderlyingQuoteEvent(
                envelope=envelope,
                symbol=str(body["symbol"]),
                ltp=self._optional_float(body.get("ltp")),
                bid=self._optional_float(body.get("bid")),
                ask=self._optional_float(body.get("ask")),
                volume=self._optional_float(body.get("volume")),
                source_latency_ms=self._optional_int(body.get("source_latency_ms")),
            )
        if event_type is PaperEventType.OPTION_CHAIN_SNAPSHOT:
            contracts = tuple(
                OptionChainContract(
                    symbol=str(contract["symbol"]),
                    option_type=(
                        OptionType(str(contract["option_type"]))
                        if contract.get("option_type") is not None
                        else None
                    ),
                    strike=self._optional_float(contract.get("strike")),
                    expiry=self._optional_date(contract.get("expiry")),
                    bid=self._optional_float(contract.get("bid")),
                    ask=self._optional_float(contract.get("ask")),
                    ltp=self._optional_float(contract.get("ltp")),
                    oi=self._optional_float(contract.get("oi")),
                    volume=self._optional_float(contract.get("volume")),
                )
                for contract in body.get("contracts", ())
            )
            return OptionChainSnapshotEvent(
                envelope=envelope,
                underlying_symbol=str(body["underlying_symbol"]),
                expiry=self._parse_date(body["expiry"]),
                contracts=contracts,
            )
        if event_type is PaperEventType.SELECTED_CONTRACT_QUOTE:
            return SelectedContractQuoteEvent(
                envelope=envelope,
                symbol=str(body["symbol"]),
                option_type=(
                    OptionType(str(body["option_type"]))
                    if body.get("option_type") is not None
                    else None
                ),
                strike=self._optional_float(body.get("strike")),
                expiry=self._optional_date(body.get("expiry")),
                bid=self._optional_float(body.get("bid")),
                ask=self._optional_float(body.get("ask")),
                ltp=self._optional_float(body.get("ltp")),
                oi=self._optional_float(body.get("oi")),
                volume=self._optional_float(body.get("volume")),
            )
        if event_type is PaperEventType.SELECTED_CONTRACT_BAR:
            raise S23PaperIngressDryRunError(
                "The first ingress-only dry run accepts planning-phase normalized events only."
            )
        if event_type is PaperEventType.TRADE_PLAN_INPUT:
            return PaperTradePlanEvent(
                envelope=envelope,
                strategy_branch=str(body["strategy_branch"]),
                order_side=str(body["order_side"]),
                lots=self._optional_int(body.get("lots")),
                quantity=self._optional_int(body.get("quantity")),
                planned_entry_price=self._optional_float(body.get("planned_entry_price")),
                target_price=self._optional_float(body.get("target_price")),
                stoploss_price=self._optional_float(body.get("stoploss_price")),
                order_reference_time=self._optional_datetime(body.get("order_reference_time")),
                order_reference_label=str(body["order_reference_label"]),
                start_strike=self._optional_float(body.get("start_strike")),
                end_strike=self._optional_float(body.get("end_strike")),
                ideal_premium=self._optional_float(body.get("ideal_premium")),
                minimum_premium=self._optional_float(body.get("minimum_premium")),
                source_workbook_rule=self._optional_text(body.get("source_workbook_rule")),
                workbook_row_number=self._optional_int(body.get("workbook_row_number")),
                fsl_price=self._optional_float(body.get("fsl_price")),
            )
        raise S23PaperIngressDryRunError(
            f"Unsupported normalized ingress event type: {event_type.value}"
        )

    def _parse_datetime(self, value: Any) -> datetime:
        return datetime.fromisoformat(str(value))

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        return self._parse_datetime(value)

    def _parse_date(self, value: Any) -> date:
        return date.fromisoformat(str(value))

    def _optional_date(self, value: Any) -> date | None:
        if value in (None, ""):
            return None
        return self._parse_date(value)

    def _optional_time(self, value: Any) -> time | None:
        if value in (None, ""):
            return None
        return time.fromisoformat(str(value))

    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    def _optional_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _optional_text(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)


class S23PaperIngressDryRunRunner:
    def __init__(
        self,
        *,
        validator: S23PaperContractValidator | None = None,
        orchestrator_factory: type[S23PaperSessionOrchestrator] = S23PaperSessionOrchestrator,
        artifact_writer: S23PaperSessionArtifactWriter | None = None,
        replay_bundle_manager: S23PaperReplayBundleManager | None = None,
        execution_journal_writer: S23PaperExecutionJournalWriter | None = None,
        reviewer: S23PaperSessionReviewer | None = None,
        thresholds: S23PaperIngressDryRunThresholds | None = None,
        max_quote_age: timedelta = DEFAULT_MAX_QUOTE_AGE,
        late_event_threshold: timedelta = _DEFAULT_EVENT_LAG_THRESHOLD,
        source_mode: str = "normalized_archive_export_jsonl",
    ) -> None:
        self._validator = validator or S23PaperContractValidator()
        self._orchestrator_factory = orchestrator_factory
        self._artifact_writer = artifact_writer or S23PaperSessionArtifactWriter(
            _DEFAULT_ARTIFACT_ROOT
        )
        self._replay_bundle_manager = replay_bundle_manager or S23PaperReplayBundleManager()
        self._execution_journal_writer = (
            execution_journal_writer or S23PaperExecutionJournalWriter()
        )
        self._reviewer = reviewer or S23PaperSessionReviewer()
        self._thresholds = thresholds or S23PaperIngressDryRunThresholds()
        self._max_quote_age = max_quote_age
        self._late_event_threshold = late_event_threshold
        self._source_mode = source_mode

    def run_jsonl(
        self,
        events_path: str | Path,
        *,
        session_id: str | None = None,
        review_json_name: str = "paper_session_review.json",
        review_md_name: str = "paper_session_review.md",
        summary_json_name: str = "s23_live_paper_dry_run.json",
        summary_md_name: str = "s23_live_paper_dry_run.md",
        finalize_at: datetime | None = None,
    ) -> S23PaperIngressDryRunArtifactSet:
        loader = S23NormalizedPaperEventLoader()
        events = loader.load_jsonl(events_path)
        return self.run_events(
            events,
            source_path=events_path,
            session_id=session_id,
            review_json_name=review_json_name,
            review_md_name=review_md_name,
            summary_json_name=summary_json_name,
            summary_md_name=summary_md_name,
            finalize_at=finalize_at,
        )

    def run_events(
        self,
        events: tuple[PaperEvent, ...],
        *,
        source_path: str | Path,
        session_id: str | None = None,
        review_json_name: str = "paper_session_review.json",
        review_md_name: str = "paper_session_review.md",
        summary_json_name: str = "s23_live_paper_dry_run.json",
        summary_md_name: str = "s23_live_paper_dry_run.md",
        finalize_at: datetime | None = None,
    ) -> S23PaperIngressDryRunArtifactSet:
        orchestrator = self._orchestrator_factory(max_quote_age=self._max_quote_age)
        event_validation_issues: list[str] = []
        timing_entries: list[S23PaperSnapshotTimingAudit] = []
        late_event_count = 0
        stale_event_count = 0
        timezone_mismatch_count = 0
        selected_contract_quote: SelectedContractQuoteEvent | None = None
        option_chain_snapshot: OptionChainSnapshotEvent | None = None

        snapshot: S23PaperSessionSnapshot | None = None
        processed_events = 0
        for event in events:
            event_validation = self._validator.validate_event(
                event,
                now=event.envelope.captured_at,
            )
            for issue in event_validation.issues:
                event_validation_issues.append(issue.code)
                if issue.code.startswith("unsupported_timezone") or issue.code.startswith(
                    "naive_"
                ):
                    timezone_mismatch_count += 1
            if isinstance(event, (UnderlyingQuoteEvent, SelectedContractQuoteEvent)):
                age_seconds = (
                    event.envelope.captured_at - event.envelope.effective_timestamp
                ).total_seconds()
                if age_seconds > self._max_quote_age.total_seconds():
                    stale_event_count += 1
            arrival_lag = event.envelope.captured_at - event.envelope.effective_timestamp
            if arrival_lag > self._late_event_threshold:
                late_event_count += 1

            if isinstance(event, UnderlyingSnapshotEvent):
                expected_timestamp = self._expected_snapshot_timestamp(
                    event.envelope.session_date,
                    event.snapshot_label,
                )
                timing_entries.append(
                    S23PaperSnapshotTimingAudit(
                        snapshot_label=event.snapshot_label.value,
                        expected_timestamp=expected_timestamp,
                        effective_timestamp=event.envelope.effective_timestamp,
                        captured_at=event.envelope.captured_at,
                        effective_drift_seconds=(
                            event.envelope.effective_timestamp - expected_timestamp
                        ).total_seconds(),
                        arrival_lag_seconds=arrival_lag.total_seconds(),
                        within_drift_threshold=(
                            abs(
                                (
                                    event.envelope.effective_timestamp - expected_timestamp
                                ).total_seconds()
                            )
                            <= self._thresholds.max_timing_drift_seconds
                            and arrival_lag.total_seconds()
                            <= self._thresholds.max_timing_drift_seconds
                        ),
                    )
                )

            if isinstance(event, SelectedContractQuoteEvent):
                selected_contract_quote = event
            elif isinstance(event, OptionChainSnapshotEvent):
                option_chain_snapshot = event

            snapshot = orchestrator.ingest_event(event, now=event.envelope.captured_at)
            processed_events += 1
            if snapshot.state in {
                PaperSessionState.ORDER_PLANNED,
                PaperSessionState.NO_TRADE,
                PaperSessionState.ABORTED,
            }:
                break

        if snapshot is None:
            raise S23PaperIngressDryRunError(
                "The normalized ingress dry run did not ingest any paper events."
            )

        resolved_completion_time = finalize_at or (
            events[-1].envelope.captured_at + timedelta(seconds=1)
        )
        if snapshot.state not in {
            PaperSessionState.ORDER_PLANNED,
            PaperSessionState.NO_TRADE,
            PaperSessionState.ABORTED,
        }:
            snapshot = orchestrator.finalize(now=resolved_completion_time)

        artifact_set = (
            self._artifact_writer.write_snapshot(snapshot, session_id=session_id)
            if snapshot.manifest is not None
            else self._write_pre_manifest_terminal_artifacts(
                snapshot=snapshot,
                events=events,
                session_id=session_id,
            )
        )
        bundle_manifest_path = self._replay_bundle_manager.create_bundle(
            artifact_set.session_directory,
            created_at=resolved_completion_time,
            source_artifact_root=artifact_set.session_directory.parents[1],
        )
        execution_artifacts = self._execution_journal_writer.write_from_session(
            artifact_set.session_directory,
            bundle_directory=artifact_set.session_directory,
            created_at=resolved_completion_time + timedelta(seconds=1),
        )
        review_summary = self._reviewer.review_session(
            artifact_set.session_directory,
            bundle_directory=artifact_set.session_directory,
        )
        review_json_path = artifact_set.session_directory / review_json_name
        review_md_path = artifact_set.session_directory / review_md_name
        self._reviewer.write_review_outputs(
            review_summary,
            out_json=review_json_path,
            out_md=review_md_path,
        )

        final_validation = snapshot.latest_validation_result
        no_trade_reasons = (
            final_validation.no_trade_reasons if final_validation is not None else ()
        )
        abort_reasons = (
            final_validation.abort_reasons if final_validation is not None else ()
        )
        stale_event_count += sum(
            1
            for code in (*no_trade_reasons, *abort_reasons)
            if code.startswith("stale_")
        )
        missing_option_chain_count = sum(
            1 for code in (*no_trade_reasons, *abort_reasons) if code == "missing_option_chain_snapshot"
        )
        missing_selected_contract_count = sum(
            1
            for code in (*no_trade_reasons, *abort_reasons)
            if code == "missing_selected_contract_quote"
        )
        unsupported_continuation_count = sum(
            1
            for code in (*no_trade_reasons, *abort_reasons)
            if code == "unsupported_continuation_path"
        )

        selected_contract_audit = self._build_selected_contract_audit(
            quote_event=selected_contract_quote,
            option_chain_snapshot=option_chain_snapshot,
            final_validation=final_validation,
            finalize_at=resolved_completion_time,
        )
        metrics = self._build_ingress_metrics(
            total_events=len(events),
            processed_events=processed_events,
            stale_event_count=stale_event_count,
            late_event_count=late_event_count,
            missing_option_chain_count=missing_option_chain_count,
            missing_selected_contract_count=missing_selected_contract_count,
            timezone_mismatch_count=timezone_mismatch_count,
            unsupported_continuation_count=unsupported_continuation_count,
            selected_contract_audit=selected_contract_audit,
            no_trade_reasons=no_trade_reasons,
            timing_entries=tuple(timing_entries),
        )

        operational_readiness = self._evaluate_operational_readiness(
            snapshot_state=snapshot.state,
            metrics=metrics,
            timing_entries=tuple(timing_entries),
        )
        summary = S23PaperIngressDryRunSummary(
            artifact_version=_ARTIFACT_VERSION,
            source_mode=self._source_mode,
            source_path=str(Path(source_path)),
            session_directory=str(artifact_set.session_directory),
            session_id=artifact_set.session_id,
            session_date=snapshot.manifest.session_date if snapshot.manifest is not None else events[0].envelope.session_date,
            terminal_state=snapshot.state,
            readiness_status=(
                snapshot.manifest.readiness_status if snapshot.manifest is not None else None
            ),
            operational_readiness=operational_readiness,
            go_no_go=self._build_go_no_go_message(
                operational_readiness=operational_readiness,
                snapshot_state=snapshot.state,
                no_trade_reasons=no_trade_reasons,
                abort_reasons=abort_reasons,
            ),
            selected_contract_audit=selected_contract_audit,
            ingress_health_metrics=metrics,
            timing_audit=tuple(timing_entries),
            no_trade_reasons=no_trade_reasons,
            abort_reasons=abort_reasons,
            warning_flags=(
                snapshot.manifest.warnings if snapshot.manifest is not None else ()
            ),
            replay_bundle_created=True,
            review_json_path=str(review_json_path),
            review_md_path=str(review_md_path),
            execution_summary_path=str(execution_artifacts.execution_summary_path),
            thresholds=self._thresholds,
            explicit_disclaimer=(
                "Ingress-only dry run: no order was placed, no fill was simulated, "
                "and no lifecycle monitoring occurred."
            ),
        )

        ingress_metrics_path = artifact_set.session_directory / "ingress_health_metrics.json"
        timing_audit_path = artifact_set.session_directory / "orpt_rc_timing_audit.json"
        selected_contract_audit_path = (
            artifact_set.session_directory / "selected_contract_audit.json"
        )
        dry_run_summary_json_path = artifact_set.session_directory / summary_json_name
        dry_run_summary_md_path = artifact_set.session_directory / summary_md_name

        self._write_json(ingress_metrics_path, metrics)
        self._write_json(
            timing_audit_path,
            {
                "artifact_version": _ARTIFACT_VERSION,
                "session_id": artifact_set.session_id,
                "entries": tuple(
                    entry
                    for entry in timing_entries
                    if entry.snapshot_label in {SnapshotLabel.ORPT.value, SnapshotLabel.RC.value}
                ),
            },
        )
        self._write_json(selected_contract_audit_path, selected_contract_audit)
        self._write_json(dry_run_summary_json_path, summary)
        self._atomic_write_text(dry_run_summary_md_path, self.render_markdown(summary))

        return S23PaperIngressDryRunArtifactSet(
            session_directory=artifact_set.session_directory,
            session_artifacts=artifact_set,
            execution_artifacts=execution_artifacts,
            replay_bundle_manifest_path=bundle_manifest_path,
            review_json_path=review_json_path,
            review_md_path=review_md_path,
            ingress_health_metrics_path=ingress_metrics_path,
            timing_audit_path=timing_audit_path,
            selected_contract_audit_path=selected_contract_audit_path,
            dry_run_summary_json_path=dry_run_summary_json_path,
            dry_run_summary_md_path=dry_run_summary_md_path,
            summary=summary,
        )

    def render_json(self, summary: S23PaperIngressDryRunSummary) -> str:
        return json.dumps(self._normalize(summary), indent=2, sort_keys=True) + "\n"

    def render_markdown(self, summary: S23PaperIngressDryRunSummary) -> str:
        lines = [
            "# S23 Normalized Live-Paper Ingress Dry Run",
            "",
            f"- session id: `{summary.session_id}`",
            f"- session date: `{summary.session_date.isoformat()}`",
            f"- source mode: `{summary.source_mode}`",
            f"- source path: `{summary.source_path}`",
            f"- terminal state: `{summary.terminal_state.value}`",
            f"- readiness status: `{summary.readiness_status.value if summary.readiness_status is not None else 'unknown'}`",
            f"- operational readiness: `{summary.operational_readiness.value}`",
            "",
            "## Go / No-Go",
            "",
            f"- {summary.go_no_go}",
            "",
            "## Selected Contract Audit",
            "",
            f"- symbol: `{summary.selected_contract_audit.symbol}`",
            f"- present in option chain: `{summary.selected_contract_audit.present_in_option_chain}`",
            f"- quote present: `{summary.selected_contract_audit.selected_contract_quote_present}`",
            f"- quote fresh at finalize: `{summary.selected_contract_audit.quote_fresh_at_finalize}`",
            "",
            "## Ingress Health Metrics",
            "",
            f"- total events: `{summary.ingress_health_metrics.total_events}`",
            f"- processed events: `{summary.ingress_health_metrics.processed_events}`",
            f"- stale events: `{summary.ingress_health_metrics.stale_event_count}`",
            f"- late events: `{summary.ingress_health_metrics.late_event_count}`",
            f"- missing option-chain count: `{summary.ingress_health_metrics.missing_option_chain_count}`",
            f"- missing selected-contract count: `{summary.ingress_health_metrics.missing_selected_contract_count}`",
            f"- timezone mismatch count: `{summary.ingress_health_metrics.timezone_mismatch_count}`",
            f"- selected-contract availability ratio: `{summary.ingress_health_metrics.selected_contract_availability_ratio:.2f}`",
            f"- no-trade rate: `{summary.ingress_health_metrics.no_trade_rate:.2f}`",
            "",
            "## Timing Audit",
            "",
        ]
        if summary.timing_audit:
            for entry in summary.timing_audit:
                lines.append(
                    f"- `{entry.snapshot_label}` effective drift `{entry.effective_drift_seconds:.1f}s`, "
                    f"arrival lag `{entry.arrival_lag_seconds:.1f}s`, within threshold `{entry.within_drift_threshold}`"
                )
        else:
            lines.append("- no snapshot timing entries were recorded")

        lines.extend(
            [
                "",
                "## Reasons",
                "",
                f"- no-trade reasons: `{', '.join(summary.no_trade_reasons) if summary.no_trade_reasons else 'none'}`",
                f"- abort reasons: `{', '.join(summary.abort_reasons) if summary.abort_reasons else 'none'}`",
                "",
                "## Thresholds",
                "",
                f"- max stale events: `{summary.thresholds.max_stale_events}`",
                f"- max timing drift seconds: `{summary.thresholds.max_timing_drift_seconds}`",
                f"- max missing chains: `{summary.thresholds.max_missing_chains}`",
                f"- required selected-contract availability ratio: `{summary.thresholds.required_selected_contract_availability_ratio:.2f}`",
                f"- max no-trade rate: `{summary.thresholds.max_no_trade_rate:.2f}`",
                "",
                "## Review Artifacts",
                "",
                f"- review json: `{summary.review_json_path}`",
                f"- review markdown: `{summary.review_md_path}`",
                f"- execution summary: `{summary.execution_summary_path}`",
                "",
                "## Safety Note",
                "",
                f"- {summary.explicit_disclaimer}",
                "- Same-day only.",
                "- No broker API was used.",
                "- No real order was placed.",
            ]
        )
        return "\n".join(lines) + "\n"

    def _build_selected_contract_audit(
        self,
        *,
        quote_event: SelectedContractQuoteEvent | None,
        option_chain_snapshot: OptionChainSnapshotEvent | None,
        final_validation: Any,
        finalize_at: datetime,
    ) -> S23PaperSelectedContractAudit:
        present_in_option_chain = False
        if quote_event is not None and option_chain_snapshot is not None:
            present_in_option_chain = any(
                contract.symbol == quote_event.symbol
                for contract in option_chain_snapshot.contracts
            )
        quote_age_seconds = None
        quote_fresh = None
        if quote_event is not None:
            quote_age_seconds = (
                finalize_at - quote_event.envelope.effective_timestamp
            ).total_seconds()
            quote_fresh = quote_age_seconds <= self._max_quote_age.total_seconds()
        return S23PaperSelectedContractAudit(
            symbol=quote_event.symbol if quote_event is not None else None,
            option_type=(
                quote_event.option_type.value
                if quote_event is not None and quote_event.option_type is not None
                else None
            ),
            strike=quote_event.strike if quote_event is not None else None,
            expiry=quote_event.expiry if quote_event is not None else None,
            selected_contract_quote_present=quote_event is not None,
            present_in_option_chain=present_in_option_chain,
            quote_fresh_at_finalize=quote_fresh,
            quote_effective_timestamp=(
                quote_event.envelope.effective_timestamp if quote_event is not None else None
            ),
            quote_captured_at=quote_event.envelope.captured_at if quote_event is not None else None,
            quote_age_seconds_at_finalize=quote_age_seconds,
            option_chain_source_id=(
                option_chain_snapshot.envelope.source_id
                if option_chain_snapshot is not None
                else None
            ),
            selected_contract_source_id=(
                quote_event.envelope.source_id if quote_event is not None else None
            ),
        )

    def _build_ingress_metrics(
        self,
        *,
        total_events: int,
        processed_events: int,
        stale_event_count: int,
        late_event_count: int,
        missing_option_chain_count: int,
        missing_selected_contract_count: int,
        timezone_mismatch_count: int,
        unsupported_continuation_count: int,
        selected_contract_audit: S23PaperSelectedContractAudit,
        no_trade_reasons: tuple[str, ...],
        timing_entries: tuple[S23PaperSnapshotTimingAudit, ...],
    ) -> S23PaperIngressHealthMetrics:
        availability_ratio = 1.0 if selected_contract_audit.selected_contract_quote_present else 0.0
        no_trade_rate = 1.0 if no_trade_reasons else 0.0
        max_quote_age = selected_contract_audit.quote_age_seconds_at_finalize
        max_snapshot_lag = (
            max((entry.arrival_lag_seconds for entry in timing_entries), default=None)
            if timing_entries
            else None
        )
        return S23PaperIngressHealthMetrics(
            total_events=total_events,
            processed_events=processed_events,
            stale_event_count=stale_event_count,
            late_event_count=late_event_count,
            missing_option_chain_count=missing_option_chain_count,
            missing_selected_contract_count=missing_selected_contract_count,
            timezone_mismatch_count=timezone_mismatch_count,
            unsupported_continuation_count=unsupported_continuation_count,
            selected_contract_availability_ratio=availability_ratio,
            no_trade_rate=no_trade_rate,
            max_quote_age_seconds_at_finalize=max_quote_age,
            max_snapshot_arrival_lag_seconds=max_snapshot_lag,
        )

    def _evaluate_operational_readiness(
        self,
        *,
        snapshot_state: PaperSessionState,
        metrics: S23PaperIngressHealthMetrics,
        timing_entries: tuple[S23PaperSnapshotTimingAudit, ...],
    ) -> S23PaperIngressReadiness:
        if snapshot_state is not PaperSessionState.ORDER_PLANNED:
            return S23PaperIngressReadiness.FAIL
        if metrics.stale_event_count > self._thresholds.max_stale_events:
            return S23PaperIngressReadiness.FAIL
        if metrics.missing_option_chain_count > self._thresholds.max_missing_chains:
            return S23PaperIngressReadiness.FAIL
        if (
            metrics.selected_contract_availability_ratio
            < self._thresholds.required_selected_contract_availability_ratio
        ):
            return S23PaperIngressReadiness.FAIL
        if metrics.no_trade_rate > self._thresholds.max_no_trade_rate:
            return S23PaperIngressReadiness.FAIL
        if any(not entry.within_drift_threshold for entry in timing_entries):
            return S23PaperIngressReadiness.FAIL
        return S23PaperIngressReadiness.PASS

    def _write_pre_manifest_terminal_artifacts(
        self,
        *,
        snapshot: S23PaperSessionSnapshot,
        events: tuple[PaperEvent, ...],
        session_id: str | None,
    ) -> S23PaperArtifactSet:
        resolved_session_id = session_id or (
            f"s23-ingress-abort-{events[0].envelope.session_date.isoformat()}"
        )
        session_directory = (
            self._artifact_writer.artifact_root
            / events[0].envelope.session_date.isoformat()
            / resolved_session_id
        )
        session_directory.mkdir(parents=True, exist_ok=True)

        final_validation = snapshot.latest_validation_result
        abort_reasons = (
            final_validation.abort_reasons if final_validation is not None else ("session_aborted",)
        )
        warnings = tuple(
            sorted(
                {
                    flag
                    for event in events
                    for flag in event.envelope.data_quality_flags
                }
            )
        )
        synthetic_fixture_used = any(event.envelope.synthetic_fixture for event in events)
        data_sources = tuple(
            {
                (
                    event.envelope.event_type.value,
                    event.envelope.source_type,
                    event.envelope.source_id,
                    event.envelope.synthetic_fixture,
                )
                for event in events
            }
        )
        manifest_payload = {
            "strategy_code": "S23",
            "symbol": "NIFTY",
            "contract_cycle": "WEEKLY",
            "mode": "paper",
            "session_date": events[0].envelope.session_date.isoformat(),
            "readiness_status": PaperReadinessStatus.ABORTED.value,
            "evaluated_state": snapshot.state.value,
            "overlays_enabled": [],
            "data_sources": [
                {
                    "event_type": event_type,
                    "source_type": source_type,
                    "source_id": source_id,
                    "synthetic_fixture": synthetic_fixture,
                }
                for event_type, source_type, source_id, synthetic_fixture in sorted(data_sources)
            ],
            "cost_slippage_version": "unknown",
            "no_trade_reasons": [],
            "abort_reasons": list(abort_reasons),
            "warnings": list(warnings),
            "synthetic_fixture_used": synthetic_fixture_used,
            "generated_at": events[-1].envelope.captured_at.isoformat(),
            "brokerage_per_lot": None,
            "slippage_entry_points": None,
            "slippage_exit_points": None,
            "spread_buffer_policy": None,
        }
        decision_summary_payload = {
            "artifact_version": _ARTIFACT_VERSION,
            "session_id": resolved_session_id,
            "session_date": events[0].envelope.session_date.isoformat(),
            "state": snapshot.state.value,
            "readiness_status": PaperReadinessStatus.ABORTED.value,
            "evaluated_state": snapshot.state.value,
            "strategy_code": "S23",
            "symbol": "NIFTY",
            "contract_cycle": "WEEKLY",
            "mode": "paper",
            "selected_contract_available": False,
            "selected_contract_symbol": None,
            "paper_order_planned": False,
            "required_snapshot_labels": [],
            "missing_snapshot_labels": [],
            "overlays_enabled": [],
            "synthetic_fixture_used": synthetic_fixture_used,
            "warning_flags": list(warnings),
            "no_trade_reasons": [],
            "abort_reasons": list(abort_reasons),
            "terminal_reason_code": abort_reasons[0] if abort_reasons else "session_aborted",
            "data_sources": manifest_payload["data_sources"],
            "guardrail_code": (
                snapshot.latest_guardrail_decision.code
                if snapshot.latest_guardrail_decision is not None
                else None
            ),
            "guardrail_message": (
                snapshot.latest_guardrail_decision.message
                if snapshot.latest_guardrail_decision is not None
                else None
            ),
            "blocking_event_type": (
                snapshot.latest_guardrail_decision.blocking_event_type.value
                if snapshot.latest_guardrail_decision is not None
                and snapshot.latest_guardrail_decision.blocking_event_type is not None
                else None
            ),
            "blocking_source_id": (
                snapshot.latest_guardrail_decision.blocking_source_id
                if snapshot.latest_guardrail_decision is not None
                else None
            ),
            "operator_action_required": (
                snapshot.latest_guardrail_decision.operator_action_required
                if snapshot.latest_guardrail_decision is not None
                else None
            ),
        }
        abort_summary_payload = {
            "artifact_version": _ARTIFACT_VERSION,
            "session_id": resolved_session_id,
            "session_date": events[0].envelope.session_date.isoformat(),
            "state": snapshot.state.value,
            "terminal_state": "ABORTED",
            "terminal_reason_code": abort_reasons[0] if abort_reasons else "session_aborted",
            "no_trade_reasons": [],
            "abort_reasons": list(abort_reasons),
            "warnings": list(warnings),
            "selected_contract_symbol": None,
            "selected_contract_quote_present": False,
            "execution_started": False,
            "fill_simulation_started": False,
            "provenance_sources": manifest_payload["data_sources"],
            "guardrail_code": decision_summary_payload["guardrail_code"],
            "guardrail_message": decision_summary_payload["guardrail_message"],
            "blocking_event_type": decision_summary_payload["blocking_event_type"],
            "blocking_source_id": decision_summary_payload["blocking_source_id"],
            "operator_action_required": decision_summary_payload["operator_action_required"],
        }
        manifest_path = session_directory / "session_manifest.json"
        audit_path = session_directory / "audit_events.jsonl"
        decision_path = session_directory / "decision_summary.json"
        abort_path = session_directory / "abort_summary.json"
        self._write_json(manifest_path, manifest_payload)
        self._write_jsonl(audit_path, snapshot.audit_events)
        self._write_json(decision_path, decision_summary_payload)
        self._write_json(abort_path, abort_summary_payload)
        return S23PaperArtifactSet(
            artifact_root=self._artifact_writer.artifact_root,
            session_directory=session_directory,
            session_id=resolved_session_id,
            session_manifest_path=manifest_path,
            audit_events_path=audit_path,
            decision_summary_path=decision_path,
            selected_contract_path=None,
            paper_order_plan_path=None,
            no_trade_summary_path=None,
            abort_summary_path=abort_path,
        )

    def _build_go_no_go_message(
        self,
        *,
        operational_readiness: S23PaperIngressReadiness,
        snapshot_state: PaperSessionState,
        no_trade_reasons: tuple[str, ...],
        abort_reasons: tuple[str, ...],
    ) -> str:
        if operational_readiness is S23PaperIngressReadiness.PASS:
            return (
                "GO: normalized S23 live-paper ingress satisfied the dry-run thresholds "
                "and reached ORDER_PLANNED without fill or lifecycle execution."
            )
        if snapshot_state is PaperSessionState.NO_TRADE:
            reason = no_trade_reasons[0] if no_trade_reasons else "no_trade"
            return (
                f"NO_GO: the normalized ingress dry run ended in NO_TRADE due to `{reason}` "
                "before an intent-only handoff could be accepted."
            )
        if snapshot_state is PaperSessionState.ABORTED:
            reason = abort_reasons[0] if abort_reasons else "aborted"
            return (
                f"NO_GO: the normalized ingress dry run aborted due to `{reason}` before "
                "an intent-only handoff could be accepted."
            )
        return (
            "NO_GO: the normalized ingress dry run did not satisfy the pre-planning "
            "operational thresholds."
        )

    def _expected_snapshot_timestamp(
        self,
        session_date: date,
        label: SnapshotLabel,
    ) -> datetime:
        expected_time = _EXPECTED_SNAPSHOT_TIMES.get(label)
        if expected_time is None:
            return datetime.combine(session_date, time(0, 0), tzinfo=_IST)
        return datetime.combine(session_date, expected_time, tzinfo=_IST)

    def _write_json(self, path: Path, payload: Any) -> None:
        rendered = json.dumps(self._normalize(payload), indent=2, sort_keys=True) + "\n"
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
