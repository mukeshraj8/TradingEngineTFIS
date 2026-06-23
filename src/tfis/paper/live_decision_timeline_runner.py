from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time
from pathlib import Path
from typing import Callable

from tfis.importers import load_strategy_rule

from .fyers_snapshot_collector import S23FyersSnapshotArtifactSet, S23FyersSnapshotCollector
from .live_decision import S23PaperLiveDecisionBuilder
from .live_ingress import S23LivePaperIngressConfig
from .live_decision_runner import prepare_fyers_env_from_tfis_auth
from .live_decision_schedule import build_schedule_note, compute_schedule_delay_seconds
from .live_decision_timeline import (
    S23LiveDecisionTimelineBuilder,
    S23LiveDecisionTimelineResult,
    S23LiveDecisionTimelineStage,
)
from .live_state_store import build_s23_paper_live_state_store_from_yaml
from .position_manager import S23PaperPositionManager
from .position_state import S23PaperPositionStateStore
from .runtime_input_derivation import load_s23_decision_reference_packet


@dataclass(frozen=True, slots=True)
class S23MorningDecisionCheckpoint:
    stage_name: str
    target_hour: int
    target_minute: int

    @property
    def stage_time(self) -> time:
        return time(self.target_hour, self.target_minute)


@dataclass(frozen=True, slots=True)
class S23MorningDecisionStageRun:
    strategy_branch: str
    checkpoint: S23MorningDecisionCheckpoint
    initial_check_time: str
    trigger_time: str
    delay_seconds: float
    schedule_note: str
    snapshot_session_directory: str
    stage_explainer_json: str
    stage_explainer_markdown: str
    monthly_status_json: str
    monthly_status_markdown: str
    stage: S23LiveDecisionTimelineStage


@dataclass(frozen=True, slots=True)
class S23MorningDecisionRunResult:
    session_directory: Path
    timeline_json: Path
    timeline_markdown: Path
    final_summary_json: Path | None
    final_summary_markdown: Path | None
    stage_runs: tuple[S23MorningDecisionStageRun, ...]
    branch_final_summary_json: dict[str, str] = field(default_factory=dict)
    branch_final_summary_markdown: dict[str, str] = field(default_factory=dict)
    branch_position_state_json: dict[str, str] = field(default_factory=dict)


def default_morning_decision_checkpoints() -> tuple[S23MorningDecisionCheckpoint, ...]:
    return (
        S23MorningDecisionCheckpoint("Opening Snapshot", 9, 16),
        S23MorningDecisionCheckpoint("ORPT Snapshot", 9, 25),
        S23MorningDecisionCheckpoint("RC Snapshot", 9, 30),
    )


