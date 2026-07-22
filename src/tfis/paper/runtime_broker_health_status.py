from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .lifecycle_runtime_config import (
    _describe_broker_health,
    connect_paper_broker_runtime,
    load_paper_broker_runtime,
    prepare_paper_broker_runtime_environment,
)
from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs


@dataclass(frozen=True, slots=True)
class PaperRuntimeBrokerHealthStatus:
    strategy_code: str
    status: str
    provider: str | None
    connection_state: str | None
    is_connected: bool | None
    reconnect_attempts: int | None
    message: str


def load_paper_runtime_broker_health_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: Path,
    tfis_root: Path | None = None,
    skip_refresh: bool = True,
) -> tuple[PaperRuntimeBrokerHealthStatus, ...]:
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=repo_root)
    statuses: list[PaperRuntimeBrokerHealthStatus] = []
    prepared_providers: set[str] = set()
    effective_tfis_root = tfis_root or repo_root
    for spec in specs:
        try:
            runtime = load_paper_broker_runtime(spec.config_path)
            provider = runtime.config.broker.provider.strip().lower()
            if provider not in prepared_providers:
                prepare_paper_broker_runtime_environment(
                    runtime.config,
                    tfis_root=effective_tfis_root,
                    skip_refresh=skip_refresh,
                )
                prepared_providers.add(provider)
            try:
                health = connect_paper_broker_runtime(
                    strategy_code=spec.strategy_code,
                    provider=runtime.config.broker.provider,
                    adapter=runtime.adapter,
                )
            finally:
                try:
                    runtime.adapter.disconnect()
                except Exception:
                    pass
            statuses.append(
                PaperRuntimeBrokerHealthStatus(
                    strategy_code=spec.strategy_code,
                    status="PASS",
                    provider=runtime.config.broker.provider,
                    connection_state=health.connection_state.value,
                    is_connected=health.is_connected,
                    reconnect_attempts=health.reconnect_attempts,
                    message=_describe_broker_health(health),
                )
            )
        except Exception as exc:
            statuses.append(
                PaperRuntimeBrokerHealthStatus(
                    strategy_code=spec.strategy_code,
                    status="FAIL",
                    provider=None,
                    connection_state=None,
                    is_connected=None,
                    reconnect_attempts=None,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(statuses)


__all__ = [
    "PaperRuntimeBrokerHealthStatus",
    "load_paper_runtime_broker_health_statuses",
]
