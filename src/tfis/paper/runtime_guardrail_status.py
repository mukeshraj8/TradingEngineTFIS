from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .lifecycle_runtime_config import (
    load_paper_broker_runtime,
    validate_paper_lifecycle_runtime_guardrails,
)
from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs


@dataclass(frozen=True, slots=True)
class PaperRuntimeGuardrailStatus:
    strategy_code: str
    status: str
    source_mode: str | None
    paper_mode_enabled: bool | None
    no_live_orders_allowed: bool | None
    kill_switch_enabled: bool | None
    session_kill_switch_active: bool | None
    message: str


def load_paper_runtime_guardrail_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: Path,
) -> tuple[PaperRuntimeGuardrailStatus, ...]:
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=repo_root)
    statuses: list[PaperRuntimeGuardrailStatus] = []
    for spec in specs:
        try:
            runtime = load_paper_broker_runtime(spec.config_path)
            failures = validate_paper_lifecycle_runtime_guardrails(runtime.config)
        except Exception as exc:
            statuses.append(
                PaperRuntimeGuardrailStatus(
                    strategy_code=spec.strategy_code,
                    status="FAIL",
                    source_mode=None,
                    paper_mode_enabled=None,
                    no_live_orders_allowed=None,
                    kill_switch_enabled=None,
                    session_kill_switch_active=None,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        statuses.append(
            PaperRuntimeGuardrailStatus(
                strategy_code=spec.strategy_code,
                status="PASS" if not failures else "FAIL",
                source_mode=runtime.config.source_mode,
                paper_mode_enabled=runtime.config.paper.paper_mode_enabled,
                no_live_orders_allowed=runtime.config.paper.no_live_orders_allowed,
                kill_switch_enabled=runtime.config.paper.kill_switch_enabled,
                session_kill_switch_active=runtime.config.paper.session_kill_switch_active,
                message=(
                    "paper runtime guardrails confirmed"
                    if not failures
                    else "; ".join(failures)
                ),
            )
        )
    return tuple(statuses)
