from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class PersistenceAuthorityMode(str, Enum):
    OBSERVATIONAL_OR_OFFLINE_ONLY = "OBSERVATIONAL_OR_OFFLINE_ONLY"


class PersistenceTruthKind(str, Enum):
    OBSERVED_BROKER_FACT = "OBSERVED_BROKER_FACT"
    LOCAL_EXPECTED_STATE = "LOCAL_EXPECTED_STATE"
    RECONCILED_STATE = "RECONCILED_STATE"
    ANALYTICAL_PROJECTION = "ANALYTICAL_PROJECTION"


class IdempotencyReservationStatus(str, Enum):
    RESERVED = "RESERVED"
    COMMITTED = "COMMITTED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    CONFLICT = "CONFLICT"


class RecoveryStatus(str, Enum):
    RECOVERABLE_OFFLINE = "RECOVERABLE_OFFLINE"
    PARTIAL_RECOVERY = "PARTIAL_RECOVERY"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    CONFIGURATION_MISMATCH = "CONFIGURATION_MISMATCH"
    RULE_VERSION_MISMATCH = "RULE_VERSION_MISMATCH"
    CORRUPTED_STATE = "CORRUPTED_STATE"
    UNSUPPORTED_SCHEMA = "UNSUPPORTED_SCHEMA"
    BLOCKED = "BLOCKED"


class ComparisonClassification(str, Enum):
    OBSERVATION_MATCH = "OBSERVATION_MATCH"
    OBSERVATION_DIFFERENCE = "OBSERVATION_DIFFERENCE"
    MISSING_LOCAL_EXPECTATION = "MISSING_LOCAL_EXPECTATION"
    MISSING_BROKER_OBSERVATION = "MISSING_BROKER_OBSERVATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class RecoveryAssessment:
    status: RecoveryStatus
    schema_version: int | None
    checked_at: datetime
    findings: tuple[str, ...]
    latest_runtime_projection_count: int
    latest_broker_projection_count: int
    pending_idempotency_count: int
    authority_mode: PersistenceAuthorityMode = PersistenceAuthorityMode.OBSERVATIONAL_OR_OFFLINE_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "schema_version": self.schema_version,
            "checked_at": self.checked_at.isoformat(),
            "findings": list(self.findings),
            "latest_runtime_projection_count": self.latest_runtime_projection_count,
            "latest_broker_projection_count": self.latest_broker_projection_count,
            "pending_idempotency_count": self.pending_idempotency_count,
            "authority_mode": self.authority_mode.value,
        }


@dataclass(frozen=True, slots=True)
class ObservationalComparison:
    classification: ComparisonClassification
    comparison_type: str
    expected_hash: str | None
    observed_hash: str | None
    differences: Mapping[str, Any]
    authority_mode: PersistenceAuthorityMode = PersistenceAuthorityMode.OBSERVATIONAL_OR_OFFLINE_ONLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "comparison_type": self.comparison_type,
            "expected_hash": self.expected_hash,
            "observed_hash": self.observed_hash,
            "differences": dict(self.differences),
            "authority_mode": self.authority_mode.value,
        }
