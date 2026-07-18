from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from .order_state import PaperOrderState, PaperOrderStateStore, paper_order_is_waiting_for_trigger
from .position_discovery import PaperOpenPositionDiscovery
from .position_state import PaperPositionState


@dataclass(frozen=True, slots=True)
class PaperLifecycleSupervisorTargetSpec:
    strategy_code: str
    config_path: Path
    artifact_root: Path
    process_lock_root: Path
    strategy_path: Path | None = None
    reference_packet_path: Path | None = None
    session_id_prefix: str | None = None
    executor: str | None = None


@dataclass(frozen=True, slots=True)
class PaperLifecycleSupervisorWatchTarget:
    spec: PaperLifecycleSupervisorTargetSpec
    mode: str
    directory: Path
    selected_contract_symbol: str
    session_date: date
    order_state: PaperOrderState | None = None
    position_state: PaperPositionState | None = None


def load_paper_lifecycle_supervisor_target_specs(
    config_path: str | Path,
    *,
    repo_root: Path,
) -> tuple[PaperLifecycleSupervisorTargetSpec, ...]:
    target = Path(config_path)
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Lifecycle supervisor target config must be a YAML object: {target}")
    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError(
            f"Lifecycle supervisor target config must contain a non-empty targets list: {target}"
        )

    specs: list[PaperLifecycleSupervisorTargetSpec] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            raise ValueError(f"Lifecycle supervisor target entry must be a mapping: {item!r}")
        specs.append(
            PaperLifecycleSupervisorTargetSpec(
                strategy_code=str(item["strategy_code"]).strip(),
                config_path=_resolve_repo_path(repo_root, item["config_path"]),
                artifact_root=_resolve_repo_path(repo_root, item["artifact_root"]),
                process_lock_root=_resolve_repo_path(repo_root, item["process_lock_root"]),
                strategy_path=(
                    _resolve_repo_path(repo_root, item["strategy_path"])
                    if item.get("strategy_path")
                    else None
                ),
                reference_packet_path=(
                    _resolve_repo_path(repo_root, item["reference_packet_path"])
                    if item.get("reference_packet_path")
                    else None
                ),
                session_id_prefix=(
                    str(item["session_id_prefix"]).strip()
                    if item.get("session_id_prefix")
                    else None
                ),
                executor=(
                    str(item["executor"]).strip()
                    if item.get("executor")
                    else None
                ),
            )
        )
    return tuple(specs)


class PaperLifecycleSupervisorTargetDiscovery:
    def __init__(
        self,
        *,
        order_store: PaperOrderStateStore | None = None,
        position_discovery: PaperOpenPositionDiscovery | None = None,
    ) -> None:
        self._order_store = order_store or PaperOrderStateStore()
        self._position_discovery = position_discovery or PaperOpenPositionDiscovery()

    def discover_targets(
        self,
        spec: PaperLifecycleSupervisorTargetSpec,
        *,
        effective_session_date: date,
    ) -> tuple[PaperLifecycleSupervisorWatchTarget, ...]:
        targets: list[PaperLifecycleSupervisorWatchTarget] = []
        state_directories: set[Path] = set()

        for candidate in self._position_discovery.find_open_positions((spec.artifact_root,)):
            if candidate.state.expiry_date < effective_session_date:
                continue
            state_directories.add(candidate.state_directory.resolve())
            targets.append(
                PaperLifecycleSupervisorWatchTarget(
                    spec=spec,
                    mode="state",
                    directory=candidate.state_directory.resolve(),
                    selected_contract_symbol=candidate.state.selected_contract_symbol,
                    session_date=effective_session_date,
                    position_state=candidate.state,
                )
            )

        for state_path in sorted(spec.artifact_root.rglob("paper_order_state.json")):
            directory = state_path.parent.resolve()
            if directory in state_directories:
                continue
            try:
                order_state = self._order_store.load_state(directory)
            except Exception:
                continue
            if not paper_order_is_waiting_for_trigger(order_state.status):
                continue
            if order_state.entry_date > effective_session_date:
                continue
            targets.append(
                PaperLifecycleSupervisorWatchTarget(
                    spec=spec,
                    mode="order",
                    directory=directory,
                    selected_contract_symbol=order_state.selected_contract_symbol,
                    session_date=effective_session_date,
                    order_state=order_state,
                )
            )

        return tuple(
            sorted(
                targets,
                key=lambda item: (
                    item.spec.strategy_code,
                    item.directory.as_posix(),
                    item.mode,
                ),
            )
        )


def _resolve_repo_path(repo_root: Path, value: object) -> Path:
    target = Path(str(value))
    if target.is_absolute():
        return target
    return (repo_root / target).resolve()


__all__ = [
    "PaperLifecycleSupervisorTargetDiscovery",
    "PaperLifecycleSupervisorTargetSpec",
    "PaperLifecycleSupervisorWatchTarget",
    "load_paper_lifecycle_supervisor_target_specs",
]
