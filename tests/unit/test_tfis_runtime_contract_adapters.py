from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

import pytest

from tfis.domain import (
    Segment,
    TFISDirection,
    TFISExecutionSide,
    TFISProductType,
    TFISTradeResult,
)
from tfis.importers import load_strategy_rule
from tfis.paper import (
    PaperRuntimeContractAdapterError,
    S23PaperTradeDecisionSummary,
    decision_from_trade_decision_summary,
    decision_from_trade_decision_summary_strict,
    legacy_reference_packet_from_runtime_input,
    load_paper_decision_reference_packet,
    runtime_input_from_decision_reference_packet,
    runtime_input_from_decision_reference_packet_strict,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_s23_reference_packet_round_trips_through_runtime_input_adapter() -> None:
    strategy_rule = load_strategy_rule(
        REPO_ROOT
        / "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    )
    reference_packet = load_paper_decision_reference_packet(
        REPO_ROOT / "config/reference_packets/s23_bear_put_live_decision_reference.json"
    )

    runtime_input = runtime_input_from_decision_reference_packet(
        strategy_rule=strategy_rule,
        reference_packet=reference_packet,
        evaluation_id="s23-eval",
        evaluated_at=datetime(2026, 7, 29, 9, 17),
        session_date=date(2026, 7, 29),
    )
    round_tripped = legacy_reference_packet_from_runtime_input(runtime_input)

    assert runtime_input.strategy_code == "S23"
    assert runtime_input.product_type is TFISProductType.OPTION_SELLING
    assert asdict(round_tripped) == asdict(reference_packet)


def test_s21_reference_packet_round_trips_through_runtime_input_adapter() -> None:
    strategy_rule = load_strategy_rule(
        REPO_ROOT
        / "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL"
    )
    reference_packet = load_paper_decision_reference_packet(
        REPO_ROOT
        / "config/reference_packets/s21_banknifty_monthly_live_decision_reference.json"
    )

    runtime_input = runtime_input_from_decision_reference_packet(
        strategy_rule=strategy_rule,
        reference_packet=reference_packet,
        evaluation_id="s21-eval",
        evaluated_at=datetime(2026, 7, 29, 9, 17),
        session_date=date(2026, 7, 29),
    )
    round_tripped = legacy_reference_packet_from_runtime_input(runtime_input)

    assert runtime_input.strategy_code == "S21"
    assert runtime_input.product_type is TFISProductType.OPTION_SELLING
    assert asdict(round_tripped) == asdict(reference_packet)


def test_trade_decision_summary_maps_to_generic_decision_without_value_drift() -> None:
    summary = _summary(strategy_code="S23")
    decision = decision_from_trade_decision_summary(
        summary=summary,
        evaluation_id="eval-1",
        decision_id="decision-1",
        decided_at=datetime(2026, 7, 29, 9, 30),
        explanation={
            "formulas": (
                {
                    "name": "entry",
                    "formula": "ENTRY",
                    "resolved_formula": "210.4",
                    "result": 210.4,
                },
                {
                    "name": "target",
                    "formula": "ENTRY-125.3",
                    "resolved_formula": "210.4-125.3",
                    "result": 85.1,
                },
                {
                    "name": "stoploss",
                    "formula": "ENTRY+48.54",
                    "resolved_formula": "210.4+48.54",
                    "result": 258.94,
                },
            ),
            "orpt_rc_timing": {"status": "BASE_ENTRY_VALID"},
        },
    )

    assert decision.strategy_code == summary.strategy_code
    assert decision.strategy_branch == summary.strategy_branch
    assert decision.trade_result is TFISTradeResult.TRADE
    assert decision.execution_side is TFISExecutionSide.SELL
    assert decision.selected_instrument is not None
    assert decision.selected_instrument.symbol == summary.selected_contract_symbol
    assert decision.entry_calculation is not None
    assert decision.entry_calculation.result == summary.planned_entry_price
    assert decision.target_policy is not None
    assert decision.target_policy.result == summary.target_price
    assert decision.msl_policy is not None
    assert decision.msl_policy.result == summary.stoploss_price
    assert decision.compatibility_payload["summary"]["planned_entry_price"] == summary.planned_entry_price


def test_legacy_decision_adapter_remains_behaviorally_unchanged() -> None:
    summary = _summary(strategy_code="S23")

    decision = decision_from_trade_decision_summary(summary=summary)

    assert decision.product_type is TFISProductType.OPTION_SELLING
    assert decision.direction is TFISDirection.SHORT
    assert decision.execution_side is TFISExecutionSide.SELL
    assert decision.rejection_reason == summary.contract_selection_reason
    assert decision.selected_instrument is not None
    assert decision.selected_instrument.segment is None


def test_strict_decision_adapter_requires_explicit_product_direction_and_side() -> None:
    summary = _summary(strategy_code="S23")

    with pytest.raises(TypeError):
        decision_from_trade_decision_summary_strict(summary=summary)  # type: ignore[call-arg]


def test_strict_option_buying_can_map_to_buy_long() -> None:
    summary = _summary(strategy_code="GENERIC_OB")

    decision = decision_from_trade_decision_summary_strict(
        summary=summary,
        product_type=TFISProductType.OPTION_BUYING,
        direction=TFISDirection.LONG,
        execution_side=TFISExecutionSide.BUY,
        selected_instrument_segment=Segment.OPTIONS_BUY,
        expected_strategy_code="GENERIC_OB",
        expected_strategy_branch=summary.strategy_branch,
    )

    assert decision.product_type is TFISProductType.OPTION_BUYING
    assert decision.direction is TFISDirection.LONG
    assert decision.execution_side is TFISExecutionSide.BUY
    assert decision.selected_instrument is not None
    assert decision.selected_instrument.segment is Segment.OPTIONS_BUY
    assert decision.rejection_reason is None
    assert (
        decision.intermediate_calculation_evidence["selection"]["selection_reason"]
        == summary.contract_selection_reason
    )


def test_strict_option_selling_maps_to_sell_short() -> None:
    summary = _summary(strategy_code="S23")

    decision = decision_from_trade_decision_summary_strict(
        summary=summary,
        product_type=TFISProductType.OPTION_SELLING,
        direction=TFISDirection.SHORT,
        execution_side=TFISExecutionSide.SELL,
        selected_instrument_segment=Segment.OPTIONS_SELL,
        expected_strategy_code="S23",
        expected_strategy_branch=summary.strategy_branch,
    )

    assert decision.product_type is TFISProductType.OPTION_SELLING
    assert decision.direction is TFISDirection.SHORT
    assert decision.execution_side is TFISExecutionSide.SELL
    assert decision.selected_instrument is not None
    assert decision.selected_instrument.segment is Segment.OPTIONS_SELL
    assert decision.rejection_reason is None


def test_strict_decision_adapter_rejects_strategy_identity_mismatch() -> None:
    summary = _summary(strategy_code="S23")

    with pytest.raises(PaperRuntimeContractAdapterError):
        decision_from_trade_decision_summary_strict(
            summary=summary,
            product_type=TFISProductType.OPTION_SELLING,
            direction=TFISDirection.SHORT,
            execution_side=TFISExecutionSide.SELL,
            selected_instrument_segment=Segment.OPTIONS_SELL,
            expected_strategy_code="S99",
            expected_strategy_branch=summary.strategy_branch,
        )


def test_strict_runtime_input_adapter_rejects_reference_packet_branch_mismatch() -> None:
    strategy_rule = load_strategy_rule(
        REPO_ROOT
        / "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL"
    )
    reference_packet = load_paper_decision_reference_packet(
        REPO_ROOT / "config/reference_packets/s23_bear_put_live_decision_reference.json"
    )

    with pytest.raises(PaperRuntimeContractAdapterError):
        runtime_input_from_decision_reference_packet_strict(
            strategy_rule=strategy_rule,
            reference_packet=reference_packet,
            evaluation_id="strict-mismatch",
            evaluated_at=datetime(2026, 7, 29, 9, 17),
            session_date=date(2026, 7, 29),
        )


def test_s21_and_s23_summary_decisions_keep_legacy_values_after_adapter() -> None:
    for strategy_code in ("S21", "S23"):
        summary = _summary(strategy_code=strategy_code)
        decision = decision_from_trade_decision_summary(
            summary=summary,
            evaluation_id=f"{strategy_code}-eval",
            decision_id=f"{strategy_code}-decision",
            decided_at=datetime(2026, 7, 29, 9, 30),
        )

        assert decision.strategy_code == strategy_code
        assert decision.quantity == summary.quantity
        assert decision.lots == summary.lots
        assert decision.entry_calculation is not None
        assert decision.entry_calculation.result == summary.planned_entry_price
        assert decision.to_json() == decision.comparison_key()


def _summary(*, strategy_code: str) -> S23PaperTradeDecisionSummary:
    symbol = "BANKNIFTY_20260730_45000_CE" if strategy_code == "S21" else "NIFTY_20260804_23900_PE"
    branch = (
        "BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL"
        if strategy_code == "S21"
        else "NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    )
    return S23PaperTradeDecisionSummary(
        status="READY",
        session_date=date(2026, 7, 29),
        mode="fresh_entry",
        strategy_code=strategy_code,
        strategy_branch=branch,
        monthly_status="BEAR",
        monthly_status_trigger="fixture",
        monthly_status_notes="fixture",
        required_market_aliases=("D2HH",),
        required_option_aliases=("OPT_PRV_2DHH",),
        checkpoint_labels=("AT_0915", "ORPT", "RC"),
        market_levels={"current_day_high": 24500.0, "current_day_low": 24100.0},
        runtime_values={"ENTRY": 210.4, "OPT_PRV_2DHH": 242.0},
        lots=1,
        quantity=35 if strategy_code == "S21" else 65,
        selected_contract_symbol=symbol,
        selected_contract_expiry="2026-08-04",
        selected_contract_strike=23900.0,
        selected_contract_option_type="PUT",
        selected_contract_ltp=210.9,
        selected_contract_oi=1350.0,
        contract_selection_reason="fixture_selected",
        contract_selection_failure_code=None,
        contract_selection_attempted_expiries=("2026-08-04",),
        rejected_candidate_counts={},
        ranked_candidates=(),
        planned_entry_price=210.4,
        target_price=85.1,
        stoploss_price=258.94,
        fsl_price=258.94,
        source_workbook_rule="fixture",
        workbook_row_number=1,
    )
