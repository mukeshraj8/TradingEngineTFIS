from __future__ import annotations

import json
import os
import time as time_module
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from .fyers_snapshot_collector import (
    PaperFyersSnapshotArtifactSet,
    PaperFyersSnapshotCollector,
    PaperFyersSnapshotCollectorError,
)


_ARTIFACT_VERSION = 1
_DEFAULT_ARTIFACT_ROOT = Path("tmp/s23_snapshot_validation_harness")


class S23SnapshotValidationWarning(str, Enum):
    MISSING_OI = "MISSING_OI"
    EMPTY_CHAIN = "EMPTY_CHAIN"
    CONTRACT_OSCILLATION = "CONTRACT_OSCILLATION"
    STALE_CHAIN = "STALE_CHAIN"
    PRELUDE_BUILD_FAILURE = "PRELUDE_BUILD_FAILURE"


@dataclass(frozen=True, slots=True)
class S23SnapshotOptionChainStatistics:
    contract_count: int
    missing_oi_count: int
    completeness_ratio: float


@dataclass(frozen=True, slots=True)
class S23SnapshotValidationSample:
    sample_index: int
    snapshot_timestamp: datetime
    session_date: date
    selected_contract_symbol: str | None
    selected_premium: float | None
    selected_oi: float | None
    expiry_used: date | None
    next_expiry_required: bool | None
    rejected_candidate_counts: dict[str, int]
    option_chain_statistics: S23SnapshotOptionChainStatistics
    selected_contract_changed: bool
    premium_drift: float | None
    oi_drift: float | None
    expiry_transition_state: str
    chain_completeness: float
    warnings: tuple[S23SnapshotValidationWarning, ...]
    collector_session_directory: str | None = None
    prelude_generated: bool = False
    selection_reason: str | None = None
    failure_code: str | None = None
    warning_message: str | None = None


@dataclass(frozen=True, slots=True)
class S23SnapshotValidationAggregateMetrics:
    total_samples: int
    successful_samples: int
    failed_samples: int
    contract_change_count: int
    stable_selection_count: int
    stale_chain_count: int
    empty_chain_count: int
    missing_oi_count: int
    prelude_build_failure_count: int
    average_premium_drift: float | None
    max_premium_drift: float | None
    average_oi_drift: float | None
    max_oi_drift: float | None
    warning_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class S23SnapshotValidationReport:
    artifact_version: int
    session_id: str
    strategy_path: str
    config_path: str
    runtime_fixture_path: str
    interval_seconds: int
    requested_samples: int
    generated_at: datetime
    samples: tuple[S23SnapshotValidationSample, ...]
    aggregate_metrics: S23SnapshotValidationAggregateMetrics
    explicit_disclaimer: str


@dataclass(frozen=True, slots=True)
class S23SnapshotValidationArtifactSet:
    session_directory: Path
    report_json_path: Path
    report_markdown_path: Path
    samples_jsonl_path: Path
    report: S23SnapshotValidationReport


PaperSnapshotValidationWarning = S23SnapshotValidationWarning
PaperSnapshotOptionChainStatistics = S23SnapshotOptionChainStatistics
PaperSnapshotValidationSample = S23SnapshotValidationSample
PaperSnapshotValidationAggregateMetrics = S23SnapshotValidationAggregateMetrics
PaperSnapshotValidationReport = S23SnapshotValidationReport
PaperSnapshotValidationArtifactSet = S23SnapshotValidationArtifactSet


class SnapshotCollectorLike(Protocol):
    def collect_from_files(
        self,
        *,
        config_path: str | Path,
        strategy_path: str | Path,
        runtime_fixture_path: str | Path | None = None,
        carry_forward_state_dir: str | Path | None = None,
        session_id: str | None = None,
        dry_run_build_prelude: bool = False,
        enable_smoke_override: bool = False,
        adapter: object | None = None,
    ) -> PaperFyersSnapshotArtifactSet: ...


