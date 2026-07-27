# TFIS Live-Money Execution And Reconciliation Boundary

Status as of Monday, July 27, 2026: `LIVE_MONEY_NO_GO_ROUTING_DISABLED`.

TFIS remains paper-safe. The current shared lifecycle supervisor manages paper
orders and paper positions from selected-contract quote/bar evidence. It polls
the broker adapter for selected-contract market events; the active lifecycle
path does not use a websocket/event stream for entry, target, stoploss, or
forced-close management.

## Current Paper Behavior

- A finalized strategy decision creates a waiting paper order, not a broker
  order.
- The shared supervisor polls selected-contract quote/bar evidence and fills
  the paper order only when the configured paper trigger is satisfied.
- Target, stoploss, FSL, expiry force-close, fresh-entry-required, and
  carry-forward decisions are local paper-state transitions.
- Broker adapter `place_order`, `modify_order`, and `cancel_order` remain
  blocked for the current paper runtime.
- Paper position state is useful operational evidence, but it is not broker
  truth and must not be reused as live-money truth.

## Required Live-Money Gates

These gates must be implemented, tested, and operator-approved before TFIS can
place live orders:

1. `DONE` Broker order-state model: `src/tfis/broker/broker_order_state.py`
   now provides a broker-agnostic state/event model plus JSON/JSONL store for
   provider, broker order id, exchange order id, exchange status,
   acknowledgement, reject, cancel, modification, fill, and timestamp
   evidence. This is evidence modeling only; it does not place live orders.
2. `DONE` Idempotent order routing contract:
   `src/tfis/broker/broker_order_idempotency.py` now provides deterministic
   restart-stable client order ids, durable reservation records, duplicate
   reservation suppression, explicit retry attempts, and reservation-to-
   broker-order-state linkage. This is route-safety infrastructure only; it
   does not place live orders.
3. `DONE` Broker position/order-book reconciliation contract:
   `src/tfis/broker/broker_reconciliation.py` now compares TFIS position and
   broker-order expectations with supplied broker position/order-book truth for
   pre-startup, during-supervision, and after-restart scopes. This does not
   fetch broker truth itself and does not place live orders.
4. `DONE` Partial-fill and reject handling:
   `src/tfis/broker/broker_order_state.py` now models pending, partial-fill,
   filled, rejected, stale, cancel-failed, and modify-failed states with
   durable quantities, reject/failure reasons, timestamps, and a shared
   operator-attention classifier. Broker reconciliation can then detect drift
   against supplied broker truth.
5. `DONE` Live exit protection:
   `src/tfis/broker/live_exit_protection.py` defines and validates target,
   stoploss, forced-close, emergency-exit, and kill-switch protection rules,
   including market-event-ingress and operator-approval requirements. This is
   a protection contract; it does not place or modify broker orders.
6. `DONE` Market-event ingress for live execution:
   `src/tfis/broker/live_market_event_ingress.py` validates websocket or
   broker-event mode, connected heartbeat freshness, required symbol
   subscriptions and event evidence, duplicate sequence rejection, and
   monotonic event ordering. Polling-only evidence still fails this contract.
7. `DONE` Multi-day live-position recovery:
   `src/tfis/broker/live_position_recovery.py` validates overnight, expiry,
   forced-close, rollover-required, and next-day resume behavior from supplied
   broker truth before startup/resume can be considered safe. This does not
   fetch broker truth itself and does not place live orders.
8. `DONE` Operator approval and kill switch:
   `src/tfis/broker/live_operator_controls.py` provides explicit live-mode
   approval records, expiring approval windows, kill-switch state, and durable
   JSONL audit events. The validator fails missing/expired approval, active or
   unavailable kill switch, and missing audit evidence.

Current live-money contract-gate blocker count: 0 for contract scaffolding.
Live-money routing is still `NO-GO`: live order routing remains disabled until
real broker truth, broker-event/websocket ingress, operator approval,
kill-switch, idempotency, and reconciliation evidence are supplied through a
separate reviewed enablement change.

## Verification Surface

- `scripts/show_tfis_live_money_boundary_status.py`
- `scripts/pre_live_readiness.py`

The readiness check is expected to pass while reporting that live-money order
routing is intentionally blocked. A future live-money implementation must
change this document, the boundary status, tests, operator guide, and readiness
criteria in the same reviewed change set.
