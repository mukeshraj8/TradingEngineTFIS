from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


SENSITIVE_FRAGMENTS = (
    "access_token",
    "app_id",
    "refresh_token",
    "authorization",
    "auth_code",
    "display_name",
    "email",
    "fy_id",
    "mobile",
    "name",
    "pan",
    "client_secret",
    "app_secret",
    "bearer",
    "cookie",
    "pin",
    "pin_change_date",
    "password",
    "pwd",
    "totp",
    "otp",
    "session_token",
)


class BrokerSessionStatus(str, Enum):
    CREDENTIAL_SOURCE_MISSING = "CREDENTIAL_SOURCE_MISSING"
    APP_CONFIGURATION_MISSING = "APP_CONFIGURATION_MISSING"
    INTERACTIVE_LOGIN_REQUIRED = "INTERACTIVE_LOGIN_REQUIRED"
    TOKEN_MISSING = "TOKEN_MISSING"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REJECTED = "TOKEN_REJECTED"
    TOKEN_SCHEMA_INVALID = "TOKEN_SCHEMA_INVALID"
    ACCOUNT_SCOPE_MISMATCH = "ACCOUNT_SCOPE_MISMATCH"
    SESSION_VALIDATION_FAILED = "SESSION_VALIDATION_FAILED"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    AUTHENTICATED = "AUTHENTICATED"


@dataclass(frozen=True, slots=True)
class BrokerCredentialReference:
    source_type: str
    path: str | None
    schema: str
    ignored_by_git: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class BrokerAuthenticationRequest:
    broker: str
    logical_account_ref: str
    environment: str
    credential_reference: BrokerCredentialReference
    authentication_method: str
    validate_session: bool = True
    allow_refresh: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class BrokerSessionIdentity:
    broker: str
    logical_account_ref: str
    environment: str
    app_id_prefix: str | None
    client_id_fingerprint: str | None
    credential_reference: BrokerCredentialReference
    authenticated_at: datetime | None
    expires_at: datetime | None
    identity_hash: str

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class BrokerAuthenticationFailure:
    status: BrokerSessionStatus
    message: str
    operator_action_required: str
    evidence: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(self)


@dataclass(frozen=True, slots=True)
class ValidatedBrokerSession:
    identity: BrokerSessionIdentity
    client: Any
    validation_payload: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "client": "REDACTED_SESSION_HANDLE",
            "validation_payload": redact_sensitive(self.validation_payload),
        }


@dataclass(frozen=True, slots=True)
class BrokerAuthenticationResult:
    broker: str
    logical_account_ref: str
    environment: str
    observed_at: datetime
    status: BrokerSessionStatus
    credential_reference: BrokerCredentialReference
    session_identity: BrokerSessionIdentity | None = None
    session: ValidatedBrokerSession | None = None
    failure: BrokerAuthenticationFailure | None = None
    refreshed: bool = False
    diagnostic_hash: str | None = None

    def __post_init__(self) -> None:
        if self.diagnostic_hash is None:
            object.__setattr__(
                self,
                "diagnostic_hash",
                canonical_hash(
                    {
                        "broker": self.broker,
                        "logical_account_ref": self.logical_account_ref,
                        "environment": self.environment,
                        "status": self.status.value,
                        "credential_reference": self.credential_reference.to_dict(),
                        "session_identity": self.session_identity.to_dict() if self.session_identity else None,
                        "failure": self.failure.to_dict() if self.failure else None,
                        "refreshed": self.refreshed,
                    }
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return redact_sensitive(
            {
                "broker": self.broker,
                "logical_account_ref": self.logical_account_ref,
                "environment": self.environment,
                "observed_at": self.observed_at.isoformat(),
                "status": self.status.value,
                "credential_reference": self.credential_reference.to_dict(),
                "session_identity": self.session_identity.to_dict() if self.session_identity else None,
                "session": self.session.to_dict() if self.session else None,
                "failure": self.failure.to_dict() if self.failure else None,
                "refreshed": self.refreshed,
                "diagnostic_hash": self.diagnostic_hash,
            }
        )


def fingerprint(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def canonical_hash(value: Any) -> str:
    rendered = json.dumps(_jsonable(redact_sensitive(value)), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            redacted[str(key)] = "REDACTED" if any(fragment in lowered for fragment in SENSITIVE_FRAGMENTS) else redact_sensitive(item)
        return redacted
    if isinstance(value, tuple | list):
        return [redact_sensitive(item) for item in value]
    return value


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
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value
