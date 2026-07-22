from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tfis.brokers.base import BrokerAdapter

from .lifecycle_runtime_config import load_paper_broker_runtime
from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs


@dataclass(frozen=True, slots=True)
class PaperRuntimeOrderRoutingStatus:
    strategy_code: str
    status: str
    provider: str | None
    no_live_orders_allowed: bool | None
    place_order_blocked: bool | None
    modify_order_blocked: bool | None
    cancel_order_blocked: bool | None
    message: str


def load_paper_runtime_order_routing_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: Path,
) -> tuple[PaperRuntimeOrderRoutingStatus, ...]:
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=repo_root)
    statuses: list[PaperRuntimeOrderRoutingStatus] = []
    for spec in specs:
        try:
            runtime = load_paper_broker_runtime(spec.config_path)
            statuses.append(_build_order_routing_status(spec.strategy_code, runtime.adapter, runtime.config))
        except Exception as exc:
            statuses.append(
                PaperRuntimeOrderRoutingStatus(
                    strategy_code=spec.strategy_code,
                    status="FAIL",
                    provider=None,
                    no_live_orders_allowed=None,
                    place_order_blocked=None,
                    modify_order_blocked=None,
                    cancel_order_blocked=None,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(statuses)


def _build_order_routing_status(
    strategy_code: str,
    adapter: BrokerAdapter,
    config,
) -> PaperRuntimeOrderRoutingStatus:
    place_order_blocked = type(adapter).place_order is BrokerAdapter.place_order
    modify_order_blocked = type(adapter).modify_order is BrokerAdapter.modify_order
    cancel_order_blocked = type(adapter).cancel_order is BrokerAdapter.cancel_order
    failures: list[str] = []
    if not config.paper.no_live_orders_allowed:
        failures.append("paper.no_live_orders_allowed must stay true")
    if not place_order_blocked:
        failures.append("adapter place_order is not blocked")
    if not modify_order_blocked:
        failures.append("adapter modify_order is not blocked")
    if not cancel_order_blocked:
        failures.append("adapter cancel_order is not blocked")
    return PaperRuntimeOrderRoutingStatus(
        strategy_code=strategy_code,
        status="PASS" if not failures else "FAIL",
        provider=config.broker.provider,
        no_live_orders_allowed=config.paper.no_live_orders_allowed,
        place_order_blocked=place_order_blocked,
        modify_order_blocked=modify_order_blocked,
        cancel_order_blocked=cancel_order_blocked,
        message=(
            "paper runtime order routing remains blocked"
            if not failures
            else "; ".join(failures)
        ),
    )


__all__ = [
    "PaperRuntimeOrderRoutingStatus",
    "load_paper_runtime_order_routing_statuses",
]
