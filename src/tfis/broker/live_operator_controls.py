from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


_APPROVAL_FILENAME = "live_operator_approval.json"
_KILL_SWITCH_FILENAME = "live_kill_switch.json"
_EVENTS_FILENAME = "live_operator_control_events.jsonl"


class LiveOperatorControlAction(str, Enum):
    APPROVE_LIVE_MODE = "APPROVE_LIVE_MODE"
    ACTIVATE_KILL_SWITCH = "ACTIVATE_KILL_SWITCH"
    CLEAR_KILL_SWITCH = "CLEAR_KILL_SWITCH"


@dataclass(frozen=True, slots=True)
class LiveOperatorApproval:
    approved: bool
    approved_by: str | None
    approved_at: datetime | None
    expires_at: datetime | None
    reason: str | None
    audit_event_id: str | None


@dataclass(frozen=True, slots=True)
class LiveKillSwitchState:
    available: bool
    active: bool
    updated_at: datetime | None
    updated_by: str | None
    reason: str | None
    audit_event_id: str | None


@dataclass(frozen=True, slots=True)
class LiveOperatorControlEvent:
    event_id: str
    action: LiveOperatorControlAction
    occurred_at: datetime
    actor: str
    reason: str


@dataclass(frozen=True, slots=True)
class LiveOperatorControlIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LiveOperatorControlValidation:
    status: str
    issue_count: int
    issues: tuple[LiveOperatorControlIssue, ...]
    message: str


def validate_live_operator_controls(
    *,
    approval: LiveOperatorApproval,
    kill_switch: LiveKillSwitchState,
    now: datetime,
) -> LiveOperatorControlValidation:
    issues: list[LiveOperatorControlIssue] = []
    if not approval.approved:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_OPERATOR_APPROVAL_MISSING",
                message="Explicit operator live-mode approval is missing.",
            )
        )
    if not approval.approved_by:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_OPERATOR_APPROVER_MISSING",
                message="Live-mode approval must record an approver.",
            )
        )
    if approval.approved_at is None:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_OPERATOR_APPROVAL_TIMESTAMP_MISSING",
                message="Live-mode approval timestamp is missing.",
            )
        )
    if approval.expires_at is None or approval.expires_at <= now:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_OPERATOR_APPROVAL_EXPIRED",
                message="Live-mode approval is missing an unexpired expiry timestamp.",
            )
        )
    if not approval.reason:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_OPERATOR_APPROVAL_REASON_MISSING",
                message="Live-mode approval must include a reason.",
            )
        )
    if not approval.audit_event_id:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_OPERATOR_APPROVAL_AUDIT_MISSING",
                message="Live-mode approval must be backed by an audit event.",
            )
        )
    if not kill_switch.available:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_KILL_SWITCH_UNAVAILABLE",
                message="A live kill switch must be available before live routing.",
            )
        )
    if kill_switch.active:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_KILL_SWITCH_ACTIVE",
                message="Live kill switch is active; live routing must remain blocked.",
            )
        )
    if not kill_switch.audit_event_id:
        issues.append(
            LiveOperatorControlIssue(
                code="LIVE_KILL_SWITCH_AUDIT_MISSING",
                message="Live kill-switch state must be backed by an audit event.",
            )
        )
    status = "FAIL" if issues else "PASS"
    return LiveOperatorControlValidation(
        status=status,
        issue_count=len(issues),
        issues=tuple(issues),
        message=(
            f"{len(issues)} live operator-control issue(s) detected."
            if issues
            else "Live operator approval is explicit, unexpired, audited, and the kill switch is available."
        ),
    )


