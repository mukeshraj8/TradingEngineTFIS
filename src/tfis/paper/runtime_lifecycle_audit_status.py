from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs
from .order_state import PaperOrderStateDiscovery, paper_order_is_waiting_for_trigger
from .position_state import PaperPositionStateStore, paper_position_is_active


_AUDIT_FILENAME = "paper_lifecycle_supervisor_events.jsonl"


@dataclass(frozen=True, slots=True)
class PaperRuntimeLifecycleAuditStatus:
    strategy_code: str
    status: str
    managed_state_count: int
    audit_state_count: int
    missing_audit_count: int
    stale_audit_count: int
    invalid_audit_count: int
    actionable_state_count: int
    latest_event_timestamp: str | None
    latest_event_type: str | None
    latest_status: str | None
    latest_reason_code: str | None
    message: str


def load_paper_runtime_lifecycle_audit_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: Path,
    stale_after_seconds: float = 300.0,
) -> tuple[PaperRuntimeLifecycleAuditStatus, ...]:
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=repo_root)
    statuses: list[PaperRuntimeLifecycleAuditStatus] = []
    for spec in specs:
        try:
            statuses.append(
                _load_strategy_lifecycle_audit_status(
                    strategy_code=spec.strategy_code,
                    artifact_root=spec.artifact_root,
                    stale_after_seconds=stale_after_seconds,
                )
            )
        except Exception as exc:
            statuses.append(
                PaperRuntimeLifecycleAuditStatus(
                    strategy_code=spec.strategy_code,
                    status="FAIL",
                    managed_state_count=0,
                    audit_state_count=0,
                    missing_audit_count=0,
                    stale_audit_count=0,
                    invalid_audit_count=1,
                    actionable_state_count=0,
                    latest_event_timestamp=None,
                    latest_event_type=None,
                    latest_status=None,
                    latest_reason_code=None,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(statuses)


def _load_strategy_lifecycle_audit_status(
    *,
    strategy_code: str,
    artifact_root: Path,
    stale_after_seconds: float,
) -> PaperRuntimeLifecycleAuditStatus:
    managed_dirs = _managed_state_directories(
        strategy_code=strategy_code,
        artifact_root=artifact_root,
    )
    if not managed_dirs:
        return PaperRuntimeLifecycleAuditStatus(
            strategy_code=strategy_code,
            status="NONE",
            managed_state_count=0,
            audit_state_count=0,
            missing_audit_count=0,
            stale_audit_count=0,
            invalid_audit_count=0,
            actionable_state_count=0,
            latest_event_timestamp=None,
            latest_event_type=None,
            latest_status=None,
            latest_reason_code=None,
            message="no managed paper order/position states found",
        )

    latest_row: dict[str, object] | None = None
    latest_dt: datetime | None = None
    audit_state_count = 0
    missing_audit_count = 0
    invalid_audit_count = 0
    stale_audit_count = 0
    actionable_state_count = 0
    now = datetime.now(UTC)
    for state_dir, actionable in managed_dirs:
        if actionable:
            actionable_state_count += 1
        audit_path = state_dir / _AUDIT_FILENAME
        if not audit_path.exists():
            missing_audit_count += 1
            continue
        rows = _load_jsonl_dicts(audit_path)
        if not rows:
            invalid_audit_count += 1
            continue
        audit_state_count += 1
        row = max(
            rows,
            key=lambda item: _parse_datetime(item.get("event_timestamp")) or datetime.min.replace(tzinfo=UTC),
        )
        row_dt = _parse_datetime(row.get("event_timestamp"))
        if row_dt is None:
            invalid_audit_count += 1
            continue
        if actionable and (now - _as_aware_utc(row_dt)).total_seconds() > stale_after_seconds:
            stale_audit_count += 1
        if latest_dt is None or _as_aware_utc(row_dt) > _as_aware_utc(latest_dt):
            latest_dt = row_dt
            latest_row = row

    if invalid_audit_count:
        status = "FAIL"
    elif missing_audit_count or stale_audit_count:
        status = "ATTENTION"
    else:
        status = "PASS"

    return PaperRuntimeLifecycleAuditStatus(
        strategy_code=strategy_code,
        status=status,
        managed_state_count=len(managed_dirs),
        audit_state_count=audit_state_count,
        missing_audit_count=missing_audit_count,
        stale_audit_count=stale_audit_count,
        invalid_audit_count=invalid_audit_count,
        actionable_state_count=actionable_state_count,
        latest_event_timestamp=latest_dt.isoformat() if latest_dt is not None else None,
        latest_event_type=_string_or_none(latest_row.get("event_type")) if latest_row else None,
        latest_status=_string_or_none(latest_row.get("status")) if latest_row else None,
        latest_reason_code=_string_or_none(latest_row.get("reason_code")) if latest_row else None,
        message=_status_message(
            status=status,
            managed_state_count=len(managed_dirs),
            audit_state_count=audit_state_count,
            missing_audit_count=missing_audit_count,
            stale_audit_count=stale_audit_count,
            invalid_audit_count=invalid_audit_count,
        ),
    )


def _managed_state_directories(
    *,
    strategy_code: str,
    artifact_root: Path,
) -> tuple[tuple[Path, bool], ...]:
    if not artifact_root.exists():
        return ()
    result: dict[Path, bool] = {}
    order_discovery = PaperOrderStateDiscovery()
    for candidate in order_discovery.find_orders((artifact_root,), strategy_code=strategy_code):
        result[candidate.state_directory] = paper_order_is_waiting_for_trigger(candidate.state.status)
    position_store = PaperPositionStateStore()
    for state_path in sorted(artifact_root.rglob("paper_position_state.json")):
        state_dir = state_path.parent.resolve()
        try:
            state = position_store.load_state(state_dir)
        except Exception:
            result.setdefault(state_dir, False)
            continue
        if state.strategy_code.strip().upper() != strategy_code.strip().upper():
            continue
        result[state_dir] = result.get(state_dir, False) or paper_position_is_active(state.lifecycle_status)
    return tuple(sorted(result.items(), key=lambda item: str(item[0])))


def _load_jsonl_dicts(path: Path) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return ()
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text.lstrip("\ufeff"))
        except json.JSONDecodeError:
            return ()
        if not isinstance(payload, dict):
            return ()
        rows.append(payload)
    return tuple(rows)


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


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _string_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _status_message(
    *,
    status: str,
    managed_state_count: int,
    audit_state_count: int,
    missing_audit_count: int,
    stale_audit_count: int,
    invalid_audit_count: int,
) -> str:
    if status == "FAIL":
        return f"{invalid_audit_count} lifecycle supervisor audit file(s) are invalid"
    if status == "ATTENTION":
        return (
            "lifecycle supervisor audit evidence needs attention: "
            f"managed={managed_state_count}, audited={audit_state_count}, "
            f"missing={missing_audit_count}, stale={stale_audit_count}"
        )
    return (
        "lifecycle supervisor audit evidence present: "
        f"managed={managed_state_count}, audited={audit_state_count}"
    )


__all__ = [
    "PaperRuntimeLifecycleAuditStatus",
    "load_paper_runtime_lifecycle_audit_statuses",
]
