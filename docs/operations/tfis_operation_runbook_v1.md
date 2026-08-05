# TFIS Operation Runbook V1

## Purpose

This runbook explains:

- how to use the current TFIS system today, Wednesday, August 5, 2026;
- what will happen if we run the current system before market open on a fresh
  next session;
- what will and will not happen automatically when the NSE market opens.

This is an operator runbook for the current accepted repository state.

External broker-order authority remains `NONE`.

## Current System Boundary

The current accepted stack is:

- unified internal-paper certification runner:
  `scripts/run_tfis_internal_paper.py`
- unified live-market internal-paper operator launcher:
  `scripts/run_live_market_internal_paper.py`
- unified professional dashboard builder/server:
  `scripts/run_tfis_dashboard.py`
- FYERS read-only diagnostics:
  `scripts/run_broker_diagnostics.py`
- FYERS token preparation:
  `scripts/fyers_token_refresh.py --prepare`

Important current truth:

- the live-market internal-paper operator entry point is now:
  `.\.venv\Scripts\python.exe scripts\run_live_market_internal_paper.py --mode live-market-internal-paper --enabled-profile baseline --dashboard-port 8766 --poll-seconds 5 --session-date 2026-08-05 --reconstruct-if-late prepare`;
- deterministic dashboard/runtime certification is green, but the governing
  next-session operator gate is now the authoritative readiness projection at
  `reports/unified_readiness/authoritative_readiness_projection.json`;
- the system is still internal-paper plus read-only observation only;
- a continuous unified supervisor does now exist through
  `scripts/run_tfis_internal_paper.py --continuous-supervisor`, but its
  current accepted use is still tightly controlled and read-only at the broker
  boundary;
- a dedicated live-market registry now exists at
  `config/live_market_internal_paper_strategy_instances.yaml` and includes
  `S21/BANKNIFTY`, `S22/RELIANCE`, `S22/TCS`, `S22/INFY`, and `S23/NIFTY`;
- no broker order placement, modification, cancellation, square-off, or live
  position mutation is allowed;
- the old deterministic registry at
  `config/internal_paper_strategy_instances.yaml` still exists for bounded
  non-live certification only;
- the fresh live-market prepare evidence is now emitted under
  `reports/live_market_internal_paper/`;
- honest remaining live blockers are the supervisor hot-path overrun and the
  stale dashboard analytics `BLOCKED_ACCOUNT` mismatch for `S21` and `S23`.

## Fastest Safe Command Today

Use this first:

```powershell
.\.venv\Scripts\python.exe scripts\run_live_market_internal_paper.py --mode live-market-internal-paper --enabled-profile baseline --dashboard-port 8766 --poll-seconds 5 --session-date 2026-08-05 --reconstruct-if-late prepare
```

What this does:

- reuses the canonical FYERS token flow;
- runs read-only broker diagnostics;
- runs complete-session preflight;
- writes fresh live-market internal-paper reports;
- keeps external broker-order authority at `NONE`.

## Monday, August 3, 2026 Live Status Addendum

As of `14:40 IST` on Monday, August 3, 2026:

- one protected late-start live supervisor is still running on
  `NSE:2026-08-03:UNIFIED_INTERNAL_PAPER`;
- FYERS diagnostics were revalidated as `AUTHENTICATED`;
- external broker-order authority is still `NONE`;
- the live cadence root cause is now understood:
  the old running process sleeps a full `5s` after work completion, so total
  loop cadence becomes work time plus sleep;
- the next-session code path has been patched to wake at the earlier of the
  next poll deadline or the next critical market-time boundary, but that fix
  will only take effect after a future restart;
- today's remaining live value is the `15:00` EOD window and the graceful
  post-market shutdown/restart assessment.

## What The System Is Doing Right Now

The current registry enables three strategy instances on one internal-paper
account:

- `S21_BANKNIFTY_INTERNAL_PAPER_A`
- `S22_RELIANCE_INTERNAL_PAPER_A`
- `S23_NIFTY_INTERNAL_PAPER_A`

The current runner supports two distinct modes:

- deterministic unified projection from accepted strategy artifacts; and
- a bounded continuous supervisor for internal-paper plus read-only live
  observation.

That means:

- it loads the enabled strategy registry;
- it can build a deterministic session result;
- it can also run a continuous supervisor loop with read-only FYERS inputs and
  internal-paper state;
- it writes reports under `reports/dashboard_v1/`;
- it writes supervisor-state and live-closure reports under
  `reports/live_supervisor/` and `reports/live_closure_20260803/`;
