from __future__ import annotations

from datetime import date, datetime

from tfis.paper import (
    PaperSessionState,
    S23PaperFillDecision,
    S23PaperFillStatus,
    S23PaperLifecycleDecision,
    S23PaperLifecycleStatus,
    S23PaperOrderIntent,
    build_paper_trade_fill_contract,
    build_paper_trade_intent_contract,
    build_paper_trade_lifecycle_contract,
)


def test_build_paper_trade_intent_contract_from_s23_intent() -> None:
    intent = S23PaperOrderIntent(
        artifact_version=1,
        session_id="s23-session-1",
        session_date=date(2026, 7, 16),
        strategy_code="S23",
        terminal_state=PaperSessionState.ORDER_PLANNED,
        status="INTENT_READY",
        selected_contract_symbol="NIFTY_20260721_23950_CE",
        selected_contract_option_type="CE",
        selected_contract_expiry=date(2026, 7, 21),
        selected_contract_ltp=282.0,
        side="SELL",
        lots=1,
        quantity=65,
        planned_entry_price=212.75,
        target_price=85.10,
        stoploss_price=258.94,
        fsl_price=None,
        order_reference_time=datetime.fromisoformat("2026-07-16T11:07:19.425271+05:30"),
        order_reference_label="ORPT",
        source_branch="NIFTY_OP_SELL_WK_DIFF_2D_3D",
        source_workbook_rule="S23 CE",
        workbook_row_number=23,
        data_source_count=2,
        data_source_ids=("snapshot-1", "snapshot-2"),
        data_source_types=("quote", "bar"),
        synthetic_fixture_used=False,
        bundle_validation_performed=True,
        bundle_valid=True,
        disclaimer="paper only",
    )

    contract = build_paper_trade_intent_contract(intent)

    assert contract.session_id == intent.session_id
    assert contract.terminal_state is PaperSessionState.ORDER_PLANNED
    assert contract.selected_contract_symbol == "NIFTY_20260721_23950_CE"
    assert contract.planned_entry_price == 212.75
    assert contract.order_reference_label == "ORPT"
    assert contract.source_branch == "NIFTY_OP_SELL_WK_DIFF_2D_3D"


def test_build_paper_trade_fill_contract_from_s23_fill_decision() -> None:
    decision = S23PaperFillDecision(
        artifact_version=1,
        session_id="s23-session-1",
        session_date=date(2026, 7, 16),
        strategy_code="S23",
        status=S23PaperFillStatus.PAPER_ORDER_FILLED,
        planned_entry_price=212.75,
        selected_contract_symbol="NIFTY_20260721_23950_CE",
        selected_contract_option_type="CE",
        selected_contract_expiry=date(2026, 7, 21),
        order_reference_time=datetime.fromisoformat("2026-07-16T11:07:19.425271+05:30"),
        order_reference_label="ORPT",
        handoff_boundary_timestamp=datetime.fromisoformat("2026-07-16T12:00:00+05:30"),
        fill_price=209.0,
        fill_timestamp=datetime.fromisoformat("2026-07-16T11:30:00+05:30"),
        source_kind="quote",
        source_type="selected_contract_quote",
        source_id="evt-1",
        source_effective_timestamp=datetime.fromisoformat("2026-07-16T11:29:59+05:30"),
        spread_points=0.25,
        slippage_entry_points=-3.75,
        quote_bid=208.9,
        quote_ask=209.1,
        quote_ltp=209.0,
        bar_high=None,
        bar_low=None,
        market_event_count=17,
        reason_code="entry_trigger_hit",
        message="Filled on selected quote.",
        no_fill_reason=None,
        operator_action_required=None,
        guardrail_code=None,
        guardrail_message=None,
        blocking_source_id=None,
        disclaimer="paper only",
    )

    contract = build_paper_trade_fill_contract(decision)

    assert contract.status == "PAPER_ORDER_FILLED"
    assert contract.fill_price == 209.0
    assert contract.source_id == "evt-1"
    assert contract.reason_code == "entry_trigger_hit"
    assert contract.message == "Filled on selected quote."


def test_build_paper_trade_lifecycle_contract_from_s23_lifecycle_decision() -> None:
    decision = S23PaperLifecycleDecision(
        artifact_version=1,
        session_id="s23-session-1",
        session_date=date(2026, 7, 16),
        strategy_code="S23",
        status=S23PaperLifecycleStatus.PAPER_POSITION_CLOSED,
        selected_contract_symbol="NIFTY_20260721_23950_CE",
        selected_contract_option_type="CE",
        selected_contract_expiry=date(2026, 7, 21),
        side="SELL",
        lots=1,
        quantity=65,
        entry_price=209.0,
        target_price=85.10,
        stoploss_price=258.94,
        fsl_price=None,
        effective_stop_price=258.94,
        entry_timestamp=datetime.fromisoformat("2026-07-16T11:30:00+05:30"),
        exit_price=86.10,
        exit_timestamp=datetime.fromisoformat("2026-07-16T12:57:59+05:30"),
        exit_reason_code="target_hit",
        message="Selected-contract bar proved target hit.",
        source_kind="bar",
        source_type="selected_contract_bar",
        source_id="bar-1",
        source_effective_timestamp=datetime.fromisoformat("2026-07-16T12:57:59+05:30"),
        quote_bid=None,
        quote_ask=None,
        quote_ltp=None,
        bar_open=90.0,
        bar_high=91.0,
        bar_low=84.5,
        bar_close=86.1,
        gross_pnl_rupees=7988.50,
        brokerage_rupees=50.0,
        net_pnl_rupees=7938.50,
        guardrail_code=None,
        guardrail_message=None,
        blocking_source_id=None,
        operator_action_required="Fresh entry recalculation required.",
        warning_flags=("fresh_entry_required",),
        disclaimer="paper only",
    )

    contract = build_paper_trade_lifecycle_contract(decision)

    assert contract.status == "PAPER_POSITION_CLOSED"
    assert contract.exit_reason_code == "target_hit"
    assert contract.net_pnl_rupees == 7938.50
    assert contract.operator_action_required == "Fresh entry recalculation required."
    assert contract.warning_flags == ("fresh_entry_required",)
