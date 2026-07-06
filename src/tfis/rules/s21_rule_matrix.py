from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.domain.strategy_rule import StrategyRule


class S21MonthlyGroup(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


@dataclass(frozen=True, slots=True)
class S21LegRule:
    monthly_group: S21MonthlyGroup
    option_type: OptionType
    trade: str
    unique_code_suffix: str
    spot_reference_alias: str
    entry_reference_alias: str
    structure_sl_reference_alias: str
    structure_sl_buffer_pct: float
    allowed_monthly_statuses: tuple[MonthlyStatus, ...]
    start_strike_formula: str
    end_strike_formula: str
    ideal_premium_formula: str
    minimum_premium_formula: str
    entry_formula: str
    target_formula: str
    stoploss_formula: str


S21_LEG_RULES: dict[str, S21LegRule] = {
    "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL": S21LegRule(
        monthly_group=S21MonthlyGroup.BULLISH,
        option_type=OptionType.CALL,
        trade="SELL_CALL",
        unique_code_suffix="BULL_CALL",
        spot_reference_alias="PRV_3DLL",
        entry_reference_alias="OPT_PRV_3DLL",
        structure_sl_reference_alias="OPT_PRV_2DHH",
        structure_sl_buffer_pct=7.0,
        allowed_monthly_statuses=(MonthlyStatus.BULL, MonthlyStatus.BULL_CF),
        start_strike_formula="ROUND_DOWN(PRV_3DLL + PARAM(strike_buffer_pct)%)",
        end_strike_formula="ROUND_DOWN(PRV_3DLL) - PARAM(strike_step)",
        ideal_premium_formula="PRV_3DLL * PARAM(ideal_premium_pct)%",
        minimum_premium_formula="PRV_3DLL * PARAM(minimum_premium_pct)%",
        entry_formula="OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        target_formula="ENTRY - PARAM(target_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
    ),
    "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT": S21LegRule(
        monthly_group=S21MonthlyGroup.BULLISH,
        option_type=OptionType.PUT,
        trade="SELL_PUT",
        unique_code_suffix="BULL_PUT",
        spot_reference_alias="PRV_2DHH",
        entry_reference_alias="OPT_PRV_2DLL",
        structure_sl_reference_alias="OPT_PRV_3DHH",
        structure_sl_buffer_pct=10.0,
        allowed_monthly_statuses=(MonthlyStatus.BULL, MonthlyStatus.BULL_CF),
        start_strike_formula="ROUND_UP(PRV_2DHH - PARAM(strike_buffer_pct)%)",
        end_strike_formula="ROUND_UP(PRV_2DHH) + PARAM(strike_step)",
        ideal_premium_formula="PRV_2DHH * PARAM(ideal_premium_pct)%",
        minimum_premium_formula="PRV_2DHH * PARAM(minimum_premium_pct)%",
        entry_formula="OPT_PRV_2DLL - PARAM(entry_discount_pct)%",
        target_formula="ENTRY - PARAM(target_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_3DHH + PARAM(sl_reference_pct)%)",
    ),
    "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL": S21LegRule(
        monthly_group=S21MonthlyGroup.BEARISH,
        option_type=OptionType.CALL,
        trade="SELL_CALL",
        unique_code_suffix="BEAR_CALL",
        spot_reference_alias="PRV_2DLL",
        entry_reference_alias="OPT_PRV_2DLL",
        structure_sl_reference_alias="OPT_PRV_3DHH",
        structure_sl_buffer_pct=10.0,
        allowed_monthly_statuses=(MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        start_strike_formula="ROUND_DOWN(PRV_2DLL + PARAM(strike_buffer_pct)%)",
        end_strike_formula="ROUND_DOWN(PRV_2DLL) - PARAM(strike_step)",
        ideal_premium_formula="PRV_2DLL * PARAM(ideal_premium_pct)%",
        minimum_premium_formula="PRV_2DLL * PARAM(minimum_premium_pct)%",
        entry_formula="OPT_PRV_2DLL - PARAM(entry_discount_pct)%",
        target_formula="ENTRY - PARAM(target_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_3DHH + PARAM(sl_reference_pct)%)",
    ),
    "BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT": S21LegRule(
        monthly_group=S21MonthlyGroup.BEARISH,
        option_type=OptionType.PUT,
        trade="SELL_PUT",
        unique_code_suffix="BEAR_PUT",
        spot_reference_alias="PRV_3DHH",
        entry_reference_alias="OPT_PRV_3DLL",
        structure_sl_reference_alias="OPT_PRV_2DHH",
        structure_sl_buffer_pct=7.0,
        allowed_monthly_statuses=(MonthlyStatus.BEAR, MonthlyStatus.BEAR_CF),
        start_strike_formula="ROUND_UP(PRV_3DHH - PARAM(strike_buffer_pct)%)",
        end_strike_formula="ROUND_UP(PRV_3DHH) + PARAM(strike_step)",
        ideal_premium_formula="PRV_3DHH * PARAM(ideal_premium_pct)%",
        minimum_premium_formula="PRV_3DHH * PARAM(minimum_premium_pct)%",
        entry_formula="OPT_PRV_3DLL - PARAM(entry_discount_pct)%",
        target_formula="ENTRY - PARAM(target_pct)%",
        stoploss_formula="MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)",
    ),
}


def get_s21_leg_rule(unique_code: str) -> S21LegRule:
    try:
        return S21_LEG_RULES[unique_code]
    except KeyError as exc:
        raise ValueError(f"Unsupported S21 unique_code: {unique_code}") from exc


def validate_s21_strategy_rule_matches_matrix(rule: StrategyRule) -> tuple[str, ...]:
    """Return mismatches between a loaded S21 strategy rule and the rule-sheet matrix."""

    if rule.strategy_code != "S21":
        return (f"strategy_code expected S21, got {rule.strategy_code}",)

    matrix_rule = get_s21_leg_rule(rule.unique_code)
    mismatches: list[str] = []
    expected_pairs = (
        ("option_type", rule.option_type, matrix_rule.option_type),
        ("allowed_monthly_statuses", rule.allowed_monthly_statuses, matrix_rule.allowed_monthly_statuses),
        ("start_strike_formula", rule.start_strike_formula, matrix_rule.start_strike_formula),
        ("end_strike_formula", rule.end_strike_formula, matrix_rule.end_strike_formula),
        ("ideal_premium_formula", rule.ideal_premium_formula, matrix_rule.ideal_premium_formula),
        ("minimum_premium_formula", rule.minimum_premium_formula, matrix_rule.minimum_premium_formula),
        ("entry_formula", rule.entry_formula, matrix_rule.entry_formula),
        ("target_formula", rule.target_formula, matrix_rule.target_formula),
        ("stoploss_formula", rule.stoploss_formula, matrix_rule.stoploss_formula),
    )
    for name, actual, expected in expected_pairs:
        if actual != expected:
            mismatches.append(f"{name} expected {expected!r}, got {actual!r}")

    actual_sl_reference_pct = rule.parameters.get("sl_reference_pct")
    if actual_sl_reference_pct != matrix_rule.structure_sl_buffer_pct:
        mismatches.append(
            "sl_reference_pct expected "
            f"{matrix_rule.structure_sl_buffer_pct!r}, got {actual_sl_reference_pct!r}"
        )

    return tuple(mismatches)
