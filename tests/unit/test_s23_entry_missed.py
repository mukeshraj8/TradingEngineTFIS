from __future__ import annotations

from datetime import datetime

import pytest

from tfis.backtest import EntryMissedInput, IntradaySnapshot, S23EntryMissedDetector
from tfis.domain.enums import OptionType


def _orpt_snapshot(*, option_low: float | None) -> IntradaySnapshot:
    return IntradaySnapshot(
        timestamp=datetime(2026, 5, 23, 9, 24, 59),
        spot_low=22120.0,
        spot_high=22380.0,
        option_low=option_low,  # type: ignore[arg-type]
        option_high=228.0,
    )


def test_call_sell_entry_is_missed_when_option_low_is_below_entry() -> None:
    result = S23EntryMissedDetector().detect(
        EntryMissedInput(
            option_type=OptionType.CALL,
            entry_price=203.5,
            orpt_snapshot=_orpt_snapshot(option_low=202.0),
        )
    )

    assert result.entry_missed is True
    assert result.rule_name == "S23_OPTIONS_SELL_ORPT_OPTION_LOW_CHECK_V1"
    assert result.compared_value == pytest.approx(202.0)
    assert result.threshold_entry_price == pytest.approx(203.5)
    assert any("2026-05-23T09:24:59" in note for note in result.notes)


@pytest.mark.parametrize("option_low", [203.5, 205.0])
def test_call_sell_entry_is_not_missed_when_option_low_is_equal_or_above_entry(
    option_low: float,
) -> None:
    result = S23EntryMissedDetector().detect(
        EntryMissedInput(
            option_type=OptionType.CALL,
            entry_price=203.5,
            orpt_snapshot=_orpt_snapshot(option_low=option_low),
        )
    )

    assert result.entry_missed is False


def test_put_sell_entry_is_missed_when_option_low_is_below_entry() -> None:
    result = S23EntryMissedDetector().detect(
        EntryMissedInput(
            option_type=OptionType.PUT,
            entry_price=186.85,
            orpt_snapshot=_orpt_snapshot(option_low=180.0),
        )
    )

    assert result.entry_missed is True
    assert result.compared_value == pytest.approx(180.0)
    assert result.threshold_entry_price == pytest.approx(186.85)


@pytest.mark.parametrize("option_low", [186.85, 190.0])
def test_put_sell_entry_is_not_missed_when_option_low_is_equal_or_above_entry(
    option_low: float,
) -> None:
    result = S23EntryMissedDetector().detect(
        EntryMissedInput(
            option_type=OptionType.PUT,
            entry_price=186.85,
            orpt_snapshot=_orpt_snapshot(option_low=option_low),
        )
    )

    assert result.entry_missed is False


def test_missing_option_low_fails_clearly() -> None:
    with pytest.raises(
        ValueError,
        match="ORPT option_low is required for S23 entry-missed detection.",
    ):
        S23EntryMissedDetector().detect(
            EntryMissedInput(
                option_type=OptionType.CALL,
                entry_price=203.5,
                orpt_snapshot=_orpt_snapshot(option_low=None),
            )
        )
