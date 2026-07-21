from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, Sequence

from .position_state import S23PaperPositionState


_ARTIFACT_VERSION = 1
_SESSION_LEDGER_FILENAME = "paper_trade_ledger.jsonl"
_POSITION_STATE_FILENAME = "paper_position_state.json"
_DEFAULT_GLOBAL_LEDGER_ROOT = Path("tmp/paper_trade_ledger")
_DEFAULT_GLOBAL_LEDGER_FILENAME = "s23_paper_trade_ledger.jsonl"


class S23PaperTradeLedgerEventType(str, Enum):
    OPEN = "OPEN"
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    ACTION_REQUIRED = "ACTION_REQUIRED"


_OPEN_MANAGER_STATUSES = {
    "PAPER_POSITION_OPENED",
    "PAPER_POSITION_HELD",
}

_CLOSE_MANAGER_STATUSES = {
    "PAPER_POSITION_TARGET_HIT",
    "PAPER_POSITION_STOPLOSS_HIT",
    "PAPER_POSITION_FORCE_CLOSED",
    "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
    "PAPER_POSITION_REVERSE_ENTRY_REQUIRED",
}

_DISPLAY_TERMINAL_MANAGER_STATUSES = {
    "PAPER_POSITION_TARGET_HIT",
    "PAPER_POSITION_STOPLOSS_HIT",
    "PAPER_POSITION_FORCE_CLOSED",
    "PAPER_POSITION_ALREADY_CLOSED",
}

_LIFECYCLE_TERMINAL_MANAGER_STATUSES = _CLOSE_MANAGER_STATUSES | {
    "PAPER_POSITION_ROLLOVER_REQUIRED",
    "PAPER_POSITION_ALREADY_CLOSED",
}


def paper_trade_ledger_candidate_paths(
    *,
    artifact_root: str | Path,
    strategy_code: str,
    repo_root: str | Path | None = None,
) -> tuple[Path, ...]:
    artifact_root_path = Path(artifact_root)
    candidate_paths: set[Path] = set()
    if artifact_root_path.exists():
        candidate_paths.update(artifact_root_path.rglob(_SESSION_LEDGER_FILENAME))
    effective_repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    global_ledger = (
        effective_repo_root
        / _DEFAULT_GLOBAL_LEDGER_ROOT
        / f"{str(strategy_code).strip().lower()}_paper_trade_ledger.jsonl"
    )
    if global_ledger.exists():
        candidate_paths.add(global_ledger)
    return tuple(sorted(candidate_paths))


def paper_trade_has_display_backing(
    state_directory: str | Path | None,
    *,
    event_type: str | None,
    lifecycle_status: str | None,
    manager_status: str | None,
) -> bool:
    if state_directory is None:
        return True
    state_path = Path(state_directory) / _POSITION_STATE_FILENAME
    if state_path.exists():
        return True
    return paper_trade_is_terminal(
        event_type=event_type,
        lifecycle_status=lifecycle_status,
        manager_status=manager_status,
    )


def paper_trade_is_terminal(
    *,
    event_type: str | None,
    lifecycle_status: str | None,
    manager_status: str | None,
) -> bool:
    normalized_event_type = str(event_type or "").upper()
    normalized_lifecycle_status = str(lifecycle_status or "").upper()
    return (
        normalized_event_type == "CLOSE"
        or "CLOSED" in normalized_lifecycle_status
        or paper_trade_manager_status_is_terminal(manager_status)
    )


def paper_trade_is_open(
    *,
    lifecycle_status: str | None,
    manager_status: str | None,
) -> bool:
    normalized_lifecycle_status = str(lifecycle_status or "").upper()
    return (
        "OPEN" in normalized_lifecycle_status
        or paper_trade_manager_status_is_open(manager_status)
    )


def paper_trade_manager_status_is_open(manager_status: str | None) -> bool:
    return str(manager_status or "").upper() in _OPEN_MANAGER_STATUSES


