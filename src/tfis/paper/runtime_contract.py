from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .models import PaperSessionState


@dataclass(frozen=True, slots=True)
class PaperTradeIntentContract:
    session_id: str
    session_date: date
    strategy_code: str
    terminal_state: PaperSessionState
    status: str
    selected_contract_symbol: str
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    side: str
    lots: int
    quantity: int
    planned_entry_price: float
    target_price: float
    stoploss_price: float
    fsl_price: float | None
    order_reference_time: datetime
    order_reference_label: str
    source_branch: str | None
    source_workbook_rule: str | None
    workbook_row_number: int | None


@dataclass(frozen=True, slots=True)
class PaperTradeFillContract:
    session_id: str
    session_date: date
    strategy_code: str
    status: str
    selected_contract_symbol: str
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    planned_entry_price: float
    handoff_boundary_timestamp: datetime
    fill_price: float | None
    fill_timestamp: datetime | None
    source_kind: str | None
    source_type: str | None
    source_id: str | None
    source_effective_timestamp: datetime | None
    reason_code: str
    message: str
    no_fill_reason: str | None
    operator_action_required: str | None


@dataclass(frozen=True, slots=True)
class PaperTradeLifecycleContract:
    session_id: str
    session_date: date
    strategy_code: str
    status: str
    selected_contract_symbol: str
    selected_contract_option_type: str | None
    selected_contract_expiry: date | None
    side: str
    lots: int
    quantity: int
    entry_price: float
    target_price: float
    stoploss_price: float | None
    fsl_price: float | None
    effective_stop_price: float
    entry_timestamp: datetime
    exit_price: float | None
    exit_timestamp: datetime | None
    exit_reason_code: str
    message: str
    source_kind: str | None
    source_type: str | None
    source_id: str | None
    source_effective_timestamp: datetime | None
    gross_pnl_rupees: float | None
    brokerage_rupees: float | None
    net_pnl_rupees: float | None
    operator_action_required: str | None
    warning_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PaperTradeShellContract:
    session_id: str
    session_date: date
    strategy_code: str
    terminal_state: PaperSessionState
    selected_contract_symbol: str
    intent_status: str | None
    execution_shell_status: str | None
    dispatch_shell_status: str | None
    handoff_shell_status: str | None
    historical_comparison_status: str | None
    historical_comparison_reason: str | None
    historical_comparison_go_no_go: str | None


__all__ = [
    "PaperTradeShellContract",
    "PaperTradeIntentContract",
    "PaperTradeFillContract",
    "PaperTradeLifecycleContract",
]