- it can build and serve a read-only dashboard from those reports;
- it still does not create broker-write financial actions by itself.

## Safe Commands To Use Today

### 1. Prepare FYERS Authentication

Run from an operator shell:

```powershell
.\.venv\Scripts\python.exe scripts\fyers_token_refresh.py --prepare
```

What this does:

- validates or refreshes the FYERS session token;
- prepares read-only broker access;
- does not grant order-write authority.

### 2. Run Read-Only Broker Diagnostics

```powershell
.\.venv\Scripts\python.exe scripts\run_broker_diagnostics.py --broker fyers
```

What this does:

- checks configuration, credentials, authentication, and read health;
- confirms order-write authority is still separate and still disabled.

### 3. Refresh Unified Internal-Paper Reports

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py
```

What this does:

- runs the deterministic unified S21/S22/S23 certification flow;
- writes fresh reports into `reports/dashboard_v1/`;
- does not start a background runtime;
- does not subscribe to live market ticks;
- does not create broker orders.

### 3A. Start The Continuous Unified Supervisor

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py --continuous-supervisor --poll-seconds 5 --dashboard-port 8766
```

What this does:

- starts one internal-paper continuous supervisor session;
- uses FYERS only in read-only mode;
- writes heartbeat/checkpoint/report state under `tmp/tfis_supervisor_state/`
  and `reports/live_supervisor/`;
- must not be started twice;
- must be stopped with:

```powershell
New-Item -ItemType File -Force tmp\tfis_supervisor_state\continuous_unified_supervisor.stop
```

### 4. Build The Dashboard

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_dashboard.py
```

What this does:

- builds static dashboard files under `tmp/tfis_dashboard_v1/`;
- reads the projection from
  `reports/dashboard_v1/s21_s22_s23_dashboard_projection.json` by default;
- does not start a server unless `--serve` is supplied.

### 5. Serve The Dashboard Locally

```powershell
.\.venv\Scripts\python.exe scripts\run_tfis_dashboard.py --serve --port 8766
```

Open:

`http://127.0.0.1:8766/index.html`

What this does:

- serves the built dashboard;
- exposes read-only local APIs and an SSE event endpoint;
- remains a local read-only operator interface;
- does not create financial actions.

## Recommended Operator Sequence Today

Use this order on Monday, August 3, 2026:

1. Run FYERS token preparation.
2. Run FYERS read-only diagnostics.
3. Run `scripts/run_tfis_internal_paper.py`.
4. Run `scripts/run_tfis_dashboard.py --serve --port 8766`.
5. If using continuous observation, start exactly one supervisor.
6. Review:
   - `reports/unified_readiness/authoritative_readiness_projection.json`
   - `reports/unified_readiness/clean_start_operator_package.md`
   - `reports/live_supervisor/complete_session_preflight.json`
   - `reports/live_closure_20260803/live_closure_summary.md`
   - `reports/s22_multi_stock/s22_multi_stock_summary.md`
   - `reports/dashboard_v1/dashboard_summary.md`
   - the dashboard itself

Expected readiness state today:

- authoritative verdict controls:
  - `GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION`, or
  - `NO_GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION`

Expected authority state today:

- external broker orders: `NONE`
- external paper orders: `NONE`
- live orders: `NONE`

## What Happens Tomorrow At Market Open

This section refers to Tuesday, August 4, 2026.

### If You Only Run The Current Accepted Commands

If tomorrow morning you run:

1. `scripts/fyers_token_refresh.py --prepare`
2. `scripts/run_broker_diagnostics.py --broker fyers`
3. `scripts/run_tfis_internal_paper.py`
4. `scripts/run_tfis_dashboard.py --serve --port 8766`

then the following is the exact current system behavior:

1. TFIS prepares read-only FYERS access.
2. TFIS validates read-only broker diagnostics.
3. TFIS loads the enabled strategy registry.
4. TFIS runs the deterministic unified certification coordinator.
5. TFIS writes refreshed report artifacts.
6. TFIS builds or serves the read-only dashboard.
7. At `09:15` market open, no automatic broker order is sent.
8. No live broker position is opened, modified, or closed.
9. No external paper order is sent.
10. The dashboard continues to show the accepted internal-paper projection and
    read-only health information.

### Why No Automatic Trading Happens Yet

Because the current accepted slice is:

