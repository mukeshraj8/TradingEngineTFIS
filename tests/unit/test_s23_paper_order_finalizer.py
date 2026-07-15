from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path

from tfis.paper import (
    S23PaperOrderFinalizer,
    S23PaperOrderState,
    S23PaperOrderStateStore,
    S23PaperOrderStatus,
)


def test_finalizer_marks_same_session_waiting_order_after_cutoff(tmp_path: Path) -> None:
    order_dir = tmp_path / "2026-06-29" / "session" / "BEAR_PUT"
    store = S23PaperOrderStateStore()
    store.save_state(order_dir, _waiting_order(entry_date=date(2026, 6, 29)))

    summary = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 35),
        cutoff_time=time(15, 30),
    )

    updated = store.load_state(order_dir)
    assert summary.scanned_count == 1
    assert summary.finalized_count == 1
    assert summary.decisions[0].action == "FINALIZED"
    assert summary.decisions[0].reason_code == "paper_order_not_triggered_by_cutoff_sweeper"
    assert updated.status is S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED
    assert updated.last_reason_code == "paper_order_not_triggered_by_cutoff_sweeper"
    assert "session-only" in (updated.last_message or "")
    assert "Pending S23 paper entry orders" not in (updated.last_message or "")
    events = (order_dir / "paper_order_events.jsonl").read_text(encoding="utf-8")
    assert "PAPER_ORDER_NOT_FILLED" in events


def test_finalizer_skips_same_session_order_before_cutoff(tmp_path: Path) -> None:
    order_dir = tmp_path / "2026-06-29" / "session" / "BEAR_CALL"
    store = S23PaperOrderStateStore()
    store.save_state(order_dir, _waiting_order(entry_date=date(2026, 6, 29)))

    summary = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 25),
        cutoff_time=time(15, 30),
    )

    updated = store.load_state(order_dir)
    assert summary.finalized_count == 0
    assert summary.skipped_count == 1
    assert summary.decisions[0].reason_code == "paper_order_cutoff_not_reached"
    assert updated.status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER


def test_finalizer_skips_prior_session_unless_included(tmp_path: Path) -> None:
    order_dir = tmp_path / "2026-06-28" / "session" / "BEAR_CALL"
    store = S23PaperOrderStateStore()
    store.save_state(order_dir, _waiting_order(entry_date=date(2026, 6, 28)))

    skipped = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 35),
        cutoff_time=time(15, 30),
    )
    assert skipped.finalized_count == 0
    assert skipped.decisions[0].reason_code == "paper_order_prior_session_not_included"
    assert store.load_state(order_dir).status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER

    repaired = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 35),
        cutoff_time=time(15, 30),
        include_prior_sessions=True,
    )
    assert repaired.finalized_count == 1
    assert repaired.decisions[0].reason_code == "paper_order_expired_untriggered_previous_session_sweeper"
    assert store.load_state(order_dir).status is S23PaperOrderStatus.PAPER_ORDER_NOT_FILLED


def test_finalizer_dry_run_does_not_modify_state(tmp_path: Path) -> None:
    order_dir = tmp_path / "2026-06-29" / "session" / "BEAR_PUT"
    store = S23PaperOrderStateStore()
    store.save_state(order_dir, _waiting_order(entry_date=date(2026, 6, 29)))

    summary = S23PaperOrderFinalizer(order_store=store).finalize(
        tmp_path,
        session_date=date(2026, 6, 29),
        marked_at=datetime(2026, 6, 29, 15, 35),
        cutoff_time=time(15, 30),
        dry_run=True,
    )

    assert summary.finalized_count == 1
    assert summary.decisions[0].action == "WOULD_FINALIZE"
    assert store.load_state(order_dir).status is S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER
    assert not (order_dir / "paper_order_events.jsonl").exists()


def _waiting_order(*, entry_date: date) -> S23PaperOrderState:
    return S23PaperOrderState(
        artifact_version=1,
        strategy_code="S23",
        strategy_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT",
        symbol="NIFTY",
        selected_contract_symbol="NIFTY_20260707_24300_PE",
        selected_contract_expiry=date(2026, 7, 7),
        selected_contract_option_type="PUT",
        selected_contract_strike=24300.0,
        expiry_type="WEEKLY",
        rollover_policy="T_MINUS_1",
        forced_close_time=time(12, 0),
        no_carry_past_expiry=True,
        order_side="SELL",
        trigger_rule="SELL_TRIGGER_WHEN_PREMIUM_AT_OR_BELOW_ENTRY",
        entry_date=entry_date,
        order_timestamp=datetime.combine(entry_date, time(9, 30)),
        planned_entry_price=212.75,
        target_price=85.10,
        stoploss_price=258.94,
        fsl_price=258.94,
        lots=1,
        quantity=65,
        status=S23PaperOrderStatus.PAPER_ORDER_WAITING_FOR_TRIGGER,
        last_updated_timestamp=datetime.combine(entry_date, time(12, 32)),
        last_market_price=387.30,
        last_market_bid=386.60,
        last_market_ask=387.85,
        last_reason_code="paper_order_waiting_quote_above_entry",
        last_message="Selected option premium is still above entry; the paper sell order remains waiting.",
    )
