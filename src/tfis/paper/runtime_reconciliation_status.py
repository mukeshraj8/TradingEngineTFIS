from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs
from .position_state import PaperPositionStateStore, paper_position_is_active
from .trade_ledger import S23PaperTradeLedgerStore, paper_trade_is_terminal


@dataclass(frozen=True, slots=True)
class PaperRuntimeReconciliationStatus:
    strategy_code: str
    status: str
    persisted_state_count: int
    checked_trade_count: int
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
    ledger_store = S23PaperTradeLedgerStore(
        global_ledger_root=repo_root / "tmp" / "paper_trade_ledger",
        global_ledger_filename=f"{strategy_code.strip().lower()}_paper_trade_ledger.jsonl",
    )
    state_paths = tuple(sorted(artifact_root.rglob("paper_position_state.json"))) if artifact_root.exists() else ()
    if not state_paths:
        return PaperRuntimeReconciliationStatus(
            strategy_code=strategy_code,
            status="NONE",
            persisted_state_count=0,
            checked_trade_count=0,
            conflict_count=0,
            message="no persisted paper position states found",
        )

    conflicts: list[str] = []
    checked_trade_count = 0
    for state_path in state_paths:
        state_dir = state_path.parent
        state = state_store.load_state(state_dir)
        checked_trade_count += 1
        trade_id = ledger_store.trade_id_for_state(state)
        latest_row = _latest_trade_row_for_state(
            state_dir=state_dir,
            global_ledger_path=ledger_store.global_ledger_path,
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

    return PaperRuntimeReconciliationStatus(
        strategy_code=strategy_code,
        status="PASS" if not conflicts else "FAIL",
        persisted_state_count=len(state_paths),
        checked_trade_count=checked_trade_count,
        conflict_count=len(conflicts),
        message=(
            "position-state and ledger authority agree"
            if not conflicts
            else "; ".join(conflicts[:5])
        ),
    )


def _latest_trade_row_for_state(
    *,
    state_dir: Path,
    global_ledger_path: Path,
    trade_id: str,
) -> dict[str, object] | None:
    candidates: list[dict[str, object]] = []
    session_ledger_path = state_dir / "paper_trade_ledger.jsonl"
    for path in (session_ledger_path, global_ledger_path):
        if not path.exists():
            continue
        for row in _iter_jsonl_dicts(path):
            if str(row.get("trade_id") or "") != trade_id:
                continue
            candidates.append(row)
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: _parse_datetime(row.get("event_timestamp")) or datetime.min,
        reverse=True,
    )
    return candidates[0]


def _iter_jsonl_dicts(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text.lstrip("\ufeff"))
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


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
