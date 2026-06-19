from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True, slots=True)
class S23MorningSupervisedTaskSpec:
    task_name: str
    repo_root: Path
    tfis_root: Path
    config_path: Path
    strategy_path: Path
    reference_packet_path: Path
    artifact_root: Path
    session_id_prefix: str
    timezone_name: str = "Asia/Kolkata"
    if_past: str = "run_now"
    skip_refresh: bool = False
    enable_smoke_override: bool = False
    carry_forward_state_dir: Path | None = None
    python_executable: Path = Path(sys.executable)


def build_s23_morning_runner_arguments(
    spec: S23MorningSupervisedTaskSpec,
) -> tuple[str, ...]:
    script_path = spec.repo_root / "scripts" / "run_s23_fyers_0916_supervised_decision.py"
    args: list[str] = [
        str(spec.python_executable),
        str(script_path),
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


def build_s23_morning_wrapper_command(
    spec: S23MorningSupervisedTaskSpec,
) -> str:
    wrapper_path = spec.repo_root / "scripts" / "start_s23_fyers_morning_supervised_decision.ps1"
    command = (
        f'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "{wrapper_path}" '
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


__all__ = [
    "S23MorningSupervisedTaskSpec",
    "build_s23_morning_runner_arguments",
    "build_s23_morning_wrapper_command",
]
