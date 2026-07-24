from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tfis.broker import (
    BrokerOrderIdempotencyKey,
    BrokerOrderIdempotencyStore,
    BrokerReconciliationScope,
    LiveExitProtectionValidation,
    LiveMarketEventIngressValidation,
    LiveOperatorControlIssue,
    LiveOperatorControlValidation,
    validate_live_execution_gate,
    validate_live_position_startup_resume,
    reconcile_broker_truth,
)


def test_live_execution_gate_blocks_when_routing_disabled_even_if_contracts_pass(
    tmp_path: Path,
) -> None:
    decision = validate_live_execution_gate(
        order_routing_enabled=False,
        broker_order_state_intent_ready=True,
        idempotency_reservation=_reservation(tmp_path),
        operator_controls=_passing_operator_controls(),
        exit_protection=_passing_exit_protection(),
        market_event_ingress=_passing_market_ingress(),
        startup_resume=validate_live_position_startup_resume(
            scope=BrokerReconciliationScope.PRE_STARTUP,
            expected_positions=(),
            broker_positions=(),
        ),
        broker_reconciliation=reconcile_broker_truth(
            scope=BrokerReconciliationScope.PRE_STARTUP,
            expected_positions=(),
            broker_positions=(),
        ),
    )

    assert decision.status == "BLOCKED_FOR_LIVE_ORDER_ROUTING"
    assert decision.live_order_allowed is False
    assert [issue.code for issue in decision.issues] == ["LIVE_ORDER_ROUTING_DISABLED"]


def test_live_execution_gate_allows_only_when_enabled_and_all_contracts_pass(
    tmp_path: Path,
) -> None:
    decision = validate_live_execution_gate(
        order_routing_enabled=True,
        broker_order_state_intent_ready=True,
        idempotency_reservation=_reservation(tmp_path),
        operator_controls=_passing_operator_controls(),
        exit_protection=_passing_exit_protection(),
        market_event_ingress=_passing_market_ingress(),
        startup_resume=validate_live_position_startup_resume(
            scope=BrokerReconciliationScope.PRE_STARTUP,
            expected_positions=(),
            broker_positions=(),
        ),
        broker_reconciliation=reconcile_broker_truth(
            scope=BrokerReconciliationScope.PRE_STARTUP,
            expected_positions=(),
            broker_positions=(),
        ),
    )

    assert decision.status == "READY_FOR_LIVE_ORDER_ROUTING"
    assert decision.live_order_allowed is True
    assert decision.issue_count == 0


def test_live_execution_gate_blocks_failed_operator_controls_and_missing_intent(
    tmp_path: Path,
) -> None:
    decision = validate_live_execution_gate(
        order_routing_enabled=True,
        broker_order_state_intent_ready=False,
        idempotency_reservation=_reservation(tmp_path),
        operator_controls=LiveOperatorControlValidation(
            status="FAIL",
            issue_count=1,
            issues=(
                LiveOperatorControlIssue(
                    code="LIVE_OPERATOR_APPROVAL_MISSING",
                    message="approval missing",
                ),
            ),
            message="1 live operator-control issue(s) detected.",
        ),
        exit_protection=_passing_exit_protection(),
        market_event_ingress=_passing_market_ingress(),
        startup_resume=validate_live_position_startup_resume(
            scope=BrokerReconciliationScope.PRE_STARTUP,
            expected_positions=(),
            broker_positions=(),
        ),
        broker_reconciliation=reconcile_broker_truth(
            scope=BrokerReconciliationScope.PRE_STARTUP,
            expected_positions=(),
            broker_positions=(),
        ),
    )

    assert decision.live_order_allowed is False
    assert {issue.code for issue in decision.issues} == {
        "LIVE_BROKER_ORDER_STATE_INTENT_MISSING",
        "LIVE_OPERATOR_CONTROLS_NOT_READY",
    }


def _reservation(tmp_path: Path):
    return BrokerOrderIdempotencyStore().reserve(
        tmp_path / "idempotency",
        key=BrokerOrderIdempotencyKey(
            provider="fyers",
            strategy_code="S23",
            strategy_branch="BRANCH",
            trade_id="TRADE-1",
            order_role="ENTRY",
        ),
        reserved_at=datetime(2026, 7, 24, 9, 15, tzinfo=timezone.utc),
    )


def _passing_operator_controls() -> LiveOperatorControlValidation:
    return LiveOperatorControlValidation(
        status="PASS",
        issue_count=0,
        issues=(),
        message="Live operator approval is explicit, unexpired, audited, and the kill switch is available.",
    )


def _passing_exit_protection() -> LiveExitProtectionValidation:
    return LiveExitProtectionValidation(
        status="PASS",
        issue_count=0,
        issues=(),
        message="Live exit protection plan includes target, stoploss, forced close, emergency exit, and kill switch rules.",
    )


def _passing_market_ingress() -> LiveMarketEventIngressValidation:
    return LiveMarketEventIngressValidation(
        status="PASS",
        issue_count=0,
        issues=(),
        message="Live market-event ingress evidence is connected, fresh, subscribed, and monotonic.",
    )
