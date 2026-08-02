from __future__ import annotations

import copy
import pytest

from tfis.adapters.phase5e import s22_reliance as s22


def test_s22_reliance_sunday_capture_is_not_trading_session() -> None:
    fixture = s22._load_fixture(s22.FIXTURE_PATH)
    result = s22._time_semantics(fixture)
    market_structure = s22._market_structure(fixture)

    assert result["capture_timestamp"].startswith("2026-08-02")
    assert result["capture_calendar_day"] == "Sunday"
    assert result["capture_is_exchange_session"] is False
    assert result["latest_completed_nse_trading_session"] == "2026-07-31"
    assert result["target_internal_paper_evaluation_date"] == "2026-08-03"
    assert market_structure["sunday_candle_included"] is False
    assert market_structure["references"] == {
        "2DHH": "1309.7",
        "2DLL": "1275.3",
        "4DHH": "1309.7",
        "4DLL": "1265.9",
    }


def test_s22_reliance_monthly_status_uses_generic_lookback_resolution() -> None:
    fixture = s22._load_fixture(s22.FIXTURE_PATH)
    result = s22._monthly_status_report(fixture)

    assert result["monthly_status"] == "BEAR_CF"
    assert result["current_window_direct_status"] == "UNKNOWN"
    assert result["borrowed_window_status"] == "BEAR_CF"
    assert result["lookback_used"] is True
    assert result["source_rule_id"] == s22.MONTHLY_STATUS_RULE_ID


def test_s22_reliance_insufficient_monthly_data_fails_closed() -> None:
    fixture = copy.deepcopy(s22._load_fixture(s22.FIXTURE_PATH))
    fixture["history"]["payload"]["candles"] = fixture["history"]["payload"]["candles"][-1:]

    with pytest.raises(ValueError):
        s22._monthly_status_report(fixture)
