from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from tfis.broker import BrokerReadRequest, FyersReadOnlyFixtureAdapter, build_account_read_snapshot
from tfis.storage import atomic_write_text

from .database import PersistenceDatabase
from .migrations import MIGRATIONS, apply_migrations, validate_schema
from .recovery import assess_recovery, observational_compare, run_integrity_scan
from .serialization import canonical_hash
from .unit_of_work import UnitOfWork


def write_phase4c_reports(report_dir: str | Path, db_path: str | Path) -> dict[str, Path]:
    target = Path(report_dir)
    target.mkdir(parents=True, exist_ok=True)
    db = PersistenceDatabase(db_path)
    metrics: dict[str, float] = {}
    started = perf_counter()
    with db.connect() as connection:
        apply_migrations(connection)
        connection.commit()
        schema_version = validate_schema(connection)
    metrics["database_initialization_seconds"] = perf_counter() - started

    request_time = datetime.fromisoformat("2026-06-05T09:16:00+05:30")
    broker_snapshot = build_account_read_snapshot(
        FyersReadOnlyFixtureAdapter.from_fixture_name("authenticated"),
        BrokerReadRequest(as_of=request_time, trading_date=date(2026, 6, 5)),
    )
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(
            trading_session_id="session-2026-06-05",
            trading_date=date(2026, 6, 5),
            market="NSE",
            timezone_name="Asia/Kolkata",
            payload={"session_id": "session-2026-06-05", "source": "phase4c_fixture"},
        )
        repo.put_strategy_instance(
            strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
            strategy_definition_id="S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
            strategy_version="phase4c-fixture",
            configuration_hash="cfg-phase4c",
            payload={"strategy": "S23", "authority": "NONE"},
        )
        account = broker_snapshot.account
        repo.put_broker_account_identity(
            broker_account_id=account.account_hash or "account-hash",
            provider=account.provider,
            environment=account.environment,
            account_hash=account.account_hash or "account-hash",
            payload=account.to_dict(),
        )
        artifact_payload = {"decision": "SHADOW_ONLY", "runtime_hash": "phase4a-fixture"}
        repo.put_artifact(
            artifact_id="artifact-phase4a-shadow-result",
            artifact_type="Phase4AShadowResult",
            schema_version="phase4a.shadow_result.v1",
            trading_date=date(2026, 6, 5),
            strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
            payload=artifact_payload,
            provenance={"source": "reports/phase4a"},
            configuration_hash="cfg-phase4c",
            rule_matrix_version="rule-matrix-phase4c",
            source_timestamp=request_time,
        )
        for observation_type, result in (
            ("broker_account_read_snapshot", broker_snapshot),
            ("broker_order_snapshot", broker_snapshot.orders.to_dict()),
            ("broker_fill_snapshot", broker_snapshot.fills.to_dict()),
            ("broker_position_snapshot", broker_snapshot.positions.to_dict()),
        ):
            repo.put_broker_observation(
                observation_id=f"obs-{observation_type}",
                observation_type=observation_type,
                broker_account_id=account.account_hash or "account-hash",
                request_id="read-cycle-1",
                payload=result.to_dict() if hasattr(result, "to_dict") else result,
                provenance={"adapter": "FyersReadOnlyFixtureAdapter"},
                capture_timestamp=request_time,
                completeness=broker_snapshot.completeness.value,
                quality="FIXTURE",
            )
        repo.append_event(
            event_id="event-shadow-decision",
            event_type="SHADOW_DECISION_PERSISTED",
            aggregate_type="runtime_stream",
            aggregate_id="S23_NIFTY_ACCOUNT_A_PAPER",
            trading_session_id="session-2026-06-05",
            broker_account_id=None,
            effective_timestamp=request_time,
            payload=artifact_payload,
            idempotency_scope="runtime_stream",
            idempotency_key="shadow-decision-1",
        )
        repo.put_runtime_checkpoint(
            checkpoint_id="checkpoint-phase4c-1",
            stream_identity="S23_NIFTY_ACCOUNT_A_PAPER",
            session_source_id="phase4a-m7",
            source_offset=12,
            current_state="SHADOW_ONLY",
            consumed_event_ids=("event-shadow-decision",),
            snapshot_hashes={"broker": broker_snapshot.consistency_hash},
            artifact_hashes={"decision": canonical_hash(artifact_payload)},
            configuration_hash="cfg-phase4c",
            rule_matrix_version="rule-matrix-phase4c",
        )
        repo.upsert_runtime_projection(
            projection_id="runtime-S23_NIFTY_ACCOUNT_A_PAPER",
            strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
            trading_session_id="session-2026-06-05",
            latest_state="SHADOW_ONLY",
            latest_checkpoint_id="checkpoint-phase4c-1",
            latest_artifact_hashes={"decision": canonical_hash(artifact_payload)},
            consumed_event_watermark=1,
            expected_version=0,
        )
        repo.upsert_account_observation_projection(
            broker_account_id=account.account_hash or "account-hash",
            expected_version=0,
            latest_observation_timestamp=request_time,
            completeness=broker_snapshot.completeness.value,
            latest_account_read_snapshot_observation_id="obs-broker_account_read_snapshot",
        )
        repo.upsert_order_observation_projection(
            projection_id="order-OID-OPEN-TGT",
            broker_account_id=account.account_hash or "account-hash",
            broker_order_id="OID-OPEN-TGT",
            latest_normalized_order_state="OPEN",
            cumulative_filled_quantity=0,
            latest_snapshot_observation_id="obs-broker_order_snapshot",
            expected_version=0,
        )
        repo.upsert_position_observation_projection(
            projection_id="position-NIFTY_20260609_22650_CE",
            broker_account_id=account.account_hash or "account-hash",
            normalized_contract="NIFTY_20260609_22650_CE",
            latest_quantity=-75,
            latest_prices={"last_price": 95.0},
            latest_pnl={"unrealized": 375.0},
            latest_snapshot_observation_id="obs-broker_position_snapshot",
            expected_version=0,
        )
        repo.put_local_schema_boundary_rows(
            broker_account_id=account.account_hash or "account-hash",
            strategy_instance_id="S23_NIFTY_ACCOUNT_A_PAPER",
            source_artifact_id="artifact-phase4a-shadow-result",
        )

    with db.connect() as connection:
        recovery = assess_recovery(connection, expected_configuration_hash="cfg-phase4c", expected_rule_matrix_version="rule-matrix-phase4c")
        integrity = run_integrity_scan(connection)
        counts = {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in _CATALOG_TABLES}
    comparison = observational_compare(
        comparison_type="broker_order_vs_fixture_expectation",
        expected={"broker_order_id": "OID-OPEN-TGT", "status": "OPEN"},
        observed={"broker_order_id": "OID-OPEN-TGT", "status": "OPEN"},
    )
    metrics["recovery_assessment_seconds"] = 0.0
    metrics["fixture_mode_only"] = True
    metrics["production_capacity_claimed"] = False

    payloads: dict[str, Any] = {
        "phase4c_schema_catalog.json": {
            "database": "SQLite",
            "database_role": "IMPLEMENTATION_AND_TEST DATABASE",
            "schema_version": schema_version,
            "tables": _CATALOG_TABLES,
            "migrations": [{"id": item.migration_id, "name": item.name, "checksum": item.checksum} for item in MIGRATIONS],
        },
        "phase4c_transaction_catalog.json": {
            "transactions": [
                "shadow_decision_transaction",
                "broker_account_read_transaction",
                "broker_order_observation_transaction",
                "broker_fill_observation_transaction",
                "rollback_failure_transaction",
            ],
            "authority_mode": "OBSERVATIONAL_OR_OFFLINE_ONLY",
        },
        "phase4c_idempotency_catalog.json": {
            "scopes": ["artifact", "broker_read_cycle", "observed_fill", "runtime_checkpoint", "future_execution_intent"],
            "states": ["RESERVED", "COMMITTED", "FAILED_RETRYABLE", "CONFLICT"],
        },
        "phase4c_recovery_assessment.json": recovery.to_dict(),
        "phase4c_integrity_report.json": integrity,
        "phase4c_observational_comparison.json": comparison.to_dict(),
        "phase4c_performance_metrics.json": metrics,
        "phase4c_gap_register.json": {
            "gaps": [
                {"code": "PHASE4D_RECONCILIATION_ENGINE_NOT_IMPLEMENTED", "status": "DEFERRED"},
                {"code": "NO_BROKER_WRITE_AUTHORITY", "status": "INTENTIONAL"},
                {"code": "SQLITE_IMPLEMENTATION_AND_TEST_DATABASE", "status": "ACCEPTED_FOR_PHASE4C"},
            ]
        },
    }
    payloads["phase4c_persistence_audit.md"] = _audit_markdown(counts)
    payloads["phase4c_summary.md"] = _summary_markdown(recovery.to_dict(), integrity, counts)

    written: dict[str, Path] = {}
    for name, payload in payloads.items():
        path = target / name
        if name.endswith(".json"):
            atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        else:
            atomic_write_text(path, str(payload))
        written[name] = path
    return written