class LiveOperatorControlStore:
    def approve_live_mode(
        self,
        control_directory: str | Path,
        *,
        actor: str,
        reason: str,
        approved_at: datetime,
        expires_at: datetime,
    ) -> LiveOperatorApproval:
        event = self._append_event(
            control_directory,
            action=LiveOperatorControlAction.APPROVE_LIVE_MODE,
            actor=actor,
            reason=reason,
            occurred_at=approved_at,
        )
        approval = LiveOperatorApproval(
            approved=True,
            approved_by=actor,
            approved_at=approved_at,
            expires_at=expires_at,
            reason=reason,
            audit_event_id=event.event_id,
        )
        self._write_json(Path(control_directory) / _APPROVAL_FILENAME, approval)
        return approval

    def activate_kill_switch(
        self,
        control_directory: str | Path,
        *,
        actor: str,
        reason: str,
        occurred_at: datetime,
    ) -> LiveKillSwitchState:
        event = self._append_event(
            control_directory,
            action=LiveOperatorControlAction.ACTIVATE_KILL_SWITCH,
            actor=actor,
            reason=reason,
            occurred_at=occurred_at,
        )
        state = LiveKillSwitchState(
            available=True,
            active=True,
            updated_at=occurred_at,
            updated_by=actor,
            reason=reason,
            audit_event_id=event.event_id,
        )
        self._write_json(Path(control_directory) / _KILL_SWITCH_FILENAME, state)
        return state

    def clear_kill_switch(
        self,
        control_directory: str | Path,
        *,
        actor: str,
        reason: str,
        occurred_at: datetime,
    ) -> LiveKillSwitchState:
        event = self._append_event(
            control_directory,
            action=LiveOperatorControlAction.CLEAR_KILL_SWITCH,
            actor=actor,
            reason=reason,
            occurred_at=occurred_at,
        )
        state = LiveKillSwitchState(
            available=True,
            active=False,
            updated_at=occurred_at,
            updated_by=actor,
            reason=reason,
            audit_event_id=event.event_id,
        )
        self._write_json(Path(control_directory) / _KILL_SWITCH_FILENAME, state)
        return state

    def load_approval(self, control_directory: str | Path) -> LiveOperatorApproval:
        payload = self._load_json(Path(control_directory) / _APPROVAL_FILENAME)
        return LiveOperatorApproval(
            approved=bool(payload["approved"]),
            approved_by=_optional_text(payload.get("approved_by")),
            approved_at=_optional_datetime(payload.get("approved_at")),
            expires_at=_optional_datetime(payload.get("expires_at")),
            reason=_optional_text(payload.get("reason")),
            audit_event_id=_optional_text(payload.get("audit_event_id")),
        )

    def load_kill_switch(self, control_directory: str | Path) -> LiveKillSwitchState:
        payload = self._load_json(Path(control_directory) / _KILL_SWITCH_FILENAME)
        return LiveKillSwitchState(
            available=bool(payload["available"]),
            active=bool(payload["active"]),
            updated_at=_optional_datetime(payload.get("updated_at")),
            updated_by=_optional_text(payload.get("updated_by")),
            reason=_optional_text(payload.get("reason")),
            audit_event_id=_optional_text(payload.get("audit_event_id")),
        )

    def load_events(
        self,
        control_directory: str | Path,
    ) -> tuple[LiveOperatorControlEvent, ...]:
        path = Path(control_directory) / _EVENTS_FILENAME
        if not path.exists():
            return ()
        events: list[LiveOperatorControlEvent] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            events.append(
                LiveOperatorControlEvent(
                    event_id=str(payload["event_id"]),
                    action=LiveOperatorControlAction(str(payload["action"])),
                    occurred_at=datetime.fromisoformat(str(payload["occurred_at"])),
                    actor=str(payload["actor"]),
                    reason=str(payload["reason"]),
                )
            )
        return tuple(events)

    def _append_event(
        self,
        control_directory: str | Path,
        *,
        action: LiveOperatorControlAction,
        actor: str,
        reason: str,
        occurred_at: datetime,
    ) -> LiveOperatorControlEvent:
        if not actor.strip():
            raise ValueError("actor is required")
        if not reason.strip():
            raise ValueError("reason is required")
        event = LiveOperatorControlEvent(
            event_id=f"{action.value}:{occurred_at.isoformat()}:{actor}",
            action=action,
            occurred_at=occurred_at,
            actor=actor,
            reason=reason,
        )
        path = Path(control_directory) / _EVENTS_FILENAME
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        rendered = existing + json.dumps(_normalize(event), sort_keys=True) + "\n"
        self._atomic_write_text(path, rendered)
        return event

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        LiveOperatorControlStore._atomic_write_text(
            path,
            json.dumps(_normalize(value), indent=2, sort_keys=True) + "\n",
        )

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"JSON object expected: {path}")
        return payload


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    return value


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "LiveKillSwitchState",
    "LiveOperatorApproval",
    "LiveOperatorControlAction",
    "LiveOperatorControlEvent",
    "LiveOperatorControlIssue",
    "LiveOperatorControlStore",
    "LiveOperatorControlValidation",
    "validate_live_operator_controls",
]
