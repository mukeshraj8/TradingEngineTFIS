from __future__ import annotations

from dataclasses import dataclass

from .broker_order_idempotency import BrokerOrderReservationResult, BrokerOrderReservationStatus
from .broker_reconciliation import BrokerReconciliationResult, BrokerReconciliationStatus
from .live_exit_protection import LiveExitProtectionValidation
from .live_market_event_ingress import LiveMarketEventIngressValidation
from .live_operator_controls import LiveOperatorControlValidation
from .live_position_recovery import LivePositionStartupResumeValidation


@dataclass(frozen=True, slots=True)
class LiveExecutionGateIssue:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LiveExecutionGateDecision:
    status: str
    live_order_allowed: bool
    issue_count: int
    issues: tuple[LiveExecutionGateIssue, ...]
    message: str


def validate_live_execution_gate(
    *,
    order_routing_enabled: bool,
    broker_order_state_intent_ready: bool,
    idempotency_reservation: BrokerOrderReservationResult | None,
    operator_controls: LiveOperatorControlValidation,
    exit_protection: LiveExitProtectionValidation,
    market_event_ingress: LiveMarketEventIngressValidation,
    startup_resume: LivePositionStartupResumeValidation,
    broker_reconciliation: BrokerReconciliationResult,
) -> LiveExecutionGateDecision:
    issues: list[LiveExecutionGateIssue] = []
    if not order_routing_enabled:
        issues.append(
            LiveExecutionGateIssue(
                code="LIVE_ORDER_ROUTING_DISABLED",
                message="Live order routing is disabled by configuration.",
            )
        )
    if not broker_order_state_intent_ready:
        issues.append(
            LiveExecutionGateIssue(
                code="LIVE_BROKER_ORDER_STATE_INTENT_MISSING",
                message="A durable broker-order intent must exist before routing.",
            )
        )
    if idempotency_reservation is None:
        issues.append(
            LiveExecutionGateIssue(
                code="LIVE_IDEMPOTENCY_RESERVATION_MISSING",
                message="A broker-order idempotency reservation is required before routing.",
            )
        )
    else:
        if idempotency_reservation.duplicate_prevented:
            issues.append(
                LiveExecutionGateIssue(
                    code="LIVE_IDEMPOTENCY_DUPLICATE_PREVENTED",
                    message="A duplicate broker-order reservation was detected; routing must be skipped.",
                )
            )
        if idempotency_reservation.reservation.status is not BrokerOrderReservationStatus.RESERVED:
            issues.append(
                LiveExecutionGateIssue(
                    code="LIVE_IDEMPOTENCY_RESERVATION_NOT_ACTIVE",
                    message="The broker-order idempotency reservation is not active.",
                )
            )
    _require_pass(
        issues,
        code="LIVE_OPERATOR_CONTROLS_NOT_READY",
        status=operator_controls.status,
        message=operator_controls.message,
    )
    _require_pass(
        issues,
        code="LIVE_EXIT_PROTECTION_NOT_READY",
        status=exit_protection.status,
        message=exit_protection.message,
    )
    _require_pass(
        issues,
        code="LIVE_MARKET_EVENT_INGRESS_NOT_READY",
        status=market_event_ingress.status,
        message=market_event_ingress.message,
    )
    _require_pass(
        issues,
        code="LIVE_STARTUP_RESUME_NOT_READY",
        status=startup_resume.status,
        message=startup_resume.message,
    )
    if broker_reconciliation.status is not BrokerReconciliationStatus.PASS:
        issues.append(
            LiveExecutionGateIssue(
                code="LIVE_BROKER_RECONCILIATION_NOT_READY",
                message=broker_reconciliation.message,
            )
        )
    live_order_allowed = not issues
    return LiveExecutionGateDecision(
        status="READY_FOR_LIVE_ORDER_ROUTING" if live_order_allowed else "BLOCKED_FOR_LIVE_ORDER_ROUTING",
        live_order_allowed=live_order_allowed,
        issue_count=len(issues),
        issues=tuple(issues),
        message=(
            "All live execution gates passed and live order routing is explicitly enabled."
            if live_order_allowed
            else f"{len(issues)} live execution gate issue(s) block live order routing."
        ),
    )


def _require_pass(
    issues: list[LiveExecutionGateIssue],
    *,
    code: str,
    status: str,
    message: str,
) -> None:
    if status != "PASS":
        issues.append(LiveExecutionGateIssue(code=code, message=message))


__all__ = [
    "LiveExecutionGateDecision",
    "LiveExecutionGateIssue",
    "validate_live_execution_gate",
]
