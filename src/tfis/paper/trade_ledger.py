from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from .position_state import S23PaperPositionState


_ARTIFACT_VERSION = 1
_SESSION_LEDGER_FILENAME = "paper_trade_ledger.jsonl"
_DEFAULT_GLOBAL_LEDGER_ROOT = Path("tmp/paper_trade_ledger")
_DEFAULT_GLOBAL_LEDGER_FILENAME = "s23_paper_trade_ledger.jsonl"


class S23PaperTradeLedgerEventType(str, Enum):
    OPEN = "OPEN"
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    ACTION_REQUIRED = "ACTION_REQUIRED"


@dataclass(frozen=True, slots=True)
class S23PaperTradeLedgerRow:
    artifact_version: int
    event_timestamp: datetime
    event_type: S23PaperTradeLedgerEventType
    trade_id: str
    strategy_id: str
    strategy_code: str
    strategy_branch: str
    symbol: str
    option_type: str
    selected_contract_symbol: str
    expiry_date: date
    side: str
    lots: int
    quantity: int
    entry_date: date
    entry_timestamp: datetime
    entry_price: float
    target_price: float
    stoploss_price: float
    fsl_price: float | None
    trp_price: float | None
    session_date: date
    lifecycle_status: str
    manager_status: str
    reason_code: str
    message: str
    exit_timestamp: datetime | None = None
    current_price: float | None = None
    current_bid: float | None = None
    current_ask: float | None = None
    exit_price: float | None = None
    gross_points: float | None = None
    gross_pnl: float | None = None
    source_kind: str | None = None
    source_id: str | None = None
    source_effective_timestamp: datetime | None = None
    fresh_entry_required: bool = False
    reverse_entry_required: bool = False
    rollover_required: bool = False
    state_directory: str | None = None


class S23PaperTradeLedgerStore:
    def __init__(
        self,
        *,
        global_ledger_root: str | Path = _DEFAULT_GLOBAL_LEDGER_ROOT,
        global_ledger_filename: str = _DEFAULT_GLOBAL_LEDGER_FILENAME,
        session_ledger_filename: str = _SESSION_LEDGER_FILENAME,
    ) -> None:
        self._global_ledger_root = Path(global_ledger_root)
        self._global_ledger_filename = global_ledger_filename
        self._session_ledger_filename = session_ledger_filename

    @property
    def global_ledger_path(self) -> Path:
        return self._global_ledger_root / self._global_ledger_filename

    def append(
        self,
        session_directory: str | Path,
        row: S23PaperTradeLedgerRow,
    ) -> tuple[Path, Path]:
        session_path = Path(session_directory) / self._session_ledger_filename
        global_path = self.global_ledger_path
        self._append_jsonl(session_path, row)
        self._append_jsonl(global_path, row)
        return session_path, global_path

    def build_row(
        self,
        *,
        state: S23PaperPositionState,
        event_timestamp: datetime,
        event_type: S23PaperTradeLedgerEventType,
        session_date: date,
        manager_status: str,
        reason_code: str,
        message: str,
        exit_timestamp: datetime | None = None,
        current_price: float | None = None,
        current_bid: float | None = None,
        current_ask: float | None = None,
        exit_price: float | None = None,
        source_kind: str | None = None,
        source_id: str | None = None,
        source_effective_timestamp: datetime | None = None,
        fresh_entry_required: bool = False,
        reverse_entry_required: bool = False,
        rollover_required: bool = False,
        state_directory: str | Path | None = None,
    ) -> S23PaperTradeLedgerRow:
        gross_points = None
        gross_pnl = None
        pnl_reference_price = exit_price if exit_price is not None else current_price
        if pnl_reference_price is not None:
            # S23 is currently option-selling paper mode: lower exit premium is profit.
            gross_points = float(state.entry_price) - float(pnl_reference_price)
            gross_pnl = gross_points * state.quantity
        return S23PaperTradeLedgerRow(
            artifact_version=_ARTIFACT_VERSION,
            event_timestamp=event_timestamp,
            event_type=event_type,
            trade_id=self.trade_id_for_state(state),
            strategy_id=f"{state.strategy_code}:{state.unique_code}",
            strategy_code=state.strategy_code,
            strategy_branch=state.unique_code,
            symbol=state.symbol,
            option_type=state.option_type.value,
            selected_contract_symbol=state.selected_contract_symbol,
            expiry_date=state.expiry_date,
            side=state.side,
            lots=state.lots,
            quantity=state.quantity,
            entry_date=state.entry_date,
            entry_timestamp=state.entry_timestamp,
            entry_price=state.entry_price,
            target_price=state.target_price,
            stoploss_price=state.stoploss_price,
            fsl_price=state.fsl_price,
            trp_price=state.trp_price,
            session_date=session_date,
            lifecycle_status=state.lifecycle_status.value,
            manager_status=manager_status,
            reason_code=reason_code,
            message=message,
            exit_timestamp=exit_timestamp,
            current_price=current_price,
            current_bid=current_bid,
            current_ask=current_ask,
            exit_price=exit_price,
            gross_points=gross_points,
            gross_pnl=gross_pnl,
            source_kind=source_kind,
            source_id=source_id,
            source_effective_timestamp=source_effective_timestamp,
            fresh_entry_required=fresh_entry_required,
            reverse_entry_required=reverse_entry_required,
            rollover_required=rollover_required,
            state_directory=str(state_directory) if state_directory is not None else None,
        )

    @staticmethod
    def trade_id_for_state(state: S23PaperPositionState) -> str:
        timestamp = state.entry_timestamp.strftime("%Y%m%dT%H%M%S")
        return (
            f"{state.strategy_code}-{state.unique_code}-"
            f"{state.selected_contract_symbol}-{timestamp}"
        )

    def _append_jsonl(self, path: Path, row: S23PaperTradeLedgerRow) -> None:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        rendered = existing + json.dumps(self._normalize(row), sort_keys=True) + "\n"
        self._atomic_write_text(path, rendered)

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.parent / f".{path.name}.tmp"
        try:
            temp_path.write_text(content, encoding="utf-8", newline="\n")
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return {
                field.name: self._normalize(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, dict):
            return {
                str(key): self._normalize(val)
                for key, val in sorted(value.items(), key=lambda item: str(item[0]))
            }
        if isinstance(value, tuple | list):
            return [self._normalize(item) for item in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, time):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        return value


__all__ = [
    "S23PaperTradeLedgerEventType",
    "S23PaperTradeLedgerRow",
    "S23PaperTradeLedgerStore",
]
