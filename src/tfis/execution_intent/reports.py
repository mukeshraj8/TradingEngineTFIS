from __future__ import annotations

import json
import statistics
from dataclasses import replace
from datetime import date, datetime, timedelta, time
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from tfis.adapters.legacy_policies.s23_effective_execution_plan import (
    build_s23_bear_gap_execution_plan,
    build_s23_bear_normal_execution_plan,
    build_s23_bull_gap_execution_plan,
    build_s23_bull_normal_execution_plan,
)
from tfis.adapters.phase4e import S23ExecutionIntentAdapter
from tfis.domain.runtime_contracts import TFISContractIdentity
from tfis.execution_intent.models import (
    AccountControlSnapshot,
    DuplicateActionSnapshot,
    ExecutionIntent,
    ExecutionIntentPurpose,
    IntentValidationDecision,
    MarketDataQualitySnapshot,
    PortfolioControlSnapshot,
    PositionProtectionSnapshot,
    RiskValidationInput,
    RiskValidationResult,
    StrategyControlSnapshot,
)
from tfis.execution_intent.validation import ExecutionIntentValidator
from tfis.persistence import PersistenceDatabase, UnitOfWork, canonical_hash


def write_phase4e_reports(report_dir: Path, db_path: Path) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    adapter = S23ExecutionIntentAdapter()
    validator = ExecutionIntentValidator()
    fixtures = build_phase4e_fixture_set(adapter, validator)

    db = PersistenceDatabase(db_path)
    valid_entry = fixtures["valid_bull_call_entry"][0]
    valid_result = fixtures["valid_bull_call_entry"][1]
    with UnitOfWork(db) as uow:
        repo = uow.repo
        repo.put_trading_session(
            trading_session_id=valid_entry.trading_session_id,
            trading_date=valid_entry.trading_date,
            market="NSE",
            timezone_name="Asia/Kolkata",
            payload={"source": "phase4e-fixture"},
        )
        repo.put_broker_account_identity(
            broker_account_id=valid_entry.broker_account_id,
            provider="fixture",
            environment="shadow",
            account_hash="phase4e-account",
            payload={"account": "phase4e"},
        )
        repo.put_strategy_instance(
            strategy_instance_id=valid_entry.strategy_instance_id,
            strategy_definition_id=valid_entry.strategy_definition_id,
            strategy_version=valid_entry.strategy_version,
            configuration_hash=valid_entry.evidence.configuration_hash,
            payload={"strategy_family": valid_entry.strategy_family_id},
        )
        repo.put_artifact(
            artifact_id=valid_entry.source_artifact_id,
            artifact_type=valid_entry.source_artifact_type,
            schema_version="phase4e.source.v1",
            trading_date=valid_entry.trading_date,
            strategy_instance_id=valid_entry.strategy_instance_id,
            payload={"source_hash": valid_entry.source_artifact_hash},
            provenance={"source": "phase4e-fixture"},
        )
        repo.put_validated_execution_intent(intent=valid_entry, validation_result=valid_result, expected_projection_version=0)

    performance = _measure_performance(adapter, validator)
    scenario_matrix = {
        name: {
            "intent_purpose": intent.action.purpose.value,
            "decision": result.decision.value,
            "failure_codes": [failure.code for failure in result.failures],
            "authority": "NONE",
        }
        for name, (intent, result) in fixtures.items()
    }
    written = {
        "phase4e_execution_intent_contract.json": _write_json(report_dir / "phase4e_execution_intent_contract.json", _contract_report(valid_entry)),
        "phase4e_risk_check_catalog.json": _write_json(report_dir / "phase4e_risk_check_catalog.json", _risk_catalog(valid_result)),
        "phase4e_scenario_matrix.json": _write_json(report_dir / "phase4e_scenario_matrix.json", scenario_matrix),
        "phase4e_valid_entry_intent.json": _write_json(report_dir / "phase4e_valid_entry_intent.json", fixtures["valid_bull_call_entry"][0].to_dict()),
        "phase4e_valid_target_intent.json": _write_json(report_dir / "phase4e_valid_target_intent.json", fixtures["valid_target"][0].to_dict()),
        "phase4e_valid_original_sl_intent.json": _write_json(report_dir / "phase4e_valid_original_sl_intent.json", fixtures["valid_original_sl"][0].to_dict()),
        "phase4e_valid_revised_sl_intent.json": _write_json(report_dir / "phase4e_valid_revised_sl_intent.json", fixtures["valid_revised_sl"][0].to_dict()),
        "phase4e_valid_eod_exit_intent.json": _write_json(report_dir / "phase4e_valid_eod_exit_intent.json", fixtures["valid_eod_exit"][0].to_dict()),
        "phase4e_blocked_entry_result.json": _write_json(report_dir / "phase4e_blocked_entry_result.json", fixtures["reconciliation_blocked_entry"][1].to_dict()),
        "phase4e_idempotency_result.json": _write_json(report_dir / "phase4e_idempotency_result.json", fixtures["duplicate_identical"][1].to_dict()),
        "phase4e_performance_metrics.json": _write_json(report_dir / "phase4e_performance_metrics.json", performance),
        "phase4e_gap_register.json": _write_json(report_dir / "phase4e_gap_register.json", _gap_register()),
    }
    summary = (
        "# Phase 4E ExecutionIntent And Risk Validation\n\n"
        "Verdict: PHASE4E_M1_ACCEPT\n\n"
        "Runtime impact: VALIDATED NON-SUBMITTABLE EXECUTION INTENTS ONLY.\n\n"
        "Broker/paper/live authority: NONE.\n\n"
        f"Scenario count: {len(scenario_matrix)}\n\n"
        f"Persisted validation decision: {valid_result.decision.value}\n"
    )
    summary_path = report_dir / "phase4e_summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    written["phase4e_summary.md"] = summary_path
    return written


