from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PaperMorningSupervisedTaskSpec:
    task_name: str
    repo_root: Path
    tfis_root: Path
    config_path: Path
    strategy_path: Path
    reference_packet_path: Path
    artifact_root: Path
    session_id_prefix: str
    runner_script_path: Path
    wrapper_script_path: Path
    timezone_name: str = "Asia/Kolkata"
    if_past: str = "run_now"
    skip_refresh: bool = False
    enable_smoke_override: bool = False
    carry_forward_state_dir: Path | None = None
    python_executable: Path = Path(sys.executable)


class PaperMorningSupervisedTargetMetadata(Protocol):
    strategy_code: str
    config_path: Path
    strategy_path: Path | None
    reference_packet_path: Path | None
    artifact_root: Path
    session_id_prefix: str | None
    runner_script_path: Path | None
    wrapper_script_path: Path | None


def build_paper_morning_task_spec_from_target(
    *,
    target: PaperMorningSupervisedTargetMetadata,
    repo_root: Path,
    tfis_root: Path,
    carry_forward_state_dir: Path | None = None,
) -> PaperMorningSupervisedTaskSpec | None:
    if (
        target.strategy_path is None
        or target.reference_packet_path is None
        or not target.session_id_prefix
        or target.runner_script_path is None
        or target.wrapper_script_path is None
    ):
        return None
    return PaperMorningSupervisedTaskSpec(
        task_name=f"TFIS {target.strategy_code.upper()} Morning Supervised Decision",
        repo_root=repo_root,
        tfis_root=tfis_root,
        config_path=target.config_path,
        strategy_path=target.strategy_path,
        reference_packet_path=target.reference_packet_path,
        artifact_root=target.artifact_root,
        session_id_prefix=target.session_id_prefix,
        runner_script_path=target.runner_script_path,
        wrapper_script_path=target.wrapper_script_path,
        skip_refresh=True,
        carry_forward_state_dir=carry_forward_state_dir,
    )


def build_paper_morning_runner_arguments(
    spec: PaperMorningSupervisedTaskSpec,
) -> tuple[str, ...]:
    args: list[str] = [
        str(spec.python_executable),
        str(spec.runner_script_path),
        "--tfis-root",
        str(spec.tfis_root),
        "--config",
        str(spec.config_path),
        "--strategy-path",
        str(spec.strategy_path),
        "--reference-packet",
        str(spec.reference_packet_path),
        "--artifact-root",
        str(spec.artifact_root),
        "--session-id-prefix",
        spec.session_id_prefix,
        "--timezone",
        spec.timezone_name,
        "--if-past",
        spec.if_past,
    ]
    if spec.skip_refresh:
        args.append("--skip-refresh")
    if spec.enable_smoke_override:
        args.append("--enable-smoke-override")
    if spec.carry_forward_state_dir is not None:
        args.extend(["--carry-forward-state-dir", str(spec.carry_forward_state_dir)])
    return tuple(args)


def build_paper_morning_wrapper_command(
    spec: PaperMorningSupervisedTaskSpec,
) -> str:
    command = (
        f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{spec.wrapper_script_path}" '
        f'-TfisRoot "{spec.tfis_root}" '
        f'-Config "{spec.config_path}" '
        f'-StrategyPath "{spec.strategy_path}" '
        f'-ReferencePacket "{spec.reference_packet_path}" '
        f'-ArtifactRoot "{spec.artifact_root}" '
        f'-SessionIdPrefix "{spec.session_id_prefix}" '
        f'-Timezone "{spec.timezone_name}" '
        f'-IfPast "{spec.if_past}"'
    )
    if spec.skip_refresh:
        command += " -SkipRefresh"
    if spec.enable_smoke_override:
        command += " -EnableSmokeOverride"
    if spec.carry_forward_state_dir is not None:
        command += f' -CarryForwardStateDir "{spec.carry_forward_state_dir}"'
    return command


S23MorningSupervisedTaskSpec = PaperMorningSupervisedTaskSpec


def build_s23_morning_runner_arguments(
    spec: PaperMorningSupervisedTaskSpec,
) -> tuple[str, ...]:
    return build_paper_morning_runner_arguments(spec)


def build_s23_morning_wrapper_command(
    spec: PaperMorningSupervisedTaskSpec,
) -> str:
    return build_paper_morning_wrapper_command(spec)


__all__ = [
    "PaperMorningSupervisedTaskSpec",
    "build_paper_morning_task_spec_from_target",
    "build_paper_morning_runner_arguments",
    "build_paper_morning_wrapper_command",
    "S23MorningSupervisedTaskSpec",
    "build_s23_morning_runner_arguments",
    "build_s23_morning_wrapper_command",
]
