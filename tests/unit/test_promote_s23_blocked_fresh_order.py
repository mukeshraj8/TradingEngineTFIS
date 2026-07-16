from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path

import pytest

import scripts.promote_s23_blocked_fresh_order as promote
from tfis.domain import (
    ExpiryType,
    MonthlyStatus,
    OptionType,
    RolloverPolicy,
    Segment,
    StrategyExpiryPolicy,
    StrategyRule,
)
from tfis.paper import S23PaperOrderStatus
from tfis.paper.order_state import S23PaperOrderStateStore
from tfis.paper.position_state import S23PaperPositionStateStore


def test_promotes_blocked_ready_decision_after_carry_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_dir = _session_dir(tmp_path)
    branch_dir = session_dir / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    branch_dir.mkdir(parents=True)
    metadata_path = session_dir / "scheduled_run_metadata.json"
    metadata_path.write_text("{}", encoding="utf-8")
    summary_path = branch_dir / "trade_decision_summary.json"
    summary_path.write_text(json.dumps({"summary": _blocked_ready_summary()}), encoding="utf-8")
    monkeypatch.setattr(promote, "_load_strategy_for_branch", lambda _branch: _strategy_rule())
    monkeypatch.setattr(
        "sys.argv",
        [
            "promote_s23_blocked_fresh_order.py",
            "--date",
            "2026-07-06",
            "--artifact-root",
            str(tmp_path),
            "--created-at",
            "2026-07-06T10:09:51+05:30",
        ],
    )

    assert promote.main() == 0

    order_state = S23PaperOrderStateStore().load_state(branch_dir)
    assert order_state.status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
    assert order_state.selected_contract_symbol == "NIFTY_20260714_24150_CE"
    assert order_state.planned_entry_price == 194.25
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    branch = "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    assert metadata["branch_order_state_json"][branch] == str(branch_dir / "paper_order_state.json")
    assert metadata["branch_order_placement_blocked"][branch] is False
    assert metadata["branch_order_placement_promoted_after_carry_exit"][branch] is True


