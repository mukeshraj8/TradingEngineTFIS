from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from tfis.domain.enums import ExpiryType, OptionType, RolloverPolicy
from tfis.paper import (
    S23PaperPositionStateError,
    S23PaperPositionStateEventType,
    S23PaperPositionStateStatus,
    S23PaperPositionStateStore,
)


IST = ZoneInfo("Asia/Kolkata")


def _ts(day: int, hour: int = 9, minute: int = 30, second: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, second, tzinfo=IST)


def _create_state(
    store: S23PaperPositionStateStore,
    *,
    carry_forward_allowed: bool = True,
    expiry_date: date = date(2026, 5, 29),
):
    return store.create_open_position_state(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260529_22400_PE",
        expiry_date=expiry_date,
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=None,
        no_carry_past_expiry=True,
        entry_date=date(2026, 5, 27),
        entry_timestamp=_ts(27),
        entry_price=199.5,
        lots=2,
        quantity=100,
        side="SELL",
        target_price=80.0,
        stoploss_price=320.0,
        fsl_price=352.0,
        trp_price=None,
        carry_forward_allowed=carry_forward_allowed,
        last_updated_timestamp=_ts(27, 15, 20),
        provenance_source_ids=("paper_order_intent.json", "execution_summary.json"),
        strategy_parameters={"strike_buffer_pct": 1.2, "sl_reference_pct": 7.0},
        stoploss_reset_buffer_pct=7.0,
        stoploss_reset_orpt_time=time(9, 24, 59),
        stoploss_reset_rc_time=time(9, 29, 59),
    )


def test_create_open_position_state() -> None:
    store = S23PaperPositionStateStore()

    state = _create_state(store)

    assert state.strategy_code == "S23"
    assert state.unique_code == "NIFTY_OP_SELL_WK_DIFF_2D_3D"
    assert state.option_type is OptionType.PUT
    assert state.carry_forward_allowed is True
    assert state.expiry_policy.expiry_type is ExpiryType.WEEKLY
    assert state.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_OPEN
    assert state.provenance_source_ids == (
        "paper_order_intent.json",
        "execution_summary.json",
    )


def test_persist_and_reload_position_state(tmp_path) -> None:
    store = S23PaperPositionStateStore()
    state = _create_state(store)

    store.save_state(tmp_path, state)
    reloaded = store.load_state(tmp_path)

    assert reloaded == state


def test_reject_corrupt_state_and_emit_invalid_event(tmp_path) -> None:
    store = S23PaperPositionStateStore()
    (tmp_path / "paper_position_state.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(S23PaperPositionStateError):
        store.load_state(tmp_path)

    events = store.load_events(tmp_path)
    assert len(events) == 1
    assert events[0].event_type is S23PaperPositionStateEventType.PAPER_POSITION_STATE_INVALID
    assert events[0].reason_code == "invalid_persisted_position_state"


def test_reject_carry_forward_when_config_disallows_it(tmp_path) -> None:
    store = S23PaperPositionStateStore()
    state = _create_state(store, carry_forward_allowed=False)
    store.save_state(tmp_path, state)

    with pytest.raises(S23PaperPositionStateError):
        store.carry_forward(
            tmp_path,
            next_session_date=date(2026, 5, 28),
            updated_at=_ts(28, 8, 45),
        )

    assert store.load_events(tmp_path) == ()


def test_allow_next_day_resume_when_expiry_has_not_passed(tmp_path) -> None:
    store = S23PaperPositionStateStore()
    state = _create_state(store, expiry_date=date(2026, 5, 29))
    store.save_state(tmp_path, state)

    carried = store.carry_forward(
        tmp_path,
        next_session_date=date(2026, 5, 28),
        updated_at=_ts(28, 8, 45),
        provenance_source_ids=("carry-forward-check",),
    )
    resumed = store.resume_position(
        tmp_path,
        session_date=date(2026, 5, 28),
        resumed_at=_ts(28, 9, 10),
        provenance_source_ids=("resume-check",),
    )

    assert carried.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_CARRIED_FORWARD
    assert resumed.lifecycle_status is S23PaperPositionStateStatus.PAPER_POSITION_RESUMED
    assert resumed.last_updated_timestamp == _ts(28, 9, 10)
    assert resumed.provenance_source_ids == (
        "paper_order_intent.json",
        "execution_summary.json",
        "carry-forward-check",
        "resume-check",
    )

    events = store.load_events(tmp_path)
    assert [event.event_type for event in events] == [
        S23PaperPositionStateEventType.PAPER_POSITION_CARRIED_FORWARD,
        S23PaperPositionStateEventType.PAPER_POSITION_RESUMED,
    ]


def test_carry_forward_and_resume_preserve_stoploss_reset_metadata(tmp_path) -> None:
    store = S23PaperPositionStateStore()
    state = _create_state(store, expiry_date=date(2026, 5, 29))
    store.save_state(tmp_path, state)
    carried_inactive = store.mark_stoploss_inactive_for_carry_forward(
        tmp_path,
        session_date=date(2026, 5, 27),
        updated_at=_ts(27, 15, 0),
        reference_price=state.stoploss_price,
        reason_code="s23_1500_carry_forward_stop_inactive",
        message="Test carry-forward keeps overnight stoploss inactive.",
    )

    carried = store.carry_forward(
        tmp_path,
        next_session_date=date(2026, 5, 28),
        updated_at=_ts(28, 8, 45),
        provenance_source_ids=("carry-forward-check",),
    )
    resumed = store.resume_position(
        tmp_path,
        session_date=date(2026, 5, 28),
        resumed_at=_ts(28, 9, 10),
        provenance_source_ids=("resume-check",),
    )
    reloaded = store.load_state(tmp_path)

    for candidate in (carried_inactive, carried, resumed, reloaded):
        assert candidate.strategy_parameters == {
            "sl_reference_pct": 7.0,
            "strike_buffer_pct": 1.2,
        }
        assert candidate.stoploss_active is False
        assert candidate.stoploss_reset_pending is True
        assert candidate.stoploss_reset_session_date == date(2026, 5, 27)
        assert candidate.stoploss_reset_reference_price == 320.0
        assert candidate.stoploss_reset_buffer_pct == 7.0
        assert candidate.stoploss_reset_orpt_time == time(9, 24, 59)
        assert candidate.stoploss_reset_rc_time == time(9, 29, 59)
        assert candidate.stoploss_reset_reason_code == "s23_1500_carry_forward_stop_inactive"


def test_reject_resume_if_expiry_has_passed(tmp_path) -> None:
    store = S23PaperPositionStateStore()
    state = _create_state(store, expiry_date=date(2026, 5, 28))
    store.save_state(tmp_path, state)

    with pytest.raises(S23PaperPositionStateError):
        store.resume_position(
            tmp_path,
            session_date=date(2026, 5, 29),
            resumed_at=_ts(29, 9, 10),
        )

    events = store.load_events(tmp_path)
    assert events[-1].event_type is S23PaperPositionStateEventType.PAPER_POSITION_STATE_INVALID
    assert events[-1].reason_code == "resume_past_expiry"
