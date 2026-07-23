from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .lifecycle_runtime_config import PaperLifecycleRuntimeConfig
from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs
from .order_state import (
    PaperOrderStateDiscovery,
    paper_order_is_terminal,
    paper_order_is_waiting_for_trigger,
)


@dataclass(frozen=True, slots=True)
class PaperRuntimeWaitingOrderStatus:
    strategy_code: str
    status: str
    session_date: date
    total_order_count: int
    waiting_order_count: int
    current_session_waiting_order_count: int
    stale_waiting_order_count: int
    terminal_order_count: int
    latest_stale_order_directory: str | None
    message: str


def load_paper_runtime_waiting_order_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: Path,
    session_date: date | None = None,
) -> tuple[PaperRuntimeWaitingOrderStatus, ...]:
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=repo_root)
    statuses: list[PaperRuntimeWaitingOrderStatus] = []
    for spec in specs:
        try:
            runtime_config = PaperLifecycleRuntimeConfig.from_yaml(spec.config_path)
            effective_session_date = session_date or datetime.now(
                ZoneInfo(runtime_config.broker.timezone)
            ).date()
            statuses.append(
                _load_strategy_waiting_order_status(
                    strategy_code=spec.strategy_code,
                    artifact_root=spec.artifact_root,
                    session_date=effective_session_date,
                )
            )
        except Exception as exc:
            fallback_session_date = session_date or date.today()
            statuses.append(
                PaperRuntimeWaitingOrderStatus(
                    strategy_code=spec.strategy_code,
                    status="FAIL",
                    session_date=fallback_session_date,
                    total_order_count=0,
                    waiting_order_count=0,
                    current_session_waiting_order_count=0,
                    stale_waiting_order_count=1,
                    terminal_order_count=0,
                    latest_stale_order_directory=None,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(statuses)


def _load_strategy_waiting_order_status(
    *,
    strategy_code: str,
    artifact_root: Path,
    session_date: date,
) -> PaperRuntimeWaitingOrderStatus:
    candidates = PaperOrderStateDiscovery().find_orders((artifact_root,), strategy_code=strategy_code)
    total_order_count = len(candidates)
    waiting_dirs: list[Path] = []
    current_waiting_dirs: list[Path] = []
    stale_waiting_dirs: list[Path] = []
    terminal_order_count = 0
    for candidate in candidates:
        state = candidate.state
        if paper_order_is_terminal(state.status):
            terminal_order_count += 1
        if not paper_order_is_waiting_for_trigger(state.status):
            continue
        waiting_dirs.append(candidate.state_directory)
        if state.entry_date == session_date:
            current_waiting_dirs.append(candidate.state_directory)
        elif state.entry_date < session_date:
            stale_waiting_dirs.append(candidate.state_directory)
        else:
            stale_waiting_dirs.append(candidate.state_directory)
    latest_stale = str(sorted(stale_waiting_dirs)[-1]) if stale_waiting_dirs else None
    status = "FAIL" if stale_waiting_dirs else "PASS"
    message = (
        "no stale waiting paper orders found"
        if not stale_waiting_dirs
        else (
            f"{len(stale_waiting_dirs)} stale/future waiting paper order(s) require finalizer "
            "or operator review before runtime start"
        )
    )
    return PaperRuntimeWaitingOrderStatus(
        strategy_code=strategy_code,
        status=status,
        session_date=session_date,
        total_order_count=total_order_count,
        waiting_order_count=len(waiting_dirs),
        current_session_waiting_order_count=len(current_waiting_dirs),
        stale_waiting_order_count=len(stale_waiting_dirs),
        terminal_order_count=terminal_order_count,
        latest_stale_order_directory=latest_stale,
        message=message,
    )


__all__ = [
    "PaperRuntimeWaitingOrderStatus",
    "load_paper_runtime_waiting_order_statuses",
]
