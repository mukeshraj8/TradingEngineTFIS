# Phase 4C Persistence Audit

Classification summary:

- Existing paper JSON/JSONL state: LEGACY_COMPATIBILITY_ONLY / REPORTING_ONLY
- Existing CSV ledgers: REPORTING_ONLY
- Existing process locks and ownership markers: REUSABLE_WITH_ADAPTER for operational checks, not authority truth
- Phase 4B read snapshots: REUSABLE_WITH_ADAPTER
- New SQLite operational store: REUSABLE for Phase 4D offline reconciliation input

Risks addressed: schema versioning, idempotency, transaction rollback, append-only events, projection versions, foreign keys, and canonical hashes.

Risks intentionally deferred: Phase 4D reconciliation corrections, paper authority, broker writes, retention automation, and production database selection.

Table counts: {'schema_migrations': 1, 'trading_sessions': 1, 'broker_account_identities': 1, 'strategy_instances': 1, 'position_cycle_identities': 0, 'immutable_artifacts': 1, 'broker_observations': 4, 'broker_read_failures': 0, 'operational_events': 1, 'current_runtime_stream_projection': 1, 'broker_account_observation_projection': 1, 'broker_order_observation_projection': 1, 'broker_position_observation_projection': 1, 'idempotency_reservations': 0, 'execution_intent_reservations': 1, 'local_client_orders': 1, 'local_fill_facts': 0, 'local_position_cycle_projections': 0, 'lifecycle_requirement_records': 0, 'runtime_checkpoints': 1}
