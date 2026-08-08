from __future__ import annotations

from types import SimpleNamespace

from tfis.domain.enums import MonthlyStatus, OptionType
from tfis.paper.s21_strategy_session import (
    eligible_s21_unique_codes,
    s21_orpt_requires_recalculation,
)


def _rule(unique_code: str):
    return SimpleNamespace(unique_code=unique_code)


RULES = (
    _rule("BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL"),
    _rule("BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT"),
    _rule("BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL"),
    _rule("BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT"),
)


def test_s21_bull_status_activates_only_call_and_put_bull_legs() -> None:
    assert eligible_s21_unique_codes(
        status=MonthlyStatus.BULL,
        strategy_rules=RULES,
    ) == (
        "BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
        "BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
    )


def test_s21_bear_cf_status_activates_only_call_and_put_bear_legs() -> None:
    assert eligible_s21_unique_codes(
        status=MonthlyStatus.BEAR_CF,
        strategy_rules=RULES,
    ) == (
        "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
        "BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT",
    )


def test_s21_orpt_call_normal_path_preserves_base_order() -> None:
    assert not s21_orpt_requires_recalculation(
        option_type=OptionType.CALL,
        base_entry=100.0,
        option_low=101.0,
        option_high=110.0,
    )


def test_s21_orpt_call_missed_path_defers_to_rc() -> None:
    assert s21_orpt_requires_recalculation(
        option_type=OptionType.CALL,
        base_entry=100.0,
        option_low=99.0,
        option_high=110.0,
    )


def test_s21_orpt_put_normal_path_preserves_base_order() -> None:
    assert not s21_orpt_requires_recalculation(
        option_type=OptionType.PUT,
        base_entry=100.0,
        option_low=90.0,
        option_high=101.0,
    )


def test_s21_orpt_put_missed_path_defers_to_rc() -> None:
    assert s21_orpt_requires_recalculation(
        option_type=OptionType.PUT,
        base_entry=100.0,
        option_low=90.0,
        option_high=99.0,
    )
