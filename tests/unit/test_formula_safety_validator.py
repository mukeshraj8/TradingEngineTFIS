from __future__ import annotations

from datetime import time

from tfis.domain.enums import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, Segment
from tfis.domain.strategy_rule import StrategyExpiryPolicy, StrategyRule
from tfis.formulas import validate_strategy_rule_formula_safety


def _option_rule(*, entry_formula: str, stoploss_formula: str) -> StrategyRule:
    return StrategyRule(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BULL,),
        option_type=OptionType.CALL,
        entry_time=time(9, 24, 59),
        recalculation_time=time(9, 29, 59),
        start_strike_formula="ROUND_DOWN(PRV_3DLL + 5%)",
        end_strike_formula="ROUND_DOWN(PRV_3DLL) - 1",
        ideal_premium_formula="PRV_3DLL * 1.20%",
        minimum_premium_formula="PRV_3DLL * 0.90%",
        minimum_oi=500,
        entry_formula=entry_formula,
        target_formula="ENTRY - 60%",
        stoploss_formula=stoploss_formula,
        carry_forward_allowed=True,
    )


def _crosscheck() -> dict:
    return {
        "source_cells": {
            "entry_formula": "M162",
            "stoploss_formula": "M163",
        },
        "sample_calculation": {
            "option_levels": {
                "OPT_PRV_3DLL": 220.0,
                "OPT_PRV_2DHH": 300.0,
            },
            "expected": {
                "entry_price": 203.5,
                "stoploss_price": 320.0,
            },
        },
    }


def test_entry_formula_using_plain_prv_for_options_strategy_is_error() -> None:
    rule = _option_rule(
        entry_formula="PRV_3DLL - PARAM(entry_discount_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
    )

    findings = validate_strategy_rule_formula_safety(rule, crosscheck=_crosscheck())

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].field_name == "entry_formula"


def test_entry_formula_using_opt_alias_for_options_strategy_passes() -> None:
    rule = _option_rule(
        entry_formula="OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
    )

    findings = validate_strategy_rule_formula_safety(rule, crosscheck=_crosscheck())

    assert findings == []


def test_stoploss_formula_using_plain_prv_for_options_strategy_is_error() -> None:
    rule = _option_rule(
        entry_formula="OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, PRV_2DHH + PARAM(sl_reference_pct)%)",
    )

    findings = validate_strategy_rule_formula_safety(rule, crosscheck=_crosscheck())

    assert len(findings) == 1
    assert findings[0].severity == "ERROR"
    assert findings[0].field_name == "stoploss_formula"


def test_strike_formula_using_plain_prv_is_allowed() -> None:
    rule = _option_rule(
        entry_formula="OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
    )

    findings = validate_strategy_rule_formula_safety(rule, crosscheck=_crosscheck())

    assert findings == []


def test_non_options_strategy_does_not_enforce_opt_rule() -> None:
    rule = StrategyRule(
        strategy_code="S01",
        unique_code="NIFTY_FUT_TEST",
        symbol="NIFTY",
        segment=Segment.FUTURES,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BULL,),
        option_type=None,
        entry_time=time(9, 24, 59),
        recalculation_time=time(9, 29, 59),
        start_strike_formula="PRV_3DLL + 5%",
        end_strike_formula="PRV_3DLL - 1",
        ideal_premium_formula="PRV_3DLL + 1.20%",
        minimum_premium_formula="PRV_3DLL + 0.90%",
        minimum_oi=0,
        entry_formula="PRV_3DLL - 7.5%",
        target_formula="ENTRY - 60%",
        stoploss_formula="MIN(ENTRY + 60%, PRV_2DHH + 7%)",
        carry_forward_allowed=False,
    )

    findings = validate_strategy_rule_formula_safety(rule, crosscheck=_crosscheck())

    assert findings == []
