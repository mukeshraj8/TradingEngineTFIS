from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Callable

from tfis.importers import load_strategy_rule

from .fyers_snapshot_collector import S23FyersSnapshotArtifactSet, S23FyersSnapshotCollector
from .live_decision import S23PaperLiveDecisionBuilder
from .live_ingress import S23LivePaperIngressConfig
from .live_decision_runner import prepare_fyers_env_from_tradingengine
from .live_decision_schedule import build_schedule_note, compute_schedule_delay_seconds
from .live_decision_timeline import (
    S23LiveDecisionTimelineBuilder,
    S23LiveDecisionTimelineResult,
    S23LiveDecisionTimelineStage,
)
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
    checkpoint: S23MorningDecisionCheckpoint
    initial_check_time: str
    trigger_time: str
    delay_seconds: float
    schedule_note: str
    snapshot_session_directory: str
    stage: S23LiveDecisionTimelineStage


@dataclass(frozen=True, slots=True)
class S23MorningDecisionRunResult:
    session_directory: Path
    timeline_json: Path
    timeline_markdown: Path
    final_summary_json: Path | None
    final_summary_markdown: Path | None
    stage_runs: tuple[S23MorningDecisionStageRun, ...]


def default_morning_decision_checkpoints() -> tuple[S23MorningDecisionCheckpoint, ...]:
    return (
        S23MorningDecisionCheckpoint("Opening Snapshot", 9, 16),
        S23MorningDecisionCheckpoint("ORPT Snapshot", 9, 25),
        S23MorningDecisionCheckpoint("RC Snapshot", 9, 30),
    )


def run_s23_morning_supervised_decision(
    *,
    tradingengine_root: str | Path,
    config_path: str | Path,
    strategy_path: str | Path,
    reference_packet_path: str | Path,
    artifact_root: str | Path,
    session_id_prefix: str,
    checkpoints: tuple[S23MorningDecisionCheckpoint, ...] | None = None,
    carry_forward_state_dir: str | Path | None = None,
    enable_smoke_override: bool = False,
    skip_refresh: bool = False,
    timezone_name: str = "Asia/Kolkata",
    if_past: str = "run_now",
    now_provider: Callable[[], datetime] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> S23MorningDecisionRunResult:
    from zoneinfo import ZoneInfo
    import time as time_module

    timezone = ZoneInfo(timezone_name)
    now_fn = now_provider or (lambda: datetime.now(timezone))
    sleep_fn = sleeper or time_module.sleep
    stage_checkpoints = checkpoints or default_morning_decision_checkpoints()

    prepare_fyers_env_from_tradingengine(
        tradingengine_root=tradingengine_root,
        skip_refresh=skip_refresh,
    )
    strategy_rule = load_strategy_rule(strategy_path)
    ingress_config = S23LivePaperIngressConfig.from_yaml(config_path)
    reference_packet = load_s23_decision_reference_packet(reference_packet_path)
    collector = S23FyersSnapshotCollector(artifact_root=artifact_root)
    decision_builder = S23PaperLiveDecisionBuilder()
    timeline_builder = S23LiveDecisionTimelineBuilder(decision_builder=decision_builder)
    carry_forward_position = (
        S23PaperPositionStateStore().load_state(carry_forward_state_dir)
        if carry_forward_state_dir is not None
        else None
    )

    session_directory: Path | None = None
    final_summary_json: Path | None = None
    final_summary_markdown: Path | None = None
    stage_runs: list[S23MorningDecisionStageRun] = []
    timeline_stages: list[S23LiveDecisionTimelineStage] = []
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
            strategy_path=strategy_path,
            carry_forward_state_dir=carry_forward_state_dir,
            session_id=session_id,
            adapter=None,
        )
        if snapshot_artifacts.collected_inputs is None:
            raise RuntimeError("Snapshot collector did not return collected inputs.")
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
        )
        timeline_stages.append(stage_build.stage)
        stage_runs.append(
            S23MorningDecisionStageRun(
                checkpoint=checkpoint,
                initial_check_time=now.isoformat(),
                trigger_time=trigger_time.isoformat(),
                delay_seconds=delay_seconds,
                schedule_note=note,
                snapshot_session_directory=str(snapshot_artifacts.session_directory),
                stage=stage_build.stage,
            )
        )
        if session_directory is None:
            session_directory = snapshot_artifacts.session_directory.parent / f"{session_id_prefix}-{trigger_time.strftime('%Y-%m-%d')}"
            session_directory.mkdir(parents=True, exist_ok=True)
        if stage_build.decision_result is not None:
            final_summary_json, final_summary_markdown = decision_builder.write_artifacts(
                stage_build.decision_result,
                output_dir=session_directory,
            )
        last_snapshot_artifacts = snapshot_artifacts

    if session_directory is None or last_snapshot_artifacts is None:
        raise RuntimeError("Morning supervised decision run did not capture any stages.")

    timeline_result = timeline_builder.build_timeline(
        session_date=last_snapshot_artifacts.summary.session_date,
        strategy_rule=strategy_rule,
        strategy_branch=reference_packet.strategy_branch or strategy_rule.unique_code,
        stages=tuple(timeline_stages),
    )
    timeline_json, timeline_markdown = timeline_builder.write_artifacts(
        timeline_result,
        output_dir=session_directory,
    )
    metadata_path = session_directory / "scheduled_run_metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "timezone": timezone_name,
                "if_past": if_past,
                "session_directory": str(session_directory),
                "timeline_json": str(timeline_json),
                "timeline_markdown": str(timeline_markdown),
                "final_summary_json": str(final_summary_json) if final_summary_json is not None else None,
                "final_summary_markdown": str(final_summary_markdown) if final_summary_markdown is not None else None,
                "stages": [
                    {
                        "stage_name": stage_run.checkpoint.stage_name,
                        "target_hour": stage_run.checkpoint.target_hour,
                        "target_minute": stage_run.checkpoint.target_minute,
                        "initial_check_time": stage_run.initial_check_time,
                        "trigger_time": stage_run.trigger_time,
                        "delay_seconds": stage_run.delay_seconds,
                        "schedule_note": stage_run.schedule_note,
                        "snapshot_session_directory": stage_run.snapshot_session_directory,
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
    return S23MorningDecisionRunResult(
        session_directory=session_directory,
        timeline_json=timeline_json,
        timeline_markdown=timeline_markdown,
        final_summary_json=final_summary_json,
        final_summary_markdown=final_summary_markdown,
        stage_runs=tuple(stage_runs),
    )


__all__ = [
    "S23MorningDecisionCheckpoint",
    "S23MorningDecisionRunResult",
    "S23MorningDecisionStageRun",
    "default_morning_decision_checkpoints",
    "run_s23_morning_supervised_decision",
]
