from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from tfis.runtime.multi_strategy.live_observation import _classify_window


IST = ZoneInfo("Asia/Calcutta")


def test_classify_window_marks_past_opening_as_missed_for_late_start() -> None:
    now = datetime(2026, 8, 3, 9, 45, tzinfo=IST)
    started = datetime(2026, 8, 3, 9, 45, tzinfo=IST)

    assert _classify_window(now, started, time(9, 15)) == "MISSED_BEFORE_SUPERVISOR_START"
    assert _classify_window(now, started, time(9, 24, 59, 400000)) == "MISSED_BEFORE_SUPERVISOR_START"
    assert _classify_window(now, started, time(15, 0)) == "FUTURE_WINDOW"
