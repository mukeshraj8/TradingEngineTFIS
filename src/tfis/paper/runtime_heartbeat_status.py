from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .lifecycle_supervisor_runtime import load_paper_lifecycle_supervisor_target_specs
from .live_state_store import PaperLiveStateSettings


_IDLE_RUNTIME_STATUSES = frozenset(
    {
        "PAPER_ORDER_NOT_FILLED",
        "PAPER_POSITION_CLOSED",
        "PAPER_POSITION_FORCE_CLOSED",
        "PAPER_POSITION_FRESH_ENTRY_REQUIRED",
        "PAPER_POSITION_ROLLOVER_REQUIRED",
        "PAPER_PREVIOUS_SESSION_ORDER_EXPIRED",
    }
)


@dataclass(frozen=True, slots=True)
class PaperRuntimeHeartbeatStatus:
    strategy_code: str
    status: str
    backend: str
    live_state_enabled: bool
    heartbeat_count: int
    latest_timestamp: str | None
    latest_trade_id: str | None
    latest_owner_id: str | None
    latest_state_directory: str | None
    latest_selected_contract_symbol: str | None
    latest_runtime_status: str | None
    latest_reason_code: str | None
    latest_supervisor_pid: int | None
    age_seconds: float | None
    message: str


def load_paper_runtime_heartbeat_statuses(
    targets_config_path: str | Path,
    *,
    repo_root: Path,
    stale_after_seconds: float = 120.0,
) -> tuple[PaperRuntimeHeartbeatStatus, ...]:
    specs = load_paper_lifecycle_supervisor_target_specs(targets_config_path, repo_root=repo_root)
    statuses: list[PaperRuntimeHeartbeatStatus] = []
    for spec in specs:
        try:
            settings = PaperLiveStateSettings.from_yaml(spec.config_path)
            statuses.append(
                _load_strategy_runtime_heartbeat_status(
                    strategy_code=spec.strategy_code,
                    settings=settings,
                    stale_after_seconds=stale_after_seconds,
                )
            )
        except Exception as exc:
            statuses.append(
                PaperRuntimeHeartbeatStatus(
                    strategy_code=spec.strategy_code,
                    status="UNAVAILABLE",
                    backend="unknown",
                    live_state_enabled=False,
                    heartbeat_count=0,
                    latest_timestamp=None,
                    latest_trade_id=None,
                    latest_owner_id=None,
                    latest_state_directory=None,
                    latest_selected_contract_symbol=None,
                    latest_runtime_status=None,
                    latest_reason_code=None,
                    latest_supervisor_pid=None,
                    age_seconds=None,
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(statuses)


def _load_strategy_runtime_heartbeat_status(
    *,
    strategy_code: str,
    settings: PaperLiveStateSettings,
    stale_after_seconds: float,
) -> PaperRuntimeHeartbeatStatus:
    provider = settings.provider.strip().lower()
    if not settings.enabled:
        return PaperRuntimeHeartbeatStatus(
            strategy_code=strategy_code,
            status="DISABLED",
            backend="null",
            live_state_enabled=False,
            heartbeat_count=0,
            latest_timestamp=None,
            latest_trade_id=None,
            latest_owner_id=None,
            latest_state_directory=None,
            latest_selected_contract_symbol=None,
            latest_runtime_status=None,
            latest_reason_code=None,
            latest_supervisor_pid=None,
            age_seconds=None,
            message="live-state heartbeat monitoring is disabled by configuration",
        )
    if provider not in {"filesystem", "file", "local"}:
        return PaperRuntimeHeartbeatStatus(
            strategy_code=strategy_code,
            status="UNAVAILABLE",
            backend=provider,
            live_state_enabled=True,
            heartbeat_count=0,
            latest_timestamp=None,
            latest_trade_id=None,
            latest_owner_id=None,
            latest_state_directory=None,
            latest_selected_contract_symbol=None,
            latest_runtime_status=None,
            latest_reason_code=None,
            latest_supervisor_pid=None,
            age_seconds=None,
            message=f"heartbeat inspection is only available for filesystem live-state backends, not {provider}",
        )
    values_root = Path(settings.root) / "values"
    payloads = _load_heartbeat_payloads(values_root, strategy_code=strategy_code)
    if not payloads:
        return PaperRuntimeHeartbeatStatus(
            strategy_code=strategy_code,
            status="NONE",
            backend="filesystem",
            live_state_enabled=True,
            heartbeat_count=0,
            latest_timestamp=None,
            latest_trade_id=None,
            latest_owner_id=None,
            latest_state_directory=None,
            latest_selected_contract_symbol=None,
            latest_runtime_status=None,
            latest_reason_code=None,
            latest_supervisor_pid=None,
            age_seconds=None,
            message="no filesystem supervisor heartbeat has been persisted yet",
        )
    latest = max(
        payloads,
        key=lambda item: _parse_datetime(item.get("timestamp")) or datetime.min.replace(tzinfo=UTC),
    )
    latest_dt = _parse_datetime(latest.get("timestamp"))
    age_seconds = None
    if latest_dt is not None:
        now = datetime.now(latest_dt.tzinfo or UTC)
        age_seconds = max(0.0, (now - latest_dt).total_seconds())
    latest_runtime_status = _string_or_none(latest.get("status"))
    latest_reason_code = _string_or_none(latest.get("reason_code"))
    if latest_runtime_status == "MARKET_DATA_UNAVAILABLE":
        status = "DEGRADED"
    elif latest_runtime_status in _IDLE_RUNTIME_STATUSES:
        status = "IDLE"
    else:
        status = "OK" if age_seconds is not None and age_seconds <= stale_after_seconds else "STALE"
    latest_pid = None
    try:
        raw_pid = latest.get("supervisor_pid")
        latest_pid = int(raw_pid) if raw_pid is not None else None
    except (TypeError, ValueError):
        latest_pid = None
    return PaperRuntimeHeartbeatStatus(
        strategy_code=strategy_code,
        status=status,
        backend="filesystem",
        live_state_enabled=True,
        heartbeat_count=len(payloads),
        latest_timestamp=latest_dt.isoformat() if latest_dt is not None else None,
        latest_trade_id=_string_or_none(latest.get("trade_id")),
        latest_owner_id=_string_or_none(latest.get("owner_id")),
        latest_state_directory=_string_or_none(latest.get("state_directory")),
        latest_selected_contract_symbol=_string_or_none(latest.get("selected_contract_symbol")),
        latest_runtime_status=latest_runtime_status,
        latest_reason_code=latest_reason_code,
        latest_supervisor_pid=latest_pid,
        age_seconds=age_seconds,
        message=_heartbeat_status_message(
            status=status,
            latest_runtime_status=latest_runtime_status,
            latest_reason_code=latest_reason_code,
        ),
    )


def _load_heartbeat_payloads(
    values_root: Path,
    *,
    strategy_code: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not values_root.exists():
        return rows
    strategy_upper = strategy_code.upper()
    for path in values_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        payload_strategy = str(payload.get("strategy_code") or "").strip().upper()
        if payload_strategy != strategy_upper:
            continue
        if not str(payload.get("trade_id") or "").strip():
            continue
        if not str(payload.get("timestamp") or "").strip():
            continue
        rows.append(payload)
    return rows


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _string_or_none(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _heartbeat_status_message(
    *,
    status: str,
    latest_runtime_status: str | None,
    latest_reason_code: str | None,
) -> str:
    if status == "DEGRADED":
        suffix = f" reason={latest_reason_code}" if latest_reason_code else ""
        return f"latest supervisor heartbeat reports {latest_runtime_status}{suffix}"
    if status == "IDLE":
        suffix = f" runtime_status={latest_runtime_status}" if latest_runtime_status else ""
        return f"latest supervisor heartbeat is for an idle paper lifecycle state{suffix}"
    if status == "OK":
        return "filesystem supervisor heartbeat is fresh"
    return "filesystem supervisor heartbeat is stale"


__all__ = [
    "PaperRuntimeHeartbeatStatus",
    "load_paper_runtime_heartbeat_statuses",
]
