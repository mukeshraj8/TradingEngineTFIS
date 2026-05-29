from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from tfis.paper import (
    S23LiveDecisionScheduleError,
    build_schedule_note,
    compute_schedule_delay_seconds,
)


IST = ZoneInfo("Asia/Kolkata")


def test_compute_schedule_delay_seconds_before_target() -> None:
    now = datetime(2026, 5, 29, 9, 10, 0, tzinfo=IST)

    delay = compute_schedule_delay_seconds(
        now=now,
        target_hour=9,
        target_minute=16,
    )

    assert delay == 360.0


def test_compute_schedule_delay_seconds_runs_immediately_after_target_when_allowed() -> None:
    now = datetime(2026, 5, 29, 9, 20, 0, tzinfo=IST)

    delay = compute_schedule_delay_seconds(
        now=now,
        target_hour=9,
        target_minute=16,
        if_past="run_now",
    )

    assert delay == 0.0


def test_compute_schedule_delay_seconds_aborts_after_target_when_requested() -> None:
    now = datetime(2026, 5, 29, 9, 20, 0, tzinfo=IST)

    with pytest.raises(S23LiveDecisionScheduleError):
        compute_schedule_delay_seconds(
            now=now,
            target_hour=9,
            target_minute=16,
            if_past="abort",
        )


def test_build_schedule_note_mentions_wait_target() -> None:
    now = datetime(2026, 5, 29, 9, 10, 0, tzinfo=IST)

    note = build_schedule_note(
        now=now,
        target_hour=9,
        target_minute=16,
        delay_seconds=360.0,
    )

    assert "09:16" in note
    assert "Waiting until" in note
