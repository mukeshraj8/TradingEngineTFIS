from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from tfis.persistence import canonical_hash


class RuntimeHealthState(str, Enum):
    HEALTHY = "HEALTHY"
    STARTING = "STARTING"
    PREMARKET_READY = "PREMARKET_READY"
    ACTIVE_INTERNAL_PAPER = "ACTIVE_INTERNAL_PAPER"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_PROTECTED = "POSITION_PROTECTED"
    POSITION_EXIT_PENDING = "POSITION_EXIT_PENDING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    DATA_DEGRADED = "DATA_DEGRADED"
    PERSISTENCE_DEGRADED = "PERSISTENCE_DEGRADED"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    GLOBAL_BLOCKED = "GLOBAL_BLOCKED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class RuntimeOperationalSnapshot:
    snapshot_id: str
    as_of_timestamp: datetime
    system: dict[str, Any]
    strategy: dict[str, Any]
    account: dict[str, Any]
    position: dict[str, Any]
    accounting: dict[str, Any]
    alerts: tuple[dict[str, Any], ...] = ()
    snapshot_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "alerts", tuple(self.alerts))
        object.__setattr__(self, "snapshot_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "snapshot_id": self.snapshot_id,
            "as_of_timestamp": self.as_of_timestamp.isoformat(),
            "system": self.system,
            "strategy": self.strategy,
            "account": self.account,
            "position": self.position,
            "accounting": self.accounting,
            "alerts": list(self.alerts),
        }
        if include_hash:
            data["snapshot_hash"] = self.snapshot_hash
        return data
