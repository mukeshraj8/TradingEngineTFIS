from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from tfis.broker import BrokerReadRequest, FyersReadOnlyFixtureAdapter, build_account_read_snapshot
from tfis.persistence import (
    ArtifactConflictError,
    IdempotencyConflictError,
    OptimisticConcurrencyError,
    PersistenceDatabase,
    RecoveryStatus,
    UnitOfWork,
    apply_migrations,
    assess_recovery,
    canonical_hash,
    canonical_json,
    from_canonical_json,
    observational_compare,
    run_integrity_scan,
    validate_schema,
)
from tfis.persistence.migrations import MIGRATIONS, MigrationError
from tfis.persistence.reports import write_phase4c_reports
from tfis.persistence.serialization import SerializationError


def _db(tmp_path: Path) -> PersistenceDatabase:
    return PersistenceDatabase(tmp_path / "phase4c.sqlite")


def _seed_identities(db: PersistenceDatabase) -> tuple[str, str, str]:
    session_id = "session-2026-06-05"
    strategy_id = "S23_NIFTY_ACCOUNT_A_PAPER"
    account_id = "account-fixture"
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(
            trading_session_id=session_id,
            trading_date=date(2026, 6, 5),
            market="NSE",
            timezone_name="Asia/Kolkata",
            payload={"session_id": session_id},
        )
        repo.put_strategy_instance(
            strategy_instance_id=strategy_id,
            strategy_definition_id="S23",
            strategy_version="v1",
            configuration_hash="cfg-ok",
            payload={"strategy": "S23"},
        )
        repo.put_broker_account_identity(
            broker_account_id=account_id,
            provider="fixture",
            environment="test",
            account_hash="account-fixture-hash",
            payload={"account_id": "AC***01"},
        )
    return session_id, strategy_id, account_id


