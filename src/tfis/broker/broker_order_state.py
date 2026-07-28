from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from tfis.storage import atomic_write_text


_ARTIFACT_VERSION = 1
_STATE_FILENAME = "broker_order_state.json"
_EVENTS_FILENAME = "broker_order_events.jsonl"


class BrokerOrderStateError(RuntimeError):
    """Raised when broker order-state evidence cannot be trusted."""


class BrokerOrderLifecycleStatus(str, Enum):
    INTENT_CREATED = "INTENT_CREATED"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    STALE = "STALE"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    CANCEL_REJECTED = "CANCEL_REJECTED"
    CANCEL_FAILED = "CANCEL_FAILED"
    MODIFY_REQUESTED = "MODIFY_REQUESTED"
    MODIFIED = "MODIFIED"
    MODIFY_REJECTED = "MODIFY_REJECTED"
    MODIFY_FAILED = "MODIFY_FAILED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class BrokerOrderEventType(str, Enum):
    INTENT_CREATED = "INTENT_CREATED"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    STATUS_SYNCED = "STATUS_SYNCED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    STALE = "STALE"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    CANCEL_REJECTED = "CANCEL_REJECTED"
    CANCEL_FAILED = "CANCEL_FAILED"
    MODIFY_REQUESTED = "MODIFY_REQUESTED"
    MODIFIED = "MODIFIED"
    MODIFY_REJECTED = "MODIFY_REJECTED"
    MODIFY_FAILED = "MODIFY_FAILED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


def broker_order_is_terminal(status: BrokerOrderLifecycleStatus | str | None) -> bool:
    normalized = _normalized_status(status)
    return normalized in {
        BrokerOrderLifecycleStatus.FILLED.value,
        BrokerOrderLifecycleStatus.REJECTED.value,
        BrokerOrderLifecycleStatus.CANCELLED.value,
        BrokerOrderLifecycleStatus.EXPIRED.value,
    }


def broker_order_requires_operator_attention(
    status: BrokerOrderLifecycleStatus | str | None,
) -> bool:
    normalized = _normalized_status(status)
    return normalized in {
        BrokerOrderLifecycleStatus.REJECTED.value,
        BrokerOrderLifecycleStatus.STALE.value,
        BrokerOrderLifecycleStatus.CANCEL_REJECTED.value,
        BrokerOrderLifecycleStatus.CANCEL_FAILED.value,
        BrokerOrderLifecycleStatus.MODIFY_REJECTED.value,
        BrokerOrderLifecycleStatus.MODIFY_FAILED.value,
        BrokerOrderLifecycleStatus.UNKNOWN.value,
    }


@dataclass(frozen=True, slots=True)
class BrokerOrderState:
    artifact_version: int
    provider: str
    strategy_code: str
    strategy_branch: str
    symbol: str
    order_role: str
    side: str
    quantity: int
    product_type: str
    order_type: str
    status: BrokerOrderLifecycleStatus
    client_order_id: str
    created_at: datetime
    last_updated_at: datetime
    broker_order_id: str | None = None
    exchange_order_id: str | None = None
    exchange_status: str | None = None
    submitted_at: datetime | None = None
    acknowledged_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    modify_requested_at: datetime | None = None
    modified_at: datetime | None = None
    rejected_at: datetime | None = None
    cancelled_at: datetime | None = None
    filled_at: datetime | None = None
    last_status_at: datetime | None = None
    filled_quantity: int = 0
    remaining_quantity: int | None = None
    average_fill_price: float | None = None
    limit_price: float | None = None
    trigger_price: float | None = None
    rejection_code: str | None = None
    rejection_message: str | None = None
    cancel_reason: str | None = None
    modify_reason: str | None = None
    last_event_type: BrokerOrderEventType | None = None
    last_message: str | None = None
    provenance_source_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrokerOrderEvent:
    artifact_version: int
    timestamp: datetime
    event_type: BrokerOrderEventType
    status: BrokerOrderLifecycleStatus
    provider: str
    client_order_id: str
    broker_order_id: str | None
    exchange_order_id: str | None
    exchange_status: str | None
    message: str
    filled_quantity: int | None = None
    remaining_quantity: int | None = None
    average_fill_price: float | None = None
    rejection_code: str | None = None
    rejection_message: str | None = None
    source_id: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerOrderStateCandidate:
    state_directory: Path
    state: BrokerOrderState


