from __future__ import annotations

from datetime import datetime, timedelta


class S23LiveDecisionScheduleError(RuntimeError):
    """Raised when a scheduled live-decision run cannot proceed safely."""


def compute_schedule_delay_seconds(
    *,
    now: datetime,
    target_hour: int,
    target_minute: int,
    if_past: str = "run_now",
) -> float:
    mode = str(if_past or "run_now").strip().lower()
    if mode not in {"run_now", "abort"}:
        raise S23LiveDecisionScheduleError(
            f"Unsupported if_past mode: {if_past!r}. Expected 'run_now' or 'abort'."
        )

    target = now.replace(
        hour=int(target_hour),
        minute=int(target_minute),
        second=0,
        microsecond=0,
    )
    if now <= target:
        return max(0.0, (target - now).total_seconds())
    if mode == "run_now":
        return 0.0
    raise S23LiveDecisionScheduleError(
        f"Scheduled decision time {target_hour:02d}:{target_minute:02d} has already passed for {now.date().isoformat()}."
    )


def build_schedule_note(
    *,
    now: datetime,
    target_hour: int,
    target_minute: int,
    delay_seconds: float,
) -> str:
    if delay_seconds <= 0:
        return (
            f"Scheduled run time {target_hour:02d}:{target_minute:02d} is already due; "
            f"running immediately at {now.isoformat()}."
        )
    scheduled_for = now + timedelta(seconds=delay_seconds)
    return (
        f"Waiting until {scheduled_for.isoformat()} "
        f"({target_hour:02d}:{target_minute:02d} local) before collecting the supervised S23 snapshot."
    )


__all__ = [
    "S23LiveDecisionScheduleError",
    "build_schedule_note",
    "compute_schedule_delay_seconds",
]