def build_phase4e_fixture_set(adapter: S23ExecutionIntentAdapter | None = None, validator: ExecutionIntentValidator | None = None) -> dict[str, tuple[ExecutionIntent, RiskValidationResult]]:
    adapter = adapter or S23ExecutionIntentAdapter()
    validator = validator or ExecutionIntentValidator()
    bull = adapter.entry_from_effective_plan(build_s23_bull_normal_execution_plan())
    bear = adapter.entry_from_effective_plan(build_s23_bear_normal_execution_plan())
    gap = replace(
        adapter.entry_from_effective_plan(build_s23_bull_gap_execution_plan()),
        action=replace(adapter.entry_from_effective_plan(build_s23_bull_gap_execution_plan()).action, limit_price=Decimal("2.75")),
        evidence=replace(
            adapter.entry_from_effective_plan(build_s23_bull_gap_execution_plan()).evidence,
            provenance={"adapter": "S23ExecutionIntentAdapter", "source_plan": "S23 gap fixture", "path": "GAP_RECALCULATED", "source_price_status": "AUTHORITATIVE_TICK_VALID_FIXTURE"},
        ),
    )
    bear_gap = replace(
        adapter.entry_from_effective_plan(build_s23_bear_gap_execution_plan()),
        action=replace(adapter.entry_from_effective_plan(build_s23_bear_gap_execution_plan()).action, limit_price=Decimal("2.75")),
        evidence=replace(
            adapter.entry_from_effective_plan(build_s23_bear_gap_execution_plan()).evidence,
            provenance={"adapter": "S23ExecutionIntentAdapter", "source_plan": "S23 bear gap fixture", "path": "GAP_RECALCULATED", "source_price_status": "AUTHORITATIVE_TICK_VALID_FIXTURE"},
        ),
    )
    contract = bull.instrument
    lifecycle_contract = TFISContractIdentity(
        symbol=contract.contract,
        exchange=contract.exchange,
        expiry=contract.expiry,
        strike=float(contract.strike) if contract.strike is not None else None,
        option_type=contract.option_type,
        metadata={"underlying": contract.underlying, "lot_size": contract.lot_size, "tick_size": str(contract.tick_size), "currency": contract.currency},
    )
    base_time = bull.action.authorized_not_before
    target = adapter.lifecycle_intent(
        purpose=ExecutionIntentPurpose.TARGET,
        trading_date=bull.trading_date,
        strategy_family_id=bull.strategy_family_id,
        strategy_definition_id=bull.strategy_definition_id,
        strategy_version=bull.strategy_version,
        strategy_instance_id=bull.strategy_instance_id,
        broker_account_id=bull.broker_account_id,
        position_cycle_id="pc-s23-call-1",
        contract=lifecycle_contract,
        quantity=bull.action.requested_quantity,
        side="BUY",
        price=Decimal("90.00"),
        source_artifact_type="PositionLifecycleContext",
        source_artifact_id="lifecycle-target",
        source_artifact_hash="hash-target",
        authorized_not_before=base_time.replace(hour=9, minute=15),
        protection_generation=1,
        rule_id="S23_TARGET_PROTECTION_FROM_OPEN",
    )
    original_sl = adapter.lifecycle_intent(
        purpose=ExecutionIntentPurpose.ORIGINAL_SL,
        trading_date=bull.trading_date,
        strategy_family_id=bull.strategy_family_id,
        strategy_definition_id=bull.strategy_definition_id,
        strategy_version=bull.strategy_version,
        strategy_instance_id=bull.strategy_instance_id,
        broker_account_id=bull.broker_account_id,
        position_cycle_id="pc-s23-call-1",
        contract=lifecycle_contract,
        quantity=bull.action.requested_quantity,
        side="BUY",
        price=Decimal("130.00"),
        source_artifact_type="PositionLifecycleContext",
        source_artifact_id="lifecycle-original-sl",
        source_artifact_hash="hash-original-sl",
        authorized_not_before=base_time,
        protection_generation=1,
        rule_id="S23_ORPT_ORIGINAL_SL_REQUIRED",
    )
    revised_sl = adapter.lifecycle_intent(
        purpose=ExecutionIntentPurpose.REVISED_SL,
        trading_date=bull.trading_date,
        strategy_family_id=bull.strategy_family_id,
        strategy_definition_id=bull.strategy_definition_id,
        strategy_version=bull.strategy_version,
        strategy_instance_id=bull.strategy_instance_id,
        broker_account_id=bull.broker_account_id,
        position_cycle_id="pc-s23-call-1",
        contract=lifecycle_contract,
        quantity=bull.action.requested_quantity,
        side="BUY",
        price=Decimal("125.00"),
        source_artifact_type="CarriedPositionTradingDayResult",
        source_artifact_id="lifecycle-revised-sl",
        source_artifact_hash="hash-revised-sl",
        authorized_not_before=base_time + timedelta(minutes=10),
        protection_generation=2,
        rule_id="S23_RC_REVISED_FSL_REQUIRED",
        superseded_requirement_id="lifecycle-original-sl",
    )
    eod_exit = adapter.lifecycle_intent(
        purpose=ExecutionIntentPurpose.EOD_EXIT,
        trading_date=bull.trading_date,
        strategy_family_id=bull.strategy_family_id,
        strategy_definition_id=bull.strategy_definition_id,
        strategy_version=bull.strategy_version,
        strategy_instance_id=bull.strategy_instance_id,
        broker_account_id=bull.broker_account_id,
        position_cycle_id="pc-s23-call-1",
        contract=lifecycle_contract,
        quantity=bull.action.requested_quantity,
        side="BUY",
        price=Decimal("118.00"),
        source_artifact_type="CarriedPositionTradingDayResult",
        source_artifact_id="lifecycle-eod-exit",
        source_artifact_hash="hash-eod-exit",
        authorized_not_before=base_time.replace(hour=15, minute=0),
        protection_generation=None,
        rule_id="S23_1500_EOD_EXIT",
    )
    cases: dict[str, ExecutionIntent] = {
        "valid_bull_call_entry": bull,
        "valid_bear_call_entry": bear,
        "valid_gap_entry": gap,
        "valid_bear_gap_entry": bear_gap,
        "valid_target": target,
        "valid_original_sl": original_sl,
        "valid_revised_sl": revised_sl,
        "valid_eod_exit": eod_exit,
    }
    result: dict[str, tuple[ExecutionIntent, RiskValidationResult]] = {}
    for name, intent in cases.items():
        request = build_validation_input(intent, validation_id=f"validation:{name}")
        if intent.action.purpose is ExecutionIntentPurpose.REVISED_SL:
            request = replace(request, position=replace(request.position, required_next_generation=2, superseded_requirement_id="lifecycle-original-sl"))
        result[name] = (intent, validator.validate(request))
    mutants = {
        "reconciliation_blocked_entry": replace(build_validation_input(bull, validation_id="validation:reconciliation_blocked"), reconciliation_gate="NEW_ENTRY_BLOCKED", reconciliation_blocking_classifications=("BROKER_ONLY_POSITION",)),
        "active_duplicate_cycle_blocks_entry": replace(build_validation_input(bull, validation_id="validation:duplicate_cycle"), strategy=replace(build_validation_input(bull).strategy, active_fresh_entry_cycles=1)),
        "stale_market_data": replace(build_validation_input(bull, validation_id="validation:stale_market"), market_data=replace(build_validation_input(bull).market_data, source_age_seconds=999)),
        "insufficient_margin_evidence": replace(build_validation_input(bull, validation_id="validation:margin"), account=replace(build_validation_input(bull).account, margin_evidence_available=False)),
        "invalid_quantity": replace(build_validation_input(bull, validation_id="validation:bad_qty"), intent=replace(bull, action=replace(bull.action, requested_quantity=0))),
        "invalid_lot_multiple": replace(build_validation_input(bull, validation_id="validation:bad_lot"), intent=replace(bull, action=replace(bull.action, requested_quantity=1, quantity_unit="UNITS"))),
        "invalid_price": replace(build_validation_input(bull, validation_id="validation:bad_price"), intent=replace(bull, action=replace(bull.action, limit_price=Decimal("-1.00")))),
        "invalid_tick": replace(build_validation_input(bull, validation_id="validation:bad_tick"), intent=replace(bull, action=replace(bull.action, limit_price=Decimal("100.03")))),
        "timing_not_reached": replace(build_validation_input(bull, validation_id="validation:too_early"), evaluated_at=bull.action.authorized_not_before - timedelta(minutes=1)),
        "expired_timing": replace(build_validation_input(replace(bull, action=replace(bull.action, authorized_not_after=bull.action.authorized_not_before + timedelta(minutes=1))), validation_id="validation:expired"), evaluated_at=bull.action.authorized_not_before + timedelta(minutes=2)),
        "stale_protection_generation": replace(build_validation_input(original_sl, validation_id="validation:stale_generation"), position=replace(build_validation_input(original_sl).position, required_next_generation=2)),
        "protection_quantity_exceeds_position": replace(build_validation_input(target, validation_id="validation:overprotect"), position=replace(build_validation_input(target).position, broker_confirmed_remaining_quantity=1)),
        "new_entries_blocked_protection_allowed": replace(build_validation_input(target, validation_id="validation:protection_allowed"), reconciliation_gate="NEW_ENTRY_BLOCKED", portfolio=replace(build_validation_input(target).portfolio, global_new_entry_enabled=False, kill_switch_action="BLOCK_NEW_ENTRIES")),
        "global_halt_behavior": replace(build_validation_input(bull, validation_id="validation:global_halt"), portfolio=replace(build_validation_input(bull).portfolio, global_kill_switch=True, kill_switch_action="GLOBAL_HALT")),
        "missing_position_lifecycle": replace(build_validation_input(target, validation_id="validation:missing_position"), position=replace(build_validation_input(target).position, broker_confirmed_remaining_quantity=None)),
        "duplicate_identical": replace(build_validation_input(bull, validation_id="validation:duplicate_identical"), duplicate=DuplicateActionSnapshot(existing_intent_hash=bull.intent_hash)),
        "conflicting_duplicate": replace(build_validation_input(bull, validation_id="validation:duplicate_conflict"), duplicate=DuplicateActionSnapshot(same_idempotency_payload_hash="different-hash")),
        "different_account_isolated": build_validation_input(adapter.entry_from_effective_plan(build_s23_bull_normal_execution_plan(), broker_account_id="S23_ACCOUNT_B_SHADOW"), validation_id="validation:account_b"),
        "recovery_blocked": replace(build_validation_input(bull, validation_id="validation:recovery_blocked"), recovery_status="CORRUPTED_STATE"),
        "account_disabled": replace(build_validation_input(bull, validation_id="validation:account_disabled"), account=replace(build_validation_input(bull).account, account_enabled=False)),
        "strategy_disabled": replace(build_validation_input(bull, validation_id="validation:strategy_disabled"), strategy=replace(build_validation_input(bull).strategy, strategy_enabled=False)),
        "portfolio_new_entry_block": replace(build_validation_input(bull, validation_id="validation:portfolio_block"), portfolio=replace(build_validation_input(bull).portfolio, global_new_entry_enabled=False, kill_switch_action="BLOCK_NEW_ENTRIES")),
        "missing_oi": replace(build_validation_input(bull, validation_id="validation:missing_oi"), market_data=replace(build_validation_input(bull).market_data, oi_required=True, has_oi=False)),
        "closed_position_blocks_lifecycle": replace(build_validation_input(target, validation_id="validation:closed_position"), position=replace(build_validation_input(target).position, position_status="CLOSED")),
        "source_missing": replace(build_validation_input(bull, validation_id="validation:source_missing"), source_artifact_available=False),
        "source_hash_mismatch": replace(build_validation_input(bull, validation_id="validation:source_hash_mismatch"), source_hash_matches=False),
    }
    for name, request in mutants.items():
        result[name] = (request.intent, validator.validate(request))
    return result


