from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from tfis.broker.authentication import BrokerAuthenticationResult, BrokerSessionStatus, redact_sensitive


class DiagnosticStatus(str, Enum):
    READY = "READY"
    PRESENT = "PRESENT"
    PASSED = "PASSED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
    NOT_CHECKED = "NOT_CHECKED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    NOT_REQUIRED = "NOT_REQUIRED"
    READABLE = "READABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class BrokerDiagnosticSnapshot:
    broker: str
    account_ref: str
    environment: str
    observed_at: datetime
    configuration_status: DiagnosticStatus
    credential_status: DiagnosticStatus
    authentication_status: BrokerSessionStatus
    session_expiry_status: DiagnosticStatus
    reference_data_status: DiagnosticStatus
    historical_data_status: DiagnosticStatus
    quote_status: DiagnosticStatus
    option_chain_status: DiagnosticStatus
    account_read_status: DiagnosticStatus
    order_write_status: DiagnosticStatus
    websocket_status: DiagnosticStatus
    degraded_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    operator_action: str
    evidence: Mapping[str, Any] = MappingProxyType({})
    diagnostic_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))
        if self.diagnostic_hash is None:
            object.__setattr__(self, "diagnostic_hash", _hash_without_observed_at(self))

    def to_dict(self) -> dict[str, Any]:
        return redact_sensitive(_jsonable(self))


def snapshot_from_authentication_result(
    result: BrokerAuthenticationResult,
    *,
    reference_data_status: DiagnosticStatus = DiagnosticStatus.NOT_CHECKED,
    historical_data_status: DiagnosticStatus = DiagnosticStatus.NOT_CHECKED,
    quote_status: DiagnosticStatus = DiagnosticStatus.NOT_CHECKED,
    option_chain_status: DiagnosticStatus = DiagnosticStatus.NOT_CHECKED,
    account_read_status: DiagnosticStatus = DiagnosticStatus.NOT_CHECKED,
    websocket_status: DiagnosticStatus = DiagnosticStatus.NOT_CHECKED,
    evidence: Mapping[str, Any] | None = None,
) -> BrokerDiagnosticSnapshot:
    authenticated = result.status == BrokerSessionStatus.AUTHENTICATED
    blocking = [] if authenticated else [result.status.value]
    operator_action = "NONE"
    if result.failure is not None:
        operator_action = result.failure.operator_action_required
    return BrokerDiagnosticSnapshot(
        broker=result.broker,
        account_ref=result.logical_account_ref,
        environment=result.environment,
        observed_at=result.observed_at,
        configuration_status=DiagnosticStatus.READY if result.status != BrokerSessionStatus.APP_CONFIGURATION_MISSING else DiagnosticStatus.FAILED,
        credential_status=DiagnosticStatus.PRESENT if result.status not in {BrokerSessionStatus.CREDENTIAL_SOURCE_MISSING, BrokerSessionStatus.TOKEN_MISSING, BrokerSessionStatus.TOKEN_SCHEMA_INVALID} else DiagnosticStatus.FAILED,
        authentication_status=result.status,
        session_expiry_status=DiagnosticStatus.NOT_CHECKED if authenticated else DiagnosticStatus.FAILED,
        reference_data_status=reference_data_status,
        historical_data_status=historical_data_status,
        quote_status=quote_status,
        option_chain_status=option_chain_status,
        account_read_status=account_read_status,
        order_write_status=DiagnosticStatus.NOT_AUTHORIZED,
        websocket_status=websocket_status,
        degraded_reasons=(),
        blocking_reasons=tuple(blocking),
        operator_action=operator_action,
        evidence=evidence or {},
    )


def _hash_without_observed_at(snapshot: BrokerDiagnosticSnapshot) -> str:
    payload = _jsonable(snapshot)
    payload.pop("observed_at", None)
    payload.pop("diagnostic_hash", None)
    rendered = json.dumps(redact_sensitive(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


__all__ = ["BrokerDiagnosticSnapshot", "DiagnosticStatus", "snapshot_from_authentication_result"]
