from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from tfis.persistence import canonical_hash


@dataclass(frozen=True, slots=True)
class StrategyInstanceReadModel:
    identity: Mapping[str, Any]
    state: Mapping[str, Any]
    plan: Mapping[str, Any]
    execution: Mapping[str, Any]
    position: Mapping[str, Any]
    accounting: Mapping[str, Any]
    operations: Mapping[str, Any]
    read_model_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "read_model_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "identity": dict(self.identity),
            "state": dict(self.state),
            "plan": dict(self.plan),
            "execution": dict(self.execution),
            "position": dict(self.position),
            "accounting": dict(self.accounting),
            "operations": dict(self.operations),
        }
        if include_hash:
            payload["read_model_hash"] = self.read_model_hash
        return payload


@dataclass(frozen=True, slots=True)
class AccountRiskProjection:
    account_reference: str
    status: str
    limits: Mapping[str, Any]
    usage: Mapping[str, Any]
    accepted_instances: tuple[str, ...]
    rejected_instances: tuple[str, ...]
    alerts: tuple[Mapping[str, Any], ...]
    projection_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted_instances", tuple(self.accepted_instances))
        object.__setattr__(self, "rejected_instances", tuple(self.rejected_instances))
        object.__setattr__(self, "alerts", tuple(dict(item) for item in self.alerts))
        object.__setattr__(self, "projection_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "account_reference": self.account_reference,
            "status": self.status,
            "limits": dict(self.limits),
            "usage": dict(self.usage),
            "accepted_instances": list(self.accepted_instances),
            "rejected_instances": list(self.rejected_instances),
            "alerts": [dict(item) for item in self.alerts],
        }
        if include_hash:
            payload["projection_hash"] = self.projection_hash
        return payload


@dataclass(frozen=True, slots=True)
class OperationalReadModel:
    schema_version: str
    system: Mapping[str, Any]
    command_centre: Mapping[str, Any]
    strategies: tuple[StrategyInstanceReadModel, ...]
    accounts: tuple[AccountRiskProjection, ...]
    orders: tuple[Mapping[str, Any], ...]
    positions: tuple[Mapping[str, Any], ...]
    analytics: Mapping[str, Any]
    alerts: tuple[Mapping[str, Any], ...]
    audit: tuple[Mapping[str, Any], ...]
    projection_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "strategies", tuple(self.strategies))
        object.__setattr__(self, "accounts", tuple(self.accounts))
        object.__setattr__(self, "orders", tuple(dict(item) for item in self.orders))
        object.__setattr__(self, "positions", tuple(dict(item) for item in self.positions))
        object.__setattr__(self, "alerts", tuple(dict(item) for item in self.alerts))
        object.__setattr__(self, "audit", tuple(dict(item) for item in self.audit))
        object.__setattr__(self, "projection_hash", canonical_hash(self.to_dict(include_hash=False)))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "system": dict(self.system),
            "command_centre": dict(self.command_centre),
            "strategies": [item.to_dict() for item in self.strategies],
            "accounts": [item.to_dict() for item in self.accounts],
            "orders": [dict(item) for item in self.orders],
            "positions": [dict(item) for item in self.positions],
            "analytics": dict(self.analytics),
            "alerts": [dict(item) for item in self.alerts],
            "audit": [dict(item) for item in self.audit],
        }
        if include_hash:
            payload["projection_hash"] = self.projection_hash
        return payload
