from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping

from .migrations import MigrationError, validate_schema
from .models import (
    ComparisonClassification,
    ObservationalComparison,
    RecoveryAssessment,
    RecoveryStatus,
)
from .serialization import canonical_hash, from_canonical_json


def assess_recovery(
    connection: sqlite3.Connection,
    *,
    expected_configuration_hash: str | None = None,
    expected_rule_matrix_version: str | None = None,
) -> RecoveryAssessment:
    findings: list[str] = []
    try:
        schema_version = validate_schema(connection)
    except MigrationError as exc:
        return RecoveryAssessment(
            status=RecoveryStatus.UNSUPPORTED_SCHEMA,
            schema_version=None,
            checked_at=_now(),
            findings=(str(exc),),
            latest_runtime_projection_count=0,
            latest_broker_projection_count=0,
            pending_idempotency_count=0,
        )
    for row in connection.execute("SELECT checkpoint_id, payload_json, checkpoint_hash, configuration_hash, rule_matrix_version FROM runtime_checkpoints"):
        try:
            payload = from_canonical_json(row["payload_json"])
            if canonical_hash(payload) != row["checkpoint_hash"]:
                findings.append(f"CORRUPTED_CHECKPOINT:{row['checkpoint_id']}")
            if expected_configuration_hash and row["configuration_hash"] != expected_configuration_hash:
                findings.append(f"CONFIGURATION_MISMATCH:{row['checkpoint_id']}")
            if expected_rule_matrix_version and row["rule_matrix_version"] != expected_rule_matrix_version:
                findings.append(f"RULE_VERSION_MISMATCH:{row['checkpoint_id']}")
        except Exception:
            findings.append(f"CORRUPTED_CHECKPOINT:{row['checkpoint_id']}")
    pending = _count(connection, "SELECT COUNT(*) FROM idempotency_reservations WHERE status = 'RESERVED'")
    runtime_count = _count(connection, "SELECT COUNT(*) FROM current_runtime_stream_projection")
    broker_count = _count(connection, "SELECT COUNT(*) FROM broker_account_observation_projection")
    if any(item.startswith("CORRUPTED") for item in findings):
        status = RecoveryStatus.CORRUPTED_STATE
    elif any(item.startswith("CONFIGURATION_MISMATCH") for item in findings):
        status = RecoveryStatus.CONFIGURATION_MISMATCH
    elif any(item.startswith("RULE_VERSION_MISMATCH") for item in findings):
        status = RecoveryStatus.RULE_VERSION_MISMATCH
    elif pending:
        status = RecoveryStatus.PARTIAL_RECOVERY
    elif broker_count and runtime_count:
        status = RecoveryStatus.RECOVERABLE_OFFLINE
    else:
        status = RecoveryStatus.RECONCILIATION_REQUIRED
    return RecoveryAssessment(
        status=status,
        schema_version=schema_version,
        checked_at=_now(),
        findings=tuple(findings),
        latest_runtime_projection_count=runtime_count,
        latest_broker_projection_count=broker_count,
        pending_idempotency_count=pending,
    )


def run_integrity_scan(connection: sqlite3.Connection) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    fk_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    for row in fk_rows:
        issues.append({"code": "FOREIGN_KEY_VIOLATION", "table": row[0], "rowid": row[1]})
    for table in ("immutable_artifacts", "broker_observations", "operational_events", "runtime_checkpoints"):
        for row in connection.execute(f"SELECT * FROM {table}"):
            payload_column = "payload_json"
            if payload_column in row.keys():
                try:
                    from_canonical_json(row[payload_column])
                except Exception:
                    issues.append({"code": "MALFORMED_PAYLOAD", "table": table, "id": row[0]})
    event_rows = connection.execute(
        "SELECT aggregate_type, aggregate_id, sequence_number FROM operational_events ORDER BY aggregate_type, aggregate_id, sequence_number"
    ).fetchall()
    last: dict[tuple[str, str], int] = {}
    for row in event_rows:
        key = (row["aggregate_type"], row["aggregate_id"])
        expected = last.get(key, 0) + 1
        if row["sequence_number"] != expected:
            issues.append({"code": "EVENT_SEQUENCE_GAP", "aggregate": list(key), "expected": expected, "actual": row["sequence_number"]})
        last[key] = row["sequence_number"]
    return {
        "status": "PASS" if not issues else "FAIL",
        "issue_count": len(issues),
        "issues": issues,
        "authority_mode": "OBSERVATIONAL_OR_OFFLINE_ONLY",
    }


def observational_compare(
    *,
    comparison_type: str,
    expected: Mapping[str, Any] | None,
    observed: Mapping[str, Any] | None,
) -> ObservationalComparison:
    if expected is None and observed is None:
        return ObservationalComparison(
            classification=ComparisonClassification.INSUFFICIENT_EVIDENCE,
            comparison_type=comparison_type,
            expected_hash=None,
            observed_hash=None,
            differences={},
        )
    if expected is None:
        return ObservationalComparison(
            classification=ComparisonClassification.MISSING_LOCAL_EXPECTATION,
            comparison_type=comparison_type,
            expected_hash=None,
            observed_hash=canonical_hash(observed),
            differences={},
        )
    if observed is None:
        return ObservationalComparison(
            classification=ComparisonClassification.MISSING_BROKER_OBSERVATION,
            comparison_type=comparison_type,
            expected_hash=canonical_hash(expected),
            observed_hash=None,
            differences={},
        )
    expected_hash = canonical_hash(expected)
    observed_hash = canonical_hash(observed)
    differences = {
        key: {"expected": expected.get(key), "observed": observed.get(key)}
        for key in sorted(set(expected) | set(observed))
        if expected.get(key) != observed.get(key)
    }
    return ObservationalComparison(
        classification=ComparisonClassification.OBSERVATION_MATCH if not differences else ComparisonClassification.OBSERVATION_DIFFERENCE,
        comparison_type=comparison_type,
        expected_hash=expected_hash,
        observed_hash=observed_hash,
        differences=differences,
    )


def _count(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0])


def _now() -> datetime:
    return datetime.now(timezone.utc)
