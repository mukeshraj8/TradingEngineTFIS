from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .position_state import (
    S23PaperPositionState,
    S23PaperPositionStateStatus,
    S23PaperPositionStateStore,
)


_OPEN_STATUSES = {
    S23PaperPositionStateStatus.PAPER_POSITION_OPEN,
    S23PaperPositionStateStatus.PAPER_POSITION_CARRIED_FORWARD,
    S23PaperPositionStateStatus.PAPER_POSITION_RESUMED,
}


@dataclass(frozen=True, slots=True)
class S23OpenPaperPositionCandidate:
    state_directory: Path
    state_path: Path
    state: S23PaperPositionState
    modified_timestamp: float


class S23OpenPaperPositionDiscovery:
    def __init__(
        self,
        *,
        state_store: S23PaperPositionStateStore | None = None,
        state_filename: str = "paper_position_state.json",
    ) -> None:
        self._state_store = state_store or S23PaperPositionStateStore()
        self._state_filename = state_filename

    def find_open_positions(
        self,
        roots: tuple[str | Path, ...],
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
                if state.lifecycle_status not in _OPEN_STATUSES:
                    continue
                if not state.carry_forward_allowed:
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

    def find_latest_open_position(
        self,
        roots: tuple[str | Path, ...],
    ) -> S23OpenPaperPositionCandidate | None:
        candidates = self.find_open_positions(roots)
        return candidates[0] if candidates else None


__all__ = [
    "S23OpenPaperPositionCandidate",
    "S23OpenPaperPositionDiscovery",
]
