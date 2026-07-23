# TFIS Paper-Live Go/No-Go Review

Review date: Wednesday, July 22, 2026.

Decision: `NO-GO_FOR_LIVE_MONEY`.

TFIS is improved for paper-live operation and operator recovery, but it is not
approved for live-money order routing. The live-money contract gates are now
implemented as broker-neutral evidence/control infrastructure, but the current
runtime remains paper-safe and intentionally blocked from broker order
placement until a separate reviewed change enables live routing.

## Current Paper-Live Evidence

- Single TFIS startup path exists through
  `scripts/reset_tfis_dashboard_and_watchers.ps1 -MorningStartup`.
- FYERS auth preparation is application/provider-owned: existing token is
  validated first, refresh is serialized by a TFIS-owned lock, and strategy
  wrappers run with refresh skipped from the app startup path.
- Separate S21/S23 scheduled morning tasks are no longer the normal startup
  route. `TFIS Morning Startup` is the preferred scheduled task.
- Full reset is market-session guarded and refuses in-market process stops
  unless an operator explicitly passes `-ForceInMarketReset`.
- Paper order routing remains blocked by adapter/config guardrails.
- Live-money boundary status is `BLOCKED_FOR_LIVE_MONEY`,
  `live_money_ready=false`, and `order_routing_enabled=false`.
- Broker order-state modeling now exists as a broker-agnostic evidence layer:
  `src/tfis/broker/broker_order_state.py` persists broker order ids,
  exchange ids/statuses, acknowledgements, rejects, cancels, modifications,
  fills, timestamps, and event history without enabling live routing.
- Idempotent broker-order reservation now exists as a broker-agnostic safety
  layer: `src/tfis/broker/broker_order_idempotency.py` creates deterministic
  restart-stable client order ids, records reservations durably, suppresses
  duplicate reservations, distinguishes explicit retry attempts, and can link
  a consumed reservation to persisted broker-order state.
- Broker-truth reconciliation now exists as a broker-agnostic comparison
  engine: `src/tfis/broker/broker_reconciliation.py` compares TFIS position
  expectations and persisted broker-order state against supplied broker
  position/order-book snapshots for pre-startup, supervision, and restart
  scopes.
- Broker execution-state handling now covers pending, partial-fill, filled,
  rejected, stale, cancel-failed, and modify-failed transitions through
  durable broker-order state, including quantities, reject/failure reasons,
  timestamps, and operator-attention classification.
- Live exit protection now has a broker-neutral contract:
  `src/tfis/broker/live_exit_protection.py` validates target, stoploss,
  forced-close, emergency-exit, and kill-switch rules, including market-event
  ingress and operator-approval requirements.
- Live market-event ingress now has a broker-neutral evidence contract:
  `src/tfis/broker/live_market_event_ingress.py` validates websocket or
  broker-event mode, fresh heartbeat, required symbol subscriptions/evidence,
  duplicate sequence rejection, and monotonic event ordering. Polling-only
  evidence fails this contract.
- Multi-day live position recovery now has a broker-truth contract:
  `src/tfis/broker/live_position_recovery.py` validates overnight, expiry,
  forced-close, rollover-required, and next-day resume cases with broker truth
  and reconciliation required for every scenario.
- Live operator approval and kill-switch governance now has a durable control
  contract: `src/tfis/broker/live_operator_controls.py` records expiring
  live-mode approvals, kill-switch state, and JSONL audit events, and fails
  missing/expired approval, active/unavailable kill switch, or missing audit
  evidence.
- Waiting-order status is clean for the configured roots:
  S23 `waiting=0/current=0/stale=0`, S21 `waiting=0/current=0/stale=0`.
- Runtime reconciliation is clean:
  S23 `positions=3/orders=18/conflicts=0`,
  S21 `positions=0/orders=14/conflicts=0`.
- Lifecycle-audit visibility exists, but current historical artifacts predate
  the new audit writer, so S23 and S21 show `ATTENTION` for missing legacy
  audit files while actionable state count is zero.
- Runtime status console now reports guardrails, broker health, heartbeats,
  lifecycle audit, waiting orders, restart/recovery status, routing safety,
  reconciliation, fresh-entry handoff, latest operator control event, and TFIS
  process counts.

## Latest Validation Evidence

- Focused startup/auth/runtime validation: `80 passed`.
- Live-money boundary validation: `95 passed`.
- Paper runtime invariant validation: `105 passed`.
- Finalizer/runtime/live-boundary validation: `101 passed`.
- Promotion/handoff/supervisor validation: `55 passed`.
- Broader finalizer/promotion/supervisor/dashboard/readiness/broker-boundary
  validation: `118 passed`.
