from __future__ import annotations

from dataclasses import dataclass

from tfis.broker import (
    broker_order_event_fields,
    broker_order_state_model_fields,
    build_broker_client_order_id,
    reconcile_broker_truth,
    validate_live_exit_protection_plan,
    validate_live_execution_gate,
    validate_live_market_event_ingress,
    validate_live_operator_controls,
    validate_live_position_recovery_plan,
)


@dataclass(frozen=True, slots=True)
class LiveMoneyReadinessGate:
    code: str
    status: str
    required_before_live: bool
    description: str


@dataclass(frozen=True, slots=True)
class LiveMoneyBoundaryStatus:
    status: str
    live_money_ready: bool
    paper_runtime_safe: bool
    order_routing_enabled: bool
    message: str
    gates: tuple[LiveMoneyReadinessGate, ...]


LIVE_MONEY_READINESS_GATES: tuple[LiveMoneyReadinessGate, ...] = (
    LiveMoneyReadinessGate(
        code="BROKER_ORDER_STATE_MODEL",
        status="DONE",
        required_before_live=True,
        description=(
            "Broker-order state model and JSON/JSONL store are available for "
            "provider, broker order id, exchange order id, exchange status, "
            "acknowledgement, reject, cancel, modification, fill, and timestamp "
            f"evidence ({len(broker_order_state_model_fields())} state fields, "
            f"{len(broker_order_event_fields())} event fields)."
        ),
    ),
    LiveMoneyReadinessGate(
        code="IDEMPOTENT_ORDER_ROUTING",
        status="DONE",
        required_before_live=True,
        description=(
            "Broker-order idempotency contract is available: deterministic "
            "client order ids, durable reservations, duplicate reservation "
            "suppression, and explicit retry attempts for entries, exits, and "
            f"retries (client id builder: {build_broker_client_order_id.__name__})."
        ),
    ),
    LiveMoneyReadinessGate(
        code="BROKER_POSITION_RECONCILIATION",
        status="DONE",
        required_before_live=True,
        description=(
            "Broker-truth reconciliation contract is available for pre-startup, "
            "during-supervision, and after-restart comparisons between TFIS "
            "position/order expectations and supplied broker position/order-book "
            f"snapshots (engine: {reconcile_broker_truth.__name__})."
        ),
    ),
    LiveMoneyReadinessGate(
        code="PARTIAL_FILL_AND_REJECT_HANDLING",
        status="DONE",
        required_before_live=True,
        description=(
            "Broker-order state supports pending, partial fill, filled, "
            "rejected, stale, cancel-failed, and modify-failed transitions with "
            "durable quantities, reject reasons, failure reasons, timestamps, "
            "and operator-attention classification."
        ),
    ),
    LiveMoneyReadinessGate(
        code="LIVE_EXIT_PROTECTION",
        status="DONE",
        required_before_live=True,
        description=(
            "Live exit-protection contract is available for target, stoploss, "
            "forced close, emergency exit, and kill-switch rules, including "
            "market-event-ingress and operator-approval requirements "
            f"(validator: {validate_live_exit_protection_plan.__name__})."
        ),
    ),
    LiveMoneyReadinessGate(
        code="MARKET_EVENT_INGRESS_FOR_LIVE",
        status="DONE",
        required_before_live=True,
        description=(
            "Live market-event ingress evidence contract is available for "
            "websocket or broker-event mode, connected heartbeat, required "
            "symbol subscription/evidence, duplicate-sequence rejection, and "
            f"monotonic event checks (validator: {validate_live_market_event_ingress.__name__})."
        ),
    ),
    LiveMoneyReadinessGate(
        code="MULTI_DAY_LIVE_POSITION_RECOVERY",
        status="DONE",
        required_before_live=True,
        description=(
            "Live position recovery contract is available for overnight, expiry, "
            "forced-close, rollover-required, and next-day resume scenarios, "
            "with broker truth and reconciliation required for every case "
            f"(validator: {validate_live_position_recovery_plan.__name__})."
        ),
    ),
    LiveMoneyReadinessGate(
        code="OPERATOR_LIVE_APPROVAL_AND_KILL_SWITCH",
        status="DONE",
        required_before_live=True,
        description=(
            "Live operator-control contract is available for explicit "
            "operator approval, expiring approval windows, kill-switch state, "
            "and durable audit events before live-order mode can be enabled "
            f"(validator: {validate_live_operator_controls.__name__})."
        ),
    ),
    LiveMoneyReadinessGate(
        code="LIVE_EXECUTION_GATE_DISABLED_BY_DEFAULT",
        status="DONE",
        required_before_live=True,
        description=(
            "A broker-neutral live execution gate now connects order-routing "
            "enablement, durable broker-order intent, idempotency reservation, "
            "operator controls, exit protection, market-event ingress, startup/"
            "resume evidence, and broker reconciliation; it blocks live routing "
            "unless every gate passes and routing is explicitly enabled "
            f"(validator: {validate_live_execution_gate.__name__})."
        ),
    ),
)


def load_live_money_boundary_status() -> LiveMoneyBoundaryStatus:
    pending = tuple(gate for gate in LIVE_MONEY_READINESS_GATES if gate.status != "DONE")
    status = (
        "LIVE_MONEY_CONTRACT_GATES_COMPLETE_ROUTING_DISABLED"
        if not pending
        else "BLOCKED_FOR_LIVE_MONEY"
    )
    message = (
        "TFIS live-money contract gates are implemented, but live order routing "
        "remains disabled until an operator approval artifact exists and a "
        "separate reviewed change enables broker routing."
        if not pending
        else (
            "TFIS live-money order routing is intentionally blocked. "
            f"{len(pending)} required gate(s) remain before live order placement can be considered."
        )
    )
    return LiveMoneyBoundaryStatus(
        status=status,
        live_money_ready=False,
        paper_runtime_safe=True,
        order_routing_enabled=False,
        message=message,
        gates=LIVE_MONEY_READINESS_GATES,
    )


__all__ = [
    "LIVE_MONEY_READINESS_GATES",
    "LiveMoneyBoundaryStatus",
    "LiveMoneyReadinessGate",
    "load_live_money_boundary_status",
]
