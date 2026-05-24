from __future__ import annotations

import pytest

from tfis.domain.enums import MonthlyStatus
from tfis.monthly_status import (
    MonthlyStatusDecisionCandidate,
    MonthlyStatusDecisionTable,
    MonthlyStatusReferenceLevels,
)


def _candidate_map(
    reference_levels: MonthlyStatusReferenceLevels,
    *,
    instrument_group: str = "nifty",
    bullish_value: float | None = None,
    bearish_value: float | None = None,
) -> dict[str, MonthlyStatusDecisionCandidate]:
    candidates = MonthlyStatusDecisionTable().build_candidates(
        instrument_group,
        reference_levels,
        bullish_value=bullish_value,
        bearish_value=bearish_value,
    )
    return {candidate.trigger_name: candidate for candidate in candidates}


def test_nifty_pmh_plus_a_pct_creates_true_bull_candidate() -> None:
    candidates = _candidate_map(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=99.0,
            PWL=91.0,
            CWH=100.0,
            CWL=92.0,
            current_price=100.80,
        )
    )

    bull_candidate = candidates["BULL_A_THRESHOLD"]
    assert bull_candidate.candidate_status == MonthlyStatus.BULL
    assert bull_candidate.threshold_value == pytest.approx(100.75)
    assert bull_candidate.condition_met is True
    assert bull_candidate.confidence == "HIGH"


def test_nifty_pml_minus_a_pct_creates_true_bear_candidate() -> None:
    candidates = _candidate_map(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=99.0,
            PWL=91.0,
            CWH=100.0,
            CWL=92.0,
            current_price=89.32,
        )
    )

    bear_candidate = candidates["BEAR_A_THRESHOLD"]
    assert bear_candidate.candidate_status == MonthlyStatus.BEAR
    assert bear_candidate.threshold_value == pytest.approx(89.325)
    assert bear_candidate.condition_met is True
    assert bear_candidate.confidence == "HIGH"


def test_stock_uses_stock_specific_thresholds() -> None:
    candidates = _candidate_map(
        MonthlyStatusReferenceLevels(
            PMH=200.0,
            PML=180.0,
            CMH=202.0,
            CML=179.0,
            PWH=198.0,
            PWL=182.0,
            CWH=199.0,
            CWL=183.0,
            current_price=205.10,
        ),
        instrument_group="stock",
        bullish_value=203.0,
        bearish_value=177.0,
    )

    assert candidates["BULL_A_THRESHOLD"].threshold_value == pytest.approx(205.0)
    assert candidates["BULL_CF_B_THRESHOLD"].threshold_value == pytest.approx(207.06)
    assert candidates["REVERSAL_BULL_C_THRESHOLD"].threshold_value == pytest.approx(200.99)


def test_reversal_bull_uses_max_pwh_or_cwh_plus_c_pct() -> None:
    candidates = _candidate_map(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=101.0,
            PWL=91.0,
            CWH=102.0,
            CWL=92.0,
            current_price=102.20,
        )
    )

    reversal_bull = candidates["REVERSAL_BULL_C_THRESHOLD"]
    assert reversal_bull.threshold_value == pytest.approx(102.153)
    assert reversal_bull.condition_met is True
    assert reversal_bull.confidence == "MEDIUM"


def test_reversal_bear_uses_min_pwl_or_cwl_minus_c_pct() -> None:
    candidates = _candidate_map(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=101.0,
            PWL=98.0,
            CWH=102.0,
            CWL=97.0,
            current_price=96.80,
        )
    )

    reversal_bear = candidates["REVERSAL_BEAR_C_THRESHOLD"]
    assert reversal_bear.threshold_value == pytest.approx(96.8545)
    assert reversal_bear.condition_met is True
    assert reversal_bear.confidence == "MEDIUM"


def test_missing_bullish_and_bearish_values_create_low_confidence_rows() -> None:
    candidates = _candidate_map(
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=101.0,
            PWL=98.0,
            CWH=102.0,
            CWL=97.0,
            current_price=100.0,
        )
    )

    bull_cf = candidates["BULL_CF_B_THRESHOLD"]
    bear_cf = candidates["BEAR_CF_B_THRESHOLD"]
    assert bull_cf.condition_met is None
    assert bull_cf.threshold_value is None
    assert bull_cf.confidence == "LOW"
    assert bear_cf.condition_met is None
    assert bear_cf.threshold_value is None
    assert bear_cf.confidence == "LOW"


def test_decision_table_returns_candidates_only_and_no_final_status() -> None:
    candidates = MonthlyStatusDecisionTable().build_candidates(
        "nifty",
        MonthlyStatusReferenceLevels(
            PMH=100.0,
            PML=90.0,
            CMH=101.0,
            CML=89.0,
            PWH=101.0,
            PWL=98.0,
            CWH=102.0,
            CWL=97.0,
            current_price=100.0,
        ),
    )

    assert isinstance(candidates, list)
    assert len(candidates) == 6
    assert all(isinstance(candidate, MonthlyStatusDecisionCandidate) for candidate in candidates)
    assert not hasattr(candidates, "final_status")
