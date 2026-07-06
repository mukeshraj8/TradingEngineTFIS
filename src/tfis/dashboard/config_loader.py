from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from .operator_dashboard import StrategyDashboardConfig


def load_dashboard_strategy_configs(
    config_path: str | Path,
    *,
    repo_root: Path,
) -> tuple[StrategyDashboardConfig, ...]:
    from .operator_dashboard import StrategyDashboardConfig

    target = Path(config_path)
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Dashboard strategy config must be a YAML object: {target}")
    raw_strategies = data.get("strategies")
    if not isinstance(raw_strategies, list) or not raw_strategies:
        raise ValueError(f"Dashboard strategy config must contain a non-empty strategies list: {target}")

    configs: list[StrategyDashboardConfig] = []
    for item in raw_strategies:
        if not isinstance(item, dict):
            raise ValueError(f"Dashboard strategy entry must be a mapping: {item!r}")
        configs.append(
            StrategyDashboardConfig(
                strategy_code=str(item["strategy_code"]).strip(),
                display_name=str(item.get("display_name") or f"{item['strategy_code']} Operator Dashboard").strip(),
                artifact_root=_resolve_repo_path(repo_root, item["artifact_root"]),
                strategy_path=_resolve_repo_path(repo_root, item["strategy_path"]),
                reference_packet_path=_resolve_repo_path(repo_root, item["reference_packet_path"]),
                session_id_prefix=str(item["session_id_prefix"]).strip(),
            )
        )
    return tuple(configs)


def _resolve_repo_path(repo_root: Path, value: object) -> Path:
    target = Path(str(value))
    if target.is_absolute():
        return target
    return (repo_root / target).resolve()
