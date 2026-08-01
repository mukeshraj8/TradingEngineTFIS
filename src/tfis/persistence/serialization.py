from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Any, Mapping


SECRET_KEY_FRAGMENTS = (
    "access_token",
    "refresh_token",
    "api_key",
    "api_secret",
    "authorization",
    "client_secret",
    "cookie",
    "password",
    "pin",
    "session_token",
    "token",
)


class SerializationError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    normalized = _normalize(value)
    _assert_no_secrets(normalized)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def from_canonical_json(payload: str) -> Any:
    return _restore(json.loads(payload))


def redacted_json(value: Any) -> str:
    return json.dumps(_redact(_normalize(value)), sort_keys=True, indent=2, ensure_ascii=True)


def _normalize(value: Any) -> Any:
    if is_dataclass(value):
        return _normalize(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise SerializationError("Decimal NaN/Infinity is not allowed.")
        return {"__type__": "Decimal", "value": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise SerializationError("Timezone-aware datetimes are required.")
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date) and not isinstance(value, datetime):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {"__type__": "time", "value": value.isoformat()}
    if isinstance(value, float):
        if not isfinite(value):
            raise SerializationError("Float NaN/Infinity is not allowed.")
        return value
    if isinstance(value, Path):
        raise SerializationError("Filesystem paths are not canonical business payloads.")
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, tuple | list):
        return [_normalize(item) for item in value]
    if value is None or isinstance(value, str | int | bool):
        return value
    raise SerializationError(f"Unsupported canonical serialization type: {type(value).__name__}")


def _restore(value: Any) -> Any:
    if isinstance(value, dict):
        marker = value.get("__type__")
        if marker == "Decimal":
            return Decimal(str(value["value"]))
        if marker == "datetime":
            return datetime.fromisoformat(str(value["value"]))
        if marker == "date":
            return date.fromisoformat(str(value["value"]))
        if marker == "time":
            return time.fromisoformat(str(value["value"]))
        return {key: _restore(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore(item) for item in value]
    return value


def _assert_no_secrets(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                raise SerializationError(f"Secret-bearing field is not allowed: {key}")
            _assert_no_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_secrets(item)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                result[str(key)] = "REDACTED"
            elif str(key) == "account_id" and isinstance(item, str) and len(item) > 4:
                result[str(key)] = f"{item[:2]}***{item[-2:]}"
            else:
                result[str(key)] = _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value