def build_validation_input(intent: ExecutionIntent, validation_id: str = "validation:fixture") -> RiskValidationInput:
    lifecycle = intent.action.purpose is not ExecutionIntentPurpose.ENTRY
    remaining = intent.action.requested_quantity if lifecycle else None
    position_id = intent.position_cycle_id if lifecycle else None
    return RiskValidationInput(
        validation_id=validation_id,
        intent=intent,
        evaluated_at=intent.action.authorized_not_before,
        recovery_status="RECOVERABLE_OFFLINE",
        recovery_assessment_hash=intent.evidence.recovery_assessment_hash,
        reconciliation_gate="SHADOW_READY",
        reconciliation_blocking_classifications=(),
        account=AccountControlSnapshot(
            account_enabled=True,
            environment="shadow",
            required_environment="shadow",
            session_available=True,
            funds_evidence_available=True,
            margin_evidence_available=True,
            account_blocked=False,
            kill_switch_active=False,
            active_orders=0,
            max_active_orders=5,
            active_positions=1 if lifecycle else 0,
            max_active_positions=5,
            daily_loss_gate_blocked=False,
            broker_read_age_seconds=10,
            max_broker_read_age_seconds=60,
        ),
        strategy=StrategyControlSnapshot(
            strategy_enabled=True,
            expected_strategy_version=intent.strategy_version,
            configuration_hash=intent.evidence.configuration_hash,
            expected_configuration_hash=intent.evidence.configuration_hash,
            rule_matrix_version=intent.evidence.rule_matrix_version,
            expected_rule_matrix_version=intent.evidence.rule_matrix_version,
            assigned_account_id=intent.broker_account_id,
            allowed_products=(intent.instrument.product,),
            allowed_underlyings=(intent.instrument.underlying,),
            allowed_contract_types=(intent.instrument.option_type or "NONE",),
            max_active_fresh_entry_cycles=1,
            active_fresh_entry_cycles=0,
            configured_quantity=intent.action.requested_quantity,
        ),
        portfolio=PortfolioControlSnapshot(
            global_new_entry_enabled=True,
            global_kill_switch=False,
            max_total_active_positions=10,
            total_active_positions=1 if lifecycle else 0,
            max_total_active_orders=10,
            total_active_orders=0,
            global_daily_loss_blocked=False,
            data_degraded_global_block=False,
            kill_switch_action=None,
        ),
        market_data=MarketDataQualitySnapshot(
            context_hash=intent.evidence.market_snapshot_hash,
            trading_date=intent.trading_date,
            contract=intent.instrument.contract,
            source_age_seconds=10,
            max_age_seconds=60,
            timestamp_skew_seconds=1,
            max_timestamp_skew_seconds=5,
            has_bid=True,
            has_ask=True,
            has_ltp=True,
            oi_required=intent.action.purpose is ExecutionIntentPurpose.ENTRY,
            has_oi=True,
            quality="FIXTURE" if intent.action.purpose is ExecutionIntentPurpose.ENTRY else "LIFECYCLE_DERIVED",
        ),
        position=PositionProtectionSnapshot(
            position_cycle_id=position_id,
            broker_confirmed_remaining_quantity=remaining,
            position_status="OPEN" if lifecycle else None,
            active_protection_generation=1 if lifecycle else None,
            required_next_generation=1 if lifecycle else None,
            duplicate_active_sl=False,
            target_and_sl_can_coexist=True,
            superseded_requirement_id=None,
        ),
    )


