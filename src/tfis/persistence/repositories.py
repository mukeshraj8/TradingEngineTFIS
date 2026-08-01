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
        "RiskValidationResult",
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
        "RECONCILIATION_COMPLETED",
        "EXECUTION_INTENT_VALIDATED",
        "INTERNAL_PAPER_ORDER_SIMULATED",
        "INTERNAL_PAPER_POSITION_UPDATED",
        "INTERNAL_PAPER_ACCOUNTING_BUILT",
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
        if status not in {
            "RESERVED_OFFLINE",
            "VALIDATION_PENDING",
            "VALIDATED_NOT_SUBMITTABLE",
            "REJECTED",
            "BLOCKED",
            "DUPLICATE",
            "EXPIRED",
            "CANCELLED_OFFLINE",
            "CONFLICT",
            "EXPIRED_OFFLINE",
        }:
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

    def put_validated_execution_intent(
        self,
        *,
        intent: object,
        validation_result: object,
        expected_projection_version: int | None,
    ) -> str:
        intent_dict = intent.to_dict()  # type: ignore[attr-defined]
        result_dict = validation_result.to_dict()  # type: ignore[attr-defined]
        reservation_id = f"eir:{intent_dict['execution_intent_id']}"
        request_hash = canonical_hash(intent_dict)
        reservation = self.connection.execute(
            "SELECT request_hash, status FROM execution_intent_reservations WHERE reservation_id = ?",
            (reservation_id,),
        ).fetchone()
        if reservation:
            if reservation["request_hash"] != request_hash:
                self.connection.execute(
                    "UPDATE execution_intent_reservations SET status = ?, updated_timestamp = ? WHERE reservation_id = ?",
                    ("CONFLICT", _now(), reservation_id),
                )
                raise IdempotencyConflictError(f"Intent reservation conflict: {reservation_id}")
        else:
            self.put_execution_intent_reservation(
                reservation_id=reservation_id,
                proposed_execution_intent_id=intent_dict["execution_intent_id"],
                broker_account_id=intent_dict["broker_account_id"],
                strategy_instance_id=intent_dict["strategy_instance_id"],
                position_cycle_id=intent_dict["position_cycle_id"],
                source_artifact_id=intent_dict["source_artifact_id"],
                idempotency_key=intent_dict["idempotency_key"],
                request_payload=intent_dict,
                status="VALIDATION_PENDING",
            )
        row = self.connection.execute(
            "SELECT intent_hash FROM execution_intents WHERE execution_intent_id = ?",
            (intent_dict["execution_intent_id"],),
        ).fetchone()
        if row:
            if row["intent_hash"] != intent_dict["intent_hash"]:
                raise ArtifactConflictError(f"Intent identity conflict: {intent_dict['execution_intent_id']}")
        else:
            self.connection.execute(
                """
                INSERT INTO execution_intents(
                    execution_intent_id, reservation_id, broker_account_id, strategy_instance_id, position_cycle_id,
                    source_artifact_id, idempotency_key, intent_hash, purpose, authority_mode, payload_json, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    intent_dict["execution_intent_id"],
                    reservation_id,
                    intent_dict["broker_account_id"],
                    intent_dict["strategy_instance_id"],
                    intent_dict["position_cycle_id"],
                    intent_dict["source_artifact_id"],
                    intent_dict["idempotency_key"],
                    intent_dict["intent_hash"],
                    intent_dict["action"]["purpose"],
                    intent_dict["evidence"]["authority_mode"],
                    canonical_json(intent_dict),
                    _now(),
                ),
            )
        existing_result = self.connection.execute(
            "SELECT result_hash FROM intent_validation_results WHERE validation_id = ?",
            (result_dict["validation_id"],),
        ).fetchone()
        if existing_result:
            if existing_result["result_hash"] == result_dict["result_hash"]:
                return str(result_dict["validation_id"])
            raise ArtifactConflictError(f"Validation identity conflict: {result_dict['validation_id']}")
        self.connection.execute(
            """
            INSERT INTO intent_validation_results(
                validation_id, execution_intent_id, intent_hash, decision, result_hash, authority_mode,
                payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result_dict["validation_id"],
                intent_dict["execution_intent_id"],
                result_dict["intent_hash"],
                result_dict["decision"],
                result_dict["result_hash"],
                result_dict["authority_mode"],
                canonical_json(result_dict),
                _now(),
            ),
        )
        for check in result_dict["checks"]:
            self.connection.execute(
                """
                INSERT INTO intent_validation_checks(validation_id, check_id, scope, result, severity, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result_dict["validation_id"],
                    check["check_id"],
                    check["scope"],
                    check["result"],
                    check["severity"],
                    canonical_json(check),
                ),
            )
        self.connection.execute(
            "UPDATE execution_intent_reservations SET status = ?, updated_timestamp = ? WHERE reservation_id = ?",
            (result_dict["decision"], _now(), reservation_id),
        )
        self._upsert_intent_validation_projection(
            intent_dict=intent_dict,
            result_dict=result_dict,
            expected_version=expected_projection_version,
        )
        self.append_event(
            event_id=f"{result_dict['validation_id']}:event",
            event_type="EXECUTION_INTENT_VALIDATED",
            aggregate_type="execution_intent",
            aggregate_id=intent_dict["execution_intent_id"],
            trading_session_id=intent_dict["trading_session_id"],
            broker_account_id=intent_dict["broker_account_id"],
            effective_timestamp=datetime.fromisoformat(intent_dict["action"]["authorized_not_before"]),
            payload={
                "execution_intent_id": intent_dict["execution_intent_id"],
                "intent_hash": intent_dict["intent_hash"],
                "validation_id": result_dict["validation_id"],
                "result_hash": result_dict["result_hash"],
                "decision": result_dict["decision"],
            },
            idempotency_scope="execution_intent_validation",
            idempotency_key=result_dict["validation_id"],
        )
        return str(result_dict["validation_id"])

    def _upsert_intent_validation_projection(
        self,
        *,
        intent_dict: Mapping[str, Any],
        result_dict: Mapping[str, Any],
        expected_version: int | None,
    ) -> int:
        projection_id = f"{intent_dict['broker_account_id']}|{intent_dict['strategy_instance_id']}|{intent_dict['execution_intent_id']}"
        row = self.connection.execute(
            "SELECT version FROM latest_intent_validation_projection WHERE projection_id = ?",
            (projection_id,),
        ).fetchone()
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Intent validation projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO latest_intent_validation_projection(
                    projection_id, broker_account_id, strategy_instance_id, position_cycle_id, execution_intent_id,
                    intent_hash, latest_validation_id, latest_result_hash, decision, purpose, version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection_id,
                    intent_dict["broker_account_id"],
                    intent_dict["strategy_instance_id"],
                    intent_dict["position_cycle_id"],
                    intent_dict["execution_intent_id"],
                    intent_dict["intent_hash"],
                    result_dict["validation_id"],
                    result_dict["result_hash"],
                    result_dict["decision"],
                    intent_dict["action"]["purpose"],
                    version,
                    _now(),
                ),
            )
            return version
        current_version = int(row["version"])
        if expected_version != current_version:
            raise OptimisticConcurrencyError("Stale intent validation projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE latest_intent_validation_projection
            SET latest_validation_id = ?, latest_result_hash = ?, decision = ?, version = ?, updated_timestamp = ?
            WHERE projection_id = ? AND version = ?
            """,
            (result_dict["validation_id"], result_dict["result_hash"], result_dict["decision"], version, _now(), projection_id, current_version),
        )
        return version

    def put_internal_paper_authority_grant(self, *, grant: object) -> str:
        grant_dict = grant.to_dict()  # type: ignore[attr-defined]
        row = self.connection.execute(
            "SELECT grant_hash FROM internal_paper_authority_grants WHERE grant_id = ?",
            (grant_dict["grant_id"],),
        ).fetchone()
        if row:
            if row["grant_hash"] == grant_dict["grant_hash"]:
                return str(grant_dict["grant_id"])
            raise ArtifactConflictError(f"Internal paper grant conflict: {grant_dict['grant_id']}")
        self.connection.execute(
            """
            INSERT INTO internal_paper_authority_grants(
                grant_id, broker_account_id, trading_session_id, strategy_instance_id, grant_hash, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                grant_dict["grant_id"],
                grant_dict["broker_account_id"],
                grant_dict["trading_session_id"],
                grant_dict["strategy_instance_id"],
                grant_dict["grant_hash"],
                canonical_json(grant_dict),
                _now(),
            ),
        )
        return str(grant_dict["grant_id"])

    def put_internal_paper_result(
        self,
        *,
        grant: object,
        result: object,
        expected_account_projection_version: int | None,
    ) -> str:
        result_dict = result.to_dict()  # type: ignore[attr-defined]
        grant_id = self.put_internal_paper_authority_grant(grant=grant)
        order = result_dict["client_order"]
        order_row = self.connection.execute(
            "SELECT order_hash FROM internal_client_order_records WHERE client_order_id = ?",
            (order["client_order_id"],),
        ).fetchone()
        if order_row:
            if order_row["order_hash"] != order["order_hash"]:
                raise ArtifactConflictError(f"Internal client order conflict: {order['client_order_id']}")
        else:
            self.connection.execute(
                """
                INSERT INTO internal_client_order_records(
                    client_order_id, execution_intent_id, account_coordinator_id, broker_account_id,
                    strategy_instance_id, trading_session_id, position_cycle_id, idempotency_key,
                    order_hash, order_purpose, current_state, authority_source, payload_json,
                    created_timestamp, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["client_order_id"],
                    order["execution_intent_id"],
                    order["account_coordinator_id"],
                    order["broker_account_id"],
                    order["strategy_instance_id"],
                    order["trading_session_id"],
                    order["position_cycle_id"],
                    order["idempotency_key"],
                    order["order_hash"],
                    order["order_purpose"],
                    "CREATED",
                    "INTERNAL_PAPER_SIMULATION",
                    canonical_json(order),
                    _now(),
                    _now(),
                ),
            )
        for event in result_dict["events"]:
            self._put_internal_paper_event(event)
        for fill in result_dict["fills"]:
            self._put_internal_paper_fill(fill)
        latest_event = result_dict["events"][-1] if result_dict["events"] else None
        cumulative = int(latest_event["cumulative_filled_quantity"]) if latest_event else 0
        final_state = result_dict["final_state"]
        self.connection.execute(
            "UPDATE internal_client_order_records SET current_state = ?, updated_timestamp = ? WHERE client_order_id = ?",
            (final_state, _now(), order["client_order_id"]),
        )
        self._upsert_internal_client_order_projection(
            client_order_id=order["client_order_id"],
            broker_account_id=order["broker_account_id"],
            current_state=final_state,
            cumulative_filled_quantity=cumulative,
            latest_event_id=latest_event["event_id"] if latest_event else None,
            order_hash=order["order_hash"],
        )
        self._upsert_internal_paper_account_projection(
            account_coordinator_id=order["account_coordinator_id"],
            broker_account_id=order["broker_account_id"],
            trading_session_id=order["trading_session_id"],
            snapshot=result_dict["account_snapshot"],
            expected_version=expected_account_projection_version,
        )
        self.append_event(
            event_id=f"{result_dict['result_hash']}:event",
            event_type="INTERNAL_PAPER_ORDER_SIMULATED",
            aggregate_type="internal_paper_order",
            aggregate_id=order["client_order_id"],
            trading_session_id=order["trading_session_id"],
            broker_account_id=order["broker_account_id"],
            effective_timestamp=datetime.fromisoformat(order["authorized_time"]),
            payload={"client_order_id": order["client_order_id"], "result_hash": result_dict["result_hash"], "grant_id": grant_id},
            idempotency_scope="internal_paper_order",
            idempotency_key=result_dict["result_hash"],
        )
        return str(order["client_order_id"])

    def _put_internal_paper_event(self, event: Mapping[str, Any]) -> None:
        row = self.connection.execute(
            "SELECT event_hash FROM internal_paper_order_events WHERE event_id = ?",
            (event["event_id"],),
        ).fetchone()
        if row:
            if row["event_hash"] == event["event_hash"]:
                return
            raise IdempotencyConflictError(f"Internal paper event conflict: {event['event_id']}")
        self.connection.execute(
            """
            INSERT INTO internal_paper_order_events(
                event_id, client_order_id, broker_account_id, sequence_number, previous_state, new_state,
                event_type, event_hash, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["client_order_id"],
                event["broker_account_id"],
                event["sequence"],
                event["previous_state"],
                event["new_state"],
                event["event_type"],
                event["event_hash"],
                canonical_json(event),
                _now(),
            ),
        )

    def _put_internal_paper_fill(self, fill: Mapping[str, Any]) -> None:
        row = self.connection.execute(
            "SELECT fill_hash FROM internal_paper_fills WHERE internal_fill_id = ?",
            (fill["internal_fill_id"],),
        ).fetchone()
        if row:
            if row["fill_hash"] == fill["fill_hash"]:
                return
            raise IdempotencyConflictError(f"Internal paper fill conflict: {fill['internal_fill_id']}")
        self.connection.execute(
            """
            INSERT INTO internal_paper_fills(
                internal_fill_id, client_order_id, broker_account_id, strategy_instance_id,
                position_cycle_id, fill_hash, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fill["internal_fill_id"],
                fill["client_order_id"],
                fill["broker_account_id"],
                fill["strategy_instance_id"],
                fill["position_cycle_id"],
                fill["fill_hash"],
                canonical_json(fill),
                _now(),
            ),
        )

    def _upsert_internal_client_order_projection(
        self,
        *,
        client_order_id: str,
        broker_account_id: str,
        current_state: str,
        cumulative_filled_quantity: int,
        latest_event_id: str | None,
        order_hash: str,
    ) -> None:
        row = self.connection.execute(
            "SELECT version FROM latest_internal_client_order_projection WHERE client_order_id = ?",
            (client_order_id,),
        ).fetchone()
        if row is None:
            self.connection.execute(
                """
                INSERT INTO latest_internal_client_order_projection(
                    client_order_id, broker_account_id, current_state, cumulative_filled_quantity,
                    latest_event_id, order_hash, version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (client_order_id, broker_account_id, current_state, cumulative_filled_quantity, latest_event_id, order_hash, 1, _now()),
            )
            return
        version = int(row["version"]) + 1
        self.connection.execute(
            """
            UPDATE latest_internal_client_order_projection
            SET current_state = ?, cumulative_filled_quantity = ?, latest_event_id = ?, version = ?, updated_timestamp = ?
            WHERE client_order_id = ?
            """,
            (current_state, cumulative_filled_quantity, latest_event_id, version, _now(), client_order_id),
        )

    def _upsert_internal_paper_account_projection(
        self,
        *,
        account_coordinator_id: str,
        broker_account_id: str,
        trading_session_id: str,
        snapshot: Mapping[str, Any],
        expected_version: int | None,
    ) -> int:
        projection_id = f"{broker_account_id}|{trading_session_id}|{account_coordinator_id}"
        row = self.connection.execute(
            "SELECT version FROM internal_paper_account_projections WHERE projection_id = ?",
            (projection_id,),
        ).fetchone()
        snapshot_hash = canonical_hash(snapshot)
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Internal paper account projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO internal_paper_account_projections(
                    projection_id, broker_account_id, trading_session_id, account_coordinator_id,
                    latest_snapshot_hash, active_order_count, available_paper_margin, payload_json,
                    version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection_id,
                    broker_account_id,
                    trading_session_id,
                    account_coordinator_id,
                    snapshot_hash,
                    snapshot["active_order_count"],
                    snapshot["available_paper_margin"],
                    canonical_json(snapshot),
                    version,
                    _now(),
                ),
            )
            return version
        current_version = int(row["version"])
        if expected_version is not None and expected_version != current_version:
            raise OptimisticConcurrencyError("Stale internal paper account projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE internal_paper_account_projections
            SET latest_snapshot_hash = ?, active_order_count = ?, available_paper_margin = ?,
                payload_json = ?, version = ?, updated_timestamp = ?
            WHERE projection_id = ?
            """,
            (snapshot_hash, snapshot["active_order_count"], snapshot["available_paper_margin"], canonical_json(snapshot), version, _now(), projection_id),
        )
        return version

    def put_internal_position_transition(
        self,
        *,
        transition: Mapping[str, Any],
        expected_projection_version: int | None,
    ) -> str:
        projection = transition["projection"]
        identity = projection["identity"]
        event = transition["event"]
        position_cycle_id = str(identity["position_cycle_id"])
        for requirement in transition.get("requirements", []):
            self._put_internal_lifecycle_requirement(requirement)
        self._put_internal_position_event(event)
        for fill_id in projection.get("entry_fill_ids", []):
            self._put_internal_position_fill_link(
                position_cycle_id=position_cycle_id,
                internal_fill_id=str(fill_id),
                client_order_id=str(event.get("source_client_order_id") or ""),
                fill_role="ENTRY",
                payload={"position_cycle_id": position_cycle_id, "internal_fill_id": fill_id, "fill_role": "ENTRY"},
            )
        for fill_id in projection.get("exit_fill_ids", []):
            self._put_internal_position_fill_link(
                position_cycle_id=position_cycle_id,
                internal_fill_id=str(fill_id),
                client_order_id=str(event.get("source_client_order_id") or ""),
                fill_role="EXIT",
                payload={"position_cycle_id": position_cycle_id, "internal_fill_id": fill_id, "fill_role": "EXIT"},
            )
        version = self._upsert_internal_position_projection(
            projection=projection,
            expected_version=expected_projection_version,
        )
        if projection.get("next_trading_session_id"):
            self.connection.execute(
                """
                INSERT INTO internal_position_recovery_refs(
                    recovery_ref_id, position_cycle_id, next_trading_session_id, carry_event_id, payload_json, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(recovery_ref_id) DO NOTHING
                """,
                (
                    f"{position_cycle_id}:{projection['next_trading_session_id']}:recovery",
                    position_cycle_id,
                    projection["next_trading_session_id"],
                    event["event_id"],
                    canonical_json({"position_cycle_id": position_cycle_id, "projection_version": version}),
                    _now(),
                ),
            )
        self.append_event(
            event_id=f"{event['event_id']}:operational",
            event_type="INTERNAL_PAPER_POSITION_UPDATED",
            aggregate_type="internal_paper_position",
            aggregate_id=position_cycle_id,
            trading_session_id=identity["trading_session_id"],
            broker_account_id=identity["broker_account_id"],
            effective_timestamp=datetime.fromisoformat(event["event_timestamp"]),
            payload={"position_cycle_id": position_cycle_id, "event_id": event["event_id"], "projection_hash": projection["projection_hash"]},
            idempotency_scope="internal_paper_position",
            idempotency_key=event["event_hash"],
        )
        return position_cycle_id

    def _put_internal_position_event(self, event: Mapping[str, Any]) -> None:
        row = self.connection.execute(
            "SELECT event_hash FROM internal_position_events WHERE event_id = ?",
            (event["event_id"],),
        ).fetchone()
        if row:
            if row["event_hash"] == event["event_hash"]:
                return
            raise IdempotencyConflictError(f"Internal position event conflict: {event['event_id']}")
        self.connection.execute(
            """
            INSERT INTO internal_position_events(
                event_id, position_cycle_id, event_sequence, event_type, prior_state, new_state,
                event_hash, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["position_cycle_id"],
                event["event_sequence"],
                event["event_type"],
                event["prior_state"],
                event["new_state"],
                event["event_hash"],
                canonical_json(event),
                _now(),
            ),
        )

    def _put_internal_position_fill_link(
        self,
        *,
        position_cycle_id: str,
        internal_fill_id: str,
        client_order_id: str,
        fill_role: str,
        payload: Mapping[str, Any],
    ) -> None:
        if not internal_fill_id:
            return
        fill_row = self.connection.execute(
            "SELECT internal_fill_id FROM internal_paper_fills WHERE internal_fill_id = ?",
            (internal_fill_id,),
        ).fetchone()
        if fill_row is None:
            return
        link_id = f"{position_cycle_id}:{internal_fill_id}:{fill_role}"
        link_hash = canonical_hash(payload)
        row = self.connection.execute(
            "SELECT link_hash FROM internal_position_fill_links WHERE link_id = ?",
            (link_id,),
        ).fetchone()
        if row:
            if row["link_hash"] == link_hash:
                return
            raise IdempotencyConflictError(f"Internal position fill-link conflict: {link_id}")
        self.connection.execute(
            """
            INSERT INTO internal_position_fill_links(
                link_id, position_cycle_id, internal_fill_id, client_order_id, fill_role,
                link_hash, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (link_id, position_cycle_id, internal_fill_id, client_order_id, fill_role, link_hash, canonical_json(payload), _now()),
        )

    def _put_internal_lifecycle_requirement(self, requirement: Mapping[str, Any]) -> None:
        row = self.connection.execute(
            "SELECT requirement_hash FROM internal_lifecycle_requirements WHERE requirement_id = ?",
            (requirement["requirement_id"],),
        ).fetchone()
        if row:
            if row["requirement_hash"] == requirement["requirement_hash"]:
                return
            raise IdempotencyConflictError(f"Internal lifecycle requirement conflict: {requirement['requirement_id']}")
        self.connection.execute(
            """
            INSERT INTO internal_lifecycle_requirements(
                requirement_id, position_cycle_id, requirement_type, protection_generation,
                requirement_hash, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                requirement["requirement_id"],
                requirement["position_cycle_id"],
                requirement["requirement_type"],
                requirement["protection_generation"],
                requirement["requirement_hash"],
                canonical_json(requirement),
                _now(),
            ),
        )

    def _upsert_internal_position_projection(self, *, projection: Mapping[str, Any], expected_version: int | None) -> int:
        identity = projection["identity"]
        position_cycle_id = str(identity["position_cycle_id"])
        row = self.connection.execute(
            "SELECT version, projection_hash FROM internal_position_cycle_projections WHERE position_cycle_id = ?",
            (position_cycle_id,),
        ).fetchone()
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Internal position projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO internal_position_cycle_projections(
                    position_cycle_id, broker_account_id, trading_session_id, strategy_instance_id,
                    lifecycle_state, confirmed_entry_quantity, remaining_quantity, realized_quantity,
                    projection_hash, payload_json, authority_source, version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position_cycle_id,
                    identity["broker_account_id"],
                    identity["trading_session_id"],
                    identity["strategy_instance_id"],
                    projection["lifecycle_state"],
                    projection["confirmed_entry_quantity"],
                    projection["remaining_quantity"],
                    projection["realized_quantity"],
                    projection["projection_hash"],
                    canonical_json(projection),
                    "INTERNAL_PAPER_ONLY",
                    version,
                    _now(),
                ),
            )
            return version
        current_version = int(row["version"])
        if row["projection_hash"] == projection["projection_hash"]:
            return current_version
        if expected_version is not None and expected_version != current_version:
            raise OptimisticConcurrencyError("Stale internal position projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE internal_position_cycle_projections
            SET lifecycle_state = ?, confirmed_entry_quantity = ?, remaining_quantity = ?,
                realized_quantity = ?, projection_hash = ?, payload_json = ?, version = ?,
                updated_timestamp = ?
            WHERE position_cycle_id = ? AND version = ?
            """,
            (
                projection["lifecycle_state"],
                projection["confirmed_entry_quantity"],
                projection["remaining_quantity"],
                projection["realized_quantity"],
                projection["projection_hash"],
                canonical_json(projection),
                version,
                _now(),
                position_cycle_id,
                current_version,
            ),
        )
        return version

    def put_accounting_build_result(
        self,
        *,
        build_result: Mapping[str, Any],
        expected_projection_version: int | None,
    ) -> str:
        trade_fact = build_result["trade_fact"]
        trade_fact_id = str(trade_fact["trade_fact_id"])
        row = self.connection.execute(
            "SELECT fact_hash FROM accounting_trade_facts WHERE trade_fact_id = ?",
            (trade_fact_id,),
        ).fetchone()
        if row:
            if row["fact_hash"] != trade_fact["fact_hash"]:
                raise ArtifactConflictError(f"TradeFact conflict: {trade_fact_id}")
        else:
            self.connection.execute(
                """
                INSERT INTO accounting_trade_facts(
                    trade_fact_id, trade_id, position_cycle_id, trading_session_id,
                    strategy_instance_id, logical_account, state, fact_hash,
                    supersedes_trade_fact_id, payload_json, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_fact_id,
                    trade_fact["trade_id"],
                    trade_fact["position_cycle_id"],
                    trade_fact["trading_session_id"],
                    trade_fact["strategy_instance"],
                    trade_fact["logical_paper_account"],
                    trade_fact["state"],
                    trade_fact["fact_hash"],
                    trade_fact.get("supersedes_trade_fact_id"),
                    canonical_json(trade_fact),
                    _now(),
                ),
            )
        for source_id in trade_fact["provenance"].get("source_fill_ids", []):
            self._put_accounting_source_link(
                fact_id=trade_fact_id,
                source_type="InternalPaperFill",
                source_id=str(source_id),
                payload={"trade_fact_id": trade_fact_id, "source_fill_id": source_id},
            )
        for source_id in trade_fact["provenance"].get("source_lifecycle_requirement_ids", []):
            self._put_accounting_source_link(
                fact_id=trade_fact_id,
                source_type="LifecycleRequirement",
                source_id=str(source_id),
                payload={"trade_fact_id": trade_fact_id, "source_lifecycle_requirement_id": source_id},
            )
        for pnl_fact in build_result.get("pnl_facts", []):
            self._put_pnl_fact(trade_fact_id=trade_fact_id, pnl_fact=pnl_fact)
        for projection in build_result.get("projections", []):
            self._upsert_accounting_projection(projection=projection, expected_version=expected_projection_version)
        event_id = f"{build_result['result_hash']}:accounting-event"
        self.connection.execute(
            """
            INSERT INTO accounting_build_events(
                build_event_id, result_hash, trade_fact_id, event_type, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(build_event_id) DO NOTHING
            """,
            (
                event_id,
                build_result["result_hash"],
                trade_fact_id,
                "INTERNAL_PAPER_ACCOUNTING_BUILT",
                canonical_json({"trade_fact_id": trade_fact_id, "result_hash": build_result["result_hash"]}),
                _now(),
            ),
        )
        self.append_event(
            event_id=f"{event_id}:operational",
            event_type="INTERNAL_PAPER_ACCOUNTING_BUILT",
            aggregate_type="internal_paper_accounting",
            aggregate_id=trade_fact_id,
            trading_session_id=None,
            broker_account_id=None,
            effective_timestamp=datetime.fromisoformat(str(trade_fact["execution"]["first_entry_timestamp"])),
            payload={"trade_fact_id": trade_fact_id, "result_hash": build_result["result_hash"]},
            idempotency_scope="internal_paper_accounting",
            idempotency_key=build_result["result_hash"],
        )
        return trade_fact_id

    def _put_pnl_fact(self, *, trade_fact_id: str, pnl_fact: Mapping[str, Any]) -> None:
        row = self.connection.execute(
            "SELECT fact_hash FROM accounting_pnl_facts WHERE pnl_fact_id = ?",
            (pnl_fact["pnl_fact_id"],),
        ).fetchone()
        if row:
            if row["fact_hash"] == pnl_fact["fact_hash"]:
                return
            raise ArtifactConflictError(f"PnLFact conflict: {pnl_fact['pnl_fact_id']}")
        self.connection.execute(
            """
            INSERT INTO accounting_pnl_facts(
                pnl_fact_id, trade_fact_id, fact_type, trading_date, account_id,
                strategy_instance_id, gross_pnl, charges, net_pnl, quality_state,
                fact_hash, supersedes_pnl_fact_id, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pnl_fact["pnl_fact_id"],
                trade_fact_id,
                pnl_fact["fact_type"],
                pnl_fact["trading_date"],
                pnl_fact["account"],
                pnl_fact["strategy"],
                pnl_fact["gross_pnl"],
                pnl_fact["charges"],
                pnl_fact["net_pnl"],
                pnl_fact["quality_state"],
                pnl_fact["fact_hash"],
                pnl_fact.get("supersedes_pnl_fact_id"),
                canonical_json(pnl_fact),
                _now(),
            ),
        )
        if pnl_fact.get("supersedes_pnl_fact_id"):
            self.connection.execute(
                """
                INSERT INTO accounting_correction_links(
                    correction_id, new_fact_id, superseded_fact_id, correction_reason, payload_json, created_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(correction_id) DO NOTHING
                """,
                (
                    f"{pnl_fact['pnl_fact_id']}:supersedes:{pnl_fact['supersedes_pnl_fact_id']}",
                    pnl_fact["pnl_fact_id"],
                    pnl_fact["supersedes_pnl_fact_id"],
                    str(pnl_fact["source_identities"].get("supersession_reason") or "ACCOUNTING_CORRECTION"),
                    canonical_json(pnl_fact),
                    _now(),
                ),
            )

    def _put_accounting_source_link(self, *, fact_id: str, source_type: str, source_id: str, payload: Mapping[str, Any]) -> None:
        link_id = f"{fact_id}:{source_type}:{source_id}"
        self.connection.execute(
            """
            INSERT INTO accounting_fact_source_links(
                link_id, fact_id, source_type, source_id, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(link_id) DO NOTHING
            """,
            (link_id, fact_id, source_type, source_id, canonical_json(payload), _now()),
        )

    def _upsert_accounting_projection(self, *, projection: Mapping[str, Any], expected_version: int | None) -> int:
        row = self.connection.execute(
            "SELECT version, projection_hash FROM accounting_projections WHERE projection_id = ?",
            (projection["projection_id"],),
        ).fetchone()
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Accounting projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO accounting_projections(
                    projection_id, projection_type, projection_hash, watermark,
                    quality_state, payload_json, version, updated_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection["projection_id"],
                    projection["projection_type"],
                    projection["projection_hash"],
                    projection["watermark"],
                    projection["quality"],
                    canonical_json(projection),
                    version,
                    _now(),
                ),
            )
            return version
        current_version = int(row["version"])
        if row["projection_hash"] == projection["projection_hash"]:
            return current_version
        if expected_version is not None and expected_version != current_version:
            raise OptimisticConcurrencyError("Stale accounting projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE accounting_projections
            SET projection_hash = ?, watermark = ?, quality_state = ?, payload_json = ?,
                version = ?, updated_timestamp = ?
            WHERE projection_id = ? AND version = ?
            """,
            (
                projection["projection_hash"],
                projection["watermark"],
                projection["quality"],
                canonical_json(projection),
                version,
                _now(),
                projection["projection_id"],
                current_version,
            ),
        )
        return version

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

    def put_reconciliation_result(
        self,
        *,
        reconciliation_result: object,
        reconciliation_input_hash: str,
        expected_projection_version: int | None,
    ) -> str:
        result_dict = reconciliation_result.to_dict()  # type: ignore[attr-defined]
        reconciliation_id = str(result_dict["reconciliation_id"])
        row = self.connection.execute(
            "SELECT result_hash, input_hash FROM reconciliation_results WHERE reconciliation_id = ?",
            (reconciliation_id,),
        ).fetchone()
        if row:
            if row["result_hash"] == result_dict["result_hash"] and row["input_hash"] == reconciliation_input_hash:
                return reconciliation_id
            raise ArtifactConflictError(f"Reconciliation identity conflict: {reconciliation_id}")
        self.connection.execute(
            """
            INSERT INTO reconciliation_results(
                reconciliation_id, broker_account_id, trading_session_id, reconciliation_scope,
                result_hash, input_hash, status, authority_gate, payload_json, created_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reconciliation_id,
                result_dict["broker_account_id"],
                result_dict["trading_session_id"],
                result_dict["scope"],
                result_dict["result_hash"],
                reconciliation_input_hash,
                result_dict["account_status"],
                result_dict["authority_gate"]["recommendation"],
                canonical_json(result_dict),
                _now(),
            ),
        )
        for item in result_dict["items"]:
            self.connection.execute(
                "INSERT INTO reconciliation_items(item_id, reconciliation_id, item_type, classification, payload_json) VALUES (?, ?, ?, ?, ?)",
                (
                    f"{reconciliation_id}:{item['item_id']}",
                    reconciliation_id,
                    item["item_type"],
                    item["classification"],
                    canonical_json(item),
                ),
            )
        for index, recommendation in enumerate(result_dict["repair_recommendations"]):
            self.connection.execute(
                """
                INSERT INTO reconciliation_repair_recommendations(
                    recommendation_id, reconciliation_id, item_id, recommendation_code, execution_not_permitted, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{reconciliation_id}:repair:{index}",
                    reconciliation_id,
                    recommendation["item_id"],
                    recommendation["code"],
                    1 if recommendation["execution_not_permitted"] else 0,
                    canonical_json(recommendation),
                ),
            )
        projection_id = f"{result_dict['broker_account_id']}|{result_dict['trading_session_id']}|{result_dict['scope']}"
        self._upsert_reconciliation_projection(
            projection_id=projection_id,
            result_dict=result_dict,
            expected_version=expected_projection_version,
        )
        self.append_event(
            event_id=f"{reconciliation_id}:event",
            event_type="RECONCILIATION_COMPLETED",
            aggregate_type="reconciliation",
            aggregate_id=projection_id,
            trading_session_id=result_dict["trading_session_id"],
            broker_account_id=result_dict["broker_account_id"],
            effective_timestamp=datetime.fromisoformat(result_dict["as_of"]),
            payload={"reconciliation_id": reconciliation_id, "result_hash": result_dict["result_hash"]},
            idempotency_scope="reconciliation",
            idempotency_key=reconciliation_id,
        )
        return reconciliation_id

    def _upsert_reconciliation_projection(
        self,
        *,
        projection_id: str,
        result_dict: Mapping[str, Any],
        expected_version: int | None,
    ) -> int:
        row = self.connection.execute(
            "SELECT version FROM latest_reconciliation_projection WHERE projection_id = ?",
            (projection_id,),
        ).fetchone()
        blocking = result_dict["authority_gate"]["blocking_reasons"]
        if row is None:
            if expected_version not in (None, 0):
                raise OptimisticConcurrencyError("Reconciliation projection does not exist for expected version.")
            version = 1
            self.connection.execute(
                """
                INSERT INTO latest_reconciliation_projection(
                    projection_id, broker_account_id, trading_session_id, reconciliation_scope,
                    latest_result_id, latest_result_hash, status, blocking_classifications_json,
                    snapshot_watermark, local_projection_version, broker_snapshot_hash, completed_timestamp, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    projection_id,
                    result_dict["broker_account_id"],
                    result_dict["trading_session_id"],
                    result_dict["scope"],
                    result_dict["reconciliation_id"],
                    result_dict["result_hash"],
                    result_dict["authority_gate"]["recommendation"],
                    canonical_json(blocking),
                    result_dict["as_of"],
                    result_dict["local_state_version"],
                    result_dict["broker_snapshot_hash"],
                    _now(),
                    version,
                ),
            )
            return version
        current_version = int(row["version"])
        if expected_version != current_version:
            raise OptimisticConcurrencyError("Stale reconciliation projection writer.")
        version = current_version + 1
        self.connection.execute(
            """
            UPDATE latest_reconciliation_projection
            SET latest_result_id = ?, latest_result_hash = ?, status = ?, blocking_classifications_json = ?,
                snapshot_watermark = ?, local_projection_version = ?, broker_snapshot_hash = ?,
                completed_timestamp = ?, version = ?
            WHERE projection_id = ? AND version = ?
            """,
            (
                result_dict["reconciliation_id"],
                result_dict["result_hash"],
                result_dict["authority_gate"]["recommendation"],
                canonical_json(blocking),
                result_dict["as_of"],
                result_dict["local_state_version"],
                result_dict["broker_snapshot_hash"],
                _now(),
                version,
                projection_id,
                current_version,
            ),
        )
        return version

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
