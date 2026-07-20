from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from tfis.brokers import BrokerAdapter, BrokerHealthEvent


class PaperLifecycleRuntimeConfigError(RuntimeError):
    """Raised when the shared paper lifecycle runtime config is invalid."""


@dataclass(frozen=True, slots=True)
class PaperLifecycleBrokerRuntime:
    config: "PaperLifecycleRuntimeConfig"
    timezone_name: str
    timezone: ZoneInfo
    adapter: BrokerAdapter


@dataclass(frozen=True, slots=True)
class PaperLifecycleBrokerConfig:
    provider: str
    timezone: str
    payload_fixture_path: str | None = None
    capture_stream_events: bool = False
    option_chain_strike_count: int = 80


@dataclass(frozen=True, slots=True)
class PaperLifecycleCostConfig:
    slippage_exit_points: float | None = None


@dataclass(frozen=True, slots=True)
class PaperLifecycleRuntimeConfig:
    broker: PaperLifecycleBrokerConfig
    costs: PaperLifecycleCostConfig
    source_mode: str = "broker_fyers_live_paper_ingress"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PaperLifecycleRuntimeConfig":
        target = Path(path)
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise PaperLifecycleRuntimeConfigError(
                f"Paper lifecycle runtime config must be a YAML object: {target}"
            )
        broker = data.get("broker") or {}
        costs = data.get("costs") or {}
        payload_fixture_path = _optional_text(broker.get("payload_fixture_path"))
        if payload_fixture_path is not None:
            payload_path = Path(payload_fixture_path)
            if not payload_path.is_absolute():
                payload_fixture_path = str((target.parent / payload_path).resolve())
        return cls(
            broker=PaperLifecycleBrokerConfig(
                provider=str(broker.get("provider", "fyers")).strip().lower(),
                timezone=str(broker.get("timezone", "Asia/Kolkata")).strip(),
                payload_fixture_path=payload_fixture_path,
                capture_stream_events=bool(broker.get("capture_stream_events", False)),
                option_chain_strike_count=max(
                    1,
                    int(broker.get("option_chain_strike_count", 80) or 80),
                ),
            ),
            costs=PaperLifecycleCostConfig(
                slippage_exit_points=_optional_float(costs.get("slippage_exit_points")),
            ),
            source_mode=str(
                data.get("source_mode", "broker_fyers_live_paper_ingress")
            ).strip(),
        )


def build_paper_broker_adapter(config: PaperLifecycleRuntimeConfig) -> BrokerAdapter:
    provider = config.broker.provider.strip().lower()
    if provider == "fyers":
        return _build_fyers_broker_adapter(config)
    raise PaperLifecycleRuntimeConfigError(
        f"Unsupported paper lifecycle broker provider: {config.broker.provider}"
    )


def load_paper_broker_runtime(
    config_path: str | Path,
    *,
    timezone_name: str | None = None,
) -> PaperLifecycleBrokerRuntime:
    config = PaperLifecycleRuntimeConfig.from_yaml(config_path)
    resolved_timezone_name = timezone_name or config.broker.timezone
    return PaperLifecycleBrokerRuntime(
        config=config,
        timezone_name=resolved_timezone_name,
        timezone=ZoneInfo(resolved_timezone_name),
        adapter=build_paper_broker_adapter(config),
    )


def prepare_paper_broker_runtime_environment(
    config: PaperLifecycleRuntimeConfig,
    *,
    tfis_root: str | Path,
    skip_refresh: bool = False,
) -> None:
    provider = config.broker.provider.strip().lower()
    if provider == "fyers":
        from tfis.brokers.fyers_token import prepare_fyers_env_from_tfis

        prepare_fyers_env_from_tfis(
            tfis_root=tfis_root,
            skip_refresh=skip_refresh,
        )
        return
    raise PaperLifecycleRuntimeConfigError(
        f"Unsupported paper lifecycle broker provider: {config.broker.provider}"
    )


def connect_paper_broker_runtime(
    *,
    strategy_code: str,
    provider: str,
    adapter: BrokerAdapter,
) -> BrokerHealthEvent:
    try:
        adapter.connect()
    except Exception as exc:
        raise RuntimeError(
            f"{strategy_code} broker connect failed for {provider}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    try:
        initial_health = adapter.health()
    except Exception as exc:
        raise RuntimeError(
            f"{strategy_code} broker health check failed for {provider}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return ensure_paper_broker_runtime_healthy(
        strategy_code=strategy_code,
        provider=provider,
        adapter=adapter,
        initial_health=initial_health,
    )


def ensure_paper_broker_runtime_healthy(
    *,
    strategy_code: str,
    provider: str,
    adapter: BrokerAdapter,
    initial_health: BrokerHealthEvent | None = None,
) -> BrokerHealthEvent:
    health = initial_health
    if health is None:
        try:
            health = adapter.health()
        except Exception as exc:
            raise RuntimeError(
                f"{strategy_code} broker health check failed for {provider}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
    if _paper_broker_health_is_healthy(health):
        return health
    try:
        reconnected_health = adapter.reconnect()
    except Exception as exc:
        raise RuntimeError(
            f"{strategy_code} broker reconnect failed for {provider}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if _paper_broker_health_is_healthy(reconnected_health):
        return reconnected_health
    raise RuntimeError(
        f"{strategy_code} broker runtime is unhealthy for {provider} after reconnect: "
        f"{_describe_broker_health(reconnected_health)}"
    )


def _paper_broker_health_is_healthy(health: BrokerHealthEvent) -> bool:
    return health.is_connected and health.connection_state.value == "CONNECTED"


def _describe_broker_health(health: BrokerHealthEvent) -> str:
    warnings = ", ".join(health.warnings) if health.warnings else "none"
    diagnostics = ", ".join(health.diagnostics) if health.diagnostics else "none"
    return (
        f"state={health.connection_state.value} "
        f"is_connected={health.is_connected} "
        f"reconnect_attempts={health.reconnect_attempts} "
        f"warnings={warnings} "
        f"diagnostics={diagnostics}"
    )


def _build_fyers_broker_adapter(config: PaperLifecycleRuntimeConfig) -> BrokerAdapter:
    from tfis.brokers import FyersBrokerAdapter

    if config.broker.payload_fixture_path:
        return FyersBrokerAdapter.from_payload_file(
            config.broker.payload_fixture_path,
            source_timezone=config.broker.timezone,
        )
    return FyersBrokerAdapter(
        source_timezone=config.broker.timezone,
        option_chain_strike_count=config.broker.option_chain_strike_count,
    )


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


__all__ = [
    "PaperLifecycleBrokerRuntime",
    "PaperLifecycleBrokerConfig",
    "PaperLifecycleCostConfig",
    "PaperLifecycleRuntimeConfig",
    "PaperLifecycleRuntimeConfigError",
    "build_paper_broker_adapter",
    "connect_paper_broker_runtime",
    "ensure_paper_broker_runtime_healthy",
    "load_paper_broker_runtime",
    "prepare_paper_broker_runtime_environment",
]
