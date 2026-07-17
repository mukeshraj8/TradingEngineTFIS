from __future__ import annotations

from .execution_journal import S23PaperOrderIntent
from .fill_simulator import S23PaperFillDecision
from .lifecycle import S23PaperLifecycleDecision
from .runtime_contract import (
    PaperTradeFillContract,
    PaperTradeIntentContract,
    PaperTradeLifecycleContract,
)


def build_paper_trade_intent_contract(
    intent: S23PaperOrderIntent,
) -> PaperTradeIntentContract:
    return PaperTradeIntentContract(
        session_id=intent.session_id,
        session_date=intent.session_date,
        strategy_code=intent.strategy_code,
        terminal_state=intent.terminal_state,
        status=intent.status,
        selected_contract_symbol=intent.selected_contract_symbol,
        selected_contract_option_type=intent.selected_contract_option_type,
        selected_contract_expiry=intent.selected_contract_expiry,
        side=intent.side,
        lots=intent.lots,
        quantity=intent.quantity,
        planned_entry_price=intent.planned_entry_price,
        target_price=intent.target_price,
        stoploss_price=intent.stoploss_price,
        fsl_price=intent.fsl_price,
        order_reference_time=intent.order_reference_time,
        order_reference_label=intent.order_reference_label,
        source_branch=intent.source_branch,
        source_workbook_rule=intent.source_workbook_rule,
        workbook_row_number=intent.workbook_row_number,
    )


def build_paper_trade_fill_contract(
    decision: S23PaperFillDecision,
) -> PaperTradeFillContract:
    return PaperTradeFillContract(
        session_id=decision.session_id,
        session_date=decision.session_date,
        strategy_code=decision.strategy_code,
        status=decision.status.value,
        selected_contract_symbol=decision.selected_contract_symbol,
        selected_contract_option_type=decision.selected_contract_option_type,
        selected_contract_expiry=decision.selected_contract_expiry,
        planned_entry_price=decision.planned_entry_price,
        handoff_boundary_timestamp=decision.handoff_boundary_timestamp,
        fill_price=decision.fill_price,
        fill_timestamp=decision.fill_timestamp,
        source_kind=decision.source_kind,
        source_type=decision.source_type,
        source_id=decision.source_id,
        source_effective_timestamp=decision.source_effective_timestamp,
        reason_code=decision.reason_code,
        message=decision.message,
        no_fill_reason=decision.no_fill_reason,
        operator_action_required=decision.operator_action_required,
    )


def build_paper_trade_lifecycle_contract(
    decision: S23PaperLifecycleDecision,
) -> PaperTradeLifecycleContract:
    return PaperTradeLifecycleContract(
        session_id=decision.session_id,
        session_date=decision.session_date,
        strategy_code=decision.strategy_code,
        status=decision.status.value,
        selected_contract_symbol=decision.selected_contract_symbol,
        selected_contract_option_type=decision.selected_contract_option_type,
        selected_contract_expiry=decision.selected_contract_expiry,
        side=decision.side,
        lots=decision.lots,
        quantity=decision.quantity,
        entry_price=decision.entry_price,
        target_price=decision.target_price,
        stoploss_price=decision.stoploss_price,
        fsl_price=decision.fsl_price,
        effective_stop_price=decision.effective_stop_price,
        entry_timestamp=decision.entry_timestamp,
        exit_price=decision.exit_price,
        exit_timestamp=decision.exit_timestamp,
        exit_reason_code=decision.exit_reason_code,
        message=decision.message,
        source_kind=decision.source_kind,
        source_type=decision.source_type,
        source_id=decision.source_id,
        source_effective_timestamp=decision.source_effective_timestamp,
        gross_pnl_rupees=decision.gross_pnl_rupees,
        brokerage_rupees=decision.brokerage_rupees,
        net_pnl_rupees=decision.net_pnl_rupees,
        operator_action_required=decision.operator_action_required,
        warning_flags=decision.warning_flags,
    )


__all__ = [
    "build_paper_trade_fill_contract",
    "build_paper_trade_intent_contract",
    "build_paper_trade_lifecycle_contract",
]