- Broker/data ingress runtime validation: `91 passed` and `101 passed` packs.
- Runtime reconciliation/status/readiness/dashboard validation: `103 passed`.
- Supervisor auditability validation: `48 passed`, plus `94 passed` broader
  runtime/readiness/dashboard pack.
- Lifecycle-audit and finalizer evidence validation: `83 passed`.
- Waiting-order gate validation: `80 passed`, plus `112 passed` broader
  dashboard/runtime/readiness/status pack.
- Operator-control evidence validation: `33 passed`.
- Restart/recovery status validation: `10 passed`, plus successful real
  `scripts/show_tfis_runtime_status.ps1` run.
- Broker order-state model validation:
  `tests/unit/test_broker_order_state.py` and
  `tests/unit/test_live_money_boundary_status.py` at `5 passed`.
- Broker idempotency validation:
  `tests/unit/test_broker_order_idempotency.py` plus the boundary/readiness
  pack at `28 passed`.
- Broker reconciliation validation:
  `tests/unit/test_broker_reconciliation.py` plus the boundary/readiness pack
  at `24 passed`.
- Partial-fill/reject validation:
  broker state, idempotency, reconciliation, boundary, and readiness pack at
  `34 passed`.
- Live exit protection validation:
  exit-protection, broker state/idempotency/reconciliation, boundary, and
  readiness pack at `38 passed`.
- Live market-event ingress validation:
  ingress, exit-protection, boundary, and readiness pack at `28 passed`.
- Multi-day recovery validation:
  recovery, ingress, boundary, and readiness pack at `28 passed`.
- Operator live approval/kill-switch validation:
  operator controls, recovery, boundary, and readiness pack at `28 passed`.
- Current `scripts/pre_live_readiness.py --profile prod --json` returns
  `overall_status=PASS` for paper-live readiness.
- `scripts/validate_project.py` returns `PROJECT VALIDATION PASSED`.

## Remaining Live-Money Blockers

These are required before live order placement can be considered:

1. `DONE` Broker order-state model: persist broker order ids, exchange
   statuses, acknowledgements, rejects, cancels, modifications, fills, and
   timestamps through the broker-agnostic state/event store. This does not
   enable live routing.
2. `DONE` Idempotent order routing contract: restart-safe client order ids,
   durable reservations, duplicate-order prevention, explicit retry attempts,
   and reservation-to-broker-order-state linkage. This does not enable live
   routing.
3. `DONE` Broker position/order-book reconciliation contract: compare TFIS
   state with supplied broker positions and order book snapshots before
   startup, during supervision, and after restart. This does not fetch broker
   truth itself or enable live routing.
4. `DONE` Partial-fill and reject handling: handle pending, partial, filled,
   rejected, stale, cancellation-failed, and modification-failed states with
   durable quantities, reasons, timestamps, and operator-attention
   classification.
5. `DONE` Live exit protection: define and validate target, stoploss,
   forced-close, emergency-exit, and kill-switch protection rules, including
   market-event-ingress and operator-approval requirements.
6. `DONE` Market-event ingress for live execution: validate websocket or
   broker-event mode, fresh heartbeat, required symbol subscriptions/evidence,
   duplicate-sequence rejection, and monotonic event ordering. Polling-only
   evidence fails this contract.
7. `DONE` Multi-day live-position recovery: validate overnight, expiry,
   forced-close, rollover-required, and next-day resume scenarios with broker
   truth and reconciliation required for every case.
8. `DONE` Operator approval and kill switch: require explicit expiring
   live-mode approval, visible kill-switch state, and durable audit events
   before any live-order mode can be enabled.

## Manual Operator Controls That Still Matter

- Run `scripts/pre_live_readiness.py --profile prod --require-token` before
  market start when token readiness must be proven.
- Use `scripts/show_tfis_runtime_status.ps1` as the read-only TFIS health and
  recovery console.
- Use `scripts/reset_tfis_dashboard_and_watchers.ps1 -MorningStartup` as the
  normal application startup path.
- Use `scripts/refresh_tfis_operator_dashboard.ps1` for dashboard-only
  in-market refresh.
- Use `scripts/pause_tfis_runtime.ps1` and `scripts/resume_tfis_runtime.ps1`
  for TFIS paper-runtime pause/resume control.
- Use the TFIS paper-order finalizer after cutoff if stale waiting orders are
  reported.

## Final Decision

Paper-live readiness: `GO` for the current blocked-paper operating contract,
subject to pre-market token check when broker access is needed.

Live-money contract gates: `COMPLETE`.

Live-money routing readiness: `NO-GO`. Live order routing remains disabled
until an operator approval artifact exists and a separate reviewed change
enables broker routing.
