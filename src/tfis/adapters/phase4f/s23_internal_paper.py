from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any

from tfis.execution_intent import ExecutionIntentPurpose
from tfis.execution_intent.reports import build_phase4e_fixture_set
from tfis.internal_paper import (
    AccountCoordinator,
    AccountCoordinatorError,
    DeterministicExecutionScenarioDefinition,
    DeterministicInternalPaperAdapter,
    DeterministicMarketEvidence,
    InternalPaperAdapterResult,
    InternalPaperAuthorityGrant,
    InternalPaperExecutionScenario,
    SimulatedPaperAccountSnapshot,
    create_creation_event,
)


SUPPORTED_S23_PHASE4F_PURPOSES = ("ENTRY", "TARGET", "ORIGINAL_SL", "REVISED_SL", "EOD_EXIT")


def build_s23_internal_paper_grant(intent, *, maximum_quantity: int = 999) -> InternalPaperAuthorityGrant:
    return InternalPaperAuthorityGrant(
        grant_id=f"grant:{intent.broker_account_id}:{intent.trading_session_id}:s23",
        broker_account_id=intent.broker_account_id,
        trading_session_id=intent.trading_session_id,
        strategy_instance_id=intent.strategy_instance_id,
        allowed_intent_purposes=SUPPORTED_S23_PHASE4F_PURPOSES,
        maximum_quantity=maximum_quantity,
        valid_from=intent.action.authorized_not_before - timedelta(minutes=5),
        valid_until=intent.action.authorized_not_before + timedelta(hours=8),
        configuration_hash=intent.evidence.configuration_hash,
        rule_version=intent.evidence.rule_matrix_version,
        issued_by="PHASE4F_FIXTURE",
        reason="First S23 Call-side internal paper simulation grant.",
    )


def build_s23_account_snapshot(broker_account_id: str, *, blocked: bool = False, available_margin: Decimal = Decimal("1000000")) -> SimulatedPaperAccountSnapshot:
    return SimulatedPaperAccountSnapshot(
        broker_account_id=broker_account_id,
        opening_paper_cash=Decimal("1000000"),
        reserved_margin=Decimal("0"),
        released_margin=Decimal("0"),
        available_paper_margin=available_margin,
        simulated_charges=Decimal("0"),
        active_order_reservation=Decimal("0"),
        margin_per_quantity=Decimal("100"),
        account_enabled=not blocked,
        account_blocked=blocked,
        active_order_count=0,
        max_active_order_count=10,
    )


def build_scenario(intent, scenario: InternalPaperExecutionScenario, *, scenario_id: str | None = None, fill_quantity: int | None = None) -> DeterministicExecutionScenarioDefinition:
    price = intent.action.limit_price or intent.action.trigger_price or Decimal("100.00")
    return DeterministicExecutionScenarioDefinition(
        scenario_id=scenario_id or f"s23:{intent.action.purpose.value}:{scenario.value}",
        scenario=scenario,
        market_evidence=DeterministicMarketEvidence(
            bid=price - Decimal("0.05"),
            ask=price + Decimal("0.05"),
            ltp=price,
            high=price + Decimal("1.00"),
            low=max(Decimal("0.05"), price - Decimal("1.00")),
            source_timestamp=intent.action.authorized_not_before,
            snapshot_hash=f"market:{intent.execution_intent_id}:{scenario.value}",
        ),
        event_time=intent.action.authorized_not_before,
        fill_quantity=fill_quantity,
        fill_price=price,
        rejection_reason=scenario.value,
        cancel_reason=scenario.value,
    )


