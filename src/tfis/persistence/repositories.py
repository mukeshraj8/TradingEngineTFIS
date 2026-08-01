from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from typing import Any, Mapping

from .models import (
    IdempotencyReservationStatus,
    PersistenceAuthorityMode,
    PersistenceTruthKind,
)
from .serialization import canonical_hash, canonical_json


class ArtifactConflictError(RuntimeError):
    pass


class IdempotencyConflictError(RuntimeError):
    pass


class OptimisticConcurrencyError(RuntimeError):
    pass


KNOWN_ARTIFACT_TYPES = frozenset(
    {
        "TFISRuntimeInput",
        "TFISDecision",
        "TFISDecisionEvidencePacket",
        "PreMarketStrategyPlan",
        "OpeningMarketContext",
        "EffectiveExecutionPlan",
        "PositionLifecycleContext",
        "CarriedPositionTradingDayResult",
        "M15RuntimeCheckpointResult",
        "Phase4AShadowResult",
        "Phase4AShadowEvidence",
    }
)
KNOWN_EVENT_TYPES = frozenset(
    {
        "SHADOW_DECISION_PERSISTED",
        "BROKER_ACCOUNT_READ_OBSERVED",
        "BROKER_ORDER_OBSERVED",
        "BROKER_FILL_OBSERVED",
        "RUNTIME_CHECKPOINT_PERSISTED",
        "IDEMPOTENCY_RESERVED",
    }
)


