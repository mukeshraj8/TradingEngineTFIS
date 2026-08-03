from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from tfis.persistence import canonical_hash


NO_EXTERNAL_AUTHORITY = {
    "external_broker_submission": "NONE",
    "broker_sandbox_submission": "NONE",
    "live_submission": "NONE",
    "external_order_mutation": "NONE",
    "external_position_mutation": "NONE",
}


@dataclass(frozen=True, slots=True)
class EnabledStrategyInstance:
    strategy_definition_id: str
    strategy_version: str
    strategy_instance_id: str
    account_reference: str
    underlying: Mapping[str, Any]
    product: str
    enabled: bool
    configured_quantity: Mapping[str, Any]
    authority_mode: str
    market_data_source: str
    rule_config_hash: str
    risk_allocation: Mapping[str, Any]
    operator_approval_status: str
    evidence_quality: str
    source_reports: Mapping[str, Any] = field(default_factory=dict)
    deterministic_projection: Mapping[str, Any] = field(default_factory=dict)
    instance_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.strategy_instance_id.strip():
            raise ValueError("strategy_instance_id is required")
        if self.authority_mode != "INTERNAL_PAPER_CONTROLLED":
            raise ValueError(f"unsupported authority_mode for {self.strategy_instance_id}: {self.authority_mode}")
        if self.product != "OPTION_SELLING":
            raise ValueError(f"unsupported product in current registry slice: {self.product}")
        lots = int(self.configured_quantity.get("lots", 0))
        if lots <= 0:
            raise ValueError(f"configured lots must be positive for {self.strategy_instance_id}")
        object.__setattr__(self, "underlying", dict(self.underlying))
        object.__setattr__(self, "configured_quantity", dict(self.configured_quantity))
        object.__setattr__(self, "risk_allocation", dict(self.risk_allocation))
        object.__setattr__(self, "source_reports", dict(self.source_reports))
        object.__setattr__(self, "deterministic_projection", dict(self.deterministic_projection))
        object.__setattr__(self, "instance_hash", canonical_hash(self.to_dict(include_hash=False)))

    @property
    def symbol(self) -> str:
        return str(self.underlying.get("symbol", ""))

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "strategy_definition_id": self.strategy_definition_id,
            "strategy_version": self.strategy_version,
            "strategy_instance_id": self.strategy_instance_id,
            "account_reference": self.account_reference,
            "underlying": dict(self.underlying),
            "product": self.product,
            "enabled": self.enabled,
            "configured_quantity": dict(self.configured_quantity),
            "authority_mode": self.authority_mode,
            "market_data_source": self.market_data_source,
            "rule_config_hash": self.rule_config_hash,
            "risk_allocation": dict(self.risk_allocation),
            "operator_approval_status": self.operator_approval_status,
            "evidence_quality": self.evidence_quality,
            "source_reports": dict(self.source_reports),
            "deterministic_projection": dict(self.deterministic_projection),
            "external_authority": NO_EXTERNAL_AUTHORITY,
        }
        if include_hash:
            payload["instance_hash"] = self.instance_hash
        return payload


@dataclass(frozen=True, slots=True)
class EnabledStrategyRegistry:
    schema_version: str
    session_scope: Mapping[str, Any]
    accounts: tuple[Mapping[str, Any], ...]
    risk: Mapping[str, Any]
    instances: tuple[EnabledStrategyInstance, ...]
    registry_hash: str = field(init=False)

    def __post_init__(self) -> None:
        ids = [item.strategy_instance_id for item in self.instances]
        if len(ids) != len(set(ids)):
            raise ValueError("strategy_instance_id values must be unique")
        if not self.instances:
            raise ValueError("at least one enabled strategy instance is required")
        if any(item.authority_mode != "INTERNAL_PAPER_CONTROLLED" for item in self.instances):
            raise ValueError("all instances must remain internal-paper controlled")
        object.__setattr__(self, "session_scope", dict(self.session_scope))
        object.__setattr__(self, "accounts", tuple(dict(item) for item in self.accounts))
        object.__setattr__(self, "risk", dict(self.risk))
        object.__setattr__(self, "registry_hash", canonical_hash(self.to_dict(include_hash=False)))

    @property
    def enabled_instances(self) -> tuple[EnabledStrategyInstance, ...]:
        return tuple(item for item in self.instances if item.enabled)

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "session_scope": dict(self.session_scope),
            "accounts": [dict(item) for item in self.accounts],
            "risk": dict(self.risk),
            "instances": [item.to_dict() for item in self.instances],
        }
        if include_hash:
            payload["registry_hash"] = self.registry_hash
        return payload


def load_enabled_strategy_registry(path: str | Path) -> EnabledStrategyRegistry:
    target = Path(path)
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"enabled strategy registry must be a YAML object: {target}")
    raw_instances = data.get("instances")
    if not isinstance(raw_instances, list):
        raise ValueError(f"enabled strategy registry requires instances list: {target}")
    return EnabledStrategyRegistry(
        schema_version=str(data.get("schema_version", "")),
        session_scope=data.get("session_scope") or {},
        accounts=tuple(data.get("accounts") or ()),
        risk=data.get("risk") or {},
        instances=tuple(EnabledStrategyInstance(**item) for item in raw_instances),
    )
