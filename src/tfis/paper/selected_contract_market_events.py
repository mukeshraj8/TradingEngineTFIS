from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from pathlib import Path
from typing import Any

from .models import SelectedContractBarEvent, SelectedContractQuoteEvent


_SELECTED_CONTRACT_MARKET_EVENTS_PATTERN = "selected_contract_market_events*.jsonl"
_SELECTED_CONTRACT_MARKET_EVENTS_FILENAME = "selected_contract_market_events.jsonl"


def selected_contract_market_event_paths(
    state_directory: str | Path,
) -> tuple[Path, ...]:
    def _path_order_key(path: Path) -> tuple[int, str]:
        return (0 if path.name == _SELECTED_CONTRACT_MARKET_EVENTS_FILENAME else 1, path.name)

    return tuple(
        sorted(
            Path(state_directory).glob(_SELECTED_CONTRACT_MARKET_EVENTS_PATTERN),
            key=_path_order_key,
        )
    )


def selected_contract_market_event_process_pid(event: dict[str, Any]) -> int | None:
    value = (
        event.get("supervisor_pid")
        if event.get("supervisor_pid") is not None
        else event.get("watcher_pid")
    )
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def append_selected_contract_market_events(
    directory: str | Path,
    *,
    events: tuple[SelectedContractQuoteEvent | SelectedContractBarEvent, ...],
    observed_at: datetime,
    process_pid: int,
    trade_id: str,
    process_role: str = "supervisor",
) -> Path:
    path = Path(directory) / _SELECTED_CONTRACT_MARKET_EVENTS_FILENAME
    if not events:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            payload = serialize_selected_contract_market_event(
                event,
                observed_at=observed_at,
                process_pid=process_pid,
                trade_id=trade_id,
                process_role=process_role,
            )
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    return path


def serialize_selected_contract_market_event(
    event: SelectedContractQuoteEvent | SelectedContractBarEvent,
    *,
    observed_at: datetime,
    process_pid: int,
    trade_id: str,
    process_role: str = "supervisor",
) -> dict[str, Any]:
    payload = _to_jsonable(asdict(event) if is_dataclass(event) else event)
    event_kind = (
        "selected_contract_quote"
        if isinstance(event, SelectedContractQuoteEvent)
        else "selected_contract_bar"
    )
    row = {
        "artifact_version": 1,
        "event_kind": event_kind,
        "observed_at": observed_at.isoformat(),
        "trade_id": trade_id,
        "symbol": event.symbol,
        "payload": payload,
    }
    if process_role == "supervisor":
        row["supervisor_pid"] = process_pid
        # Keep legacy compatibility for historical artifacts and older readers.
        row["watcher_pid"] = process_pid
    else:
        row["watcher_pid"] = process_pid
    return row


def load_selected_contract_market_events(
    state_directory: str | Path,
) -> tuple[dict[str, Any], ...]:
    events: list[dict[str, Any]] = []
    for path in selected_contract_market_event_paths(state_directory):
        events.extend(_load_jsonl_dicts(path))
    return tuple(events)


def _load_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except OSError:
        return rows
    return rows


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


__all__ = [
    "append_selected_contract_market_events",
    "load_selected_contract_market_events",
    "selected_contract_market_event_paths",
    "selected_contract_market_event_process_pid",
    "serialize_selected_contract_market_event",
]