def run_s23_morning_supervised_decision(
    *,
    tfis_root: str | Path | None = None,
    config_path: str | Path,
    strategy_path: str | Path,
    strategy_paths: tuple[str | Path, ...] | None = None,
    reference_packet_path: str | Path,
    artifact_root: str | Path,
    session_id_prefix: str,
    checkpoints: tuple[S23MorningDecisionCheckpoint, ...] | None = None,
    carry_forward_state_dir: str | Path | None = None,
    enable_smoke_override: bool = False,
    skip_refresh: bool = False,
    timezone_name: str = "Asia/Kolkata",
    if_past: str = "run_now",
    dashboard_output_root: str | Path | None = "tmp/operator_dashboard",
    now_provider: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> S23MorningDecisionRunResult:
    from zoneinfo import ZoneInfo
    import time as time_module

    timezone = ZoneInfo(timezone_name)
    now_fn = now_provider or (lambda: datetime.now(timezone))
    sleep_fn = sleeper or time_module.sleep
    stage_checkpoints = checkpoints or default_morning_decision_checkpoints()
    live_state_store = build_s23_paper_live_state_store_from_yaml(config_path)

    prepare_fyers_env_from_tfis_auth(tfis_root=tfis_root, skip_refresh=skip_refresh)
    selected_strategy_paths = tuple(strategy_paths or (strategy_path,))
    if not selected_strategy_paths:
        raise RuntimeError("At least one S23 strategy path is required.")
    strategy_rules = tuple(load_strategy_rule(path) for path in selected_strategy_paths)
    primary_strategy_rule = strategy_rules[0]
    primary_strategy_path = selected_strategy_paths[0]
    ingress_config = S23LivePaperIngressConfig.from_yaml(config_path)
    base_reference_packet = load_s23_decision_reference_packet(reference_packet_path)
    collector = S23FyersSnapshotCollector(artifact_root=artifact_root)
    decision_builder = S23PaperLiveDecisionBuilder()
    timeline_builder = S23LiveDecisionTimelineBuilder(decision_builder=decision_builder)
    dashboard_builder = _build_dashboard_builder(
        artifact_root=artifact_root,
        strategy_path=primary_strategy_path,
        reference_packet_path=reference_packet_path,
        session_id_prefix=session_id_prefix,
    )
    carry_forward_position = (
        S23PaperPositionStateStore().load_state(carry_forward_state_dir)
        if carry_forward_state_dir is not None
        else None
    )

    session_directory: Path | None = None
    final_summary_json: Path | None = None
    final_summary_markdown: Path | None = None
    branch_final_summary_json: dict[str, str] = {}
    branch_final_summary_markdown: dict[str, str] = {}
    branch_position_state_json: dict[str, str] = {}
    stage_runs: list[S23MorningDecisionStageRun] = []
    timeline_stages_by_branch: dict[str, list[S23LiveDecisionTimelineStage]] = {
        rule.unique_code: [] for rule in strategy_rules
    }
    final_decisions_by_branch = {}
    last_snapshot_artifacts: S23FyersSnapshotArtifactSet | None = None

    for checkpoint in stage_checkpoints:
        now = now_fn()
        delay_seconds = compute_schedule_delay_seconds(
            now=now,
            target_hour=checkpoint.target_hour,
            target_minute=checkpoint.target_minute,
            if_past=if_past,
        )
        note = build_schedule_note(
            now=now,
            target_hour=checkpoint.target_hour,
            target_minute=checkpoint.target_minute,
            delay_seconds=delay_seconds,
        )
        if delay_seconds > 0:
            sleep_fn(delay_seconds)
        trigger_time = now_fn()
        session_id = f"{session_id_prefix}-{checkpoint.target_hour:02d}{checkpoint.target_minute:02d}-{trigger_time.strftime('%Y-%m-%d')}"
        snapshot_artifacts = collector.collect_from_files(
            config_path=config_path,
            strategy_path=primary_strategy_path,
            carry_forward_state_dir=carry_forward_state_dir,
            session_id=session_id,
            adapter=None,
        )
        if snapshot_artifacts.collected_inputs is None:
            raise RuntimeError("Snapshot collector did not return collected inputs.")
        if session_directory is None:
            session_directory = snapshot_artifacts.session_directory.parent / f"{session_id_prefix}-{trigger_time.strftime('%Y-%m-%d')}"
            session_directory.mkdir(parents=True, exist_ok=True)

        for strategy_rule in strategy_rules:
            strategy_branch = strategy_rule.unique_code
            reference_packet = replace(
                base_reference_packet,
                strategy_branch=strategy_branch,
            )
            stage_build = timeline_builder.build_stage(
                stage_name=checkpoint.stage_name,
                stage_time=checkpoint.stage_time,
                strategy_rule=strategy_rule,
                reference_packet=reference_packet,
                collected_inputs=snapshot_artifacts.collected_inputs,
                carry_forward_position=carry_forward_position,
                smoke_override_enabled=enable_smoke_override,
                smoke_override_selected_contract_symbol=(
                    ingress_config.market.selected_contract_symbol if enable_smoke_override else None
                ),
                allow_branch_pinned_unknown_monthly_status=True,
            )
            timeline_stages_by_branch[strategy_branch].append(stage_build.stage)
            output_dir = (
                session_directory
                if len(strategy_rules) == 1
                else session_directory / strategy_branch
            )
            (
                stage_explainer_json,
                stage_explainer_markdown,
                monthly_status_json,
                monthly_status_markdown,
            ) = timeline_builder.write_stage_artifacts(
                session_date=snapshot_artifacts.summary.session_date,
                strategy_code=strategy_rule.strategy_code,
                strategy_branch=strategy_branch,
                stage=stage_build.stage,
                output_dir=output_dir,
            )
            stage_runs.append(
                S23MorningDecisionStageRun(
                    strategy_branch=strategy_branch,
                    checkpoint=checkpoint,
                    initial_check_time=now.isoformat(),
                    trigger_time=trigger_time.isoformat(),
                    delay_seconds=delay_seconds,
                    schedule_note=note,
                    snapshot_session_directory=str(snapshot_artifacts.session_directory),
                    stage_explainer_json=str(stage_explainer_json),
                    stage_explainer_markdown=str(stage_explainer_markdown),
                    monthly_status_json=str(monthly_status_json),
                    monthly_status_markdown=str(monthly_status_markdown),
                    stage=stage_build.stage,
                )
            )
            if stage_build.decision_result is not None:
                final_decisions_by_branch[strategy_branch] = stage_build.decision_result
                summary_json, summary_markdown = decision_builder.write_artifacts(
                    stage_build.decision_result,
                    output_dir=output_dir,
                )
                branch_final_summary_json[strategy_branch] = str(summary_json)
                branch_final_summary_markdown[strategy_branch] = str(summary_markdown)
                if final_summary_json is None:
                    final_summary_json = summary_json
                    final_summary_markdown = summary_markdown
        _rebuild_dashboard(
            dashboard_builder=dashboard_builder,
            dashboard_output_root=dashboard_output_root,
        )
        last_snapshot_artifacts = snapshot_artifacts

    if session_directory is None or last_snapshot_artifacts is None:
        raise RuntimeError("Morning supervised decision run did not capture any stages.")

    primary_timeline_json: Path | None = None
    primary_timeline_markdown: Path | None = None
    for strategy_rule in strategy_rules:
        strategy_branch = strategy_rule.unique_code
        timeline_result = timeline_builder.build_timeline(
            session_date=last_snapshot_artifacts.summary.session_date,
            strategy_rule=strategy_rule,
            strategy_branch=strategy_branch,
            stages=tuple(timeline_stages_by_branch[strategy_branch]),
        )
        output_dir = (
            session_directory
            if len(strategy_rules) == 1
            else session_directory / strategy_branch
        )
        timeline_json, timeline_markdown = timeline_builder.write_artifacts(
            timeline_result,
            output_dir=output_dir,
        )
        if primary_timeline_json is None:
            primary_timeline_json = timeline_json
            primary_timeline_markdown = timeline_markdown
        decision_result = final_decisions_by_branch.get(strategy_branch)
        if (
            decision_result is not None
            and decision_result.summary.status == "READY"
            and decision_result.summary.selected_contract_symbol
            and decision_result.summary.planned_entry_price is not None
        ):
            opened_at = (
                datetime.fromisoformat(stage_runs[-1].trigger_time)
                if stage_runs
                else datetime.combine(decision_result.summary.session_date, time(9, 30))
            )
            provenance_source_ids = tuple(
                item
                for item in (
                    branch_final_summary_json.get(strategy_branch),
                    str(timeline_json),
                )
                if item
            )
            position_result = S23PaperPositionManager(
                live_state_store=live_state_store,
            ).open_from_live_decision(
                output_dir,
                strategy_rule=strategy_rule,
                decision=decision_result,
                opened_at=opened_at,
                provenance_source_ids=provenance_source_ids,
            )
            branch_position_state_json[strategy_branch] = str(position_result.state_path)
    assert primary_timeline_json is not None
    assert primary_timeline_markdown is not None
    metadata_path = session_directory / "scheduled_run_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "timezone": timezone_name,
                "if_past": if_past,
                "session_directory": str(session_directory),
                "timeline_json": str(primary_timeline_json),
                "timeline_markdown": str(primary_timeline_markdown),
                "final_summary_json": str(final_summary_json) if final_summary_json is not None else None,
                "final_summary_markdown": str(final_summary_markdown) if final_summary_markdown is not None else None,
                "branch_final_summary_json": branch_final_summary_json,
                "branch_final_summary_markdown": branch_final_summary_markdown,
                "branch_position_state_json": branch_position_state_json,
                "stages": [
                    {
                        "strategy_branch": stage_run.strategy_branch,
                        "stage_name": stage_run.checkpoint.stage_name,
                        "target_hour": stage_run.checkpoint.target_hour,
                        "target_minute": stage_run.checkpoint.target_minute,
                        "initial_check_time": stage_run.initial_check_time,
                        "trigger_time": stage_run.trigger_time,
                        "delay_seconds": stage_run.delay_seconds,
                        "schedule_note": stage_run.schedule_note,
                        "snapshot_session_directory": stage_run.snapshot_session_directory,
                        "stage_explainer_json": stage_run.stage_explainer_json,
                        "stage_explainer_markdown": stage_run.stage_explainer_markdown,
                        "monthly_status_json": stage_run.monthly_status_json,
                        "monthly_status_markdown": stage_run.monthly_status_markdown,
                        "can_finalize_trade_decision": stage_run.stage.can_finalize_trade_decision,
                    }
                    for stage_run in stage_runs
                ],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _rebuild_dashboard(
        dashboard_builder=dashboard_builder,
        dashboard_output_root=dashboard_output_root,
    )
    return S23MorningDecisionRunResult(
        session_directory=session_directory,
        timeline_json=primary_timeline_json,
        timeline_markdown=primary_timeline_markdown,
        final_summary_json=final_summary_json,
        final_summary_markdown=final_summary_markdown,
        stage_runs=tuple(stage_runs),
        branch_final_summary_json=branch_final_summary_json,
        branch_final_summary_markdown=branch_final_summary_markdown,
        branch_position_state_json=branch_position_state_json,
    )


__all__ = [
    "S23MorningDecisionCheckpoint",
    "S23MorningDecisionRunResult",
    "S23MorningDecisionStageRun",
    "default_morning_decision_checkpoints",
    "run_s23_morning_supervised_decision",
]


def _build_dashboard_builder(
    *,
    artifact_root: str | Path,
    strategy_path: str | Path,
    reference_packet_path: str | Path,
    session_id_prefix: str,
) -> object:
    from tfis.dashboard import StrategyDashboardConfig, TfisOperatorDashboardBuilder

    strategy_rule = load_strategy_rule(strategy_path)
    return TfisOperatorDashboardBuilder(
        strategy_configs=(
            StrategyDashboardConfig(
                strategy_code=strategy_rule.strategy_code,
                display_name=f"{strategy_rule.strategy_code} Operator Dashboard",
                artifact_root=Path(artifact_root),
                strategy_path=Path(strategy_path),
                reference_packet_path=Path(reference_packet_path),
                session_id_prefix=session_id_prefix,
            ),
        )
    )


def _rebuild_dashboard(
    *,
    dashboard_builder: object,
    dashboard_output_root: str | Path | None,
) -> None:
    if dashboard_output_root is None:
        return
    dashboard_builder.build(output_root=Path(dashboard_output_root))