def test_clean_database_initialization_migration_idempotency_and_checksum(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with db.connect() as connection:
        apply_migrations(connection)
        apply_migrations(connection)
        assert validate_schema(connection) == 1
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        checksum = connection.execute("SELECT checksum FROM schema_migrations WHERE migration_id = 1").fetchone()[0]
        connection.execute("UPDATE schema_migrations SET checksum = 'bad' WHERE migration_id = 1")
        with pytest.raises(MigrationError):
            validate_schema(connection)
        connection.execute("UPDATE schema_migrations SET checksum = ? WHERE migration_id = 1", (checksum,))


def test_immutable_artifact_insert_idempotency_and_conflict(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _, strategy_id, _ = _seed_identities(db)
    with UnitOfWork(db) as uow:
        first = uow.repo.put_artifact(
            artifact_id="artifact-1",
            artifact_type="TFISDecision",
            schema_version="v1",
            strategy_instance_id=strategy_id,
            payload={"decision": "NO_TRADE"},
            provenance={"source": "test"},
        )
        second = uow.repo.put_artifact(
            artifact_id="artifact-1",
            artifact_type="TFISDecision",
            schema_version="v1",
            strategy_instance_id=strategy_id,
            payload={"decision": "NO_TRADE"},
            provenance={"source": "test"},
        )
        assert first == second
        with pytest.raises(ArtifactConflictError):
            uow.repo.put_artifact(
                artifact_id="artifact-1",
                artifact_type="TFISDecision",
                schema_version="v1",
                strategy_instance_id=strategy_id,
                payload={"decision": "TRADE"},
                provenance={"source": "test"},
            )


def test_broker_account_read_order_and_fill_transactions(tmp_path: Path) -> None:
    db = _db(tmp_path)
    session_id, _, account_id = _seed_identities(db)
    request_time = datetime.fromisoformat("2026-06-05T09:16:00+05:30")
    snapshot = build_account_read_snapshot(
        FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated"),
        BrokerReadRequest(as_of=request_time, trading_date=date(2026, 6, 5)),
    )
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_broker_observation(
            observation_id="obs-account",
            observation_type="broker_account_read_snapshot",
            broker_account_id=account_id,
            request_id="read-1",
            payload=snapshot.to_dict(),
            provenance={"adapter": "fixture"},
            capture_timestamp=request_time,
            completeness=snapshot.completeness.value,
        )
        repo.put_broker_observation(
            observation_id="obs-order",
            observation_type="broker_order_snapshot",
            broker_account_id=account_id,
            request_id="read-1",
            payload=snapshot.orders.to_dict(),
            provenance={"adapter": "fixture"},
            capture_timestamp=request_time,
        )
        repo.put_broker_observation(
            observation_id="obs-fill",
            observation_type="broker_fill_snapshot",
            broker_account_id=account_id,
            request_id="read-1",
            payload=snapshot.fills.to_dict(),
            provenance={"adapter": "fixture"},
            capture_timestamp=request_time,
        )
        repo.append_event(
            event_id="event-account",
            event_type="BROKER_ACCOUNT_READ_OBSERVED",
            aggregate_type="broker_account",
            aggregate_id=account_id,
            trading_session_id=session_id,
            broker_account_id=account_id,
            effective_timestamp=request_time,
            payload={"observation_id": "obs-account"},
            idempotency_scope="broker_read",
            idempotency_key="read-1",
        )
        repo.upsert_account_observation_projection(
            broker_account_id=account_id,
            expected_version=0,
            latest_observation_timestamp=request_time,
            completeness=snapshot.completeness.value,
            latest_account_read_snapshot_observation_id="obs-account",
        )
        repo.upsert_order_observation_projection(
            projection_id="order-1",
            broker_account_id=account_id,
            broker_order_id="OID-PARTIAL",
            latest_normalized_order_state="PARTIALLY_FILLED",
            cumulative_filled_quantity=75,
            expected_version=0,
            latest_snapshot_observation_id="obs-order",
        )
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM broker_observations").fetchone()[0] == 3
        assert connection.execute("SELECT cumulative_filled_quantity FROM broker_order_observation_projection WHERE projection_id='order-1'").fetchone()[0] == 75


def test_transaction_rollback_leaves_no_partial_state(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _seed_identities(db)
    with pytest.raises(RuntimeError):
        with UnitOfWork(db) as uow:
            uow.repo.put_artifact(
                artifact_id="artifact-rollback",
                artifact_type="TFISDecision",
                schema_version="v1",
                payload={"decision": "NO_TRADE"},
                provenance={"source": "test"},
            )
            raise RuntimeError("induced failure")
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM immutable_artifacts WHERE artifact_id='artifact-rollback'").fetchone()[0] == 0


def test_event_append_sequence_idempotency_and_conflict(tmp_path: Path) -> None:
    db = _db(tmp_path)
    session_id, _, account_id = _seed_identities(db)
    ts = datetime.fromisoformat("2026-06-05T09:16:00+05:30")
    with UnitOfWork(db) as uow:
        repo = uow.repo
        event_id = repo.append_event(
            event_id="event-1",
            event_type="BROKER_ORDER_OBSERVED",
            aggregate_type="order",
            aggregate_id="OID-1",
            trading_session_id=session_id,
            broker_account_id=account_id,
            effective_timestamp=ts,
            payload={"status": "OPEN"},
            idempotency_scope="order",
            idempotency_key="OID-1/1",
        )
        duplicate = repo.append_event(
            event_id="event-duplicate",
            event_type="BROKER_ORDER_OBSERVED",
            aggregate_type="order",
            aggregate_id="OID-1",
            trading_session_id=session_id,
            broker_account_id=account_id,
            effective_timestamp=ts,
            payload={"status": "OPEN"},
            idempotency_scope="order",
            idempotency_key="OID-1/1",
        )
        assert duplicate == event_id
        with pytest.raises(IdempotencyConflictError):
            repo.append_event(
                event_id="event-conflict",
                event_type="BROKER_ORDER_OBSERVED",
                aggregate_type="order",
                aggregate_id="OID-1",
                trading_session_id=session_id,
                broker_account_id=account_id,
                effective_timestamp=ts,
                payload={"status": "FILLED"},
                idempotency_scope="order",
                idempotency_key="OID-1/1",
            )


def test_projection_optimistic_concurrency_multi_account_and_multi_stream(tmp_path: Path) -> None:
    db = _db(tmp_path)
    session_id, strategy_id, account_id = _seed_identities(db)
    ts = datetime.fromisoformat("2026-06-05T09:16:00+05:30")
    with UnitOfWork(db) as uow:
        version = uow.repo.upsert_runtime_projection(
            projection_id="runtime-1",
            strategy_instance_id=strategy_id,
            trading_session_id=session_id,
            latest_state="ACTIVE",
            expected_version=0,
        )
        uow.repo.upsert_runtime_projection(
            projection_id="runtime-2",
            strategy_instance_id=strategy_id,
            trading_session_id=session_id,
            latest_state="ACTIVE",
            expected_version=0,
        )
        uow.repo.upsert_account_observation_projection(
            broker_account_id=account_id,
            expected_version=0,
            latest_observation_timestamp=ts,
            completeness="COMPLETE",
        )
        uow.repo.put_broker_account_identity(
            broker_account_id="account-2",
            provider="fixture",
            environment="test",
            account_hash="account-2-hash",
            payload={"account_id": "AC***02"},
        )
        uow.repo.upsert_account_observation_projection(
            broker_account_id="account-2",
            expected_version=0,
            latest_observation_timestamp=ts,
            completeness="COMPLETE",
        )
        assert version == 1
        with pytest.raises(OptimisticConcurrencyError):
            uow.repo.upsert_runtime_projection(
                projection_id="runtime-1",
                strategy_instance_id=strategy_id,
                trading_session_id=session_id,
                latest_state="STALE",
                expected_version=0,
            )
        assert uow.repo.upsert_runtime_projection(
            projection_id="runtime-1",
            strategy_instance_id=strategy_id,
            trading_session_id=session_id,
            latest_state="RELOADED",
            expected_version=1,
        ) == 2


def test_runtime_checkpoint_recovery_corruption_config_and_rule_mismatch(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _seed_identities(db)
    with UnitOfWork(db) as uow:
        uow.repo.put_runtime_checkpoint(
            checkpoint_id="checkpoint-1",
            stream_identity="stream-1",
            session_source_id="source-1",
            source_offset=12,
            current_state="ACTIVE",
            consumed_event_ids=("e1",),
            snapshot_hashes={"s": "h"},
            artifact_hashes={"a": "h"},
            configuration_hash="cfg-ok",
            rule_matrix_version="rule-ok",
        )
    with db.connect() as connection:
        assert assess_recovery(connection, expected_configuration_hash="cfg-ok", expected_rule_matrix_version="rule-ok").status in {RecoveryStatus.RECONCILIATION_REQUIRED, RecoveryStatus.RECOVERABLE_OFFLINE}
        assert assess_recovery(connection, expected_configuration_hash="cfg-bad").status is RecoveryStatus.CONFIGURATION_MISMATCH
        assert assess_recovery(connection, expected_rule_matrix_version="rule-bad").status is RecoveryStatus.RULE_VERSION_MISMATCH
        connection.execute("UPDATE runtime_checkpoints SET payload_json = '{bad' WHERE checkpoint_id = 'checkpoint-1'")
        assert assess_recovery(connection).status is RecoveryStatus.CORRUPTED_STATE


def test_idempotency_reservation_and_incomplete_detection(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _seed_identities(db)
    with UnitOfWork(db) as uow:
        first = uow.repo.reserve_idempotency(
            reservation_id="idem-1",
            scope="runtime_checkpoint",
            idempotency_key="key-1",
            request_payload={"value": 1},
        )
        second = uow.repo.reserve_idempotency(
            reservation_id="idem-duplicate",
            scope="runtime_checkpoint",
            idempotency_key="key-1",
            request_payload={"value": 1},
        )
        assert first == second
        with pytest.raises(IdempotencyConflictError):
            uow.repo.reserve_idempotency(
                reservation_id="idem-conflict",
                scope="runtime_checkpoint",
                idempotency_key="key-1",
                request_payload={"value": 2},
            )
        assert uow.repo.reserve_idempotency(
            reservation_id="idem-account-2",
            scope="runtime_checkpoint/account-2",
            idempotency_key="key-1",
            request_payload={"value": 2},
        ) == "idem-account-2"
    with db.connect() as connection:
        assert assess_recovery(connection).pending_idempotency_count >= 1


def test_execution_intent_and_order_schema_boundaries_do_not_authorize_submission(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _, strategy_id, account_id = _seed_identities(db)
    with UnitOfWork(db) as uow:
        artifact = uow.repo.put_artifact(
            artifact_id="source-artifact",
            artifact_type="EffectiveExecutionPlan",
            schema_version="v1",
            strategy_instance_id=strategy_id,
            payload={"plan": "offline"},
            provenance={"source": "test"},
        )
        uow.repo.put_local_schema_boundary_rows(
            broker_account_id=account_id,
            strategy_instance_id=strategy_id,
            source_artifact_id=artifact,
        )
    with db.connect() as connection:
        row = connection.execute("SELECT authority_mode FROM local_client_orders").fetchone()
        assert row[0] == "OBSERVATIONAL_OR_OFFLINE_ONLY"


def test_canonical_serialization_secret_decimal_timezone_and_null_zero() -> None:
    ts = datetime.fromisoformat("2026-06-05T09:16:00+05:30")
    payload = {"amount": Decimal("1.2300"), "timestamp": ts, "none": None, "zero": 0}
    restored = from_canonical_json(canonical_json(payload))

    assert restored["amount"] == Decimal("1.2300")
    assert restored["timestamp"] == ts
    assert restored["none"] is None
    assert restored["zero"] == 0
    assert canonical_hash(payload) == canonical_hash(payload)
    with pytest.raises(SerializationError):
        canonical_json({"access_token": "secret"})
    with pytest.raises(SerializationError):
        canonical_json({"nan": float("nan")})


def test_observational_comparison_no_reconciliation_mutation_and_integrity(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _seed_identities(db)
    comparison = observational_compare(
        comparison_type="order",
        expected={"order_id": "O1", "status": "OPEN"},
        observed={"order_id": "O1", "status": "FILLED"},
    )
    assert comparison.classification.value == "OBSERVATION_DIFFERENCE"
    with db.connect() as connection:
        assert run_integrity_scan(connection)["status"] == "PASS"
        assert connection.execute("SELECT COUNT(*) FROM local_position_cycle_projections").fetchone()[0] == 0


def test_database_failure_modes_locked_readonly_and_foreign_key(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _seed_identities(db)
    read_only = PersistenceDatabase(db.path, read_only=True)
    with read_only.connect() as connection:
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("INSERT INTO trading_sessions(trading_session_id, trading_date, market, timezone, payload_json, payload_hash, created_timestamp) VALUES ('x','2026-06-05','NSE','IST','{}','h','t')")
    with UnitOfWork(db) as uow:
        with pytest.raises(sqlite3.IntegrityError):
            uow.repo.put_broker_observation(
                observation_id="bad-fk",
                observation_type="broker_order_snapshot",
                broker_account_id="missing",
                request_id="r",
                payload={"x": 1},
                provenance={},
                capture_timestamp=datetime.fromisoformat("2026-06-05T09:16:00+05:30"),
            )


def test_phase4c_reports_are_generated_without_test_database_commit(tmp_path: Path) -> None:
    report_dir = tmp_path / "reports"
    db_path = tmp_path / "phase4c.sqlite"
    written = write_phase4c_reports(report_dir, db_path)

    assert {
        "phase4c_persistence_audit.md",
        "phase4c_schema_catalog.json",
        "phase4c_transaction_catalog.json",
        "phase4c_idempotency_catalog.json",
        "phase4c_recovery_assessment.json",
        "phase4c_integrity_report.json",
        "phase4c_observational_comparison.json",
        "phase4c_performance_metrics.json",
        "phase4c_gap_register.json",
        "phase4c_summary.md",
    } == set(written)
    assert "PHASE4C_M1_ACCEPT" in (report_dir / "phase4c_summary.md").read_text(encoding="utf-8")
    assert db_path.exists()


def test_phase4b_regression_snapshot_still_read_only() -> None:
    snapshot = build_account_read_snapshot(
        FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated"),
        BrokerReadRequest(as_of=datetime.fromisoformat("2026-06-05T09:16:00+05:30")),
    )

    assert snapshot.completeness.value == "COMPLETE"
    assert len(snapshot.orders.records) == 3
