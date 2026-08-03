from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from tfis.persistence import canonical_hash


ALLOWED_COMMANDS = {
    "GLOBAL_DISABLE_NEW_ENTRIES",
    "GLOBAL_HALT",
    "READ_ONLY_RECOVERY",
    "GRACEFUL_SHUTDOWN",
    "ACCOUNT_DISABLE_ENTRIES",
    "ACCOUNT_LIFECYCLE_ONLY",
    "ACCOUNT_HALT",
    "INSTANCE_ENABLE_INTERNAL_PAPER_OBSERVATION",
    "INSTANCE_DISABLE_FRESH_ENTRIES",
    "INSTANCE_EXPORT_STATE",
    "ALERT_ACKNOWLEDGE",
}

PROHIBITED_COMMANDS = {
    "BROKER_BUY",
    "BROKER_SELL",
    "FYERS_PLACE_ORDER",
    "FYERS_MODIFY_ORDER",
    "FYERS_CANCEL_ORDER",
    "LIVE_EXIT_POSITION",
}


@dataclass(frozen=True, slots=True)
class AuditCommandResult:
    accepted: bool
    command: str
    audit_event: Mapping[str, Any]
    command_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "audit_event", dict(self.audit_event))
        object.__setattr__(self, "command_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "accepted": self.accepted,
            "command": self.command,
            "audit_event": dict(self.audit_event),
        }
        if include_hash:
            payload["command_hash"] = self.command_hash
        return payload


def audit_dashboard_command(command: str, *, operator: str, scope: str, reason: str, preview: bool = True) -> AuditCommandResult:
    normalized = command.strip().upper()
    accepted = normalized in ALLOWED_COMMANDS and normalized not in PROHIBITED_COMMANDS
    timestamp = datetime(2026, 8, 3, 8, 45, tzinfo=ZoneInfo("Asia/Kolkata"))
    audit = {
        "operator": operator,
        "timestamp": timestamp.isoformat(),
        "command": normalized,
        "scope": scope,
        "reason": reason,
        "preview": preview,
        "result": "ACCEPTED_FOR_AUDITED_INTERNAL_PAPER_CONTROL" if accepted else "REJECTED_COMMAND_NOT_AUTHORIZED",
        "previous_state": "UNCHANGED",
        "new_state": "UNCHANGED" if preview else "PENDING_CONTROL_EFFECT",
        "broker_order_authority": "NONE",
    }
    audit["evidence_hash"] = canonical_hash(audit)
    return AuditCommandResult(accepted=accepted, command=normalized, audit_event=audit)