class S23SnapshotValidationHarness:
    def __init__(
        self,
        *,
        artifact_root: str | Path = _DEFAULT_ARTIFACT_ROOT,
        collector: SnapshotCollectorLike | None = None,
        sleep_fn: callable | None = None,
    ) -> None:
        self._artifact_root = Path(artifact_root)
        self._collector = collector or PaperFyersSnapshotCollector(artifact_root=artifact_root)
        self._sleep_fn = sleep_fn or time_module.sleep

    def run_from_files(
        self,
        *,
        config_path: str | Path,
        strategy_path: str | Path,
        runtime_fixture_path: str | Path,
        carry_forward_state_dir: str | Path | None = None,
        session_id: str | None = None,
        samples: int = 3,
        interval_seconds: int = 60,
        enable_smoke_override: bool = False,
    ) -> S23SnapshotValidationArtifactSet:
        if samples <= 0:
            raise ValueError("samples must be positive")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative")

        resolved_session_id = session_id or self._derive_session_id(runtime_fixture_path)
        session_directory = self._artifact_root / resolved_session_id
        collected_samples: list[S23SnapshotValidationSample] = []
        previous_success: S23SnapshotValidationSample | None = None

        for index in range(samples):
            try:
                artifact = self._collector.collect_from_files(
                    config_path=config_path,
                    strategy_path=strategy_path,
                    runtime_fixture_path=runtime_fixture_path,
                    carry_forward_state_dir=carry_forward_state_dir,
                    session_id=f"{resolved_session_id}-sample-{index + 1:03d}",
                    dry_run_build_prelude=True,
                    enable_smoke_override=enable_smoke_override,
                )
                sample = self._build_success_sample(
                    artifact=artifact,
                    sample_index=index + 1,
                    previous_success=previous_success,
                )
                previous_success = sample if sample.selected_contract_symbol is not None else previous_success
            except PaperFyersSnapshotCollectorError as exc:
                sample = self._build_failure_sample(
                    sample_index=index + 1,
                    runtime_fixture_path=runtime_fixture_path,
                    session_id=resolved_session_id,
                    error=exc,
                )
            collected_samples.append(sample)
            if index < samples - 1 and interval_seconds > 0:
                self._sleep_fn(interval_seconds)

        report = S23SnapshotValidationReport(
            artifact_version=_ARTIFACT_VERSION,
            session_id=resolved_session_id,
            strategy_path=str(Path(strategy_path)),
            config_path=str(Path(config_path)),
            runtime_fixture_path=str(Path(runtime_fixture_path)),
            interval_seconds=interval_seconds,
            requested_samples=samples,
            generated_at=datetime.now(),
            samples=tuple(collected_samples),
            aggregate_metrics=self._build_aggregate_metrics(tuple(collected_samples)),
            explicit_disclaimer=(
                "Snapshot validation harness collects repeated one-shot FYERS snapshots for "
                "S23 paper readiness only. It does not start a socket loop, execute lifecycle "
                "logic, or place broker orders."
            ),
        )

        report_json_path = session_directory / "snapshot_validation_report.json"
        report_markdown_path = session_directory / "snapshot_validation_report.md"
        samples_jsonl_path = session_directory / "snapshot_validation_samples.jsonl"
        self._write_json(report_json_path, report)
        self._atomic_write_text(report_markdown_path, self.render_markdown(report))
        self._write_jsonl(samples_jsonl_path, tuple(collected_samples))
        return S23SnapshotValidationArtifactSet(
            session_directory=session_directory,
            report_json_path=report_json_path,
            report_markdown_path=report_markdown_path,
            samples_jsonl_path=samples_jsonl_path,
            report=report,
        )

    def render_json(self, report: S23SnapshotValidationReport) -> str:
        return json.dumps(self._normalize(report), indent=2, sort_keys=True) + "\n"

    def render_markdown(self, report: S23SnapshotValidationReport) -> str:
        metrics = report.aggregate_metrics
        lines = [
            "# S23 Snapshot Validation Harness",
            "",
            "## Overview",
            f"- Session ID: `{report.session_id}`",
            f"- Strategy Path: `{report.strategy_path}`",
            f"- Config Path: `{report.config_path}`",
            f"- Runtime Fixture: `{report.runtime_fixture_path}`",
            f"- Requested Samples: `{report.requested_samples}`",
            f"- Interval Seconds: `{report.interval_seconds}`",
            "",
            "## Aggregate Metrics",
            f"- Successful Samples: `{metrics.successful_samples}`",
            f"- Failed Samples: `{metrics.failed_samples}`",
            f"- Contract Change Count: `{metrics.contract_change_count}`",
            f"- Stable Selection Count: `{metrics.stable_selection_count}`",
            f"- Stale Chain Count: `{metrics.stale_chain_count}`",
            f"- Empty Chain Count: `{metrics.empty_chain_count}`",
            f"- Missing OI Count: `{metrics.missing_oi_count}`",
            f"- Prelude Build Failure Count: `{metrics.prelude_build_failure_count}`",
            f"- Average Premium Drift: `{metrics.average_premium_drift if metrics.average_premium_drift is not None else 'n/a'}`",
            f"- Max Premium Drift: `{metrics.max_premium_drift if metrics.max_premium_drift is not None else 'n/a'}`",
            f"- Average OI Drift: `{metrics.average_oi_drift if metrics.average_oi_drift is not None else 'n/a'}`",
            f"- Max OI Drift: `{metrics.max_oi_drift if metrics.max_oi_drift is not None else 'n/a'}`",
            "",
            "## Samples",
        ]
        for sample in report.samples:
            lines.extend(
                [
                    f"### Sample {sample.sample_index}",
                    f"- Snapshot Timestamp: `{sample.snapshot_timestamp.isoformat()}`",
                    f"- Selected Contract: `{sample.selected_contract_symbol or 'n/a'}`",
                    f"- Selected Premium: `{sample.selected_premium if sample.selected_premium is not None else 'n/a'}`",
                    f"- Selected OI: `{sample.selected_oi if sample.selected_oi is not None else 'n/a'}`",
                    f"- Expiry Used: `{sample.expiry_used.isoformat() if sample.expiry_used is not None else 'n/a'}`",
                    f"- Next Expiry Required: `{sample.next_expiry_required if sample.next_expiry_required is not None else 'n/a'}`",
                    f"- Selected Contract Changed: `{sample.selected_contract_changed}`",
                    f"- Premium Drift: `{sample.premium_drift if sample.premium_drift is not None else 'n/a'}`",
                    f"- OI Drift: `{sample.oi_drift if sample.oi_drift is not None else 'n/a'}`",
                    f"- Expiry Transition State: `{sample.expiry_transition_state}`",
                    f"- Chain Completeness: `{sample.chain_completeness:.2f}`",
                    f"- Rejected Candidate Counts: `{sample.rejected_candidate_counts}`",
                    f"- Warnings: `{', '.join(item.value for item in sample.warnings) if sample.warnings else 'none'}`",
                ]
            )
            if sample.warning_message:
                lines.append(f"- Warning Message: {sample.warning_message}")
        lines.extend(["", "## Disclaimer", f"- {report.explicit_disclaimer}", ""])
        return "\n".join(lines)

    def _build_success_sample(
        self,
        *,
        artifact: PaperFyersSnapshotArtifactSet,
        sample_index: int,
        previous_success: S23SnapshotValidationSample | None,
    ) -> S23SnapshotValidationSample:
        if artifact.collected_inputs is None or artifact.prelude_result is None:
            raise PaperFyersSnapshotCollectorError(
                "PRELUDE_BUILD_FAILURE",
                "Snapshot collector did not return in-memory prelude details for validation.",
            )
        option_chain = artifact.collected_inputs.option_chain_snapshot
        stats = self._build_chain_stats(option_chain)
        session_context = artifact.collected_inputs.session_context
        prelude_result = artifact.prelude_result
        selection = prelude_result.contract_selection
        selected_symbol = selection.selected_contract_symbol if selection is not None else None
        selected_premium = selection.premium_used if selection is not None else None
        selected_oi = selection.oi_used if selection is not None else None
        warnings: list[S23SnapshotValidationWarning] = []
        if stats.missing_oi_count > 0:
            warnings.append(S23SnapshotValidationWarning.MISSING_OI)
        chain_age_seconds = abs(
            (session_context.generated_at - option_chain.envelope.captured_at).total_seconds()
        )
        if chain_age_seconds > 5.0:
            warnings.append(S23SnapshotValidationWarning.STALE_CHAIN)
        selected_contract_changed = (
            previous_success is not None
            and previous_success.selected_contract_symbol != selected_symbol
        )
        if selected_contract_changed:
            warnings.append(S23SnapshotValidationWarning.CONTRACT_OSCILLATION)
        premium_drift = (
            None
            if previous_success is None
            or previous_success.selected_premium is None
            or selected_premium is None
            else selected_premium - previous_success.selected_premium
        )
        oi_drift = (
            None
            if previous_success is None
            or previous_success.selected_oi is None
            or selected_oi is None
            else selected_oi - previous_success.selected_oi
        )
        next_expiry_required = artifact.collected_inputs.expiry_governance.should_select_next_expiry(
            artifact.collected_inputs.strategy_rule,
            artifact.collected_inputs.session_context.session_date,
        )
        if next_expiry_required:
            expiry_transition_state = "NEXT_EXPIRY_REQUIRED"
        elif artifact.collected_inputs.weekly_expiry == option_chain.expiry:
            expiry_transition_state = "CURRENT_EXPIRY_ACTIVE"
        else:
            expiry_transition_state = "EXPLICIT_EXPIRY_OVERRIDE"
        return S23SnapshotValidationSample(
            sample_index=sample_index,
            snapshot_timestamp=session_context.generated_at,
            session_date=session_context.session_date,
            selected_contract_symbol=selected_symbol,
            selected_premium=selected_premium,
            selected_oi=selected_oi,
            expiry_used=artifact.collected_inputs.weekly_expiry,
            next_expiry_required=next_expiry_required,
            rejected_candidate_counts=(
                dict(selection.rejected_candidate_counts) if selection is not None else {}
            ),
            option_chain_statistics=stats,
            selected_contract_changed=selected_contract_changed,
            premium_drift=premium_drift,
            oi_drift=oi_drift,
            expiry_transition_state=expiry_transition_state,
            chain_completeness=stats.completeness_ratio,
            warnings=tuple(dict.fromkeys(warnings)),
            collector_session_directory=str(artifact.session_directory),
            prelude_generated=True,
            selection_reason=selection.selection_reason if selection is not None else None,
            failure_code=None,
            warning_message=None,
        )

    def _build_failure_sample(
        self,
        *,
        sample_index: int,
        runtime_fixture_path: str | Path,
        session_id: str,
        error: PaperFyersSnapshotCollectorError,
    ) -> S23SnapshotValidationSample:
        runtime_fixture = json.loads(Path(runtime_fixture_path).read_text(encoding="utf-8"))
        timestamp = datetime.fromisoformat(str(runtime_fixture["generated_at"]))
        session_date = date.fromisoformat(str(runtime_fixture["session_date"]))
        warnings: list[S23SnapshotValidationWarning] = []
        if error.code == "MISSING_CONTRACT_OI":
            warnings.append(S23SnapshotValidationWarning.MISSING_OI)
        elif error.code == "OPTION_CHAIN_MISSING":
            warnings.append(S23SnapshotValidationWarning.EMPTY_CHAIN)
        else:
            warnings.append(S23SnapshotValidationWarning.PRELUDE_BUILD_FAILURE)
        return S23SnapshotValidationSample(
            sample_index=sample_index,
            snapshot_timestamp=timestamp,
            session_date=session_date,
            selected_contract_symbol=None,
            selected_premium=None,
            selected_oi=None,
            expiry_used=None,
            next_expiry_required=None,
            rejected_candidate_counts={},
            option_chain_statistics=S23SnapshotOptionChainStatistics(
                contract_count=0,
                missing_oi_count=0,
                completeness_ratio=0.0,
            ),
            selected_contract_changed=False,
            premium_drift=None,
            oi_drift=None,
            expiry_transition_state="UNKNOWN",
            chain_completeness=0.0,
            warnings=tuple(warnings),
            collector_session_directory=None,
            prelude_generated=False,
            selection_reason=None,
            failure_code=error.code,
            warning_message=str(error),
        )

    @staticmethod
    def _build_chain_stats(option_chain: Any) -> S23SnapshotOptionChainStatistics:
        contract_count = len(option_chain.contracts)
        missing_oi_count = sum(1 for contract in option_chain.contracts if contract.oi is None)
        completeness_ratio = 0.0
        if contract_count > 0:
            completeness_ratio = (contract_count - missing_oi_count) / contract_count
        return S23SnapshotOptionChainStatistics(
            contract_count=contract_count,
            missing_oi_count=missing_oi_count,
            completeness_ratio=completeness_ratio,
        )

    def _build_aggregate_metrics(
        self,
        samples: tuple[S23SnapshotValidationSample, ...],
    ) -> S23SnapshotValidationAggregateMetrics:
        warning_counts: dict[str, int] = {}
        successful = 0
        failed = 0
        contract_change_count = 0
        stale_chain_count = 0
        empty_chain_count = 0
        missing_oi_count = 0
        prelude_build_failure_count = 0
        premium_drifts: list[float] = []
        oi_drifts: list[float] = []

        for sample in samples:
            if sample.prelude_generated:
                successful += 1
            else:
                failed += 1
            if sample.selected_contract_changed:
                contract_change_count += 1
            if sample.premium_drift is not None:
                premium_drifts.append(abs(sample.premium_drift))
            if sample.oi_drift is not None:
                oi_drifts.append(abs(sample.oi_drift))
            for warning in sample.warnings:
                warning_counts[warning.value] = warning_counts.get(warning.value, 0) + 1
                if warning is S23SnapshotValidationWarning.STALE_CHAIN:
                    stale_chain_count += 1
                elif warning is S23SnapshotValidationWarning.EMPTY_CHAIN:
                    empty_chain_count += 1
                elif warning is S23SnapshotValidationWarning.MISSING_OI:
                    missing_oi_count += 1
                elif warning is S23SnapshotValidationWarning.PRELUDE_BUILD_FAILURE:
                    prelude_build_failure_count += 1

        return S23SnapshotValidationAggregateMetrics(
            total_samples=len(samples),
            successful_samples=successful,
            failed_samples=failed,
            contract_change_count=contract_change_count,
            stable_selection_count=max(successful - contract_change_count, 0),
            stale_chain_count=stale_chain_count,
            empty_chain_count=empty_chain_count,
            missing_oi_count=missing_oi_count,
            prelude_build_failure_count=prelude_build_failure_count,
            average_premium_drift=(
                sum(premium_drifts) / len(premium_drifts) if premium_drifts else None
            ),
            max_premium_drift=max(premium_drifts) if premium_drifts else None,
            average_oi_drift=sum(oi_drifts) / len(oi_drifts) if oi_drifts else None,
            max_oi_drift=max(oi_drifts) if oi_drifts else None,
            warning_counts=dict(sorted(warning_counts.items())),
        )

    @staticmethod
    def _derive_session_id(runtime_fixture_path: str | Path) -> str:
        return f"s23-snapshot-validation-{Path(runtime_fixture_path).stem}"

    def _write_json(self, path: Path, payload: Any) -> None:
        self._atomic_write_text(
            path,
            json.dumps(self._normalize(payload), indent=2, sort_keys=True) + "\n",
        )

    def _write_jsonl(self, path: Path, rows: tuple[Any, ...]) -> None:
        rendered = "".join(json.dumps(self._normalize(row), sort_keys=True) + "\n" for row in rows)
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
            return {str(key): self._normalize(val) for key, val in value.items()}
        if isinstance(value, tuple | list):
            return [self._normalize(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value


PaperSnapshotValidationHarness = S23SnapshotValidationHarness
