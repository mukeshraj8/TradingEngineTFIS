from __future__ import annotations

import pytest

from tfis.domain.enums import MonthlyStatus
from tfis.monthly_status import (
    MonthlyStatusEngine,
    MonthlyStatusReferenceLevels,
)


def test_nifty_price_above_bull_trigger_but_below_bull_cf_is_bull() -> None:
    result = MonthlyStatusEngine().classify(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
                CML=91.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=101.0,
        ),
    )

    assert result.status == MonthlyStatus.BULL
    assert result.trigger_name == "BULL_A_THRESHOLD"
    assert result.threshold_value == pytest.approx(100.75)
    assert result.reversal_dominated is False


def test_nifty_price_above_bull_cf_threshold_is_bull_cf() -> None:
    result = MonthlyStatusEngine().classify(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
                CMH=101.6,
                CML=91.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=101.6,
        ),
    )

    assert result.status == MonthlyStatus.BULL_CF
    assert result.trigger_name == "BULL_CF_B_THRESHOLD"
    assert result.threshold_value == pytest.approx(101.505625)
    assert result.reversal_dominated is False


def test_nifty_price_below_bear_trigger_but_above_bear_cf_is_bear() -> None:
    result = MonthlyStatusEngine().classify(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
                CMH=100.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=89.0,
        ),
    )

    assert result.status == MonthlyStatus.BEAR
    assert result.trigger_name == "BEAR_A_THRESHOLD"
    assert result.threshold_value == pytest.approx(89.325)
    assert result.reversal_dominated is False


def test_nifty_price_below_bear_cf_threshold_is_bear_cf() -> None:
    result = MonthlyStatusEngine().classify(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
                CMH=100.0,
                CML=88.5,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=88.5,
        ),
    )

    assert result.status == MonthlyStatus.BEAR_CF
    assert result.trigger_name == "BEAR_CF_B_THRESHOLD"
    assert result.threshold_value == pytest.approx(88.6550625)
    assert result.reversal_dominated is False


def test_effective_bull_reverses_to_bear_on_weekly_c_threshold() -> None:
    result = MonthlyStatusEngine().apply_current_price_transitions(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=110.0,
            PWL=104.0,
            CWH=109.0,
            CWL=103.0,
                current_price=102.0,
            ),
        effective_status=MonthlyStatus.BULL,
    )

    assert result.status == MonthlyStatus.BEAR
    assert result.trigger_name == "REVERSAL_BEAR_C_THRESHOLD"
    assert result.reversal_dominated is True
    assert "reversed to bearish" in result.notes


def test_effective_bear_reverses_to_bull_on_weekly_c_threshold() -> None:
    result = MonthlyStatusEngine().apply_current_price_transitions(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=87.0,
            PWL=70.0,
            CWH=88.0,
            CWL=71.0,
                current_price=88.5,
            ),
        effective_status=MonthlyStatus.BEAR,
    )

    assert result.status == MonthlyStatus.BULL
    assert result.trigger_name == "REVERSAL_BULL_C_THRESHOLD"
    assert result.reversal_dominated is True
    assert "reversed to bullish" in result.notes


def test_unknown_when_no_trigger_is_met() -> None:
    result = MonthlyStatusEngine().classify(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=95.0,
        ),
    )

    assert result.status == MonthlyStatus.UNKNOWN
    assert result.trigger_name == "NO_MONTHLY_TRIGGER"
    assert result.threshold_value is None
    assert result.reversal_dominated is False


def test_stock_thresholds_produce_expected_status() -> None:
    result = MonthlyStatusEngine().classify(
        "stock",
        MonthlyStatusReferenceLevels(
            PMH=200.0,
            PML=180.0,
                CMH=209.5,
                CML=181.0,
            PWH=215.0,
            PWL=160.0,
            CWH=214.0,
            CWL=161.0,
            current_price=209.5,
        ),
    )

    assert result.status == MonthlyStatus.BULL_CF
    assert result.trigger_name == "BULL_CF_B_THRESHOLD"
    assert result.threshold_value == pytest.approx(209.1)


def test_engine_returns_candidates_for_audit() -> None:
    result = MonthlyStatusEngine().classify(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=105.0,
            PWL=85.0,
            CWH=104.0,
            CWL=86.0,
            current_price=101.6,
        ),
    )

    assert len(result.candidates) == 6
    assert {candidate.trigger_name for candidate in result.candidates} == {
        "BULL_A_THRESHOLD",
        "BEAR_A_THRESHOLD",
        "BULL_CF_B_THRESHOLD",
        "BEAR_CF_B_THRESHOLD",
        "REVERSAL_BULL_C_THRESHOLD",
        "REVERSAL_BEAR_C_THRESHOLD",
    }
