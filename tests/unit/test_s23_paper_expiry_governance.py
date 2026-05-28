from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from tfis.domain import ExpiryType, StrategyExpiryPolicy, StrategyRule
from tfis.domain.enums import MonthlyStatus, OptionType, RolloverPolicy, Segment
from tfis.paper import (
    DeterministicExpiryCalendar,
    S23PaperExpiryGovernance,
    S23PaperPositionStateEventType,
    S23PaperPositionStateStore,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(day: int, hour: int = 9, minute: int = 30) -> datetime:
    return datetime(2026, 5, day, hour, minute, tzinfo=IST)


def _strategy(*, rollover_policy: RolloverPolicy) -> StrategyRule:
    return StrategyRule(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=rollover_policy,
            forced_close_time=None,
            no_carry_past_expiry=True,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BULL, MonthlyStatus.BULL_CF),
        option_type=OptionType.CALL,
        entry_time=time(9, 24, 59),
        recalculation_time=time(9, 29, 59),
        start_strike_formula="A",
        end_strike_formula="B",
        ideal_premium_formula="C",
        minimum_premium_formula="D",
        minimum_oi=500,
        entry_formula="E",
        target_formula="F",
        stoploss_formula="G",
        carry_forward_allowed=True,
    )


def _position_state(
    *,
    rollover_policy: RolloverPolicy,
    expiry_date: date = date(2026, 5, 28),
):
    store = S23PaperPositionStateStore()
    return store.create_open_position_state(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260528_22400_PE",
        expiry_date=expiry_date,
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=rollover_policy,
        forced_close_time=None,
        no_carry_past_expiry=True,
        entry_date=date(2026, 5, 26),
        entry_timestamp=_ts(26),
        entry_price=199.5,
        lots=2,
        quantity=100,
        side="SELL",
        target_price=80.0,
        stoploss_price=320.0,
        fsl_price=352.0,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=_ts(26, 15, 20),
        provenance_source_ids=("paper_order_intent.json",),
    )


def _calendar() -> DeterministicExpiryCalendar:
    return DeterministicExpiryCalendar()


def test_normal_non_expiry_carry_forward_allowed() -> None:
    governance = S23PaperExpiryGovernance(_calendar())
    position = _position_state(rollover_policy=RolloverPolicy.T_MINUS_1)

    assert governance.can_carry_forward(position, date(2026, 5, 26)) is True
    assert governance.must_force_close(position, date(2026, 5, 26), time(10, 0)) is False


def test_t_minus_1_policy_blocks_current_expiry_continuation_one_trading_day_before_expiry() -> None:
    governance = S23PaperExpiryGovernance(_calendar())
    position = _position_state(rollover_policy=RolloverPolicy.T_MINUS_1)

    decision = governance.evaluate_position(
        position,
        session_date=date(2026, 5, 27),
        current_time=time(10, 0),
    )

    assert decision.can_carry_forward is False
    assert decision.should_select_next_expiry is True
    assert decision.must_force_close is True
    assert S23PaperPositionStateEventType.PAPER_NEXT_EXPIRY_REQUIRED in decision.event_types


def test_t_minus_2_policy_blocks_current_expiry_continuation_two_trading_days_before_expiry() -> None:
    governance = S23PaperExpiryGovernance(_calendar())
    position = _position_state(rollover_policy=RolloverPolicy.T_MINUS_2)

    assert governance.can_carry_forward(position, date(2026, 5, 26)) is False
    assert governance.should_select_next_expiry(position, date(2026, 5, 26)) is True


def test_expiry_day_carry_forward_rejected() -> None:
    governance = S23PaperExpiryGovernance(_calendar())
    position = _position_state(rollover_policy=RolloverPolicy.T_MINUS_1)

    assert governance.can_carry_forward(position, date(2026, 5, 28)) is False
    assert governance.must_force_close(position, date(2026, 5, 28), time(9, 20)) is True


def test_post_expiry_resume_rejected(tmp_path) -> None:
    store = S23PaperPositionStateStore()
    governance = S23PaperExpiryGovernance(_calendar())
    state = _position_state(
        rollover_policy=RolloverPolicy.T_MINUS_1,
        expiry_date=date(2026, 5, 28),
    )
    store.save_state(tmp_path, state)

    with pytest.raises(Exception):
        store.resume_position(
            tmp_path,
            session_date=date(2026, 5, 29),
            resumed_at=_ts(29, 9, 10),
            expiry_governance=governance,
        )


def test_next_expiry_selection_required_near_expiry() -> None:
    governance = S23PaperExpiryGovernance(_calendar())
    strategy = _strategy(rollover_policy=RolloverPolicy.T_MINUS_1)

    assert governance.should_select_next_expiry(strategy, date(2026, 5, 27)) is True
    assert governance.should_select_next_expiry(strategy, date(2026, 5, 26)) is False
