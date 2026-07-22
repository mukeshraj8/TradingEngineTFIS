from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PaperRuntimeControlState:
    control_root: Path
    global_pause_active: bool
    paused_strategies: frozenset[str]

    def strategy_paused(self, strategy_code: str) -> bool:
        return self.global_pause_active or strategy_code.strip().upper() in self.paused_strategies


@dataclass(frozen=True)
class PaperRuntimeControlEvent:
    action: str
    occurred_at: str
    scope: str
    strategy_code: str | None
    reason: str | None
    actor: str | None
    marker_path: str | None


def paper_runtime_control_root(repo_root: Path | str) -> Path:
    return Path(repo_root).resolve() / "tmp" / "operator_controls"


def global_pause_marker_path(control_root: Path | str) -> Path:
    return Path(control_root).resolve() / "global_pause.json"


def strategy_pause_marker_path(control_root: Path | str, strategy_code: str) -> Path:
    normalized_code = strategy_code.strip().upper()
    if not normalized_code:
        raise ValueError("strategy_code must not be blank")
    return Path(control_root).resolve() / f"strategy_{normalized_code}.pause.json"


def operator_control_event_log_path(control_root: Path | str) -> Path:
    return Path(control_root).resolve() / "operator_control_events.jsonl"


def load_paper_runtime_control_state(repo_root: Path | str) -> PaperRuntimeControlState:
    return load_paper_runtime_control_state_from_root(paper_runtime_control_root(repo_root))


def load_paper_runtime_control_state_from_root(control_root: Path | str) -> PaperRuntimeControlState:
    control_root = Path(control_root).resolve()
    paused_strategies: set[str] = set()
    for marker in control_root.glob("strategy_*.pause.json"):
        name = marker.name
        if not name.startswith("strategy_") or not name.endswith(".pause.json"):
            continue
        strategy_code = name[len("strategy_") : -len(".pause.json")].strip().upper()
        if strategy_code:
            paused_strategies.add(strategy_code)
    return PaperRuntimeControlState(
        control_root=control_root,
        global_pause_active=global_pause_marker_path(control_root).exists(),
        paused_strategies=frozenset(sorted(paused_strategies)),
    )


def load_latest_operator_control_event(repo_root: Path | str) -> PaperRuntimeControlEvent | None:
    return load_latest_operator_control_event_from_root(paper_runtime_control_root(repo_root))


def load_latest_operator_control_event_from_root(control_root: Path | str) -> PaperRuntimeControlEvent | None:
    event_log = operator_control_event_log_path(control_root)
    if not event_log.exists():
        return None
    latest_payload: dict[str, Any] | None = None
    for raw_line in event_log.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            latest_payload = payload
    if latest_payload is None:
        return None
    strategy_code = latest_payload.get("strategy_code")
    normalized_strategy_code = (
        str(strategy_code).strip().upper()
        if strategy_code is not None and str(strategy_code).strip()
        else None
    )
    return PaperRuntimeControlEvent(
        action=str(latest_payload.get("action", "")).strip().upper() or "UNKNOWN",
        occurred_at=str(latest_payload.get("occurred_at", "")).strip() or "unknown",
        scope=str(latest_payload.get("scope", "")).strip().upper() or "UNKNOWN",
        strategy_code=normalized_strategy_code,
        reason=_optional_str(latest_payload.get("reason")),
        actor=_optional_str(latest_payload.get("actor")),
        marker_path=_optional_str(latest_payload.get("marker_path")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