def paper_trade_manager_status_is_terminal(manager_status: str | None) -> bool:
    return str(manager_status or "").upper() in _DISPLAY_TERMINAL_MANAGER_STATUSES


def paper_trade_manager_status_is_lifecycle_terminal(manager_status: str | None) -> bool:
    return str(manager_status or "").upper() in _LIFECYCLE_TERMINAL_MANAGER_STATUSES


def paper_trade_event_type_for_manager_status(
    manager_status: str | None,
) -> S23PaperTradeLedgerEventType:
    normalized = str(manager_status or "").upper()
    if normalized == "PAPER_POSITION_OPENED":
        return S23PaperTradeLedgerEventType.OPEN
    if normalized == "PAPER_POSITION_HELD":
        return S23PaperTradeLedgerEventType.HOLD
    if normalized in _CLOSE_MANAGER_STATUSES:
        return S23PaperTradeLedgerEventType.CLOSE
    return S23PaperTradeLedgerEventType.ACTION_REQUIRED


def paper_trade_action_required(
    *,
    fresh_entry_required: bool,
    reverse_entry_required: bool,
    rollover_required: bool,
) -> bool:
    return fresh_entry_required or reverse_entry_required or rollover_required


def paper_trade_display_status_label(label: str | None) -> str:
    value = str(label or "").strip()
    if value in {"", "n/a"}:
        return ""
    if value == "PAPER_ORDER_WAITING_FOR_TRIGGER":
        return "ORDER_WAITING_FOR_TRIGGER"
    if value == "PAPER_ORDER_NOT_FILLED":
        return "ORDER_NOT_FILLED"
    return value


def paper_trade_status_kind(
    *,
    lifecycle_status: str | None,
    manager_status: str | None,
    event_type: str | None,
    fresh_entry_required: bool,
    reverse_entry_required: bool,
    rollover_required: bool,
) -> str:
    normalized_manager_status = str(manager_status or "").upper()
    normalized_lifecycle_status = str(lifecycle_status or "").upper()
    if paper_trade_is_terminal(
        event_type=event_type,
        lifecycle_status=lifecycle_status,
        manager_status=manager_status,
    ):
        return "closed"
    if paper_trade_action_required(
        fresh_entry_required=fresh_entry_required,
        reverse_entry_required=reverse_entry_required,
        rollover_required=rollover_required,
    ):
        return "action"
    if (
        normalized_manager_status == "PAPER_ORDER_NOT_FILLED"
        or normalized_lifecycle_status == "ORDER_NOT_FILLED"
    ):
        return "not_filled"
    if (
        normalized_manager_status == "PAPER_ORDER_WAITING_FOR_TRIGGER"
        or normalized_lifecycle_status == "ORDER_WAITING_FOR_TRIGGER"
    ):
        return "waiting"
    if paper_trade_is_open(
        lifecycle_status=lifecycle_status,
        manager_status=manager_status,
    ):
        return "open"
    return "neutral"


def paper_trade_visible_for_latest_session(
    *,
    row_session_date: date | None,
    event_timestamp: datetime | None,
    latest_session_date: date | None,
    event_type: str | None,
    lifecycle_status: str | None,
    manager_status: str | None,
    fresh_entry_required: bool,
    reverse_entry_required: bool,
    rollover_required: bool,
) -> bool:
    if latest_session_date is None:
        return True
    status_kind = paper_trade_status_kind(
        event_type=event_type,
        lifecycle_status=lifecycle_status,
        manager_status=manager_status,
        fresh_entry_required=fresh_entry_required,
        reverse_entry_required=reverse_entry_required,
        rollover_required=rollover_required,
    )
    effective_row_session_date = row_session_date
    if effective_row_session_date is None and event_timestamp is not None:
        effective_row_session_date = event_timestamp.date()
    if effective_row_session_date == latest_session_date:
        return status_kind != "closed"
    if effective_row_session_date is not None and effective_row_session_date > latest_session_date:
        return False
    return status_kind in {"open", "action"}