- unified deterministic internal-paper projection;
- professional read-only dashboard;
- read-only FYERS diagnostics;
- no approved broker-write authority;
- no accepted autonomous live market-session execution loop in this runbook.

So tomorrow's market open is operationally:

- a supervised read-only and internal-paper observation session;
- not a live trading session.

## The Current Runtime Sequence Model

The accepted multi-strategy runtime coordinator documents this startup order:

1. `load_enabled_strategy_registry`
2. `validate_persistence_and_recovery`
3. `run_broker_diagnostics_once_per_broker_account`
4. `restore_carried_positions`
5. `build_premarket_plans`
6. `request_shared_market_subscriptions`
7. `route_immutable_observations`
8. `coordinate_opening_orpt_rc_eod`
9. `validate_execution_intents`
10. `route_accepted_intents_to_account_coordinator`
11. `simulate_internal_paper_orders_and_fills`
12. `update_position_cycles_and_accounting`
13. `emit_dashboard_read_models`
14. `checkpoint_state`
15. `graceful_shutdown`

Important current limitation:

In the current accepted script path, this sequence is exercised as a
deterministic certification/projection flow. It is not yet the same thing as a
real-time all-day live market runtime.

## What To Watch In Tomorrow's Session

Tomorrow, Tuesday, August 4, 2026, the operator should focus on:

- FYERS token readiness before `09:15`;
- read-only diagnostics health;
- dashboard availability on local port `8766`;
- whether S22 RELIANCE live opening evidence can be captured cleanly;
- whether opening, ORPT, and RC evidence can replace the current deterministic
  S22 timing supplement;
- whether any command unexpectedly implies broker-write authority
  (it should not).

## What The Dashboard Should Show

The dashboard should show:

- system and broker health;
- account-level internal-paper state;
- strategy instances for S21, S22, and S23;
- plan, execution, position, accounting, and operations sections;
- alerts, evidence quality, and known gaps;
- read-only API health.

It should not:

- calculate hidden strategy formulas in the frontend;
- place manual broker buy or sell orders;
- mutate external broker state.

## Known Limitations For Tomorrow

These limitations still apply on Tuesday, August 4, 2026:

- the current registry session scope is still
  `NSE:2026-08-03:INTERNAL_PAPER`;
- the current scripts are accepted for unified internal-paper certification and
  dashboard serving, not full live-session autonomy;
- S22 RELIANCE still needs real opening/ORPT/RC evidence;
- the dashboard is read-only;
- broker order authority remains `NONE`.

## Operator Verdict For Tomorrow

Use the current TFIS stack tomorrow as:

- a read-only broker-health and dashboard session;
- a deterministic unified internal-paper projection session;
- an evidence-gathering session for S22 RELIANCE live opening/ORPT/RC capture.

Do not use it tomorrow as:

- a broker-connected live order engine;
- an external paper-trading engine;
- an autonomous market-open execution service.

## Fast Checklist

### Today, Monday, August 3, 2026

```powershell
.\.venv\Scripts\python.exe scripts\fyers_token_refresh.py --prepare
.\.venv\Scripts\python.exe scripts\run_broker_diagnostics.py --broker fyers
.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py
.\.venv\Scripts\python.exe scripts\run_tfis_dashboard.py --serve --port 8766
```

### Tomorrow, Tuesday, August 4, 2026

Do not reuse the old simple sequence blindly. Use the clean-start package in:

- `reports/unified_readiness/clean_start_operator_package.md`

For the next before-market-open session, the required command order is:

1. `.\.venv\Scripts\python.exe scripts\fyers_token_refresh.py --prepare`
2. `.\.venv\Scripts\python.exe scripts\run_broker_diagnostics.py --broker fyers`
3. `New-Item -ItemType File -Force tmp\tfis_supervisor_state\continuous_unified_supervisor.stop`
   if the previous late-start supervisor is still active
4. `.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py --preflight-complete-session`
5. `.\.venv\Scripts\python.exe scripts\run_tfis_internal_paper.py --continuous-supervisor --poll-seconds 5 --dashboard-port 8766`
6. `.\.venv\Scripts\python.exe scripts\run_tfis_dashboard.py --serve --port 8766`

Expected result:

- broker diagnostics authenticated;
- preflight returns `READY_FOR_COMPLETE_UNIFIED_SESSION`;
- authoritative readiness projection returns
  `GO_FOR_NEXT_COMPLETE_UNIFIED_SESSION`;
- dashboard up;
- no external order action at `09:15`;
- internal-paper only.
