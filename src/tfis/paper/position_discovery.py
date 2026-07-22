from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .position_state import (
    PaperPositionState,
    PaperPositionStateStore,
    PaperPositionStateStatus,
    paper_position_is_active,
    paper_position_blocks_new_entry,
)


@dataclass(frozen=True, slots=True)
class S23OpenPaperPositionCandidate:
    state_directory: Path
    state_path: Path
    state: PaperPositionState
    modified_timestamp: float


@dataclass(frozen=True, slots=True)
class S23TerminalPaperPositionSnapshot:
    state_directory: Path
    state_path: Path
    strategy_code: str
    lifecycle_status: str
    last_updated_timestamp: datetime | None
    modified_timestamp: float


class S23OpenPaperPositionDiscovery:
    def __init__(
        self,
        *,
        state_store: PaperPositionStateStore | None = None,
        state_filename: str = "paper_position_state.json",
    ) -> None:
        self._state_store = state_store or PaperPositionStateStore()
        self._state_filename = state_filename

    def find_open_positions(
        self,
        roots: tuple[str | Path, ...],
    ) -> tuple[S23OpenPaperPositionCandidate, ...]:
        return self._find_candidates(
            roots,
            predicate=lambda state: (
                paper_position_is_active(state.lifecycle_status)
                and state.carry_forward_allowed
            ),
        )

    def find_latest_open_position(
        self,
        roots: tuple[str | Path, ...],
    ) -> S23OpenPaperPositionCandidate | None:
        candidates = self.find_open_positions(roots)
        return candidates[0] if candidates else None

    def find_positions_blocking_new_entry(
        self,
        roots: tuple[str | Path, ...],
    ) -> tuple[S23OpenPaperPositionCandidate, ...]:
        return self._find_candidates(
            roots,
            predicate=lambda state: (
                paper_position_blocks_new_entry(state.lifecycle_status)
                or state.lifecycle_status
                is PaperPositionStateStatus.PAPER_REVERSE_ENTRY_REQUIRED
            ),
        )

    def find_latest_terminal_position(
        self,
        roots: tuple[str | Path, ...],
        *,
        strategy_code: str | None = None,
    ) -> S23TerminalPaperPositionSnapshot | None:
        candidates: list[S23TerminalPaperPositionSnapshot] = []
        normalized_strategy_code = (
            str(strategy_code).strip().upper() if strategy_code is not None else None
        )
        for root in roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            paths = (
                (root_path,)
                if root_path.name == self._state_filename and root_path.is_file()
                else tuple(root_path.rglob(self._state_filename))
            )
            for state_path in paths:
                state_dir = state_path.parent
                try:
                    payload = json.loads(state_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(payload, dict):
                    continue
                payload_strategy_code = str(payload.get("strategy_code") or "").strip()
                if (
                    normalized_strategy_code is not None
                    and payload_strategy_code.upper() != normalized_strategy_code
                ):
                    continue
                lifecycle_status = str(payload.get("lifecycle_status") or "").strip()
                if not lifecycle_status or paper_position_is_active(lifecycle_status):
                    continue
                timestamp = _parse_datetime(
                    payload.get("last_updated_timestamp")
                    or payload.get("entry_timestamp")
                    or ""
                )
                candidates.append(
                    S23TerminalPaperPositionSnapshot(
                        state_directory=state_dir,
                        state_path=state_path,
                        strategy_code=payload_strategy_code,
                        lifecycle_status=lifecycle_status,
                        last_updated_timestamp=timestamp,
                        modified_timestamp=state_path.stat().st_mtime,
                    )
                )
        return (
            sorted(
                candidates,
                key=lambda item: (
                    item.last_updated_timestamp or datetime.min,
                    item.modified_timestamp,
                ),
                reverse=True,
            )[0]
            if candidates
            else None
        )

    def _find_candidates(
        self,
        roots: tuple[str | Path, ...],
        *,
        predicate,
    ) -> tuple[S23OpenPaperPositionCandidate, ...]:
        candidates: list[S23OpenPaperPositionCandidate] = []
        for root in roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            paths = (
                (root_path,)
                if root_path.name == self._state_filename and root_path.is_file()
                else tuple(root_path.rglob(self._state_filename))
            )
            for state_path in paths:
                state_dir = state_path.parent
                try:
                    state = self._state_store.load_state(state_dir)
                except Exception:
                    continue
                if not predicate(state):
                    continue
                candidates.append(
                    S23OpenPaperPositionCandidate(
                        state_directory=state_dir,
                        state_path=state_path,
                        state=state,
                        modified_timestamp=state_path.stat().st_mtime,
                    )
                )
        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.state.last_updated_timestamp,
                    item.modified_timestamp,
                ),
                reverse=True,
            )
        )


__all__ = [
    "PaperOpenPositionCandidate",
    "PaperOpenPositionDiscovery",
    "S23OpenPaperPositionCandidate",
    "S23OpenPaperPositionDiscovery",
    "PaperTerminalPositionSnapshot",
    "S23TerminalPaperPositionSnapshot",
]


PaperOpenPositionCandidate = S23OpenPaperPositionCandidate
PaperOpenPositionDiscovery = S23OpenPaperPositionDiscovery
PaperTerminalPositionSnapshot = S23TerminalPaperPositionSnapshot


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