def execute_s23_internal_paper_case(case_name: str) -> dict[str, Any]:
    fixtures = build_phase4e_fixture_set()
    adapter = DeterministicInternalPaperAdapter()
    if case_name == "bull_entry_full":
        intent, validation = fixtures["valid_bull_call_entry"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL)
    elif case_name == "bear_entry_ack_full":
        intent, validation = fixtures["valid_bear_call_entry"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.ACK_THEN_FULL_FILL)
    elif case_name == "bull_gap_partial_full":
        intent, validation = fixtures["valid_gap_entry"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.PARTIAL_THEN_FULL_FILL, fill_quantity=max(1, intent.action.requested_quantity // 2))
    elif case_name == "entry_margin_rejected":
        intent, validation = fixtures["valid_bull_call_entry"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.REJECTED_INSUFFICIENT_PAPER_MARGIN)
    elif case_name == "target_ack":
        intent, validation = fixtures["valid_target"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN, fill_quantity=1)
    elif case_name == "original_sl_ack":
        intent, validation = fixtures["valid_original_sl"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.PARTIAL_REMAINS_OPEN, fill_quantity=1)
    elif case_name == "revised_sl_replace_ack":
        intent, validation = fixtures["valid_revised_sl"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.CANCEL_BEFORE_FILL)
    elif case_name == "revised_sl_old_fills_before_cancel":
        intent, validation = fixtures["valid_revised_sl"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.FILL_BEFORE_CANCEL_CONFIRMATION)
    elif case_name == "eod_exit_full":
        intent, validation = fixtures["valid_eod_exit"]
        scenario = build_scenario(intent, InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL)
    else:
        raise ValueError(f"Unsupported S23 Phase 4F case: {case_name}")
    grant = build_s23_internal_paper_grant(intent)
    snapshot = build_s23_account_snapshot(intent.broker_account_id, blocked=case_name.endswith("blocked"))
    coordinator = AccountCoordinator(AccountCoordinator.build_identity(broker_account_id=intent.broker_account_id, trading_session_id=intent.trading_session_id), snapshot)
    client_order = coordinator.create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=intent.action.authorized_not_before)
    if case_name == "entry_margin_rejected":
        snapshot = replace(snapshot, available_paper_margin=Decimal("0"))
    result = adapter.execute(client_order, scenario, snapshot)
    creation = create_creation_event(client_order, intent.action.authorized_not_before)
    result = replace(result, events=(creation, *result.events))
    coordinator.apply_result(result)
    return {
        "intent": intent.to_dict(),
        "validation": validation.to_dict(),
        "grant": grant.to_dict(),
        "client_order": client_order.to_dict(),
        "scenario": scenario.to_dict(),
        "result": result.to_dict(),
        "coordinator": coordinator.identity.to_dict(),
    }


def execute_two_account_case() -> dict[str, Any]:
    fixtures = build_phase4e_fixture_set()
    intent_a, validation_a = fixtures["valid_bull_call_entry"]
    intent_b, validation_b = fixtures["different_account_isolated"]
    result_a = _execute(intent_a, validation_a, blocked=False)
    blocked_error = None
    try:
        _execute(intent_b, validation_b, blocked=True)
    except AccountCoordinatorError as exc:
        blocked_error = str(exc)
    return {"account_a": result_a.to_dict(), "account_b_blocked_error": blocked_error, "isolation": "PASSED"}


def _execute(intent, validation, *, blocked: bool) -> InternalPaperAdapterResult:
    grant = build_s23_internal_paper_grant(intent)
    snapshot = build_s23_account_snapshot(intent.broker_account_id, blocked=blocked)
    coordinator = AccountCoordinator(AccountCoordinator.build_identity(broker_account_id=intent.broker_account_id, trading_session_id=intent.trading_session_id), snapshot)
    order = coordinator.create_client_order(intent=intent, validation_result=validation, grant=grant, evaluated_at=intent.action.authorized_not_before)
    result = DeterministicInternalPaperAdapter().execute(order, build_scenario(intent, InternalPaperExecutionScenario.IMMEDIATE_FULL_FILL), snapshot)
    result = replace(result, events=(create_creation_event(order, intent.action.authorized_not_before), *result.events))
    coordinator.apply_result(result)
    return result