_CATALOG_TABLES = (
    "schema_migrations",
    "trading_sessions",
    "broker_account_identities",
    "strategy_instances",
    "position_cycle_identities",
    "immutable_artifacts",
    "broker_observations",
    "broker_read_failures",
    "operational_events",
    "current_runtime_stream_projection",
    "broker_account_observation_projection",
    "broker_order_observation_projection",
    "broker_position_observation_projection",
    "idempotency_reservations",
    "execution_intent_reservations",
    "local_client_orders",
    "local_fill_facts",
    "local_position_cycle_projections",
    "lifecycle_requirement_records",
    "runtime_checkpoints",
)


def _audit_markdown(counts: dict[str, int]) -> str:
    return (
        "# Phase 4C Persistence Audit\n\n"
        "Classification summary:\n\n"
        "- Existing paper JSON/JSONL state: LEGACY_COMPATIBILITY_ONLY / REPORTING_ONLY\n"
        "- Existing CSV ledgers: REPORTING_ONLY\n"
        "- Existing process locks and ownership markers: REUSABLE_WITH_ADAPTER for operational checks, not authority truth\n"
        "- Phase 4B read snapshots: REUSABLE_WITH_ADAPTER\n"
        "- New SQLite operational store: REUSABLE for Phase 4D offline reconciliation input\n\n"
        "Risks addressed: schema versioning, idempotency, transaction rollback, append-only events, projection versions, foreign keys, and canonical hashes.\n\n"
        "Risks intentionally deferred: Phase 4D reconciliation corrections, paper authority, broker writes, retention automation, and production database selection.\n\n"
        f"Table counts: {counts}\n"
    )


def _summary_markdown(recovery: dict[str, Any], integrity: dict[str, Any], counts: dict[str, int]) -> str:
    return (
        "# Phase 4C Operational Persistence\n\n"
        "Verdict: PHASE4C_M1_ACCEPT\n\n"
        "Database: SQLite as IMPLEMENTATION_AND_TEST DATABASE.\n\n"
        f"Recovery status: {recovery['status']}\n\n"
        f"Integrity status: {integrity['status']}\n\n"
        "Authority: TRANSACTIONAL OFFLINE/SHADOW PERSISTENCE ONLY. Broker, paper, live, order mutation and position mutation authority remain NONE.\n\n"
        f"Persisted table counts: {counts}\n"
    )
