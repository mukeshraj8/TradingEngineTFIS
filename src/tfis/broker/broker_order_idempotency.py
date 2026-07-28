from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from tfis.storage import atomic_write_text


_REGISTRY_FILENAME = "broker_order_idempotency_records.jsonl"


class BrokerOrderIdempotencyError(RuntimeError):
    """Raised when broker order idempotency evidence cannot be trusted."""


class BrokerOrderReservationStatus(str, Enum):
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"


@dataclass(frozen=True, slots=True)
class BrokerOrderIdempotencyKey:
    provider: str
    strategy_code: str
    strategy_branch: str
    trade_id: str
    order_role: str
    attempt: int = 1

    def normalized(self) -> str:
        if self.attempt <= 0:
            raise BrokerOrderIdempotencyError("attempt must be positive")
        parts = (
            self.provider,
            self.strategy_code,
            self.strategy_branch,
            self.trade_id,
            self.order_role,
            str(self.attempt),
        )
        for value in parts:
            if not str(value).strip():
                raise BrokerOrderIdempotencyError("idempotency key values are required")
        return "|".join(str(value).strip().upper() for value in parts)


@dataclass(frozen=True, slots=True)
class BrokerOrderReservation:
    artifact_version: int
    idempotency_key: str
    provider: str
    strategy_code: str
    strategy_branch: str
    trade_id: str
    order_role: str
    attempt: int
    client_order_id: str
    status: BrokerOrderReservationStatus
    reserved_at: datetime
    last_updated_at: datetime
    broker_order_state_path: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class BrokerOrderReservationResult:
    reservation: BrokerOrderReservation
    created: bool
    duplicate_prevented: bool
    message: str


def build_broker_client_order_id(key: BrokerOrderIdempotencyKey) -> str:
    normalized = key.normalized()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()[:16]
    strategy = _compact_token(key.strategy_code, max_length=8)
    role = _compact_token(key.order_role, max_length=10)
    return f"TFIS-{strategy}-{role}-{digest}"


class BrokerOrderIdempotencyStore:
    def reserve(
        self,
        registry_directory: str | Path,
        *,
        key: BrokerOrderIdempotencyKey,
        reserved_at: datetime,
    ) -> BrokerOrderReservationResult:
        registry_path = Path(registry_directory) / _REGISTRY_FILENAME
        records = self.load_records(registry_directory)
        idempotency_key = key.normalized()
        client_order_id = build_broker_client_order_id(key)

        for record in records:
            if record.idempotency_key == idempotency_key:
                if record.status is BrokerOrderReservationStatus.RELEASED:
                    break
                return BrokerOrderReservationResult(
                    reservation=record,
                    created=False,
                    duplicate_prevented=True,
                    message=(
                        "Broker order reservation already exists for this "
                        "idempotency key; duplicate routing must be skipped."
                    ),
                )
            if (
                record.client_order_id == client_order_id
                and record.idempotency_key != idempotency_key
                and record.status is not BrokerOrderReservationStatus.RELEASED
            ):
                raise BrokerOrderIdempotencyError(
                    "client_order_id collision with a different idempotency key"
                )

        reservation = BrokerOrderReservation(
            artifact_version=1,
            idempotency_key=idempotency_key,
            provider=key.provider,
            strategy_code=key.strategy_code,
            strategy_branch=key.strategy_branch,
            trade_id=key.trade_id,
            order_role=key.order_role,
            attempt=key.attempt,
            client_order_id=client_order_id,
            status=BrokerOrderReservationStatus.RESERVED,
            reserved_at=reserved_at,
            last_updated_at=reserved_at,
            message="Broker order client id reserved before any routing attempt.",
        )
        self._append_record(registry_path, reservation)
        return BrokerOrderReservationResult(
            reservation=reservation,
            created=True,
            duplicate_prevented=False,
            message="Broker order client id reserved.",
        )

    def mark_consumed(
        self,
        registry_directory: str | Path,
        *,
        idempotency_key: str,
        consumed_at: datetime,
        broker_order_state_path: str | Path,
    ) -> BrokerOrderReservation:
        records = self.load_records(registry_directory)
        current = self._latest_by_key(records).get(idempotency_key)
        if current is None:
            raise BrokerOrderIdempotencyError("reservation is missing")
        updated = BrokerOrderReservation(
            artifact_version=current.artifact_version,
            idempotency_key=current.idempotency_key,
            provider=current.provider,
            strategy_code=current.strategy_code,
            strategy_branch=current.strategy_branch,
            trade_id=current.trade_id,
            order_role=current.order_role,
            attempt=current.attempt,
            client_order_id=current.client_order_id,
            status=BrokerOrderReservationStatus.CONSUMED,
            reserved_at=current.reserved_at,
            last_updated_at=consumed_at,
            broker_order_state_path=str(broker_order_state_path),
            message="Broker order reservation consumed by persisted broker order state.",
        )
        self._append_record(Path(registry_directory) / _REGISTRY_FILENAME, updated)
        return updated

    def load_records(self, registry_directory: str | Path) -> tuple[BrokerOrderReservation, ...]:
        path = Path(registry_directory) / _REGISTRY_FILENAME
        if not path.exists():
            return ()
        records: list[BrokerOrderReservation] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BrokerOrderIdempotencyError(
                    f"Invalid broker order idempotency JSON at {path}:{line_number}"
                ) from exc
            records.append(
                BrokerOrderReservation(
                    artifact_version=int(payload["artifact_version"]),
                    idempotency_key=str(payload["idempotency_key"]),
                    provider=str(payload["provider"]),
                    strategy_code=str(payload["strategy_code"]),
                    strategy_branch=str(payload["strategy_branch"]),
                    trade_id=str(payload["trade_id"]),
                    order_role=str(payload["order_role"]),
                    attempt=int(payload["attempt"]),
                    client_order_id=str(payload["client_order_id"]),
                    status=BrokerOrderReservationStatus(str(payload["status"])),
                    reserved_at=datetime.fromisoformat(str(payload["reserved_at"])),
                    last_updated_at=datetime.fromisoformat(str(payload["last_updated_at"])),
                    broker_order_state_path=(
                        str(payload["broker_order_state_path"])
                        if payload.get("broker_order_state_path") is not None
                        else None
                    ),
                    message=(
                        str(payload["message"])
                        if payload.get("message") is not None
                        else None
                    ),
                )
            )
        return tuple(records)

    @staticmethod
    def _latest_by_key(
        records: tuple[BrokerOrderReservation, ...],
    ) -> dict[str, BrokerOrderReservation]:
        result: dict[str, BrokerOrderReservation] = {}
        for record in records:
            result[record.idempotency_key] = record
        return result

    @staticmethod
    def _append_record(path: Path, reservation: BrokerOrderReservation) -> None:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        rendered = existing + json.dumps(_normalize(reservation), sort_keys=True) + "\n"
        atomic_write_text(path, rendered)


def _compact_token(value: str, *, max_length: int) -> str:
    token = re.sub(r"[^A-Z0-9]+", "", value.upper())
    if not token:
        raise BrokerOrderIdempotencyError("client order id token is empty")
    return token[:max_length]


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    return value


__all__ = [
    "BrokerOrderIdempotencyError",
    "BrokerOrderIdempotencyKey",
    "BrokerOrderIdempotencyStore",
    "BrokerOrderReservation",
    "BrokerOrderReservationResult",
    "BrokerOrderReservationStatus",
    "build_broker_client_order_id",
]
