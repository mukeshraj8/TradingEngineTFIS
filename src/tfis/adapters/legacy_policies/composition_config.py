from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml

from tfis.decision import PolicySelection


REQUIRED_POLICY_FIELDS = (
    "product_policy",
    "entry_policy",
    "gap_policy",
    "missed_entry_policy",
    "contract_selection_policy",
    "target_policy",
    "msl_policy",
)


@dataclass(frozen=True, slots=True)
class StrategyPolicyCompositionRecord:
    strategy_instance: str
    strategy_code: str
    policy_selection: PolicySelection


@dataclass(frozen=True, slots=True)
class StrategyPolicyCompositionConfig:
    version: str
    records: Mapping[str, StrategyPolicyCompositionRecord]

    def selection_for_instance(self, strategy_instance: str) -> PolicySelection:
        try:
            return self.records[strategy_instance].policy_selection
        except KeyError as exc:
            raise KeyError(
                f"No policy composition configured for {strategy_instance!r}"
            ) from exc


def load_strategy_policy_composition_config(
    path: str | Path,
) -> StrategyPolicyCompositionConfig:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("strategy policy composition config must be a mapping")
    strategies = payload.get("strategies")
    if not isinstance(strategies, dict) or not strategies:
        raise ValueError("strategy policy composition config requires strategies")
    records: dict[str, StrategyPolicyCompositionRecord] = {}
    for strategy_instance, data in strategies.items():
        if not isinstance(data, dict):
            raise ValueError(f"composition for {strategy_instance} must be a mapping")
        strategy_code = _required_text(data, "strategy_code", strategy_instance)
        missing = [
            field
            for field in REQUIRED_POLICY_FIELDS
            if not str(data.get(field) or "").strip()
        ]
        if missing:
            raise ValueError(
                f"composition for {strategy_instance} missing required policies: "
                + ", ".join(missing)
            )
        records[strategy_instance] = StrategyPolicyCompositionRecord(
            strategy_instance=strategy_instance,
            strategy_code=strategy_code,
            policy_selection=PolicySelection(
                product=str(data["product_policy"]).strip(),
                entry=str(data["entry_policy"]).strip(),
                gap=str(data["gap_policy"]).strip(),
                missed_entry=str(data["missed_entry_policy"]).strip(),
                contract_selection=str(data["contract_selection_policy"]).strip(),
                target=str(data["target_policy"]).strip(),
                msl=str(data["msl_policy"]).strip(),
            ),
        )
    return StrategyPolicyCompositionConfig(
        version=str(payload.get("version") or "unknown"),
        records=MappingProxyType(records),
    )


def _required_text(
    data: Mapping[str, object],
    field: str,
    strategy_instance: str,
) -> str:
    value = str(data.get(field) or "").strip()
    if not value:
        raise ValueError(f"composition for {strategy_instance} requires {field}")
    return value