class PersistenceRepositories:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def put_trading_session(
        self,
        *,
        trading_session_id: str,
        trading_date: date,
        market: str,
        timezone_name: str,
        payload: Mapping[str, Any],
    ) -> str:
        payload_json = canonical_json(payload)
        self.connection.execute(
            """
            INSERT INTO trading_sessions(trading_session_id, trading_date, market, timezone, payload_json, payload_hash, created_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trading_session_id) DO NOTHING
            """,
            (
                trading_session_id,
                trading_date.isoformat(),
                market,
                timezone_name,
                payload_json,
                canonical_hash(payload),
                _now(),
            ),
        )
        return trading_session_id

    def put_broker_account_identity(
        self,
        *,
        broker_account_id: str,
        provider: str,
        environment: str,
        account_hash: str,
        payload: Mapping[str, Any],
    ) -> str:
        self.connection.execute(
            """
            INSERT INTO broker_account_identities(broker_account_id, provider, environment, account_hash, payload_json, created_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(broker_account_id) DO NOTHING
            """,
            (broker_account_id, provider, environment, account_hash, canonical_json(payload), _now()),
        )
        return broker_account_id

    def put_strategy_instance(
        self,
        *,
        strategy_instance_id: str,
        strategy_definition_id: str,
        strategy_version: str,
        configuration_hash: str,
        payload: Mapping[str, Any],
    ) -> str:
        self.connection.execute(
            """
            INSERT INTO strategy_instances(strategy_instance_id, strategy_definition_id, strategy_version, configuration_hash, payload_json, created_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy_instance_id) DO NOTHING
            """,
            (
                strategy_instance_id,
                strategy_definition_id,
                strategy_version,
                configuration_hash,
                canonical_json(payload),
                _now(),
            ),
        )
        return strategy_instance_id

    def put_position_cycle_identity(
        self,
        *,
        position_cycle_id: str,
        strategy_instance_id: str,
        trading_session_id: str,
        payload: Mapping[str, Any],
    ) -> str:
        self.connection.execute(
            """
            INSERT INTO position_cycle_identities(position_cycle_id, strategy_instance_id, trading_session_id, payload_json, created_timestamp)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(position_cycle_id) DO NOTHING
            """,
            (position_cycle_id, strategy_instance_id, trading_session_id, canonical_json(payload), _now()),
        )
        return position_cycle_id

    def put_artifact(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        schema_version: str,
        payload: Mapping[str, Any],
        provenance: Mapping[str, Any],
        trading_date: date | None = None,
        strategy_instance_id: str | None = None,
        position_cycle_id: str | None = None,
        configuration_hash: str | None = None,
        rule_matrix_version: str | None = None,
        source_timestamp: datetime | None = None,
    ) -> str:
        if artifact_type not in KNOWN_ARTIFACT_TYPES:
            raise ValueError(f"Unsupported artifact type: {artifact_type}")
        payload_json = canonical_json(payload)
        content_hash = canonical_hash(payload)
        row = self.connection.execute(
            "SELECT content_hash FROM immutable_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        if row:
            if row["content_hash"] == content_hash:
                return artifact_id
            raise ArtifactConflictError(f"Artifact identity conflict: {artifact_id}")
        self.connection.execute(
            """
            INSERT INTO immutable_artifacts(
                artifact_id, artifact_type, schema_version, trading_date, strategy_instance_id, position_cycle_id,
                content_hash, payload_json, provenance_json, configuration_hash, rule_matrix_version, source_timestamp, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                artifact_type,
                schema_version,
                trading_date.isoformat() if trading_date else None,
                strategy_instance_id,
                position_cycle_id,
                content_hash,
                payload_json,
                canonical_json(provenance),
                configuration_hash,
                rule_matrix_version,
                (source_timestamp or _now_dt()).isoformat(),
                _now(),
            ),
        )
        return artifact_id

    def put_broker_observation(
        self,
        *,
        observation_id: str,
        observation_type: str,
        broker_account_id: str,
        request_id: str,
        payload: Mapping[str, Any],
        provenance: Mapping[str, Any],
        capture_timestamp: datetime,
        source_timestamp: datetime | None = None,
        raw_response_hash: str | None = None,
        completeness: str | None = None,
        quality: str = "FIXTURE",
        pagination: Mapping[str, Any] | None = None,
        adapter_version: str = "phase4b.fixture.v1",
    ) -> str:
        normalized_hash = canonical_hash(payload)
        self.connection.execute(
            """
            INSERT INTO broker_observations(
                observation_id, observation_type, broker_account_id, request_id, capture_timestamp, source_timestamp,
                raw_response_hash, normalized_record_hash, payload_json, provenance_json, completeness, quality,
                pagination_json, adapter_version, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(observation_id) DO NOTHING
            """,
            (
                observation_id,
                observation_type,
                broker_account_id,
                request_id,
                capture_timestamp.isoformat(),
                source_timestamp.isoformat() if source_timestamp else None,
                raw_response_hash,
                normalized_hash,
                canonical_json(payload),
                canonical_json(provenance),
                completeness,
                quality,
                canonical_json(pagination or {}),
                adapter_version,
                _now(),
            ),
        )
        return observation_id

    def put_broker_read_failure(
        self,
        *,
        failure_id: str,
        observation_id: str,
        failure_code: str,
        payload: Mapping[str, Any],
    ) -> str:
        self.connection.execute(
            "INSERT INTO broker_read_failures(failure_id, observation_id, failure_code, payload_json, created_timestamp) VALUES (?, ?, ?, ?, ?) ON CONFLICT(failure_id) DO NOTHING",
            (failure_id, observation_id, failure_code, canonical_json(payload), _now()),
        )
        return failure_id

    def append_event(
        self,
        *,
        event_id: str,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        trading_session_id: str | None,
        broker_account_id: str | None,
        effective_timestamp: datetime,
        payload: Mapping[str, Any],
        idempotency_scope: str,
        idempotency_key: str,
        source_timestamp: datetime | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        schema_version: str = "phase4c.event.v1",
        provenance: Mapping[str, Any] | None = None,
    ) -> str:
        if event_type not in KNOWN_EVENT_TYPES:
            raise ValueError(f"Unsupported event type: {event_type}")
        payload_hash = canonical_hash(payload)
        existing = self.connection.execute(
            "SELECT payload_hash, event_id FROM operational_events WHERE idempotency_scope = ? AND idempotency_key = ?",
            (idempotency_scope, idempotency_key),
        ).fetchone()
        if existing:
            if existing["payload_hash"] == payload_hash:
                return str(existing["event_id"])
            raise IdempotencyConflictError(f"Operational event idempotency conflict: {idempotency_scope}/{idempotency_key}")
        row = self.connection.execute(
            "SELECT COALESCE(MAX(sequence_number), 0) + 1 AS next_sequence FROM operational_events WHERE aggregate_type = ? AND aggregate_id = ?",
            (aggregate_type, aggregate_id),
        ).fetchone()
        sequence = int(row["next_sequence"])
        self.connection.execute(
            """
            INSERT INTO operational_events(
                event_id, event_type, aggregate_type, aggregate_id, sequence_number, trading_session_id,
                broker_account_id, effective_timestamp, source_timestamp, recorded_timestamp, payload_json,
                payload_hash, causation_id, correlation_id, idempotency_scope, idempotency_key, schema_version, provenance_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event_type,
                aggregate_type,
                aggregate_id,
                sequence,
                trading_session_id,
                broker_account_id,
                effective_timestamp.isoformat(),
                source_timestamp.isoformat() if source_timestamp else None,
                _now(),
                canonical_json(payload),
                payload_hash,
                causation_id,
                correlation_id,
                idempotency_scope,
                idempotency_key,
                schema_version,
                canonical_json(provenance or {}),
            ),
        )
        return event_id

    def upsert_runtime_projection(
        self,
        *,
        projection_id: str,
        strategy_instance_id: str,
        trading_session_id: str,
        latest_state: str,
        expected_version: int | None,
        latest_checkpoint_id: str | None = None,
        latest_artifact_hashes: Mapping[str, Any] | None = None,
        consumed_event_watermark: int = 0,
    ) -> int:
        row = self.connection.execute(
            "SELECT version FROM current_runtime_stream_projection WHERE projection_id = ?",
            (projection_id,),
        ).fetchone()
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO current_runtime_stream_projection(
                    projection_id, strategy_instance_id, trading_session_id, latest_state, latest_checkpoint_id,
                    latest_artifact_hashes_json, consumed_event_watermark, version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection_id,
                    strategy_instance_id,
                    trading_session_id,
                    latest_state,
                    latest_checkpoint_id,
                    canonical_json(latest_artifact_hashes or {}),
                    consumed_event_watermark,
                    version,
                    _now(),
                ),
            )
            return version
        current_version = int(row["version"])
        if expected_version != current_version:
            raise OptimisticConcurrencyError("Stale runtime projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE current_runtime_stream_projection
            SET latest_state = ?, latest_checkpoint_id = ?, latest_artifact_hashes_json = ?,
                consumed_event_watermark = ?, version = ?, updated_timestamp = ?
            WHERE projection_id = ? AND version = ?
            """,
            (
                latest_state,
                latest_checkpoint_id,
                canonical_json(latest_artifact_hashes or {}),
                consumed_event_watermark,
                version,
                _now(),
                projection_id,
                current_version,
            ),
        )
        return version

    def upsert_account_observation_projection(
        self,
        *,
        broker_account_id: str,
        expected_version: int | None,
        latest_observation_timestamp: datetime,
        completeness: str,
        latest_account_session_observation_id: str | None = None,
        latest_funds_observation_id: str | None = None,
        latest_margin_observation_id: str | None = None,
        latest_account_read_snapshot_observation_id: str | None = None,
    ) -> int:
        row = self.connection.execute(
            "SELECT version FROM broker_account_observation_projection WHERE broker_account_id = ?",
            (broker_account_id,),
        ).fetchone()
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Account projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO broker_account_observation_projection(
                    broker_account_id, latest_account_session_observation_id, latest_funds_observation_id,
                    latest_margin_observation_id, latest_account_read_snapshot_observation_id, latest_observation_timestamp,
                    completeness, version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    broker_account_id,
                    latest_account_session_observation_id,
                    latest_funds_observation_id,
                    latest_margin_observation_id,
                    latest_account_read_snapshot_observation_id,
                    latest_observation_timestamp.isoformat(),
                    completeness,
                    version,
                    _now(),
                ),
            )
            return version
        current_version = int(row["version"])
        if expected_version != current_version:
            raise OptimisticConcurrencyError("Stale account projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE broker_account_observation_projection
            SET latest_account_session_observation_id = ?, latest_funds_observation_id = ?,
                latest_margin_observation_id = ?, latest_account_read_snapshot_observation_id = ?,
                latest_observation_timestamp = ?, completeness = ?, version = ?, updated_timestamp = ?
            WHERE broker_account_id = ? AND version = ?
            """,
            (
                latest_account_session_observation_id,
                latest_funds_observation_id,
                latest_margin_observation_id,
                latest_account_read_snapshot_observation_id,
                latest_observation_timestamp.isoformat(),
                completeness,
                version,
                _now(),
                broker_account_id,
                current_version,
            ),
        )
        return version

    def upsert_order_observation_projection(
        self,
        *,
        projection_id: str,
        broker_account_id: str,
        broker_order_id: str,
        latest_normalized_order_state: str,
        cumulative_filled_quantity: int,
        expected_version: int | None,
        latest_event_id: str | None = None,
        latest_snapshot_observation_id: str | None = None,
    ) -> int:
        row = self.connection.execute(
            "SELECT version FROM broker_order_observation_projection WHERE projection_id = ?",
            (projection_id,),
        ).fetchone()
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Order projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO broker_order_observation_projection(
                    projection_id, broker_account_id, broker_order_id, latest_normalized_order_state,
                    cumulative_filled_quantity, latest_event_id, latest_snapshot_observation_id, version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (projection_id, broker_account_id, broker_order_id, latest_normalized_order_state, cumulative_filled_quantity, latest_event_id, latest_snapshot_observation_id, version, _now()),
            )
            return version
        current_version = int(row["version"])
        if expected_version != current_version:
            raise OptimisticConcurrencyError("Stale order projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE broker_order_observation_projection
            SET latest_normalized_order_state = ?, cumulative_filled_quantity = ?, latest_event_id = ?,
                latest_snapshot_observation_id = ?, version = ?, updated_timestamp = ?
            WHERE projection_id = ? AND version = ?
            """,
            (latest_normalized_order_state, cumulative_filled_quantity, latest_event_id, latest_snapshot_observation_id, version, _now(), projection_id, current_version),
        )
        return version

    def upsert_position_observation_projection(
        self,
        *,
        projection_id: str,
        broker_account_id: str,
        normalized_contract: str,
        latest_quantity: int,
        latest_prices: Mapping[str, Any],
        latest_pnl: Mapping[str, Any],
        expected_version: int | None,
        latest_snapshot_observation_id: str | None = None,
    ) -> int:
        row = self.connection.execute(
            "SELECT version FROM broker_position_observation_projection WHERE projection_id = ?",
            (projection_id,),
        ).fetchone()
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Position projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO broker_position_observation_projection(
                    projection_id, broker_account_id, normalized_contract, latest_quantity, latest_prices_json,
                    latest_pnl_json, latest_snapshot_observation_id, version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (projection_id, broker_account_id, normalized_contract, latest_quantity, canonical_json(latest_prices), canonical_json(latest_pnl), latest_snapshot_observation_id, version, _now()),
            )
            return version
        current_version = int(row["version"])
        if expected_version != current_version:
            raise OptimisticConcurrencyError("Stale position projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE broker_position_observation_projection
            SET latest_quantity = ?, latest_prices_json = ?, latest_pnl_json = ?, latest_snapshot_observation_id = ?,
                version = ?, updated_timestamp = ?
            WHERE projection_id = ? AND version = ?
            """,
            (latest_quantity, canonical_json(latest_prices), canonical_json(latest_pnl), latest_snapshot_observation_id, version, _now(), projection_id, current_version),
        )
        return version

    def reserve_idempotency(
        self,
        *,
        reservation_id: str,
        scope: str,
        idempotency_key: str,
        request_payload: Mapping[str, Any],
    ) -> str:
        request_hash = canonical_hash(request_payload)
        row = self.connection.execute(
            "SELECT reservation_id, request_hash, status FROM idempotency_reservations WHERE scope = ? AND idempotency_key = ?",
            (scope, idempotency_key),
        ).fetchone()
        if row:
            if row["request_hash"] == request_hash:
                return str(row["reservation_id"])
            self.connection.execute(
                "UPDATE idempotency_reservations SET status = ? WHERE reservation_id = ?",
                (IdempotencyReservationStatus.CONFLICT.value, row["reservation_id"]),
            )
            raise IdempotencyConflictError(f"Idempotency reservation conflict: {scope}/{idempotency_key}")
        self.connection.execute(
            """
            INSERT INTO idempotency_reservations(reservation_id, scope, idempotency_key, request_hash, status, created_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (reservation_id, scope, idempotency_key, request_hash, IdempotencyReservationStatus.RESERVED.value, _now()),
        )
        return reservation_id

    def complete_idempotency(self, *, reservation_id: str, result_reference: str) -> None:
        self.connection.execute(
            "UPDATE idempotency_reservations SET status = ?, completed_timestamp = ?, result_reference = ? WHERE reservation_id = ?",
            (IdempotencyReservationStatus.COMMITTED.value, _now(), result_reference, reservation_id),
        )

    def put_execution_intent_reservation(
        self,
        *,
        reservation_id: str,
        proposed_execution_intent_id: str,
        broker_account_id: str,
        strategy_instance_id: str,
        source_artifact_id: str,
        idempotency_key: str,
        request_payload: Mapping[str, Any],
        status: str = "RESERVED_OFFLINE",
        position_cycle_id: str | None = None,
    ) -> str:
        if status not in {"RESERVED_OFFLINE", "CANCELLED_OFFLINE", "CONFLICT", "EXPIRED_OFFLINE"}:
            raise ValueError("Phase 4C execution-intent reservation status is not allowed.")
        self.connection.execute(
            """
            INSERT INTO execution_intent_reservations(
                reservation_id, proposed_execution_intent_id, broker_account_id, strategy_instance_id,
                position_cycle_id, source_artifact_id, idempotency_key, request_hash, status, authority_mode,
                created_timestamp, updated_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(reservation_id) DO NOTHING
            """,
            (
                reservation_id,
                proposed_execution_intent_id,
                broker_account_id,
                strategy_instance_id,
                position_cycle_id,
                source_artifact_id,
                idempotency_key,
                canonical_hash(request_payload),
                status,
                PersistenceAuthorityMode.OBSERVATIONAL_OR_OFFLINE_ONLY.value,
                _now(),
                _now(),
            ),
        )
        return reservation_id

    def put_runtime_checkpoint(
        self,
        *,
        checkpoint_id: str,
        stream_identity: str,
        session_source_id: str,
        source_offset: int,
        current_state: str,
        consumed_event_ids: tuple[str, ...],
        snapshot_hashes: Mapping[str, Any],
        artifact_hashes: Mapping[str, Any],
        configuration_hash: str,
        rule_matrix_version: str,
    ) -> str:
        payload = {
            "checkpoint_id": checkpoint_id,
            "stream_identity": stream_identity,
            "session_source_id": session_source_id,
            "source_offset": source_offset,
            "current_state": current_state,
            "consumed_event_ids": consumed_event_ids,
            "snapshot_hashes": snapshot_hashes,
            "artifact_hashes": artifact_hashes,
            "configuration_hash": configuration_hash,
            "rule_matrix_version": rule_matrix_version,
        }
        checkpoint_hash = canonical_hash(payload)
        self.connection.execute(
            """
            INSERT INTO runtime_checkpoints(
                checkpoint_id, stream_identity, session_source_id, source_offset, current_state,
                consumed_event_ids_json, snapshot_hashes_json, artifact_hashes_json, configuration_hash,
                rule_matrix_version, checkpoint_hash, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(checkpoint_id) DO NOTHING
            """,
            (
                checkpoint_id,
                stream_identity,
                session_source_id,
                source_offset,
                current_state,
                canonical_json(consumed_event_ids),
                canonical_json(snapshot_hashes),
                canonical_json(artifact_hashes),
                configuration_hash,
                rule_matrix_version,
                checkpoint_hash,
                canonical_json(payload),
                _now(),
            ),
        )
        return checkpoint_id

    def put_local_schema_boundary_rows(self, *, broker_account_id: str, strategy_instance_id: str, source_artifact_id: str) -> None:
        self.put_execution_intent_reservation(
            reservation_id="eir-fixture-1",
            proposed_execution_intent_id="future-intent-1",
            broker_account_id=broker_account_id,
            strategy_instance_id=strategy_instance_id,
            source_artifact_id=source_artifact_id,
            idempotency_key="future-intent-key",
            request_payload={"source_artifact_id": source_artifact_id},
        )
        self.connection.execute(
            """
            INSERT INTO local_client_orders(client_order_id, execution_intent_reservation_id, broker_account_id, order_purpose, status, quantity, fill_quantity, protection_generation, truth_kind, authority_mode, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_order_id) DO NOTHING
            """,
            (
                "client-order-schema-boundary",
                "eir-fixture-1",
                broker_account_id,
                "ENTRY_PROTECTION_BOUNDARY",
                "OBSERVATIONAL_SCHEMA_ONLY",
                75,
                0,
                0,
                PersistenceTruthKind.LOCAL_EXPECTED_STATE.value,
                PersistenceAuthorityMode.OBSERVATIONAL_OR_OFFLINE_ONLY.value,
                1,
            ),
        )

    def count(self, table: str) -> int:
        return int(self.connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()
