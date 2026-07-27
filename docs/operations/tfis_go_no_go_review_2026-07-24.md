# TFIS Live-Money Readiness Go/No-Go Review

Review date: Friday, July 24, 2026.

Decision: `NO-GO_FOR_LIVE_MONEY`.

TFIS is acceptable for the current blocked paper-live operating contract, but
it is not approved for live-money order routing. The live execution contracts
are now connected behind a broker-neutral gate, and that gate remains disabled
by default.

## Current Evidence

- `scripts/show_tfis_runtime_status.ps1` reports `MarketSessionPhase=PRE_MARKET`
  and `RestartRecoveryStatus=READY_FOR_MORNING_STARTUP`, which is expected
  before the scheduled app startup.
- Paper guardrails pass for S21 and S23.
- Broker health probes report FYERS connected for S21 and S23.
- Waiting-order status is clean for the configured roots:
  S23 `waiting=0/current=0/stale=0`, S21 `waiting=0/current=0/stale=0`.
- Runtime reconciliation is clean:
  S23 `positions=4/orders=20/conflicts=0`,
  S21 `positions=0/orders=16/conflicts=0`.
- Lifecycle audit is clean in the market-phase-aware runtime console:
  S23 and S21 both report `PASS`.
- Order routing safety remains blocked:
  place, modify, and cancel order paths are blocked for S21 and S23.
- Live-money boundary status is
  `LIVE_MONEY_NO_GO_ROUTING_DISABLED`,
  `live_money_ready=false`, and `order_routing_enabled=false`.

## Completed Since July 22

- Dashboard terminology now separates active trades from finalized orders.
- The global Orders Manager route is served correctly.
- Morning startup now prepares broker auth once and launches configured
  strategy wrappers concurrently instead of serializing S21 behind S23.
- Runtime status is market-phase aware and no longer asks for supervisor
  restart after market cutoff when current order/reconciliation checks are
  clean.
- Windows process detection now includes slash-normalized repo matching,
  virtualenv parent/child handling, process roles, and dashboard port-owner
  fallback through `netstat -ano`.
- The paper lifecycle supervisor fails closed on stale, missing, or
  future-dated selected-contract events before lifecycle logic can fill
  orders or manage positions.
- Live startup/resume validation now requires supplied broker truth when TFIS
  expects open or carried live positions.
- A disabled-by-default live execution gate now connects broker-order intent,
  idempotency reservation, operator controls, exit protection, market-event
  ingress, startup/resume evidence, and broker reconciliation.

## Validation Evidence

- Runtime/process/status focused tests: `16 passed`.
- Paper lifecycle supervisor runtime suite: `55 passed`.
- Live position recovery plus broker reconciliation tests: `11 passed`.
- Live execution gate, live-money boundary, and readiness tests: `23 passed`.
- `scripts/validate_project.py`: `PROJECT VALIDATION PASSED`.
- `scripts/pre_live_readiness.py --profile prod --json`: `overall_status=PASS`.
- `scripts/show_tfis_live_money_boundary_status.py --json`: live routing
  remains disabled.

## Remaining Requirements Before Live Money

1. Observe the next scheduled paper startup end to end after the concurrent
   wrapper and dashboard fixes.
2. Provide a reviewed live-routing enablement change that explicitly turns on
   routing only through `validate_live_execution_gate`.
3. Supply real broker position/order-book truth to the startup/resume and
   reconciliation contracts before any live position is managed.
4. Supply real broker-event or websocket market ingress evidence; polling-only
   evidence must remain insufficient for live execution.
5. Create explicit operator live approval and kill-switch artifacts for the
   session.
6. Run a final human operator approval review immediately before any live order
   mode is enabled.

## Final Decision

Paper-live readiness: `GO` for the current blocked paper operating contract,
subject to pre-market token verification when broker access is required.

Live-money contract infrastructure: implemented but disabled.

Live-money routing readiness: `NO-GO`. Live order routing remains disabled
until a separate reviewed change enables routing through the live execution
gate with all broker-truth, ingress, approval, and reconciliation evidence
present.
