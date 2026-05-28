from __future__ import annotations

from datetime import time

import pytest

from tfis.domain import InstrumentRef, MarketLevels, StrategyExpiryPolicy, StrategyRule, TradePlan
from tfis.domain.enums import ExpiryType, MonthlyStatus, OptionType, RolloverPolicy, RoundingMode, Segment


def test_enums_expose_expected_members() -> None:
    assert Segment.FUTURES.value == "FUTURES"
    assert ExpiryType.WEEKLY.value == "WEEKLY"
    assert MonthlyStatus.BULL_CF.value == "BULL_CF"
    assert OptionType.PUT.value == "PUT"
    assert RolloverPolicy.T_MINUS_1.value == "T_MINUS_1"
    assert RoundingMode.NEAREST.value == "NEAREST"


def test_instrument_ref_creation() -> None:
    instrument = InstrumentRef(symbol="NIFTY", segment=Segment.FUTURES)

    assert instrument.symbol == "NIFTY"
    assert instrument.segment is Segment.FUTURES


def test_market_levels_creation() -> None:
    levels = MarketLevels(
        previous_month_high=25100.0,
        previous_month_low=24000.0,
        previous_week_high=24950.0,
        previous_week_low=24400.0,
        d2hh=24810.0,
        d2ll=24510.0,
        d3hh=24725.0,
        d3ll=24485.0,
        d4hh=24610.0,
        d4ll=24395.0,
        current_day_high=24675.0,
        current_day_low=24580.0,
    )

    assert levels.d2hh == 24810.0
    assert levels.current_day_low == 24580.0


def test_market_levels_reject_inverted_ranges() -> None:
    with pytest.raises(ValueError, match="previous_month_high"):
        MarketLevels(previous_month_high=100.0, previous_month_low=110.0)



def test_strategy_rule_creation_for_options() -> None:
    rule = StrategyRule(
        strategy_code="TFIS_A",
        unique_code="TFIS_A_01",
        symbol="NIFTY",
        segment=Segment.OPTIONS_BUY,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BULL, MonthlyStatus.BULL_CF),
        option_type=OptionType.CALL,
        entry_time=time(9, 20),
        recalculation_time=time(9, 30),
        start_strike_formula="ROUND_DOWN(spot - 200)",
        end_strike_formula="ROUND_UP(spot + 200)",
        ideal_premium_formula="spot * 0.01",
        minimum_premium_formula="spot * 0.005",
        minimum_oi=10000,
        entry_formula="breakout_level + 5",
        target_formula="entry * 1.2",
        stoploss_formula="entry * 0.9",
        carry_forward_allowed=False,
    )

    assert rule.option_type is OptionType.CALL
    assert rule.allowed_monthly_statuses == (MonthlyStatus.BULL, MonthlyStatus.BULL_CF)
    assert rule.expiry_policy.expiry_type is ExpiryType.WEEKLY



def test_strategy_rule_rejects_missing_option_type_for_option_segment() -> None:
    with pytest.raises(ValueError, match="option_type is required"):
        StrategyRule(
            strategy_code="TFIS_A",
            unique_code="TFIS_A_01",
            symbol="NIFTY",
            segment=Segment.OPTIONS_BUY,
            expiry_policy=StrategyExpiryPolicy(
                expiry_type=ExpiryType.WEEKLY,
                rollover_policy=RolloverPolicy.T_MINUS_1,
            ),
            allowed_monthly_statuses=(MonthlyStatus.BULL,),
            option_type=None,
            entry_time=time(9, 20),
            recalculation_time=time(9, 30),
            start_strike_formula="A",
            end_strike_formula="B",
            ideal_premium_formula="C",
            minimum_premium_formula="D",
            minimum_oi=10000,
            entry_formula="E",
            target_formula="F",
            stoploss_formula="G",
            carry_forward_allowed=True,
        )



def test_strategy_rule_rejects_empty_monthly_statuses() -> None:
    with pytest.raises(ValueError, match="allowed_monthly_statuses"):
        StrategyRule(
            strategy_code="TFIS_B",
            unique_code="TFIS_B_01",
            symbol="NIFTY",
            segment=Segment.FUTURES,
            expiry_policy=StrategyExpiryPolicy(
                expiry_type=ExpiryType.WEEKLY,
                rollover_policy=RolloverPolicy.T_MINUS_1,
            ),
            allowed_monthly_statuses=(),
            option_type=None,
            entry_time=time(9, 20),
            recalculation_time=time(9, 30),
            start_strike_formula="A",
            end_strike_formula="B",
            ideal_premium_formula="C",
            minimum_premium_formula="D",
            minimum_oi=0,
            entry_formula="E",
            target_formula="F",
            stoploss_formula="G",
            carry_forward_allowed=False,
        )



def test_trade_plan_creation() -> None:
    plan = TradePlan(
        strategy_code="TFIS_A",
        symbol="NIFTY",
        option_type=OptionType.CALL,
        start_strike=24500,
        end_strike=24700,
        ideal_premium=180.0,
        minimum_premium=120.0,
        entry_price=150.0,
        stoploss_price=110.0,
        target_price=210.0,
    )

    assert plan.start_strike == 24500
    assert plan.target_price == 210.0



def test_trade_plan_allows_descending_strike_window() -> None:
    plan = TradePlan(
        strategy_code="TFIS_A",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        start_strike=24800,
        end_strike=24600,
        ideal_premium=180.0,
        minimum_premium=120.0,
        entry_price=150.0,
        stoploss_price=110.0,
        target_price=210.0,
    )

    assert plan.start_strike == 24800
    assert plan.end_strike == 24600
