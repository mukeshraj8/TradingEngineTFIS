from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from tfis.adapters.legacy_policies.s23_effective_execution_plan import build_s23_bull_normal_execution_plan
from tfis.adapters.phase4e import S23ExecutionIntentAdapter
from tfis.execution_intent import ExecutionIntentPurpose, ExecutionIntentValidator, IntentValidationDecision
from tfis.execution_intent.reports import build_phase4e_fixture_set, build_validation_input, write_phase4e_reports
from tfis.persistence import IdempotencyConflictError, PersistenceDatabase, UnitOfWork


def _fixtures():
    return build_phase4e_fixture_set()


def test_execution_intent_immutability_deterministic_hash_and_no_broker_fields() -> None:
    intent = _fixtures()["valid_bull_call_entry"][0]
    duplicate = S23ExecutionIntentAdapter().entry_from_effective_plan(build_s23_bull_normal_execution_plan())

    with pytest.raises(FrozenInstanceError):
        intent.execution_intent_id = "mutated"  # type: ignore[misc]
    assert intent.intent_hash == duplicate.intent_hash
    payload = intent.to_dict()
    assert "broker_order_id" not in str(payload)
    assert "exchange_order_id" not in str(payload)
    assert "access_token" not in str(payload)
    assert intent.order_creation_permitted is False