class PaperTradeDisplayCandidate(Protocol):
    event_timestamp: datetime | None
    event_type: str
    lifecycle_status: str
    manager_status: str


class PaperTradeStatusCandidate(PaperTradeDisplayCandidate, Protocol):
    fresh_entry_required: bool
    reverse_entry_required: bool
    rollover_required: bool


class PaperTradeIdentityCandidate(PaperTradeStatusCandidate, Protocol):
    trade_id: str


class PaperTradeHistoricalCandidate(PaperTradeIdentityCandidate, Protocol):
    strategy_code: str


def paper_trade_select_display_row(
    rows: Sequence[PaperTradeDisplayCandidate],
) -> PaperTradeDisplayCandidate:
    terminal_rows = [
        row
        for row in rows
        if paper_trade_is_terminal(
            event_type=row.event_type,
            lifecycle_status=row.lifecycle_status,
            manager_status=row.manager_status,
        )
    ]
    candidate_rows = terminal_rows if terminal_rows else rows
    return max(
        candidate_rows,
        key=lambda item: item.event_timestamp.isoformat() if item.event_timestamp else "",
    )


def paper_trade_latest_active_rows(
    rows: Sequence[PaperTradeIdentityCandidate],
    *,
    latest_session_date: date | None,
) -> list[PaperTradeIdentityCandidate]:
    grouped_rows: dict[str, list[PaperTradeIdentityCandidate]] = {}
    for row in rows:
        grouped_rows.setdefault(row.trade_id, []).append(row)
    latest_by_trade = {
        trade_id: paper_trade_select_display_row(trade_rows)
        for trade_id, trade_rows in grouped_rows.items()
    }
    return sorted(
        (
            row
            for row in latest_by_trade.values()
            if paper_trade_visible_for_latest_session(
                row_session_date=getattr(row, "session_date", None),
                event_timestamp=row.event_timestamp,
                latest_session_date=latest_session_date,
                event_type=row.event_type,
                lifecycle_status=row.lifecycle_status,
                manager_status=row.manager_status,
                fresh_entry_required=row.fresh_entry_required,
                reverse_entry_required=row.reverse_entry_required,
                rollover_required=row.rollover_required,
            )
        ),
        key=lambda item: item.event_timestamp.isoformat() if item.event_timestamp else "",
        reverse=True,
    )


def paper_trade_latest_historical_close_rows(
    rows: Sequence[PaperTradeHistoricalCandidate],
) -> list[PaperTradeHistoricalCandidate]:
    latest_close_by_trade: dict[tuple[str, str], PaperTradeHistoricalCandidate] = {}
    for row in rows:
        if str(row.event_type).upper() != "CLOSE":
            continue
        key = (row.strategy_code.upper(), row.trade_id)
        current = latest_close_by_trade.get(key)
        if current is None or (
            row.event_timestamp is not None
            and (
                current.event_timestamp is None
                or row.event_timestamp > current.event_timestamp
            )
        ):
            latest_close_by_trade[key] = row
    return sorted(
        latest_close_by_trade.values(),
        key=lambda item: item.event_timestamp.isoformat() if item.event_timestamp else "",
        reverse=True,
    )


def paper_trade_summary_counts(
    rows: Sequence[PaperTradeDisplayCandidate],
) -> dict[str, int]:
    counts = {
        "unique_trades": len(rows),
        "open_positions": 0,
        "action_required": 0,
        "closed_trades": 0,
    }
    for row in rows:
        status_kind = paper_trade_status_kind(
            event_type=row.event_type,
            lifecycle_status=row.lifecycle_status,
            manager_status=row.manager_status,
            fresh_entry_required=getattr(row, "fresh_entry_required", False),
            reverse_entry_required=getattr(row, "reverse_entry_required", False),
            rollover_required=getattr(row, "rollover_required", False),
        )
        if status_kind == "open":
            counts["open_positions"] += 1
        if status_kind == "action":
            counts["action_required"] += 1
        if status_kind == "closed":
            counts["closed_trades"] += 1
    return counts


