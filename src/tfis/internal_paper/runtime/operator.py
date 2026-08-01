from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from tfis.persistence import canonical_hash


class OperatorCommandType(str, Enum):
    PREVIEW = "preview"
    ENABLE_INTERNAL_PAPER = "enable_internal_paper"
    DISABLE_NEW_ENTRIES = "disable_new_entries"
    STOP_STRATEGY = "stop_strategy"
    PRESERVE_LIFECYCLE = "preserve_lifecycle"
    ACCOUNT_HALT = "account_halt"
    GLOBAL_HALT = "global_halt"
    RESUME_AFTER_RECOVERY = "resume_after_recovery"
    GRACEFUL_SHUTDOWN = "graceful_shutdown"
    STATUS = "status"
    EXPORT_SESSION_SUMMARY = "export_session_summary"


@dataclass(frozen=True, slots=True)
class OperatorCommand:
    command_type: OperatorCommandType
    operator_reference: str
    timestamp: datetime
    reason: str
    local_test_context: bool = True
    command_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.local_test_context:
            raise ValueError("Phase 5A operator commands require local explicit test/operator context.")
        object.__setattr__(self, "command_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "command_type": self.command_type.value,
            "operator_reference": self.operator_reference,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "local_test_context": self.local_test_context,
        }
        if include_hash:
            data["command_hash"] = self.command_hash
        return data