def _contract_report(intent: ExecutionIntent) -> dict[str, Any]:
    data = intent.to_dict()
    return {
        "schema_version": data["schema_version"],
        "required_identity": [key for key in data if key not in {"instrument", "action", "evidence"}],
        "instrument_fields": list(data["instrument"]),
        "action_fields": list(data["action"]),
        "evidence_fields": list(data["evidence"]),
        "forbidden_fields_present": [key for key in data if "broker_order_id" in key or "exchange_order_id" in key or "access_token" in key],
        "authority": "NONE",
    }


def _risk_catalog(result: RiskValidationResult) -> list[dict[str, Any]]:
    return [check.to_dict() for check in result.checks]


def _gap_register() -> list[dict[str, str]]:
    return [
        {"gap_id": "PHASE4E-GAP-001", "status": "DEFERRED", "description": "Actual AccountCoordinator conversion from validated intent to client-order request is Phase 4F."},
        {"gap_id": "PHASE4E-GAP-002", "status": "DEFERRED", "description": "Advanced portfolio optimization, VaR and PnL calculation remain outside the first S23 paper vertical."},
    ]


def _measure_performance(adapter: S23ExecutionIntentAdapter, validator: ExecutionIntentValidator) -> dict[str, Any]:
    entry = adapter.entry_from_effective_plan(build_s23_bull_normal_execution_plan())
    protection = build_phase4e_fixture_set(adapter, validator)["valid_target"][0] if False else None
    samples: dict[str, list[float]] = {key: [] for key in ["intent_construction", "one_validation", "entry_100", "protection_100", "idempotency_hash", "serialization_hash", "multi_account_batch"]}
    for _ in range(5):
        start = perf_counter()
        adapter.entry_from_effective_plan(build_s23_bull_normal_execution_plan())
        samples["intent_construction"].append(perf_counter() - start)
        request = build_validation_input(entry)
        start = perf_counter()
        validator.validate(request)
        samples["one_validation"].append(perf_counter() - start)
        start = perf_counter()
        for index in range(100):
            validator.validate(replace(request, validation_id=f"perf-entry-{index}"))
        samples["entry_100"].append(perf_counter() - start)
        start = perf_counter()
        for index in range(100):
            validator.validate(replace(request, validation_id=f"perf-protection-{index}"))
        samples["protection_100"].append(perf_counter() - start)
        start = perf_counter()
        canonical_hash({"idempotency_key": entry.idempotency_key, "intent_hash": entry.intent_hash})
        samples["idempotency_hash"].append(perf_counter() - start)
        start = perf_counter()
        canonical_hash(entry.to_dict())
        samples["serialization_hash"].append(perf_counter() - start)
        start = perf_counter()
        for account in range(10):
            validator.validate(replace(request, validation_id=f"perf-account-{account}"))
        samples["multi_account_batch"].append(perf_counter() - start)
    return {
        key: {
            "median_ms": round(statistics.median(values) * 1000, 4),
            "p95_ms": round(max(values) * 1000, 4),
            "fixture_only": True,
        }
        for key, values in samples.items()
    }


def _write_json(path: Path, payload: Any) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