def paper_trade_status_labels(
    row: PaperTradeStatusCandidate,
) -> list[str]:
    if paper_trade_is_terminal(
        event_type=row.event_type,
        lifecycle_status=row.lifecycle_status,
        manager_status=row.manager_status,
    ):
        return ["POSITION_CLOSED"]
    status_labels: list[str] = []
    for label in (row.lifecycle_status, row.manager_status):
        normalized = paper_trade_display_status_label(label)
        if normalized and normalized not in status_labels:
            status_labels.append(normalized)
    action_flags = []
    if row.fresh_entry_required:
        action_flags.append("Fresh Entry")
    if row.reverse_entry_required:
        action_flags.append("Reverse Entry")
    if row.rollover_required:
        action_flags.append("Rollover")
    action_text = ", ".join(action_flags)
    if action_text:
        status_labels.append(action_text)
    return status_labels


def paper_trade_followup_note(
    row: PaperTradeStatusCandidate,
) -> str:
    if not paper_trade_is_terminal(
        event_type=row.event_type,
        lifecycle_status=row.lifecycle_status,
        manager_status=row.manager_status,
    ):
        return ""
    notes = []
    if row.fresh_entry_required:
        notes.append("fresh entry recalculation required")
    if row.reverse_entry_required:
        notes.append("reverse entry review required")
    if row.rollover_required:
        notes.append("rollover review required")
    if not notes:
        return ""
    return "Follow-up: " + "; ".join(notes) + "."


def paper_trade_normalized_message(message: str | None) -> str:
    value = str(message or "")
    if not value:
        return ""
    return value.replace("S23 READY decision created", "READY decision created")


def paper_trade_option_label(symbol: str | None) -> str:
    text = str(symbol or "").upper()
    if text.endswith("_CE") or "_CE-" in text:
        return "CE"
    if text.endswith("_PE") or "_PE-" in text:
        return "PE"
    return "OPTION"


def paper_trade_branch_label(branch: str | None) -> str:
    text = str(branch or "").upper()
    if "BEAR" in text and ("CALL" in text or text.endswith("_CE")):
        return "Bear Call"
    if "BEAR" in text and ("PUT" in text or text.endswith("_PE")):
        return "Bear Put"
    if "BULL" in text and ("CALL" in text or text.endswith("_CE")):
        return "Bull Call"
    if "BULL" in text and ("PUT" in text or text.endswith("_PE")):
        return "Bull Put"
    return str(branch or "n/a").replace("_", " ").title()


def paper_trade_pnl_tone(gross_pnl: float | None) -> str:
    if gross_pnl is None:
        return ""
    return "good-text" if gross_pnl >= 0 else "bad-text"


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
    "paper_trade_action_required",
    "paper_trade_branch_label",
    "paper_trade_display_status_label",
    "paper_trade_event_type_for_manager_status",
    "paper_trade_followup_note",
    "paper_trade_has_display_backing",
    "paper_trade_is_open",
    "paper_trade_is_terminal",
    "paper_trade_latest_active_rows",
    "paper_trade_latest_historical_close_rows",
    "paper_trade_manager_status_is_open",
    "paper_trade_manager_status_is_lifecycle_terminal",
    "paper_trade_manager_status_is_terminal",
    "paper_trade_normalized_message",
    "paper_trade_option_label",
    "paper_trade_pnl_tone",
    "paper_trade_status_kind",
    "paper_trade_status_labels",
    "paper_trade_select_display_row",
    "paper_trade_summary_counts",
    "paper_trade_visible_for_latest_session",
    "S23PaperTradeLedgerEventType",
    "S23PaperTradeLedgerRow",
    "S23PaperTradeLedgerStore",
]
