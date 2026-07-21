from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .fresh_entry_promotion import (
    PaperFreshEntryPromotionError,
    PaperFreshEntryPromotionSummary,
    promote_blocked_fresh_entries,
)


@dataclass(frozen=True, slots=True)
class PaperFreshEntryHandoffResult:
    action: str
    marker_path: Path
    runner_name: str | None = None
    pid: int | None = None
    promotion_summary: PaperFreshEntryPromotionSummary | None = None


def fresh_decision_launch_marker_path(
    session_directory: str | Path,
    *,
    marker_filename: str = "fresh_decision_launch.json",
) -> Path:
    return Path(session_directory) / marker_filename


def handoff_fresh_entry_requirement(
    *,
    strategy_code: str,
    session_directory: str | Path,
    session_date: date,
    trade_id: str,
    final_step_status: str,
    evaluated_at: datetime,
    artifact_root: str | Path,
    session_id_prefix: str | None,
    marker_filename: str = "fresh_decision_launch.json",
    promotion_loader: Callable[..., PaperFreshEntryPromotionSummary] = promote_blocked_fresh_entries,
    runner_name: str | None = None,
    spawn_runner: Callable[[], int | None] | None = None,
) -> PaperFreshEntryHandoffResult:
    marker_path = fresh_decision_launch_marker_path(
        session_directory,
        marker_filename=marker_filename,
    )
    if final_step_status != "PAPER_POSITION_FRESH_ENTRY_REQUIRED":
        return PaperFreshEntryHandoffResult(
            action="not_required",
            marker_path=marker_path,
        )
    if marker_path.exists():
        return PaperFreshEntryHandoffResult(
            action="already_recorded",
            marker_path=marker_path,
        )
    if session_id_prefix:
        try:
            summary = promotion_loader(
                artifact_root,
                session_date=session_date,
                created_at=evaluated_at,
                session_id_prefix=session_id_prefix,
            )
        except PaperFreshEntryPromotionError:
            pass
        else:
            _write_marker(
                marker_path,
                {
                    "launched_at": evaluated_at.isoformat(),
                    "strategy_code": strategy_code,
                    "trade_id": trade_id,
                    "mode": "promoted_existing_blocked_decision",
                    "promoted_session_dir": str(summary.session_dir),
                    "promotions": [
                        {
                            "branch": item.branch,
                            "status": item.status,
                            "order_state_json": item.order_state_json,
                        }
                        for item in summary.promotions
                    ],
                },
            )
            return PaperFreshEntryHandoffResult(
                action="promoted_existing_blocked_decision",
                marker_path=marker_path,
                promotion_summary=summary,
            )
    if runner_name is None or spawn_runner is None:
        return PaperFreshEntryHandoffResult(
            action="launch_unavailable",
            marker_path=marker_path,
        )
    pid = spawn_runner()
    _write_marker(
        marker_path,
        {
            "launched_at": evaluated_at.isoformat(),
            "strategy_code": strategy_code,
            "trade_id": trade_id,
            "runner_script": runner_name,
            "pid": pid,
        },
    )
    return PaperFreshEntryHandoffResult(
        action="spawned_fresh_supervised_runner",
        marker_path=marker_path,
        runner_name=runner_name,
        pid=pid,
    )


def _write_marker(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


__all__ = [
    "PaperFreshEntryHandoffResult",
    "fresh_decision_launch_marker_path",
    "handoff_fresh_entry_requirement",
]
