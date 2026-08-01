from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .serialization import canonical_hash


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Migration:
    migration_id: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return canonical_hash({"id": self.migration_id, "name": self.name, "sql": self.sql})


INITIAL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id INTEGER PRIMARY KEY,
    migration_name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS trading_sessions (
    trading_session_id TEXT PRIMARY KEY,
    trading_date TEXT NOT NULL,
    market TEXT NOT NULL,
    timezone TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    created_timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS broker_account_identities (
    broker_account_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    environment TEXT NOT NULL,
    account_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    UNIQUE(provider, environment, account_hash)
);
CREATE TABLE IF NOT EXISTS strategy_instances (
    strategy_instance_id TEXT PRIMARY KEY,
    strategy_definition_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS position_cycle_identities (
    position_cycle_id TEXT PRIMARY KEY,
    strategy_instance_id TEXT NOT NULL,
    trading_session_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(strategy_instance_id) REFERENCES strategy_instances(strategy_instance_id),
    FOREIGN KEY(trading_session_id) REFERENCES trading_sessions(trading_session_id)
);
CREATE TABLE IF NOT EXISTS immutable_artifacts (
    artifact_id TEXT PRIMARY KEY,
    artifact_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    trading_date TEXT,
    strategy_instance_id TEXT,
    position_cycle_id TEXT,
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    configuration_hash TEXT,
    rule_matrix_version TEXT,
    source_timestamp TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(strategy_instance_id) REFERENCES strategy_instances(strategy_instance_id),
    FOREIGN KEY(position_cycle_id) REFERENCES position_cycle_identities(position_cycle_id)
);
CREATE TABLE IF NOT EXISTS broker_observations (
    observation_id TEXT PRIMARY KEY,
    observation_type TEXT NOT NULL,
    broker_account_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    capture_timestamp TEXT NOT NULL,
    source_timestamp TEXT,
    raw_response_hash TEXT,
    normalized_record_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    completeness TEXT,
    quality TEXT NOT NULL,
    pagination_json TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
CREATE TABLE IF NOT EXISTS broker_read_failures (
    failure_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL,
    failure_code TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(observation_id) REFERENCES broker_observations(observation_id)
);
CREATE TABLE IF NOT EXISTS operational_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    trading_session_id TEXT,
    broker_account_id TEXT,
    effective_timestamp TEXT NOT NULL,
    source_timestamp TEXT,
    recorded_timestamp TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    idempotency_scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    UNIQUE(aggregate_type, aggregate_id, sequence_number),
    UNIQUE(idempotency_scope, idempotency_key),
    FOREIGN KEY(trading_session_id) REFERENCES trading_sessions(trading_session_id),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
CREATE TABLE IF NOT EXISTS current_runtime_stream_projection (
    projection_id TEXT PRIMARY KEY,
    strategy_instance_id TEXT NOT NULL,
    trading_session_id TEXT NOT NULL,
    latest_state TEXT NOT NULL,
    latest_checkpoint_id TEXT,
    latest_artifact_hashes_json TEXT NOT NULL,
    consumed_event_watermark INTEGER NOT NULL,
    version INTEGER NOT NULL,
    updated_timestamp TEXT NOT NULL,
    FOREIGN KEY(strategy_instance_id) REFERENCES strategy_instances(strategy_instance_id),
    FOREIGN KEY(trading_session_id) REFERENCES trading_sessions(trading_session_id)
);
CREATE TABLE IF NOT EXISTS broker_account_observation_projection (
    broker_account_id TEXT PRIMARY KEY,
    latest_account_session_observation_id TEXT,
    latest_funds_observation_id TEXT,
    latest_margin_observation_id TEXT,
    latest_account_read_snapshot_observation_id TEXT,
    latest_observation_timestamp TEXT NOT NULL,
    completeness TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_timestamp TEXT NOT NULL,
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
CREATE TABLE IF NOT EXISTS broker_order_observation_projection (
    projection_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    broker_order_id TEXT NOT NULL,
    latest_normalized_order_state TEXT NOT NULL,
    cumulative_filled_quantity INTEGER NOT NULL,
    latest_event_id TEXT,
    latest_snapshot_observation_id TEXT,
    version INTEGER NOT NULL,
    updated_timestamp TEXT NOT NULL,
    UNIQUE(broker_account_id, broker_order_id),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
CREATE TABLE IF NOT EXISTS broker_position_observation_projection (
    projection_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    normalized_contract TEXT NOT NULL,
    latest_quantity INTEGER NOT NULL,
    latest_prices_json TEXT NOT NULL,
    latest_pnl_json TEXT NOT NULL,
    latest_snapshot_observation_id TEXT,
    version INTEGER NOT NULL,
    updated_timestamp TEXT NOT NULL,
    UNIQUE(broker_account_id, normalized_contract),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
CREATE TABLE IF NOT EXISTS idempotency_reservations (
    reservation_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    completed_timestamp TEXT,
    result_reference TEXT,
    UNIQUE(scope, idempotency_key)
);
CREATE TABLE IF NOT EXISTS execution_intent_reservations (
    reservation_id TEXT PRIMARY KEY,
    proposed_execution_intent_id TEXT NOT NULL,
    broker_account_id TEXT NOT NULL,
    strategy_instance_id TEXT NOT NULL,
    position_cycle_id TEXT,
    source_artifact_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    authority_mode TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    updated_timestamp TEXT NOT NULL,
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id),
    FOREIGN KEY(strategy_instance_id) REFERENCES strategy_instances(strategy_instance_id),
    FOREIGN KEY(position_cycle_id) REFERENCES position_cycle_identities(position_cycle_id),
    FOREIGN KEY(source_artifact_id) REFERENCES immutable_artifacts(artifact_id)
);
CREATE TABLE IF NOT EXISTS local_client_orders (
    client_order_id TEXT PRIMARY KEY,
    execution_intent_reservation_id TEXT NOT NULL,
    broker_account_id TEXT NOT NULL,
    order_purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    broker_order_id TEXT,
    quantity INTEGER NOT NULL,
    fill_quantity INTEGER NOT NULL,
    protection_generation INTEGER NOT NULL,
    truth_kind TEXT NOT NULL,
    authority_mode TEXT NOT NULL,
    version INTEGER NOT NULL,
    FOREIGN KEY(execution_intent_reservation_id) REFERENCES execution_intent_reservations(reservation_id),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
CREATE TABLE IF NOT EXISTS local_fill_facts (
    fill_fact_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    truth_kind TEXT NOT NULL,
    authority_mode TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
CREATE TABLE IF NOT EXISTS local_position_cycle_projections (
    position_cycle_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    truth_kind TEXT NOT NULL,
    authority_mode TEXT NOT NULL,
    version INTEGER NOT NULL,
    FOREIGN KEY(position_cycle_id) REFERENCES position_cycle_identities(position_cycle_id)
);
CREATE TABLE IF NOT EXISTS lifecycle_requirement_records (
    requirement_id TEXT PRIMARY KEY,
    position_cycle_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    truth_kind TEXT NOT NULL,
    authority_mode TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(position_cycle_id) REFERENCES position_cycle_identities(position_cycle_id)
);
CREATE TABLE IF NOT EXISTS runtime_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    stream_identity TEXT NOT NULL,
    session_source_id TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    current_state TEXT NOT NULL,
    consumed_event_ids_json TEXT NOT NULL,
    snapshot_hashes_json TEXT NOT NULL,
    artifact_hashes_json TEXT NOT NULL,
    configuration_hash TEXT NOT NULL,
    rule_matrix_version TEXT NOT NULL,
    checkpoint_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL
);
"""


MIGRATIONS = (
    Migration(1, "phase4c_operational_persistence", INITIAL_SCHEMA_SQL),
    Migration(
        2,
        "phase4d_reconciliation_evidence",
        """
CREATE TABLE IF NOT EXISTS reconciliation_results (
    reconciliation_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    trading_session_id TEXT NOT NULL,
    reconciliation_scope TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    authority_gate TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id),
    FOREIGN KEY(trading_session_id) REFERENCES trading_sessions(trading_session_id)
);
CREATE TABLE IF NOT EXISTS reconciliation_items (
    item_id TEXT PRIMARY KEY,
    reconciliation_id TEXT NOT NULL,
    item_type TEXT NOT NULL,
    classification TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY(reconciliation_id) REFERENCES reconciliation_results(reconciliation_id)
);
CREATE TABLE IF NOT EXISTS reconciliation_repair_recommendations (
    recommendation_id TEXT PRIMARY KEY,
    reconciliation_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    recommendation_code TEXT NOT NULL,
    execution_not_permitted INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY(reconciliation_id) REFERENCES reconciliation_results(reconciliation_id)
);
CREATE TABLE IF NOT EXISTS latest_reconciliation_projection (
    projection_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    trading_session_id TEXT NOT NULL,
    reconciliation_scope TEXT NOT NULL,
    latest_result_id TEXT NOT NULL,
    latest_result_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    blocking_classifications_json TEXT NOT NULL,
    snapshot_watermark TEXT NOT NULL,
    local_projection_version INTEGER NOT NULL,
    broker_snapshot_hash TEXT NOT NULL,
    completed_timestamp TEXT NOT NULL,
    version INTEGER NOT NULL,
    UNIQUE(broker_account_id, trading_session_id, reconciliation_scope),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id),
    FOREIGN KEY(trading_session_id) REFERENCES trading_sessions(trading_session_id),
    FOREIGN KEY(latest_result_id) REFERENCES reconciliation_results(reconciliation_id)
);
""",
    ),
    Migration(
        3,
        "phase4e_execution_intent_validation",
        """
CREATE TABLE IF NOT EXISTS execution_intents (
    execution_intent_id TEXT PRIMARY KEY,
    reservation_id TEXT NOT NULL,
    broker_account_id TEXT NOT NULL,
    strategy_instance_id TEXT NOT NULL,
    position_cycle_id TEXT,
    source_artifact_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    purpose TEXT NOT NULL,
    authority_mode TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(reservation_id) REFERENCES execution_intent_reservations(reservation_id),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id),
    FOREIGN KEY(strategy_instance_id) REFERENCES strategy_instances(strategy_instance_id),
    FOREIGN KEY(position_cycle_id) REFERENCES position_cycle_identities(position_cycle_id),
    FOREIGN KEY(source_artifact_id) REFERENCES immutable_artifacts(artifact_id)
);
CREATE TABLE IF NOT EXISTS intent_validation_results (
    validation_id TEXT PRIMARY KEY,
    execution_intent_id TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    decision TEXT NOT NULL,
    result_hash TEXT NOT NULL,
    authority_mode TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(execution_intent_id) REFERENCES execution_intents(execution_intent_id)
);
CREATE TABLE IF NOT EXISTS intent_validation_checks (
    validation_id TEXT NOT NULL,
    check_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    result TEXT NOT NULL,
    severity TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY(validation_id, check_id),
    FOREIGN KEY(validation_id) REFERENCES intent_validation_results(validation_id)
);
CREATE TABLE IF NOT EXISTS latest_intent_validation_projection (
    projection_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    strategy_instance_id TEXT NOT NULL,
    position_cycle_id TEXT,
    execution_intent_id TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    latest_validation_id TEXT NOT NULL,
    latest_result_hash TEXT NOT NULL,
    decision TEXT NOT NULL,
    purpose TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_timestamp TEXT NOT NULL,
    UNIQUE(broker_account_id, strategy_instance_id, execution_intent_id),
    FOREIGN KEY(latest_validation_id) REFERENCES intent_validation_results(validation_id)
);
""",
    ),
    Migration(
        4,
        "phase4f_internal_paper_order_simulation",
        """
CREATE TABLE IF NOT EXISTS internal_paper_authority_grants (
    grant_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    trading_session_id TEXT NOT NULL,
    strategy_instance_id TEXT NOT NULL,
    grant_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id),
    FOREIGN KEY(trading_session_id) REFERENCES trading_sessions(trading_session_id),
    FOREIGN KEY(strategy_instance_id) REFERENCES strategy_instances(strategy_instance_id)
);
CREATE TABLE IF NOT EXISTS internal_client_order_records (
    client_order_id TEXT PRIMARY KEY,
    execution_intent_id TEXT NOT NULL,
    account_coordinator_id TEXT NOT NULL,
    broker_account_id TEXT NOT NULL,
    strategy_instance_id TEXT NOT NULL,
    trading_session_id TEXT NOT NULL,
    position_cycle_id TEXT,
    idempotency_key TEXT NOT NULL,
    order_hash TEXT NOT NULL,
    order_purpose TEXT NOT NULL,
    current_state TEXT NOT NULL,
    authority_source TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    updated_timestamp TEXT NOT NULL,
    UNIQUE(broker_account_id, idempotency_key),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id),
    FOREIGN KEY(strategy_instance_id) REFERENCES strategy_instances(strategy_instance_id),
    FOREIGN KEY(trading_session_id) REFERENCES trading_sessions(trading_session_id),
    FOREIGN KEY(position_cycle_id) REFERENCES position_cycle_identities(position_cycle_id)
);
CREATE TABLE IF NOT EXISTS internal_paper_order_events (
    event_id TEXT PRIMARY KEY,
    client_order_id TEXT NOT NULL,
    broker_account_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    previous_state TEXT,
    new_state TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    UNIQUE(client_order_id, sequence_number),
    FOREIGN KEY(client_order_id) REFERENCES internal_client_order_records(client_order_id),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
CREATE TABLE IF NOT EXISTS internal_paper_fills (
    internal_fill_id TEXT PRIMARY KEY,
    client_order_id TEXT NOT NULL,
    broker_account_id TEXT NOT NULL,
    strategy_instance_id TEXT NOT NULL,
    position_cycle_id TEXT,
    fill_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_timestamp TEXT NOT NULL,
    FOREIGN KEY(client_order_id) REFERENCES internal_client_order_records(client_order_id),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id),
    FOREIGN KEY(strategy_instance_id) REFERENCES strategy_instances(strategy_instance_id),
    FOREIGN KEY(position_cycle_id) REFERENCES position_cycle_identities(position_cycle_id)
);
CREATE TABLE IF NOT EXISTS internal_paper_account_projections (
    projection_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    trading_session_id TEXT NOT NULL,
    account_coordinator_id TEXT NOT NULL,
    latest_snapshot_hash TEXT NOT NULL,
    active_order_count INTEGER NOT NULL,
    available_paper_margin TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_timestamp TEXT NOT NULL,
    UNIQUE(broker_account_id, trading_session_id, account_coordinator_id),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id),
    FOREIGN KEY(trading_session_id) REFERENCES trading_sessions(trading_session_id)
);
CREATE TABLE IF NOT EXISTS latest_internal_client_order_projection (
    client_order_id TEXT PRIMARY KEY,
    broker_account_id TEXT NOT NULL,
    current_state TEXT NOT NULL,
    cumulative_filled_quantity INTEGER NOT NULL,
    latest_event_id TEXT,
    order_hash TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_timestamp TEXT NOT NULL,
    FOREIGN KEY(client_order_id) REFERENCES internal_client_order_records(client_order_id),
    FOREIGN KEY(broker_account_id) REFERENCES broker_account_identities(broker_account_id)
);
""",
    ),
)


def apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    for migration in MIGRATIONS:
        rows = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE migration_id = ?",
            (migration.migration_id,),
        ).fetchall() if _table_exists(connection, "schema_migrations") else []
        if rows:
            if rows[0]["checksum"] != migration.checksum:
                raise MigrationError(f"Migration checksum mismatch for {migration.migration_id}.")
            continue
        try:
            connection.executescript(migration.sql)
            connection.execute(
                "INSERT INTO schema_migrations(migration_id, migration_name, checksum, applied_timestamp, schema_version) VALUES (?, ?, ?, ?, ?)",
                (
                    migration.migration_id,
                    migration.name,
                    migration.checksum,
                    datetime.now(timezone.utc).isoformat(),
                    migration.migration_id,
                ),
            )
        except Exception as exc:
            raise MigrationError(f"Migration {migration.migration_id} failed: {exc}") from exc


def validate_schema(connection: sqlite3.Connection) -> int:
    if not _table_exists(connection, "schema_migrations"):
        raise MigrationError("schema_migrations table is missing.")
    row = connection.execute("SELECT MAX(schema_version) AS version FROM schema_migrations").fetchone()
    version = int(row["version"] or 0)
    if version < MIGRATIONS[-1].migration_id:
        raise MigrationError("Schema is too old.")
    if version > MIGRATIONS[-1].migration_id:
        raise MigrationError("Schema is too new.")
    for migration in MIGRATIONS:
        row = connection.execute("SELECT checksum FROM schema_migrations WHERE migration_id = ?", (migration.migration_id,)).fetchone()
        if row is None or row["checksum"] != migration.checksum:
            raise MigrationError(f"Schema checksum mismatch for migration {migration.migration_id}.")
    return version


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None
