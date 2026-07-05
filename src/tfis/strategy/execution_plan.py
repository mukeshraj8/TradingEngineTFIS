from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


EXECUTION_ALLOWED_REGISTRY_STATUSES = frozenset({"ACTIVE", "ACTIVE_CANDIDATE"})


@dataclass(frozen=True, slots=True)
class StrategyExecutionPlanItem:
    strategy_code: str
    enabled: bool
    executor: str | None
    registry_ids: tuple[str, ...]
    strategy_paths: tuple[str, ...]
    status: str
    reason: str

    @property
    def runnable(self) -> bool:
        return self.status == "RUNNABLE"


@dataclass(frozen=True, slots=True)
class StrategyExecutionPlan:
    items: tuple[StrategyExecutionPlanItem, ...]

    @property
    def runnable_items(self) -> tuple[StrategyExecutionPlanItem, ...]:
        return tuple(item for item in self.items if item.runnable)

    @property
    def blocked_items(self) -> tuple[StrategyExecutionPlanItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.enabled and not item.runnable
        )


def build_strategy_execution_plan(
    config: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
    supported_executors: Sequence[str],
) -> StrategyExecutionPlan:
    """Build a generic enabled-strategy execution plan from runtime config.

    This function is deliberately broker-agnostic. It does not import or call a
    broker adapter, and it does not execute strategy code. It only decides which
    configured strategies are runnable, skipped, or blocked.
    """

    supported = frozenset(str(item) for item in supported_executors)
    registry_entries = _registry_entries(registry)
    items = tuple(
        _build_item(entry, registry_entries=registry_entries, supported_executors=supported)
        for entry in _configured_strategy_entries(config)
    )
    return StrategyExecutionPlan(items=items)


def assert_no_blocked_enabled_strategies(plan: StrategyExecutionPlan) -> None:
    blocked = plan.blocked_items
    if not blocked:
        return
    rendered = "; ".join(
        f"{item.strategy_code}: {item.status} - {item.reason}" for item in blocked
    )
    raise ValueError(f"Enabled strategy execution plan has blocked item(s): {rendered}")


def _configured_strategy_entries(config: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    raw_entries = config.get("strategies")
    if isinstance(raw_entries, list):
        entries = tuple(item for item in raw_entries if isinstance(item, Mapping))
        if entries:
            return entries

    paper = config.get("paper")
    if isinstance(paper, Mapping) and paper.get("strategy_code"):
        return (
            {
                "strategy_code": paper["strategy_code"],
                "enabled": bool(paper.get("paper_mode_enabled", True)),
                "executor": str(paper.get("strategy_code")).lower(),
                "registry_ids": (),
                "strategy_paths": (),
            },
        )
    return ()


def _build_item(
    entry: Mapping[str, Any],
    *,
    registry_entries: Mapping[str, Mapping[str, Any]],
    supported_executors: frozenset[str],
) -> StrategyExecutionPlanItem:
    strategy_code = str(
        entry.get("strategy_code")
        or entry.get("code")
        or entry.get("strategy_id")
        or ""
    ).strip()
    if not strategy_code:
        raise ValueError("Configured strategy entry is missing strategy_code")
    enabled = bool(entry.get("enabled", True))
    executor = _optional_text(entry.get("executor"))
    registry_ids = _tuple_text(entry.get("registry_ids"))
    if not registry_ids and _optional_text(entry.get("registry_id")):
        registry_ids = (_optional_text(entry.get("registry_id")) or "",)
    strategy_paths = _tuple_text(entry.get("strategy_paths"))

    if not enabled:
        return StrategyExecutionPlanItem(
            strategy_code=strategy_code,
            enabled=False,
            executor=executor,
            registry_ids=registry_ids,
            strategy_paths=strategy_paths,
            status="SKIPPED_DISABLED",
            reason="Strategy is disabled in runtime config.",
        )
    if executor is None:
        return StrategyExecutionPlanItem(
            strategy_code=strategy_code,
            enabled=True,
            executor=None,
            registry_ids=registry_ids,
            strategy_paths=strategy_paths,
            status="BLOCKED_MISSING_EXECUTOR",
            reason="Enabled strategy does not declare an executor.",
        )
    if executor not in supported_executors:
        return StrategyExecutionPlanItem(
            strategy_code=strategy_code,
            enabled=True,
            executor=executor,
            registry_ids=registry_ids,
            strategy_paths=strategy_paths,
            status="BLOCKED_UNSUPPORTED_EXECUTOR",
            reason=f"Executor {executor!r} is not supported by this runtime.",
        )

    blocked_registry = _blocked_registry_statuses(registry_ids, registry_entries)
    if blocked_registry:
        return StrategyExecutionPlanItem(
            strategy_code=strategy_code,
            enabled=True,
            executor=executor,
            registry_ids=registry_ids,
            strategy_paths=strategy_paths,
            status="BLOCKED_REGISTRY_STATUS",
            reason=", ".join(blocked_registry),
        )

    return StrategyExecutionPlanItem(
        strategy_code=strategy_code,
        enabled=True,
        executor=executor,
        registry_ids=registry_ids,
        strategy_paths=strategy_paths,
        status="RUNNABLE",
        reason="Strategy is enabled, registry-allowed, and executor-supported.",
    )


def _blocked_registry_statuses(
    registry_ids: tuple[str, ...],
    registry_entries: Mapping[str, Mapping[str, Any]],
) -> tuple[str, ...]:
    blocked: list[str] = []
    for registry_id in registry_ids:
        entry = registry_entries.get(registry_id)
        if not isinstance(entry, Mapping):
            blocked.append(f"{registry_id}: missing registry entry")
            continue
        status = str(entry.get("status", "")).strip()
        if status not in EXECUTION_ALLOWED_REGISTRY_STATUSES:
            blocked.append(f"{registry_id}: status {status or 'UNKNOWN'}")
    return tuple(blocked)


def _registry_entries(registry: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    strategies = registry.get("strategies")
    if not isinstance(strategies, Mapping):
        raise ValueError("Strategy registry is missing strategies mapping")
    return {
        str(key): value
        for key, value in strategies.items()
        if isinstance(value, Mapping)
    }


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _tuple_text(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        rendered = value.strip()
        return (rendered,) if rendered else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),)
