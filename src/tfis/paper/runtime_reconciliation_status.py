from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs
from .order_state import PaperOrderStateDiscovery, PaperOrderStatus
from .position_state import PaperPositionStateStore, paper_position_is_active
from .trade_ledger import S23PaperTradeLedgerStore, paper_trade_is_terminal


@dataclass(frozen=True, slots=True)
class PaperRuntimeReconciliationStatus:
    strategy_code: str
    status: str
    persisted_state_count: int
    checked_trade_count: int
    persisted_order_state_count: int
    checked_order_event_count: int
    conflict_count: int
    message: str


def load_paper_runtime_reconciliation_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: Path,
) -> tuple[PaperRuntimeReconciliationStatus, ...]:
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=repo_root)
    statuses: list[PaperRuntimeReconciliationStatus] = []
    for spec in specs:
        try:
            statuses.append(_reconciliation_status_for_spec(spec.strategy_code, spec.artifact_root, repo_root))
        except Exception as exc:
            statuses.append(
                PaperRuntimeReconciliationStatus(
                    strategy_code=spec.strategy_code,
                    status="FAIL",
                    persisted_state_count=0,
                    checked_trade_count=0,
                    persisted_order_state_count=0,
                    checked_order_event_count=0,
                    conflict_count=1,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(statuses)


def _reconciliation_status_for_spec(
    strategy_code: str,
    artifact_root: Path,
    repo_root: Path,
) -> PaperRuntimeReconciliationStatus:
    state_store = PaperPositionStateStore()
    order_discovery = PaperOrderStateDiscovery()
    ledger_store = S23PaperTradeLedgerStore(
        global_ledger_root=repo_root / "tmp" / "paper_trade_ledger",
        global_ledger_filename=f"{strategy_code.strip().lower()}_paper_trade_ledger.jsonl",
    )
    state_paths = tuple(sorted(artifact_root.rglob("paper_position_state.json"))) if artifact_root.exists() else ()
    order_candidates = (
        order_discovery.find_orders((artifact_root,), strategy_code=strategy_code)
        if artifact_root.exists()
        else ()
    )
    if not state_paths and not order_candidates:
        return PaperRuntimeReconciliationStatus(
            strategy_code=strategy_code,
            status="NONE",
            persisted_state_count=0,
            checked_trade_count=0,
            persisted_order_state_count=0,
            checked_order_event_count=0,
            conflict_count=0,
            message="no persisted paper position/order states found",
        )

    conflicts: list[str] = []

    # Load persisted states once, then scan the global ledger once for only the
    # trade IDs that are actually needed. Previously the global JSONL ledger
    # was re-read in full for every persisted position state, which made
    # dashboard construction O(number_of_states * ledger_size).
    loaded_states: list[tuple[Path, object, str]] = []
    for state_path in state_paths:
        state_dir = state_path.parent
        state = state_store.load_state(state_dir)
        loaded_states.append((state_dir, state, ledger_store.trade_id_for_state(state)))

    global_latest_rows = _latest_trade_rows_by_id(
        ledger_store.global_ledger_path,
        trade_ids={trade_id for _, _, trade_id in loaded_states},
    )

    checked_trade_count = 0
    for state_dir, state, trade_id in loaded_states:
        checked_trade_count += 1
        latest_row = _latest_trade_row_for_state(
            state_dir=state_dir,
            global_latest_row=global_latest_rows.get(trade_id),
            trade_id=trade_id,
        )
        if latest_row is None:
            conflicts.append(f"{state_dir}: missing ledger row for trade_id={trade_id}")
            continue
        latest_row_terminal = paper_trade_is_terminal(
            event_type=latest_row.get("event_type"),
            lifecycle_status=latest_row.get("lifecycle_status"),
            manager_status=latest_row.get("manager_status"),
        )
        state_is_active = paper_position_is_active(state.lifecycle_status)
        if state_is_active and latest_row_terminal:
            conflicts.append(
                f"{state_dir}: active position state {state.lifecycle_status.value} conflicts with terminal ledger row "
                f"{latest_row.get('manager_status') or latest_row.get('lifecycle_status') or latest_row.get('event_type')}"
            )
        if (not state_is_active) and (not latest_row_terminal):
            conflicts.append(
                f"{state_dir}: terminal position state {state.lifecycle_status.value} conflicts with non-terminal ledger row "
                f"{latest_row.get('manager_status') or latest_row.get('lifecycle_status') or latest_row.get('event_type')}"
            )

    checked_order_event_count = 0
    for candidate in order_candidates:
        latest_event = _latest_order_event_for_state(candidate.state_directory)
        state_status = candidate.state.status.value
        if latest_event is None:
            if candidate.state.status is not PaperOrderStatus.PAPER_ORDER_NOT_FILLED:
                conflicts.append(f"{candidate.state_directory}: missing order event row")
            continue
        checked_order_event_count += 1
        latest_status = str(latest_event.get("status") or "").strip()
        if (
            candidate.state.status is not PaperOrderStatus.PAPER_ORDER_NOT_FILLED
            and latest_status != state_status
        ):
            conflicts.append(
                f"{candidate.state_directory}: order state {state_status} conflicts with latest order event {latest_status or '<missing>'}"
            )
        if candidate.state.status.value == "PAPER_ORDER_FILLED":
            event_fill_price = latest_event.get("fill_price")
            if candidate.state.fill_price is None or event_fill_price in (None, ""):
                conflicts.append(
                    f"{candidate.state_directory}: filled order state/event missing fill_price"
                )
            event_fill_timestamp = latest_event.get("timestamp")
            if candidate.state.fill_timestamp is None or event_fill_timestamp in (None, ""):
                conflicts.append(
                    f"{candidate.state_directory}: filled order state/event missing fill timestamp"
                )

    return PaperRuntimeReconciliationStatus(
        strategy_code=strategy_code,
        status="PASS" if not conflicts else "FAIL",
        persisted_state_count=len(state_paths),
        checked_trade_count=checked_trade_count,
        persisted_order_state_count=len(order_candidates),
        checked_order_event_count=checked_order_event_count,
        conflict_count=len(conflicts),
        message=(
            "position ledger and order event authority agree"
            if not conflicts
            else "; ".join(conflicts[:5])
        ),
    )


def _latest_trade_row_for_state(
    *,
    state_dir: Path,
    global_latest_row: dict[str, object] | None,
    trade_id: str,
) -> dict[str, object] | None:
    # Session ledgers are normally small and are authoritative for the local
    # state directory. Scan them once, streaming line-by-line, then compare
    # against the already-indexed global row.
    session_latest = _latest_trade_row_in_path(
        state_dir / "paper_trade_ledger.jsonl",
        trade_id=trade_id,
    )
    candidates = [row for row in (session_latest, global_latest_row) if row is not None]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda row: _parse_datetime(row.get("event_timestamp")) or datetime.min,
    )


def _latest_trade_row_in_path(
    path: Path,
    *,
    trade_id: str,
) -> dict[str, object] | None:
    latest: dict[str, object] | None = None
    latest_timestamp = datetime.min
    if not path.exists():
        return None
    for row in _iter_jsonl_dicts(path):
        if str(row.get("trade_id") or "") != trade_id:
            continue
        row_timestamp = _parse_datetime(row.get("event_timestamp")) or datetime.min
        if latest is None or row_timestamp >= latest_timestamp:
            latest = row
            latest_timestamp = row_timestamp
    return latest


def _latest_trade_rows_by_id(
    path: Path,
    *,
    trade_ids: set[str],
) -> dict[str, dict[str, object]]:
    if not trade_ids or not path.exists():
        return {}

    latest_rows: dict[str, dict[str, object]] = {}
    latest_timestamps: dict[str, datetime] = {}
    for row in _iter_jsonl_dicts(path):
        trade_id = str(row.get("trade_id") or "")
        if trade_id not in trade_ids:
            continue
        row_timestamp = _parse_datetime(row.get("event_timestamp")) or datetime.min
        current_timestamp = latest_timestamps.get(trade_id)
        if current_timestamp is None or row_timestamp >= current_timestamp:
            latest_rows[trade_id] = row
            latest_timestamps[trade_id] = row_timestamp
    return latest_rows


def _latest_order_event_for_state(state_dir: Path) -> dict[str, object] | None:
    events_path = state_dir / "paper_order_events.jsonl"
    if not events_path.exists():
        return None
    latest: dict[str, object] | None = None
    latest_timestamp = datetime.min
    for row in _iter_jsonl_dicts(events_path):
        row_timestamp = _parse_datetime(row.get("timestamp")) or datetime.min
        if latest is None or row_timestamp >= latest_timestamp:
            latest = row
            latest_timestamp = row_timestamp
    return latest


def _iter_jsonl_dicts(path: Path):
    """Yield JSON object rows without loading the complete ledger into memory."""
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text.lstrip("\ufeff"))
            if isinstance(payload, dict):
                yield payload


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


__all__ = [
    "PaperRuntimeReconciliationStatus",
    "load_paper_runtime_reconciliation_statuses",
]