class BrokerOrderStateStore:
    def create_intent(
        self,
        state_directory: str | Path,
        *,
        provider: str,
        strategy_code: str,
        strategy_branch: str,
        symbol: str,
        order_role: str,
        side: str,
        quantity: int,
        product_type: str,
        order_type: str,
        client_order_id: str,
        created_at: datetime,
        limit_price: float | None = None,
        trigger_price: float | None = None,
        provenance_source_ids: tuple[str, ...] = (),
    ) -> tuple[BrokerOrderState, Path, Path]:
        if quantity <= 0:
            raise BrokerOrderStateError("quantity must be positive")
        for field_name, value in {
            "provider": provider,
            "strategy_code": strategy_code,
            "strategy_branch": strategy_branch,
            "symbol": symbol,
            "order_role": order_role,
            "side": side,
            "product_type": product_type,
            "order_type": order_type,
            "client_order_id": client_order_id,
        }.items():
            if not str(value).strip():
                raise BrokerOrderStateError(f"{field_name} is required")

        state = BrokerOrderState(
            artifact_version=_ARTIFACT_VERSION,
            provider=provider,
            strategy_code=strategy_code,
            strategy_branch=strategy_branch,
            symbol=symbol,
            order_role=order_role,
            side=side,
            quantity=quantity,
            product_type=product_type,
            order_type=order_type,
            status=BrokerOrderLifecycleStatus.INTENT_CREATED,
            client_order_id=client_order_id,
            created_at=created_at,
            last_updated_at=created_at,
            remaining_quantity=quantity,
            limit_price=limit_price,
            trigger_price=trigger_price,
            last_event_type=BrokerOrderEventType.INTENT_CREATED,
            last_message="Broker order intent was persisted; no broker routing has been attempted.",
            provenance_source_ids=provenance_source_ids,
        )
        event = BrokerOrderEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=created_at,
            event_type=BrokerOrderEventType.INTENT_CREATED,
            status=state.status,
            provider=provider,
            client_order_id=client_order_id,
            broker_order_id=None,
            exchange_order_id=None,
            exchange_status=None,
            message=state.last_message or "",
            remaining_quantity=quantity,
        )
        state_path = self.save_state(state_directory, state)
        events_path = self.append_event(state_directory, event)
        return state, state_path, events_path

    def record_event(
        self,
        state_directory: str | Path,
        *,
        event_type: BrokerOrderEventType,
        status: BrokerOrderLifecycleStatus,
        timestamp: datetime,
        message: str,
        broker_order_id: str | None = None,
        exchange_order_id: str | None = None,
        exchange_status: str | None = None,
        filled_quantity: int | None = None,
        remaining_quantity: int | None = None,
        average_fill_price: float | None = None,
        limit_price: float | None = None,
        trigger_price: float | None = None,
        rejection_code: str | None = None,
        rejection_message: str | None = None,
        cancel_reason: str | None = None,
        modify_reason: str | None = None,
        source_id: str | None = None,
    ) -> tuple[BrokerOrderState, BrokerOrderEvent, Path, Path]:
        state = self.load_state(state_directory)
        final_filled = state.filled_quantity if filled_quantity is None else filled_quantity
        final_remaining = (
            max(state.quantity - final_filled, 0)
            if remaining_quantity is None and filled_quantity is not None
            else remaining_quantity
        )
        if final_remaining is None:
            final_remaining = state.remaining_quantity
        state = replace(
            state,
            status=status,
            broker_order_id=broker_order_id if broker_order_id is not None else state.broker_order_id,
            exchange_order_id=exchange_order_id if exchange_order_id is not None else state.exchange_order_id,
            exchange_status=exchange_status if exchange_status is not None else state.exchange_status,
            submitted_at=timestamp if event_type is BrokerOrderEventType.SUBMITTED else state.submitted_at,
            acknowledged_at=timestamp if event_type is BrokerOrderEventType.ACKNOWLEDGED else state.acknowledged_at,
            cancel_requested_at=(
                timestamp
                if event_type is BrokerOrderEventType.CANCEL_REQUESTED
                else state.cancel_requested_at
            ),
            modify_requested_at=(
                timestamp
                if event_type is BrokerOrderEventType.MODIFY_REQUESTED
                else state.modify_requested_at
            ),
            modified_at=timestamp if event_type is BrokerOrderEventType.MODIFIED else state.modified_at,
            rejected_at=timestamp if event_type is BrokerOrderEventType.REJECTED else state.rejected_at,
            cancelled_at=timestamp if event_type is BrokerOrderEventType.CANCELLED else state.cancelled_at,
            filled_at=timestamp if status is BrokerOrderLifecycleStatus.FILLED else state.filled_at,
            last_status_at=timestamp,
            filled_quantity=final_filled,
            remaining_quantity=final_remaining,
            average_fill_price=(
                average_fill_price
                if average_fill_price is not None
                else state.average_fill_price
            ),
            limit_price=limit_price if limit_price is not None else state.limit_price,
            trigger_price=trigger_price if trigger_price is not None else state.trigger_price,
            rejection_code=rejection_code if rejection_code is not None else state.rejection_code,
            rejection_message=(
                rejection_message
                if rejection_message is not None
                else state.rejection_message
            ),
            cancel_reason=cancel_reason if cancel_reason is not None else state.cancel_reason,
            modify_reason=modify_reason if modify_reason is not None else state.modify_reason,
            last_updated_at=timestamp,
            last_event_type=event_type,
            last_message=message,
        )
        event = BrokerOrderEvent(
            artifact_version=_ARTIFACT_VERSION,
            timestamp=timestamp,
            event_type=event_type,
            status=status,
            provider=state.provider,
            client_order_id=state.client_order_id,
            broker_order_id=state.broker_order_id,
            exchange_order_id=state.exchange_order_id,
            exchange_status=state.exchange_status,
            message=message,
            filled_quantity=final_filled,
            remaining_quantity=final_remaining,
            average_fill_price=state.average_fill_price,
            rejection_code=state.rejection_code,
            rejection_message=state.rejection_message,
            source_id=source_id,
        )
        state_path = self.save_state(state_directory, state)
        events_path = self.append_event(state_directory, event)
        return state, event, state_path, events_path

    def save_state(self, state_directory: str | Path, state: BrokerOrderState) -> Path:
        path = Path(state_directory) / _STATE_FILENAME
        self._write_json(path, state)
        return path

    def load_state(self, state_directory: str | Path) -> BrokerOrderState:
        payload = self._load_json_required(Path(state_directory) / _STATE_FILENAME)
        return BrokerOrderState(
            artifact_version=int(payload["artifact_version"]),
            provider=str(payload["provider"]),
            strategy_code=str(payload["strategy_code"]),
            strategy_branch=str(payload["strategy_branch"]),
            symbol=str(payload["symbol"]),
            order_role=str(payload["order_role"]),
            side=str(payload["side"]),
            quantity=int(payload["quantity"]),
            product_type=str(payload["product_type"]),
            order_type=str(payload["order_type"]),
            status=BrokerOrderLifecycleStatus(str(payload["status"])),
            client_order_id=str(payload["client_order_id"]),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
            last_updated_at=datetime.fromisoformat(str(payload["last_updated_at"])),
            broker_order_id=_optional_text(payload.get("broker_order_id")),
            exchange_order_id=_optional_text(payload.get("exchange_order_id")),
            exchange_status=_optional_text(payload.get("exchange_status")),
            submitted_at=_optional_datetime(payload.get("submitted_at")),
            acknowledged_at=_optional_datetime(payload.get("acknowledged_at")),
            cancel_requested_at=_optional_datetime(payload.get("cancel_requested_at")),
            modify_requested_at=_optional_datetime(payload.get("modify_requested_at")),
            modified_at=_optional_datetime(payload.get("modified_at")),
            rejected_at=_optional_datetime(payload.get("rejected_at")),
            cancelled_at=_optional_datetime(payload.get("cancelled_at")),
            filled_at=_optional_datetime(payload.get("filled_at")),
            last_status_at=_optional_datetime(payload.get("last_status_at")),
            filled_quantity=int(payload.get("filled_quantity", 0)),
            remaining_quantity=(
                int(payload["remaining_quantity"])
                if payload.get("remaining_quantity") is not None
                else None
            ),
            average_fill_price=_optional_float(payload.get("average_fill_price")),
            limit_price=_optional_float(payload.get("limit_price")),
            trigger_price=_optional_float(payload.get("trigger_price")),
            rejection_code=_optional_text(payload.get("rejection_code")),
            rejection_message=_optional_text(payload.get("rejection_message")),
            cancel_reason=_optional_text(payload.get("cancel_reason")),
            modify_reason=_optional_text(payload.get("modify_reason")),
            last_event_type=(
                BrokerOrderEventType(str(payload["last_event_type"]))
                if payload.get("last_event_type") is not None
                else None
            ),
            last_message=_optional_text(payload.get("last_message")),
            provenance_source_ids=tuple(
                str(item) for item in payload.get("provenance_source_ids", ())
            ),
        )

    def load_events(self, state_directory: str | Path) -> tuple[BrokerOrderEvent, ...]:
        path = Path(state_directory) / _EVENTS_FILENAME
        if not path.exists():
            return ()
        events: list[BrokerOrderEvent] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BrokerOrderStateError(
                    f"Invalid broker order event JSON at {path}:{line_number}"
                ) from exc
            events.append(
                BrokerOrderEvent(
                    artifact_version=int(payload["artifact_version"]),
                    timestamp=datetime.fromisoformat(str(payload["timestamp"])),
                    event_type=BrokerOrderEventType(str(payload["event_type"])),
                    status=BrokerOrderLifecycleStatus(str(payload["status"])),
                    provider=str(payload["provider"]),
                    client_order_id=str(payload["client_order_id"]),
                    broker_order_id=_optional_text(payload.get("broker_order_id")),
                    exchange_order_id=_optional_text(payload.get("exchange_order_id")),
                    exchange_status=_optional_text(payload.get("exchange_status")),
                    message=str(payload["message"]),
                    filled_quantity=(
                        int(payload["filled_quantity"])
                        if payload.get("filled_quantity") is not None
                        else None
                    ),
                    remaining_quantity=(
                        int(payload["remaining_quantity"])
                        if payload.get("remaining_quantity") is not None
                        else None
                    ),
                    average_fill_price=_optional_float(payload.get("average_fill_price")),
                    rejection_code=_optional_text(payload.get("rejection_code")),
                    rejection_message=_optional_text(payload.get("rejection_message")),
                    source_id=_optional_text(payload.get("source_id")),
                )
            )
        return tuple(events)

    def append_event(self, state_directory: str | Path, event: BrokerOrderEvent) -> Path:
        path = Path(state_directory) / _EVENTS_FILENAME
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        rendered = existing + json.dumps(self._normalize(event), sort_keys=True) + "\n"
        self._atomic_write_text(path, rendered)
        return path

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        rendered = json.dumps(BrokerOrderStateStore._normalize(value), indent=2, sort_keys=True)
        BrokerOrderStateStore._atomic_write_text(path, rendered + "\n")

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        atomic_write_text(path, content)

    @staticmethod
    def _load_json_required(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise BrokerOrderStateError(f"Missing broker order state: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BrokerOrderStateError(f"Invalid broker order state: {path}") from exc
        if not isinstance(payload, dict):
            raise BrokerOrderStateError(f"Broker order state must be a JSON object: {path}")
        return payload

    @staticmethod
    def _normalize(value: Any) -> Any:
        if is_dataclass(value):
            return BrokerOrderStateStore._normalize(asdict(value))
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, tuple):
            return [BrokerOrderStateStore._normalize(item) for item in value]
        if isinstance(value, list):
            return [BrokerOrderStateStore._normalize(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): BrokerOrderStateStore._normalize(item)
                for key, item in value.items()
            }
        return value


class BrokerOrderStateDiscovery:
    def __init__(self, *, store: BrokerOrderStateStore | None = None) -> None:
        self._store = store or BrokerOrderStateStore()

    def find_orders(
        self,
        artifact_roots: tuple[str | Path, ...],
        *,
        provider: str | None = None,
        strategy_code: str | None = None,
    ) -> tuple[BrokerOrderStateCandidate, ...]:
        candidates: list[BrokerOrderStateCandidate] = []
        for path in broker_order_state_candidate_paths(artifact_roots):
            try:
                state = self._store.load_state(path.parent)
            except BrokerOrderStateError:
                continue
            if provider is not None and state.provider != provider:
                continue
            if strategy_code is not None and state.strategy_code != strategy_code:
                continue
            candidates.append(BrokerOrderStateCandidate(state_directory=path.parent, state=state))
        return tuple(candidates)


def broker_order_state_candidate_paths(
    artifact_roots: tuple[str | Path, ...],
) -> tuple[Path, ...]:
    candidate_paths: set[Path] = set()
    for artifact_root in artifact_roots:
        root = Path(artifact_root)
        if not root.exists():
            continue
        candidate_paths.update(root.rglob(_STATE_FILENAME))
    return tuple(sorted(candidate_paths))


def broker_order_state_model_fields() -> tuple[str, ...]:
    return tuple(field.name for field in fields(BrokerOrderState))


def broker_order_event_fields() -> tuple[str, ...]:
    return tuple(field.name for field in fields(BrokerOrderEvent))


def _normalized_status(status: BrokerOrderLifecycleStatus | str | None) -> str:
    if isinstance(status, BrokerOrderLifecycleStatus):
        return status.value
    return str(status or "").strip()


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "BrokerOrderEvent",
    "BrokerOrderEventType",
    "BrokerOrderLifecycleStatus",
    "BrokerOrderState",
    "BrokerOrderStateCandidate",
    "BrokerOrderStateDiscovery",
    "BrokerOrderStateError",
    "BrokerOrderStateStore",
    "broker_order_event_fields",
    "broker_order_is_terminal",
    "broker_order_requires_operator_attention",
    "broker_order_state_candidate_paths",
    "broker_order_state_model_fields",
]
