from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from tfis.persistence import canonical_hash


@dataclass(frozen=True, slots=True)
class InternalPaperSessionAudit:
    audit_id: str
    session_identity: dict[str, Any]
    operator_actions: tuple[dict[str, Any], ...]
    profile: dict[str, Any]
    strategy_instance: str
    account: str
    authority_grant: dict[str, Any]
    source_market_stream: dict[str, Any]
    plans_decisions: dict[str, Any]
    orders_events_fills: dict[str, Any]
    position_cycles: dict[str, Any]
    lifecycle_actions: dict[str, Any]
    trade_facts_pnl_facts: dict[str, Any]
    kill_switch_actions: tuple[dict[str, Any], ...]
    alerts: tuple[dict[str, Any], ...]
    startup_assessment: dict[str, Any]
    shutdown_assessment: dict[str, Any]
    final_pnl: dict[str, Any]
    completed_at: datetime
    audit_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_actions", tuple(self.operator_actions))
        object.__setattr__(self, "kill_switch_actions", tuple(self.kill_switch_actions))
        object.__setattr__(self, "alerts", tuple(self.alerts))
        object.__setattr__(self, "audit_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        data = {
            "audit_id": self.audit_id,
            "session_identity": self.session_identity,
            "operator_actions": list(self.operator_actions),
            "profile": self.profile,
            "strategy_instance": self.strategy_instance,
            "account": self.account,
            "authority_grant": self.authority_grant,
            "source_market_stream": self.source_market_stream,
            "plans_decisions": self.plans_decisions,
            "orders_events_fills": self.orders_events_fills,
            "position_cycles": self.position_cycles,
            "lifecycle_actions": self.lifecycle_actions,
            "trade_facts_pnl_facts": self.trade_facts_pnl_facts,
            "kill_switch_actions": list(self.kill_switch_actions),
            "alerts": list(self.alerts),
            "startup_assessment": self.startup_assessment,
            "shutdown_assessment": self.shutdown_assessment,
            "final_pnl": self.final_pnl,
            "completed_at": self.completed_at.isoformat(),
        }
        if include_hash:
            data["audit_hash"] = self.audit_hash
        return data
