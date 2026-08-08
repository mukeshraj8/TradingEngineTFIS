from __future__ import annotations

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.paper.s21_strategy_session import s21_orpt_requires_recalculation
from tfis.strategy_engine.s21 import (
    MinuteBarEvidence,
    OptionContractEvidence,
    S21StrategyEngine,
    S21StrategyEvidence,
    S21_NUMBER_OF_EXPIRIES_TO_CHECK,
)


def _parameters():
    codes = (
        "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
        "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
        "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
        "BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT",
    )
    return {
        code: {
            "strike_buffer_pct": 5.0,
            "strike_step": 100.0,
            "ideal_premium_pct": 2.0,
            "minimum_premium_pct": 1.5,
            "entry_discount_pct": 7.5,
            "target_pct": 60.0,
            "sl_entry_pct": 60.0,
            "sl_reference_pct": 7.0 if code.endswith(("BULL_CALL", "BEAR_PUT")) else 10.0,
            "minimum_lots": 500.0,
            "lot_size": 35.0,
        }
        for code in codes
    }


def _evidence():
    return S21StrategyEvidence(
        session_date="2026-08-06",
        monthly_status="BULL_CF",
        monthly_status_source="TEST",
        underlying_references={
            "PRV_2DHH": 58068.95,
            "PRV_2DLL": 57352.65,
            "PRV_3DHH": 58247.95,
            "PRV_3DLL": 57352.65,
            "PRV_4DHH": 58247.95,
            "PRV_4DLL": 57139.60,
        },
        option_chain=(
            OptionContractEvidence(
                symbol="NEAR_CALL",
                option_type="CALL",
                strike=57200.0,
                expiry="2026-08-25",
                oi=0.0,
                chain_ltp=100.0,
            ),
            OptionContractEvidence(
                symbol="NEXT_CALL",
                option_type="CALL",
                strike=57200.0,
                expiry="2026-09-29",
                oi=999999.0,
                chain_ltp=9999.0,
            ),
        ),
        option_historical_references={},
        option_minute_bars={},
        spot_bars={},
        branch_parameters=_parameters(),
    )


def test_s21_workbook_authority_checks_exactly_one_expiry():
    assert S21_NUMBER_OF_EXPIRIES_TO_CHECK == 1
    engine = S21StrategyEngine()
    required = engine.required_candidate_symbols(_evidence())
    call_symbols = required["BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL"]
    assert "NEAR_CALL" in call_symbols
    assert "NEXT_CALL" not in call_symbols


def test_s21_put_orpt_entry_missed_uses_low_not_high():
    # High is above entry, but LOW crossed below it: workbook says entry missed.
    assert s21_orpt_requires_recalculation(
        option_type=OptionType.PUT,
        base_entry=100.0,
        option_low=99.0,
        option_high=120.0,
    ) is True


def test_s21_put_orpt_entry_not_missed_when_low_does_not_cross():
    assert s21_orpt_requires_recalculation(
        option_type=OptionType.PUT,
        base_entry=100.0,
        option_low=100.0,
        option_high=120.0,
    ) is False


def test_s21_call_orpt_still_uses_low():
    assert s21_orpt_requires_recalculation(
        option_type=OptionType.CALL,
        base_entry=100.0,
        option_low=99.0,
        option_high=120.0,
    ) is True


def test_pure_engine_put_missed_test_uses_low():
    bar = MinuteBarEvidence(
        symbol="X",
        bar_start="2026-08-06T09:24:00+05:30",
        high=120.0,
        low=99.0,
    )
    assert S21StrategyEngine._base_entry_missed(
        option_type=OptionType.PUT,
        entry=100.0,
        bar=bar,
    ) is True


def test_equal_low_is_not_missed_because_workbook_uses_strict_less_than():
    bar = MinuteBarEvidence(
        symbol="X",
        bar_start="2026-08-06T09:24:00+05:30",
        high=120.0,
        low=100.0,
    )
    assert S21StrategyEngine._base_entry_missed(
        option_type=OptionType.PUT,
        entry=100.0,
        bar=bar,
    ) is False
