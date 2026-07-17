from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from tfis.brokers import BrokerAdapter, FyersBrokerAdapter


class PaperLifecycleRuntimeConfigError(RuntimeError):
    """Raised when the shared paper lifecycle runtime config is invalid."""


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
        if config.broker.payload_fixture_path:
            return FyersBrokerAdapter.from_payload_file(
                config.broker.payload_fixture_path,
                source_timezone=config.broker.timezone,
            )
        return FyersBrokerAdapter(
            source_timezone=config.broker.timezone,
            option_chain_strike_count=config.broker.option_chain_strike_count,
        )
    raise PaperLifecycleRuntimeConfigError(
        f"Unsupported paper lifecycle broker provider: {config.broker.provider}"
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
    "PaperLifecycleBrokerConfig",
    "PaperLifecycleCostConfig",
    "PaperLifecycleRuntimeConfig",
    "PaperLifecycleRuntimeConfigError",
    "build_paper_broker_adapter",
]
