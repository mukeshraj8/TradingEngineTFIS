from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .fresh_entry_handoff import load_fresh_decision_launch_marker
from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs
from .trade_ledger import paper_trade_is_terminal


@dataclass(frozen=True, slots=True)
class PaperRuntimeFreshEntryHandoffStatus:
    strategy_code: str
    status: str
    fresh_close_count: int
    resolved_count: int
    unresolved_count: int
    message: str


def load_paper_runtime_fresh_entry_handoff_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: Path,
) -> tuple[PaperRuntimeFreshEntryHandoffStatus, ...]:
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=repo_root)
    statuses: list[PaperRuntimeFreshEntryHandoffStatus] = []
    for spec in specs:
        try:
            statuses.append(
                _handoff_status_for_spec(
                    strategy_code=spec.strategy_code,
                    artifact_root=spec.artifact_root,
                    repo_root=repo_root,
                )
            )
        except Exception as exc:
            statuses.append(
                PaperRuntimeFreshEntryHandoffStatus(
                    strategy_code=spec.strategy_code,
                    status="FAIL",
                    fresh_close_count=0,
                    resolved_count=0,
                    unresolved_count=1,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(statuses)


def _handoff_status_for_spec(
    *,
    strategy_code: str,
    artifact_root: Path,
    repo_root: Path,
) -> PaperRuntimeFreshEntryHandoffStatus:
    ledger_paths = list(_candidate_ledger_paths(artifact_root=artifact_root, strategy_code=strategy_code, repo_root=repo_root))
    rows: list[dict[str, object]] = []
    for path in ledger_paths:
        rows.extend(_iter_jsonl_dicts(path))
    latest_rows = _latest_rows_by_trade(rows)
    fresh_close_rows = [
        row
        for row in latest_rows
        if bool(row.get("fresh_entry_required"))
        and paper_trade_is_terminal(
            event_type=_text(row.get("event_type")),
            lifecycle_status=_text(row.get("lifecycle_status")),
            manager_status=_text(row.get("manager_status")),
        )
    ]
    if not fresh_close_rows:
        return PaperRuntimeFreshEntryHandoffStatus(
            strategy_code=strategy_code,
            status="NONE",
            fresh_close_count=0,
            resolved_count=0,
            unresolved_count=0,
            message="no fresh-entry-required terminal trade rows found",
        )

    unresolved: list[str] = []
    resolved_count = 0
    for row in fresh_close_rows:
        resolution = _resolve_handoff(row=row, all_rows=rows, artifact_root=artifact_root)
        if resolution is None:
            unresolved.append(
                f"{row.get('trade_id') or 'unknown_trade'}@{row.get('strategy_branch') or 'unknown_branch'}"
            )
        else:
            resolved_count += 1

    return PaperRuntimeFreshEntryHandoffStatus(
        strategy_code=strategy_code,
        status="PASS" if not unresolved else "FAIL",
        fresh_close_count=len(fresh_close_rows),
        resolved_count=resolved_count,
        unresolved_count=len(unresolved),
        message=(
            f"fresh-entry handoff evidence confirmed for {resolved_count} terminal close(s)"
            if not unresolved
            else "missing fresh-entry handoff evidence for " + ", ".join(unresolved[:5])
        ),
    )


def _resolve_handoff(
    *,
    row: dict[str, object],
    all_rows: list[dict[str, object]],
    artifact_root: Path,
) -> str | None:
    state_directory = _text(row.get("state_directory"))
    if state_directory:
        marker = load_fresh_decision_launch_marker(Path(state_directory))
        if marker is not None:
            return "marker"
    branch = _text(row.get("strategy_branch"))
    event_timestamp = _parse_datetime(row.get("event_timestamp"))
    if branch and event_timestamp is not None:
        for candidate in all_rows:
            if _text(candidate.get("strategy_branch")) != branch:
                continue
            candidate_timestamp = _parse_datetime(candidate.get("event_timestamp"))
            if candidate_timestamp is None or candidate_timestamp <= event_timestamp:
                continue
            candidate_kind = _trade_row_status_kind(candidate)
            if candidate_kind in {"waiting", "not_filled", "open", "action"}:
                return f"subsequent_{candidate_kind}_row"
    if branch and _has_later_branch_session_artifact(
        artifact_root=artifact_root,
        branch=branch,
        after_session_date=_parse_date(row.get("session_date")),
    ):
        return "later_branch_session_artifact"
    return None


def _trade_row_status_kind(row: dict[str, object]) -> str:
    manager_status = _text(row.get("manager_status")).upper()
    lifecycle_status = _text(row.get("lifecycle_status")).upper()
    event_type = _text(row.get("event_type")).upper()
    if paper_trade_is_terminal(
        event_type=event_type,
        lifecycle_status=lifecycle_status,
        manager_status=manager_status,
    ):
        return "closed"
    if bool(row.get("fresh_entry_required")) or bool(row.get("reverse_entry_required")) or bool(row.get("rollover_required")):
        return "action"
    if manager_status == "PAPER_ORDER_NOT_FILLED" or lifecycle_status == "ORDER_NOT_FILLED":
        return "not_filled"
    if manager_status == "PAPER_ORDER_WAITING_FOR_TRIGGER" or lifecycle_status == "ORDER_WAITING_FOR_TRIGGER":
        return "waiting"
    if "OPEN" in lifecycle_status or manager_status in {"PAPER_POSITION_OPENED", "PAPER_POSITION_HELD"}:
        return "open"
    return "neutral"


def _candidate_ledger_paths(
    *,
    artifact_root: Path,
    strategy_code: str,
    repo_root: Path,
) -> tuple[Path, ...]:
    paths: set[Path] = set()
    if artifact_root.exists():
        paths.update(artifact_root.rglob("paper_trade_ledger.jsonl"))
    global_ledger = repo_root / "tmp" / "paper_trade_ledger" / f"{strategy_code.strip().lower()}_paper_trade_ledger.jsonl"
    if global_ledger.exists():
        paths.add(global_ledger)
    return tuple(sorted(paths))


def _has_later_branch_session_artifact(
    *,
    artifact_root: Path,
    branch: str,
    after_session_date: date | None,
) -> bool:
    if not artifact_root.exists():
        return False
    for date_dir in sorted(artifact_root.iterdir()):
        if not date_dir.is_dir():
            continue
        session_date = _parse_date(date_dir.name)
        if session_date is None:
            continue
        if after_session_date is not None and session_date <= after_session_date:
            continue
        for branch_dir in date_dir.glob(f"*/{branch}"):
            if not branch_dir.is_dir():
                continue
            if any(
                (branch_dir / filename).exists()
                for filename in (
                    "trade_decision_summary.json",
                    "trade_decision_explainer.json",
                    "paper_order_state.json",
                    "paper_position_state.json",
                )
            ):
                return True
    return False


def _latest_rows_by_trade(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    latest_by_trade: dict[str, dict[str, object]] = {}
    for row in rows:
        trade_id = _text(row.get("trade_id"))
        if not trade_id:
            continue
        current = latest_by_trade.get(trade_id)
        row_timestamp = _parse_datetime(row.get("event_timestamp")) or datetime.min
        current_timestamp = _parse_datetime(current.get("event_timestamp")) if current is not None else None
        if current is None or current_timestamp is None or row_timestamp >= current_timestamp:
            latest_by_trade[trade_id] = row
    return list(latest_by_trade.values())


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
    text = _text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_date(value: object) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _text(value: object) -> str:
    return str(value or "").strip()


__all__ = [
    "PaperRuntimeFreshEntryHandoffStatus",
    "load_paper_runtime_fresh_entry_handoff_statuses",
]