def test_refuses_promotion_when_active_position_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_dir = _session_dir(tmp_path)
    session_dir.mkdir(parents=True)
    (session_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")
    active_dir = tmp_path / "2026-07-02" / "session-2026-07-02" / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    active_dir.mkdir(parents=True)
    store = S23PaperPositionStateStore()
    store.save_state(
        active_dir,
        store.create_open_position_state(
            strategy_code="S23",
            unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
            symbol="NIFTY",
            option_type=OptionType.PUT,
            selected_contract_symbol="NIFTY_20260714_24200_PE",
            expiry_date=date(2026, 7, 14),
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
            forced_close_time=time(12, 0),
            no_carry_past_expiry=True,
            entry_date=date(2026, 7, 2),
            entry_timestamp=datetime(2026, 7, 2, 9, 46),
            entry_price=212.35,
            lots=1,
            quantity=65,
            side="SELL",
            target_price=85.10,
            stoploss_price=258.94,
            fsl_price=None,
            trp_price=None,
            carry_forward_allowed=True,
            last_updated_timestamp=datetime(2026, 7, 2, 9, 46),
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "promote_s23_blocked_fresh_order.py",
            "--date",
            "2026-07-06",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        promote.main()

    assert "active paper position(s) still exist" in str(exc_info.value)
    assert str(active_dir / "paper_position_state.json") in str(exc_info.value)


def test_refuses_promotion_when_reverse_entry_required_position_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_dir = _session_dir(tmp_path)
    session_dir.mkdir(parents=True)
    (session_dir / "scheduled_run_metadata.json").write_text("{}", encoding="utf-8")
    blocked_dir = tmp_path / "2026-07-05" / "session-2026-07-05" / "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    blocked_dir.mkdir(parents=True)
    store = S23PaperPositionStateStore()
    store.save_state(
        blocked_dir,
        store.create_open_position_state(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        option_type=OptionType.PUT,
        selected_contract_symbol="NIFTY_20260714_24200_PE",
        expiry_date=date(2026, 7, 14),
        expiry_type=ExpiryType.WEEKLY,
        rollover_policy=RolloverPolicy.T_MINUS_1,
        forced_close_time=time(12, 0),
        no_carry_past_expiry=True,
        entry_date=date(2026, 7, 5),
        entry_timestamp=datetime(2026, 7, 5, 9, 46),
        entry_price=212.35,
        lots=1,
        quantity=65,
        side="SELL",
        target_price=85.10,
        stoploss_price=258.94,
        fsl_price=None,
        trp_price=None,
        carry_forward_allowed=True,
        last_updated_timestamp=datetime(2026, 7, 5, 9, 46),
    ),
    )
    store.mark_position_closed(
        blocked_dir,
        session_date=date(2026, 7, 5),
        closed_at=datetime(2026, 7, 5, 12, 57),
        reason_code="stoploss_or_fsl_hit",
        message="Reverse entry required.",
        reverse_entry_required=True,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "promote_s23_blocked_fresh_order.py",
            "--date",
            "2026-07-06",
            "--artifact-root",
            str(tmp_path),
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        promote.main()

    assert "active paper position(s) still exist" in str(exc_info.value)
    assert str(blocked_dir / "paper_position_state.json") in str(exc_info.value)


def _session_dir(root: Path) -> Path:
    return (
        root
        / "2026-07-06"
        / "s23-fyers-morning-supervised-decision-2026-07-06"
    )


def _strategy_rule() -> StrategyRule:
    return StrategyRule(
        strategy_code="S23",
        unique_code="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        symbol="NIFTY",
        segment=Segment.OPTIONS_SELL,
        expiry_policy=StrategyExpiryPolicy(
            expiry_type=ExpiryType.WEEKLY,
            rollover_policy=RolloverPolicy.T_MINUS_1,
            forced_close_time=time(12, 0),
            no_carry_past_expiry=True,
        ),
        allowed_monthly_statuses=(MonthlyStatus.BEAR,),
        option_type=OptionType.CALL,
        entry_time=time(9, 24, 59),
        recalculation_time=time(9, 29, 59),
        start_strike_formula="1",
        end_strike_formula="1",
        ideal_premium_formula="1",
        minimum_premium_formula="1",
        minimum_oi=32500,
        entry_formula="1",
        target_formula="1",
        stoploss_formula="1",
        carry_forward_allowed=True,
        parameters={"sl_reference_pct": 7.0},
    )


def _blocked_ready_summary() -> dict[str, object]:
    return {
        "status": "READY",
        "session_date": "2026-07-06",
        "mode": "fresh_entry",
        "strategy_code": "S23",
        "strategy_branch": "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "monthly_status": "BEAR",
        "monthly_status_trigger": "BEAR_CONTINUES",
        "monthly_status_notes": "test",
        "required_market_aliases": [],
        "required_option_aliases": [],
        "checkpoint_labels": ["0915", "ORPT", "RC"],
        "market_levels": {},
        "runtime_values": {},
        "lots": 1,
        "quantity": 65,
        "selected_contract_symbol": "NIFTY_20260714_24150_CE",
        "selected_contract_expiry": "2026-07-14",
        "selected_contract_strike": 24150,
        "selected_contract_option_type": "CALL",
        "selected_contract_ltp": 292.35,
        "selected_contract_oi": 139945,
        "contract_selection_reason": "Selected first strike meeting ideal premium.",
        "contract_selection_failure_code": None,
        "contract_selection_attempted_expiries": ["2026-07-14"],
        "rejected_candidate_counts": {},
        "ranked_candidates": [],
        "planned_entry_price": 194.25,
        "target_price": 77.70,
        "stoploss_price": 242.00,
        "fsl_price": None,
        "source_workbook_rule": "unit-test",
        "workbook_row_number": 1,
        "governance_event_types": [],
        "resume_event_type": None,
        "notes": [],
        "order_placement_blocked": True,
        "order_placement_block_reason": "OPEN_CARRY_FORWARD_POSITION",
    }