@pytest.mark.parametrize(
    ("case_name", "decision"),
    [
        ("valid_bull_call_entry", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("valid_bear_call_entry", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("valid_gap_entry", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("reconciliation_blocked_entry", IntentValidationDecision.BLOCKED),
        ("recovery_blocked", IntentValidationDecision.BLOCKED),
        ("account_disabled", IntentValidationDecision.BLOCKED),
        ("strategy_disabled", IntentValidationDecision.BLOCKED),
        ("portfolio_new_entry_block", IntentValidationDecision.BLOCKED),
        ("insufficient_margin_evidence", IntentValidationDecision.INSUFFICIENT_EVIDENCE),
        ("stale_market_data", IntentValidationDecision.INSUFFICIENT_EVIDENCE),
        ("missing_oi", IntentValidationDecision.INSUFFICIENT_EVIDENCE),
        ("invalid_quantity", IntentValidationDecision.REJECTED),
        ("invalid_lot_multiple", IntentValidationDecision.REJECTED),
        ("invalid_price", IntentValidationDecision.REJECTED),
        ("invalid_tick", IntentValidationDecision.REJECTED),
        ("timing_not_reached", IntentValidationDecision.BLOCKED),
        ("expired_timing", IntentValidationDecision.EXPIRED),
        ("valid_target", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("valid_original_sl", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("valid_revised_sl", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("stale_protection_generation", IntentValidationDecision.BLOCKED),
        ("protection_quantity_exceeds_position", IntentValidationDecision.BLOCKED),
        ("valid_eod_exit", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("new_entries_blocked_protection_allowed", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("global_halt_behavior", IntentValidationDecision.BLOCKED),
        ("missing_position_lifecycle", IntentValidationDecision.BLOCKED),
        ("duplicate_identical", IntentValidationDecision.DUPLICATE),
        ("conflicting_duplicate", IntentValidationDecision.DUPLICATE),
        ("different_account_isolated", IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE),
        ("closed_position_blocks_lifecycle", IntentValidationDecision.BLOCKED),
        ("source_missing", IntentValidationDecision.INSUFFICIENT_EVIDENCE),
        ("source_hash_mismatch", IntentValidationDecision.BLOCKED),
    ],
)
def test_phase4e_scenarios_fail_closed(case_name: str, decision: IntentValidationDecision) -> None:
    result = _fixtures()[case_name][1]

    assert result.decision is decision
    assert result.broker_submission_permitted is False
    assert result.paper_submission_permitted is False
    assert result.live_submission_permitted is False
    assert result.order_creation_permitted is False
    assert result.position_mutation_permitted is False
    assert result.checks


def test_risk_check_hierarchy_records_source_evidence() -> None:
    result = _fixtures()["valid_bull_call_entry"][1]
    check_ids = [check.check_id for check in result.checks]

    assert check_ids.index("AUTHORITY_MODE_OFFLINE_ONLY") < check_ids.index("RECOVERY_READY")
    assert check_ids.index("RECOVERY_READY") < check_ids.index("RECONCILIATION_GATE")
    assert check_ids.index("RECONCILIATION_GATE") < check_ids.index("ACCOUNT_ENABLED")
    assert check_ids.index("ACCOUNT_ENABLED") < check_ids.index("STRATEGY_ENABLED")
    assert check_ids.index("PRICE_POSITIVE") < check_ids.index("TIMING_WINDOW")
    assert all(check.evidence.evidence_hash for check in result.checks)


def test_duplicate_same_key_conflict_and_account_isolation() -> None:
    fixtures = _fixtures()
    intent = fixtures["valid_bull_call_entry"][0]
    validator = ExecutionIntentValidator()
    conflict_intent = replace(intent, action=replace(intent.action, limit_price=Decimal("101.00")))
    conflict_request = replace(build_validation_input(conflict_intent, "validation:conflict"), duplicate=replace(build_validation_input(conflict_intent).duplicate, same_idempotency_payload_hash="different"))

    assert validator.validate(conflict_request).decision is IntentValidationDecision.DUPLICATE
    assert fixtures["different_account_isolated"][0].broker_account_id != intent.broker_account_id
    assert fixtures["different_account_isolated"][1].decision is IntentValidationDecision.VALIDATED_NOT_SUBMITTABLE


def test_validation_persistence_idempotency_conflict_and_rollback(tmp_path: Path) -> None:
    intent, result = _fixtures()["valid_bull_call_entry"]
    db = PersistenceDatabase(tmp_path / "phase4e.sqlite")
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(trading_session_id=intent.trading_session_id, trading_date=intent.trading_date, market="NSE", timezone_name="Asia/Kolkata", payload={})
        repo.put_broker_account_identity(broker_account_id=intent.broker_account_id, provider="fixture", environment="shadow", account_hash="acct", payload={})
        repo.put_strategy_instance(strategy_instance_id=intent.strategy_instance_id, strategy_definition_id=intent.strategy_definition_id, strategy_version=intent.strategy_version, configuration_hash=intent.evidence.configuration_hash, payload={})
        repo.put_artifact(artifact_id=intent.source_artifact_id, artifact_type=intent.source_artifact_type, schema_version="v1", trading_date=intent.trading_date, strategy_instance_id=intent.strategy_instance_id, payload={"h": intent.source_artifact_hash}, provenance={})
        assert repo.put_validated_execution_intent(intent=intent, validation_result=result, expected_projection_version=0) == result.validation_id
    with UnitOfWork(db) as uow:
        assert uow.repo.put_validated_execution_intent(intent=intent, validation_result=result, expected_projection_version=None) == result.validation_id
    conflict = replace(intent, source_artifact_hash="different")
    with pytest.raises(IdempotencyConflictError):
        with UnitOfWork(db) as uow:
            uow.repo.put_validated_execution_intent(intent=conflict, validation_result=result, expected_projection_version=None)
    with pytest.raises(RuntimeError):
        with UnitOfWork(db) as uow:
            target_intent, target_result = _fixtures()["valid_target"]
            uow.repo.put_position_cycle_identity(
                position_cycle_id=target_intent.position_cycle_id,
                strategy_instance_id=target_intent.strategy_instance_id,
                trading_session_id=target_intent.trading_session_id,
                payload={"source": "phase4e-rollback"},
            )
            uow.repo.put_artifact(
                artifact_id=target_intent.source_artifact_id,
                artifact_type=target_intent.source_artifact_type,
                schema_version="v1",
                trading_date=target_intent.trading_date,
                strategy_instance_id=target_intent.strategy_instance_id,
                position_cycle_id=target_intent.position_cycle_id,
                payload={"h": target_intent.source_artifact_hash},
                provenance={},
            )
            uow.repo.put_validated_execution_intent(intent=target_intent, validation_result=target_result, expected_projection_version=0)
            raise RuntimeError("induced rollback")
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM execution_intents").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM local_client_orders").fetchone()[0] == 0


def test_reports_are_generated(tmp_path: Path) -> None:
    written = write_phase4e_reports(tmp_path / "reports", tmp_path / "phase4e.sqlite")

    assert "phase4e_summary.md" in written
    assert (tmp_path / "reports" / "phase4e_valid_entry_intent.json").exists()
    assert "PHASE4E_M1_ACCEPT" in (tmp_path / "reports" / "phase4e_summary.md").read_text(encoding="utf-8")
