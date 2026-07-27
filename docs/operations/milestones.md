# Milestones

## Current Snapshot

- as of Thursday, July 23, 2026, the operator dashboard now separates
  finalized orders from open trades: the global Active Trades Monitor shows
  open paper positions only, the new global Orders Manager shows
  waiting/actionable finalized paper orders across strategies, strategy pages
  split `Active Trades` from `Orders Finalized`, and the dashboard manifest
  exposes both `trades_page` and `orders_page`
- as of Thursday, July 23, 2026, the live-paper morning startup was observed
  end to end: the Windows scheduled task fired at `09:08:38`, S23 initially
  produced `09:16` artifacts, a sequential-wrapper startup gap delayed S21,
  manual recovery brought both S21 and S23 through `09:16`, `09:25`, and
  `09:30`, final paper order states were written, the shared lifecycle
  supervisor was started once, and prod readiness reported PASS
- as of Thursday, July 23, 2026, `reset_tfis_dashboard_and_watchers.ps1
  -MorningStartup` now launches all configured strategy wrappers concurrently
  after app-level auth preparation and waits for all of them before shared
  supervisor startup, removing the S21-behind-S23 serialization issue for
  future scheduled runs
- as of Thursday, July 23, 2026, the shared runtime status console is now
  market-phase aware: it prints `MarketSessionPhase`, reports missing
  supervisor visibility as urgent only during `ACTIVE_MARKET`, reports
  `AFTER_MARKET_IDLE` after cutoff when order/reconciliation checks are clean,
  and filters terminal historical paper orders out of missing lifecycle-audit
  attention so live-readiness signals are quieter and more accurate
- as of Thursday, July 23, 2026, Windows dashboard process detection is
  stronger: the shared runtime helper now handles slash-normalized repo paths,
  virtualenv parent/child process discovery, process-role classification, and
  a `netstat -ano` dashboard port-owner fallback; the real status console now
  shows the dashboard listener as `DashboardProcesses=1` with
  `Role=dashboard_port_owner`
- as of Thursday, July 23, 2026, the shared paper lifecycle supervisor fails
  closed on stale selected-contract market evidence: successful quote/bar
  fetches are checked against a configurable freshness threshold before any
  waiting-order or open-position lifecycle decision, and stale/missing/future
  events write `MARKET_DATA_UNAVAILABLE` heartbeat and audit evidence instead
  of driving fills, exits, targets, SL, FSL, or rollover handling
- as of Friday, July 24, 2026, the live position recovery contract includes
  broker-truth startup/resume validation: TFIS open/carry expectations require
  supplied broker position truth, and mismatches are checked through the
  broker-neutral reconciliation engine without enabling live routing or
  fetching broker data
- as of Friday, July 24, 2026, the broker-neutral live execution gate exists
  and remains disabled by default: it connects live routing enablement,
  broker-order intent, idempotency reservation, operator controls, exit
  protection, market-event ingress, startup/resume evidence, and broker
  reconciliation into one validation decision before any future live adapter
  can place an order
- as of Friday, July 24, 2026, the updated go/no-go review is documented in
  `docs/operations/tfis_go_no_go_review_2026-07-24.md`: paper-live is `GO`
  only for the blocked paper contract, live execution infrastructure is
  `COMPLETE_BUT_DISABLED`, and live-money routing remains `NO-GO`
- as of Monday, July 27, 2026, the FYERS-backed S23 snapshot preflight path is
  less brittle during morning startup: transient broker normalization failures
  for quote or option-chain snapshot reads are retried with bounded attempts,
  successful retries are visible in preflight issues, and exhausted malformed
  broker data still fails closed without placing orders
- as of Monday, July 27, 2026, paper trade ledger writes no longer use a
  shared temp-file replace path for append operations; session and global
  ledger JSONL rows are appended under per-ledger lock files so concurrent
  supervisor/manager writers do not collide or silently lose rows
- as of Monday, July 27, 2026, runtime process reporting separates raw process
  discovery from logical component counting, so Windows launcher/child pairs
  remain visible for diagnostics but dashboard/supervisor counts reflect one
  logical runtime component
- as of Monday, July 27, 2026, active-market shared-supervisor recovery is
  available through the existing reset script's `-RecoverSharedSupervisor`
  mode; it performs safety checks and starts only the shared supervisor without
  full reset, dashboard rebuild, auth refresh, or strategy recalculation
- as of Wednesday, July 22, 2026, TFIS has an explicit ordered
  application-startup/live-readiness TODO track: centralize provider auth,
  correct the existing startup/reset entrypoint instead of adding duplicate
  scripts, launch enabled strategies through one app-owned path, keep
  lifecycle execution paper-safe, and only consider live-money order routing
  after broker-truth reconciliation and operator controls are proven
- as of Wednesday, July 22, 2026, the first application-startup hardening
  slice is implemented: FYERS auth preparation now validates and reuses an
  existing token before refreshing, refresh fallback is serialized by one
  TFIS-owned lock, `fyers_token_refresh.py --prepare` exposes that
  validate-or-refresh path, and the existing dashboard/supervisor reset script
  now supports an opt-in `-MorningStartup` mode for one app-level dashboard/
  provider-auth/strategy/supervisor launch sequence
- as of Wednesday, July 22, 2026, the Windows scheduled startup pattern has
  been migrated on the host: `TFIS Morning Startup` is enabled for weekdays at
  `09:08` and points to the existing reset script's `-MorningStartup` mode,
  while the separate S21 and S23 morning scheduled tasks are disabled to avoid
  strategy-level auth-refresh races
- as of Wednesday, July 22, 2026, the full TFIS reset path is now
  market-session guarded: during `09:15-15:30` on a trading day it refuses to
  stop runtime processes without explicit `-ForceInMarketReset`, keeping
  dashboard-only refresh as the normal in-market recovery path
- as of Wednesday, July 22, 2026, TFIS now has an explicit live-money
  execution/reconciliation boundary: the current paper lifecycle is documented
  as polling-based and not live-order management, a read-only status command
  reports `BLOCKED_FOR_LIVE_MONEY`, pre-live readiness includes that boundary,
  and required gates are listed before live order placement can be considered
- as of Wednesday, July 22, 2026, the first live-money execution/
  reconciliation gate has a broker-agnostic model/evidence implementation:
  `src/tfis/broker/broker_order_state.py` persists broker order ids, exchange
  ids/statuses, acknowledgements, rejects, cancels, modifications, fills,
  timestamps, and event history through JSON/JSONL artifacts without enabling
  live order routing
- as of Wednesday, July 22, 2026, the second live-money execution/
  reconciliation gate now has broker-agnostic idempotency infrastructure:
  `src/tfis/broker/broker_order_idempotency.py` creates deterministic
  restart-stable client order ids, persists reservations, suppresses duplicate
  reservation attempts, distinguishes explicit retry attempts, and links
  consumed reservations to broker-order state without enabling live routing
- as of Wednesday, July 22, 2026, the third live-money execution/
  reconciliation gate now has broker-agnostic reconciliation infrastructure:
  `src/tfis/broker/broker_reconciliation.py` compares TFIS position
  expectations and persisted broker-order state against supplied broker
  position/order-book snapshots for pre-startup, supervision, and restart
  scopes without fetching broker truth or enabling live routing
- as of Wednesday, July 22, 2026, the fourth live-money execution/
  reconciliation gate now has explicit broker execution-state handling:
  broker-order state covers pending, partial-fill, filled, rejected, stale,
  cancel-failed, and modify-failed transitions with durable quantities,
  reject/failure reasons, timestamps, and shared operator-attention
  classification
- as of Wednesday, July 22, 2026, the fifth live-money execution/
  reconciliation gate now has broker-neutral exit-protection contract
  coverage: `src/tfis/broker/live_exit_protection.py` validates target,
  stoploss, forced-close, emergency-exit, and kill-switch rules, including
  market-event ingress and operator-approval requirements, without placing or
  modifying broker orders
- as of Wednesday, July 22, 2026, the sixth live-money execution/
  reconciliation gate now has broker-neutral live market-event ingress
  evidence coverage: `src/tfis/broker/live_market_event_ingress.py` validates
  websocket or broker-event mode, fresh heartbeat, required symbol
  subscriptions/evidence, duplicate sequence rejection, and monotonic event
  ordering; polling-only evidence fails this contract
- as of Wednesday, July 22, 2026, the seventh live-money execution/
  reconciliation gate now has broker-truth multi-day recovery contract
  coverage: `src/tfis/broker/live_position_recovery.py` validates overnight,
  expiry, forced-close, rollover-required, and next-day resume scenarios with
  broker truth and reconciliation required for every case
- as of Wednesday, July 22, 2026, the eighth live-money execution/
  reconciliation gate now has explicit operator approval and kill-switch
  governance coverage: `src/tfis/broker/live_operator_controls.py` records
  expiring live-mode approvals, kill-switch state, and durable JSONL audit
  events before any live-order mode can be enabled
- as of Wednesday, July 22, 2026, the current S21/S23 paper-runtime invariants
  were re-verified after startup hardening: the focused dashboard/supervisor/
  market-event/lifecycle/captured-session pack passed at `105 passed`, the
  operator dashboard rebuilt successfully, and project validation remained
  green
- as of Wednesday, July 22, 2026, the post-cutoff paper-order finalizer has
  been corrected into a TFIS application-level scheduled safety net while
  preserving the existing compatibility script names: it now reads
  `config/paper_lifecycle_supervisor_targets.yaml`, sweeps the configured
  S21/S23 paper artifact roots, the host task `TFIS Paper Order Finalizer` is
  enabled at `15:35`, and the old S23-only finalizer task is disabled
- as of Wednesday, July 22, 2026, the shared blocked fresh-entry promotion path
  now creates waiting paper orders from a neutral `PaperOrderDecisionIntent`
  contract instead of requiring an S23 decision-summary dataclass internally,
  while keeping the existing S23 compatibility inputs and behavior intact
- as of Wednesday, July 22, 2026, the shared paper lifecycle supervisor now
  handles selected-contract market-data fetch failures as an explicit
  fail-closed target state: it publishes `MARKET_DATA_UNAVAILABLE` heartbeat
  evidence and skips lifecycle transitions instead of letting ambiguous market
  data drive order or position changes
- as of Wednesday, July 22, 2026, the operator-facing heartbeat read-model now
  classifies fresh `MARKET_DATA_UNAVAILABLE` runtime heartbeats as `DEGRADED`
  and exposes the latest runtime status/reason code through the console and
  dashboard Operator Status panel
- as of Wednesday, July 22, 2026, the broker/data ingress failure-handling
  checklist item is closed for the current paper runtime: readiness, runtime
  logs, live-state heartbeat evidence, runtime status, and dashboard Operator
  Status now surface broker health and selected-contract market-data ambiguity
  without allowing ambiguous market data to drive lifecycle transitions
- as of Wednesday, July 22, 2026, paper runtime reconciliation now covers both
  sides of the persisted trade story: position states reconcile against the
  trade ledger, paper order states reconcile against their latest order-event
  trail, actionable waiting/fill conflicts fail readiness evidence, and local
  configured S23/S21 reconciliation plus prod readiness both remain PASS
- as of Wednesday, July 22, 2026, the shared paper lifecycle supervisor now
  writes a compact per-state `paper_lifecycle_supervisor_events.jsonl` audit
  trail for runtime skips and lifecycle steps, including lock-busy,
  selected-contract market-data unavailable, stale waiting-order expiration,
  and emitted lifecycle-step decisions
- as of Wednesday, July 22, 2026, lifecycle-supervisor audit evidence is now
  exposed through a shared read model, console command, TFIS runtime-status
  rollup, and pre-live readiness check; the same pass used the existing
  configured finalizer to close the two stale actionable S21 waiting paper
  orders from `2026-07-21`, leaving S21/S23 actionable stale order count at
  zero while prod readiness remains PASS
- as of Wednesday, July 22, 2026, stale waiting paper orders are now a named
  readiness gate: the shared waiting-order status read model and console
  command distinguish current-session waiting orders from stale/future-dated
  waiting orders, `show_tfis_runtime_status.ps1` reports `WaitingOrders`, and
  `pre_live_readiness.py` fails if any configured strategy has a stale
  actionable waiting order before startup
- as of Wednesday, July 22, 2026, operator-control evidence is more complete:
  pre-live readiness and the TFIS runtime status console now surface latest
  pause/resume action, scope, strategy, timestamp, actor, reason, and marker
  path so recovery reviews do not require opening the raw operator-control
  JSONL file
- as of Wednesday, July 22, 2026, the TFIS runtime status console also reports
  `RestartRecoveryStatus`, a read-only pending-action summary derived from
  dashboard availability, dashboard/supervisor/other TFIS process counts, and
  stale waiting-order status so operators can distinguish stopped, healthy,
  and partially recovered runtime states
- as of Wednesday, July 22, 2026, TFIS has a consolidated paper-live go/no-go
  review at `docs/operations/tfis_go_no_go_review_2026-07-22.md`: paper-live
  is acceptable only under the current blocked-paper contract, live-money
  contract gates are complete, and live-money routing remains `NO-GO` until an
  operator approval artifact exists and a separate reviewed change enables
  broker routing
- as of Wednesday, July 22, 2026, TFIS survived a real market-time startup
  recovery drill: S23 launched on schedule, S21 initially failed because of a
  simultaneous FYERS auth refresh collision, both morning wrappers were then
  hardened to retry once with `--skip-refresh` on `invalid auth code`, and a
  host-style S21 rerun completed the `2026-07-22` morning paper flow so both
  strategies reached valid session artifacts and shared lifecycle-supervisor
  startup by about `09:31 IST`
- as of Saturday, July 18, 2026, TFIS is entering a weekend
  live-money-readiness hardening track, but the repository contract still
  blocks silent live enablement until the remaining paper-runtime,
  reconciliation, ingress, and operator-control gaps are closed and explicitly
  reviewed
- as of Tuesday, July 21, 2026, the remaining shared paper review/replay/
  comparison naming seam is now closed: neutral paper aliases cover review
  summaries, replay-bundle management, and paper-vs-historical comparison
  contracts while the older S23 names remain exported for compatibility, and
  the focused regression pack for that slice passed at `92 passed`
- as of Tuesday, July 21, 2026, one more shared comparison seam is now clean:
  the `paper_vs_historical.py` loader itself now consumes the neutral
  `PaperSessionReviewer`, `PaperReviewSummary`, and `PaperReviewError`
  contracts instead of importing S23-prefixed review types directly, while the
  older S23 comparison exports remain intact; the impacted regression pack for
  this follow-up slice passed at `137 passed`
- as of Tuesday, July 21, 2026, the next shared state-orchestration seam is
  now clean as well: `expiry_governance.py` and `lifecycle_supervisor.py` now
  consume neutral `Paper...` order/position/event aliases internally instead
  of typing those generic flows through S23-specific state classes, while the
  public S23 compatibility surface remains exported; the impacted regression
  pack for that slice passed at `108 passed`
- as of Tuesday, July 21, 2026, the next shared live-decision/ledger seam is
  now clean as well: `live_prelude.py`, `live_decision.py`,
  `live_decision_timeline.py`, and `trade_ledger.py` now consume neutral
  paper position-state aliases in their shared carry-forward and ledger flows
  instead of importing S23-prefixed position-state types directly, while the
  outward S23 contracts remain exported; the impacted regression pack for that
  slice passed at `116 passed`
- as of Tuesday, July 21, 2026, the next shared order-state seam is now clean
  as well: `order_finalizer.py` and `fresh_entry_promotion.py` now consume
  neutral `PaperOrderState...` aliases internally in their generic waiting-
  order and blocked fresh-entry promotion flows instead of importing
  S23-prefixed order-state types directly, while the outward S23 contracts
  remain exported; the impacted regression pack for that slice passed at
  `115 passed`
- as of Wednesday, July 22, 2026, the shared position-manager boundary is now
  cleaner as well: `position_manager.py` now consumes neutral
  `PaperOrderState` / `PaperOrderStatus` / `PaperLiveStateStore` aliases in
  its generic order-to-position and live-state wiring paths instead of
  importing S23-prefixed order/live-state types directly, while the outward
  S23 position-manager contracts remain exported; the impacted regression pack
  for that slice passed at `124 passed`
- as of Wednesday, July 22, 2026, that same shared position-manager surface is
  now internally aligned with the paper-first contract too: the module
  declares `PaperPositionManager...` classes first and keeps the older S23
  names as compatibility aliases, with the focused regression pack and local
  `prod` readiness both passing again afterward at `124 passed` and
  `overall_status=PASS`
- as of Wednesday, July 22, 2026, the shared order-state surface is now
  cleaner as well: `order_state.py` now declares its status, state, event,
  discovery, and store types through neutral `PaperOrder...` names first,
  while the outward S23 names remain exported as compatibility aliases; the
  impacted regression pack for that slice passed at `143 passed`, and local
  `prod` readiness remained `overall_status=PASS`
- as of Wednesday, July 22, 2026, the shared position-state surface is now
  cleaner as well: `position_state.py` now declares its status, event-type,
  state, event, and store types through neutral `PaperPositionState...` names
  first, while the outward S23 names remain exported as compatibility aliases;
  the impacted regression pack for that slice passed at `131 passed`, and
  local `prod` readiness remained `overall_status=PASS`
- as of Wednesday, July 22, 2026, the shared trade-ledger surface is now
  cleaner as well: `trade_ledger.py` now declares its ledger event type, row,
  and store types through neutral `PaperTradeLedger...` names first, while the
  outward S23 names remain exported as compatibility aliases; the impacted
  regression pack for that slice passed at `139 passed`, and local `prod`
  readiness remained `overall_status=PASS`
- as of Wednesday, July 22, 2026, the shared lifecycle-supervisor surface is
  now cleaner as well: `lifecycle_supervisor.py` now declares its context,
  step, result, and supervisor types through neutral
  `PaperLifecycleSupervisor...` names first, while the outward S23 names
  remain exported as compatibility aliases; the impacted regression pack for
  that slice passed at `139 passed`, and local `prod` readiness remained
  `overall_status=PASS`
- as of Wednesday, July 22, 2026, the shared live-state surface is now
  cleaner as well: `live_state_store.py` now declares its primary settings,
  diagnostics, store, provider implementations, and build/inspect helpers in
  neutral `Paper...` names first, while the outward S23 names remain exported
  as compatibility aliases and wrappers; the impacted regression pack for that
  slice passed at `155 passed`
- as of Tuesday, July 21, 2026, TFIS also recovered the same-day scheduled
  paper-start path after a real startup audit: the S23 morning launcher no
  longer crashes when Task Scheduler omits `RunDate`, the shared
  Windows-process lock now treats reused PIDs as stale lock candidates
  instead of unconditional duplicate starts, a fresh S23 session was launched
  for `2026-07-21`, the shared lifecycle supervisor was started successfully,
  the operator dashboard was refreshed without stopping runtime, and the
  production paper-readiness gate passed afterward
- as of Tuesday, July 21, 2026, TFIS also added the first shared operator
  pause-control slice: global and per-strategy runtime pause markers now have
  dedicated PowerShell operator commands, and the shared lifecycle supervisor
  now honors those controls directly instead of forcing operators to kill
  windows just to stop one strategy temporarily
- as of Tuesday, July 21, 2026, the operator dashboard also gained the first
  shared runtime-alert/control visibility slice: index, strategy, and
  consolidated trade pages now show a shared Operator Status panel with pause
  scope, paused strategies, stale/no-stream counts, alert text, and the
  primary pause/resume/refresh commands needed during operator recovery
- as of Tuesday, July 21, 2026, that operator-control slice now also has a
  shared audit trail: pause/resume commands append JSONL events under
  `tmp/operator_controls`, the shared operator-control module can load the
  latest event generically, and the dashboard Operator Status panel now shows
  the most recent manual control action alongside the current pause state
- as of Tuesday, July 21, 2026, TFIS also gained a read-only operator status
  command: `scripts/show_tfis_runtime_status.ps1` reports the current TFIS
  runtime processes, pause scope, paused strategies, and latest operator
  control event without interrupting the active paper runtime
- as of Tuesday, July 21, 2026, the pre-live readiness gate now also fails on
  active TFIS paper-runtime pause markers, so a lingering global or
  per-strategy pause is detected before market start instead of silently
  suppressing shared supervisor management later
- as of Tuesday, July 21, 2026, the shared paper lifecycle runtime now also
  enforces one broker-neutral paper-start guardrail contract: runtime configs
  must remain on a paper-ingress source mode with paper mode enabled, no live
  orders allowed, kill switch enabled, and session kill switch inactive, and
  both readiness plus supervisor bootstrap now fail closed when those flags
  drift out of the supported paper posture
- as of Tuesday, July 21, 2026, TFIS also added one shared fresh-entry
  handoff-authority audit: the same helper now feeds pre-live readiness, the
  read-only runtime-status command, and the dashboard Operator Status panel,
  and it treats launch markers, later same-branch lifecycle rows, or later
  same-branch supervised-session artifacts as valid handoff evidence
- the Tuesday, July 21, 2026 prod-paper readiness pass is now green again on
  that expanded runtime surface: an older Sunday, July 6, 2026 S23
  fresh-entry-required close no longer fails the current-day gate once later
  same-branch supervised-session evidence is present
- as of Tuesday, July 21, 2026, the operator dashboard also consumes that same
  shared guardrail truth: Operator Status now shows a paper-guardrail
  PASS/FAIL badge and raises explicit alerts when any configured strategy no
  longer satisfies the supported paper-only runtime contract
- as of Tuesday, July 21, 2026, the operator dashboard also gained the first
  shared runtime-heartbeat visibility slice: when the paper runtime uses the
  filesystem live-state backend, Operator Status now reads the persisted
  supervisor heartbeat and flags stale or unavailable supervision directly on
  the shared operator surface
- the same Tuesday, July 21, 2026 heartbeat slice now also exposes the latest
  persisted supervisor `owner_id` plus `state_directory`, and the shared live-
  state loader now accepts both nested `storage.live_state` / `storage.redis`
  config blocks and their top-level `live_state` / `redis` aliases so the
  heartbeat read-model and the runtime-store bootstrap no longer depend on
  different YAML shapes
- the operator dashboard now also renders that same heartbeat owner/state
  detail on the shared Operator Status panel, so the latest shared supervisor
  identity and watched state directory are visible at operator time without
  dropping into the raw heartbeat store
- the operator home strategy cards now also surface visible-trade, open-
  position, action-required, and closed-row counts from the shared live
  monitor, giving the multi-strategy dashboard a denser at-a-glance operator
  summary without changing any runtime or strategy behavior
- the shared chart-review page now also includes an instrument filter over the
  selected-contract chart cards, so operators can narrow the same chart
  surface by underlying symbol as the number of active strategies and
  instruments grows
- TFIS now also has a shared opt-in broker-health probe surface: one reusable
  runtime status loader can actively connect configured paper broker adapters,
  the read-only runtime console can print that probe result, and pre-live
  readiness can include the same broker-health truth when explicitly asked to
  do so
- as of Tuesday, July 21, 2026, the operator dashboard navigation now also
  uses one shared operator nav strip across the home, strategy, all-trades,
  historical-trades, monthly-status, and manual-S23 pages, so the main
  operator surface now scales through one consistent navigation pattern
  instead of page-local back-link layouts
- as of Tuesday, July 21, 2026, the operator dashboard also gained the first
  shared chart-review surface: `tools/charts/index.html` now brings active
  selected-contract market-evidence charts and a direct NIFTY/BANKNIFTY
  monthly-structure review entry into the same operator navigation model, with
  simple strategy/stream filters plus evidence summary counts for operator-time
  review, and the monthly-status tool now accepts preselected instrument
  defaults from chart-page links
- the first weekend Step 2 lifecycle-correctness fix is now in place: active
  dashboard trade monitors suppress terminal trade rows by default, leaving
  closed trades to the historical view instead of presenting live and closed
  truths at the same time
- the next weekend Step 2 groundwork slice is now in place too: lifecycle
  supervisor target specs can carry supervised-decision relaunch metadata, and
  TFIS now has a generic paper morning supervised-task launcher seam with S23
  compatibility aliases preserved
- the next weekend Step 2 runtime slice is now in place as well: the shared
  lifecycle supervisor can react to `PAPER_POSITION_FRESH_ENTRY_REQUIRED` by
  launching one fresh supervised decision request through shared target
  metadata plus the generic paper-task launcher seam, with focused runtime,
  launcher, supervisor, and dashboard regressions still green
- the next weekend Step 2 hardening slice is now in place too: fresh-entry
  relaunch from the shared supervisor is now idempotent per terminal session
  directory, with a durable `fresh_decision_launch.json` marker preventing the
  same closed trade from spawning duplicate fresh supervised-decision runs
  after restart or repeat polling, and focused runtime regressions remain green
- the next weekend Step 2 lifecycle handoff slice is now in place as well: the
  shared supervisor now prefers promoting an already-calculated blocked same-
  day READY decision through one shared fresh-entry promotion helper before it
  falls back to launching a brand-new supervised decision, while preserving the
  old fail-closed rule that reverse-entry-required states still block that
  promotion path
- the final weekend Step 2 dashboard-truth slice is now in place too: live
  monitor rows now suppress concrete current-price display when no selected-
  contract stream evidence exists, and they explicitly label stale live quotes
  instead of presenting them as silently current
- the first weekend Step 3 operator-control slice is now in place too: TFIS
  now has a dedicated `stop_tfis_runtime.ps1` command, and the reset path now
  shares one runtime-process helper with that stop command so manual stop and
  restart/recovery follow the same TFIS-only process ownership rules
- the next operator-control slice is now in place as of Monday, July 20,
  2026: TFIS now has a dedicated
  `scripts/refresh_tfis_operator_dashboard.ps1` command for in-market
  dashboard rebuilds without stopping the shared paper supervisor, and the
  existing reset command now explicitly warns that it is a full runtime
  restart path rather than a dashboard-only refresh
- the next broker/runtime failure-posture slice is now also in place as of
  Monday, July 20, 2026: the shared paper lifecycle runtime now rechecks
  broker health during supervisor loops, drives one reconnect attempt through
  the shared broker-neutral runtime helper when the adapter reports an
  unhealthy state, and fails closed with explicit strategy/provider context if
  the runtime remains unhealthy after that reconnect
- the next trade-ledger authority slice is now also in place as of Monday,
  July 20, 2026: TFIS now exposes shared helpers for latest active-trade row
  selection and latest historical-close selection, and the operator dashboard
  has been cut over to those shared helpers so active strategy pages, the
  consolidated all-trades monitor, and the historical closed-trades page no
  longer maintain separate latest-row selection logic
- the next Tuesday, July 21, 2026 operator-safety slice now also separates
  order-routing truth from generic paper guardrails: TFIS now has one shared
  paper runtime order-routing status helper that confirms per strategy that
  `no_live_orders_allowed` remains enabled and broker adapters still inherit
  the blocked paper-only order methods, and that same PASS/FAIL truth now
  surfaces through pre-live readiness, the read-only runtime-status command,
  and the dashboard Operator Status panel
- the Tuesday, July 21, 2026 readiness audit then passed on the current paper
  runtime surface as well: the focused `prod` readiness checks succeeded both
  with and without `--require-token`, confirming shared supervisor targets,
  broker runtime assembly, paper guardrails, order-routing safety, filesystem
  live-state readiness, operator-control state, and local FYERS token-store
  availability
- the next Tuesday, July 21, 2026 dashboard-truth slice now also removes one
  more page-local visibility rule: the shared paper trade-ledger layer now
  owns current-session waiting-order filtering plus terminal-row suppression
  for the active trade monitor, so the dashboard no longer pre-filters those
  rows inline before delegating to the shared latest-row selection helpers
- that same Tuesday, July 21, 2026 shared monitor helper now also keeps
  prior-session `ORDER_NOT_FILLED` rows out of the live monitor, so a strategy
  with no current-day session no longer leaks stale unfilled orders from an
  older day back into the consolidated active-trades surface
- as of Tuesday, July 21, 2026, the consolidated operator surfaces now also
  anchor waiting/not-filled visibility to the later of the current operator
  day and the newest discovered strategy session date, so stale prior-day
  unfilled rows cannot reappear in the active all-trades or chart-review
  surfaces just because another strategy has not produced a fresh session yet
- as of Tuesday, July 21, 2026, each strategy page now follows that same
  current-day active-monitor rule: past-session waiting or `ORDER_NOT_FILLED`
  rows can still appear in the latest-session decision summary for audit, but
  they no longer leak back into the active "Trades Taken" monitor or strategy
  Operator Status panel as if they were current live trades
- the Tuesday, July 21, 2026 focused validation pass is green again on that
  expanded operator surface: `tests/unit/test_operator_dashboard.py` passed at
  `31 passed`, the supporting runtime/readiness/reset pack passed at
  `58 passed`, the shared handoff/process-lock/operator-control/wrapper pack
  passed at `86 passed`, and the `prod` readiness audit passed both with and
  without `--require-token`
- the same Tuesday, July 21, 2026 broker-readiness pass is now also proven on
  the stronger path: `scripts/pre_live_readiness.py --profile prod
  --require-token --probe-broker-health --json` confirmed
  `S23=>fyers/CONNECTED` and `S21=>fyers/CONNECTED`, while the latest
  `lifecycle_runtime_config.py` cleanup moved adapter construction plus
  runtime-environment preparation behind one narrower provider-registry seam
  with the focused lifecycle-runtime/readiness regression pack passing at
  `50 passed`
- the next Tuesday, July 21, 2026 Phase 4 naming/plumbing slice is now also
  complete: shared paper runners, timeline builders, generated-prelude flow,
  live-ingress runner, capture-ingress suite, and generic order/position entry
  helpers now consume the neutral `Paper...` live-decision and ingress-dry-run
  aliases instead of importing `S23...` names directly, with the focused
  impacted regression pack passing at `147 passed`; the broader shared safety
  sweep over operator dashboard, readiness, lifecycle-supervisor runtime, and
  reset-path regressions then also passed at `89 passed`, with local `prod`
  readiness still returning `overall_status=PASS`
- the next Tuesday, July 21, 2026 Phase 4 broker-bootstrap slice is now also
  complete: the shared paper runtime-config layer now exports a broker-config-
  level adapter builder, and both the live-ingress runner plus the FYERS
  snapshot collector now consume that shared helper instead of duplicating
  provider checks and fixture/live adapter creation logic inline. The focused
  affected regression pack passed at `110 passed`, the broader shared safety
  sweep passed at `90 passed`, and local `prod` readiness remained
  `overall_status=PASS`
- the same Tuesday, July 21, 2026 bootstrap-hardening slice then also
  centralized broker-credential readiness: the shared paper runtime-config
  layer now owns provider-specific credential-availability checks, and both
  the neutral live-ingress preflight plus the FYERS snapshot collector consume
  that same helper instead of probing FYERS credentials inline. The focused
  affected regression pack passed at `112 passed`, and local `prod` readiness
  remained `overall_status=PASS`
- the same Tuesday, July 21, 2026 shared-ingress wording slice then also
  removed one more public S23/FYERS-only signal from the shared paper path:
  the neutral live-ingress runner now renders generic paper-broker summary and
  preflight headings plus generic configured-broker safety wording, with the
  focused affected regression pack still passing at `112 passed` and local
  `prod` readiness remaining `overall_status=PASS`
- the same Tuesday, July 21, 2026 shared reviewer/state-store cutover batch is
  now also clean: generated-prelude dry runs, position discovery, position
  management, the morning timeline runner, execution journal, fill simulator,
  lifecycle simulator, ingress dry-run, and the FYERS snapshot collector now
  consume neutral `Paper...` reviewer/state-store aliases where those surfaces
  are already shared, while preserving compatibility symbols for older module-
  level monkeypatch hooks. The impacted regression pack passed at `190 passed`,
  and local `prod` readiness remained `overall_status=PASS`
- the same Tuesday, July 21, 2026 handoff-truth slice also made fresh-entry
  recovery more operator-visible: the shared paper layer now reads
  `fresh_decision_launch.json`, and dashboard follow-up text for
  fresh-entry-required closes now states whether TFIS promoted a blocked READY
  decision or launched a fresh supervised runner
- as of Tuesday, July 21, 2026, the S21 morning wrapper now also follows the
  shared effective-run-date plus no-run helper path and always writes
  explicit skip/finish/failure evidence into its task log, so its scheduled
  behavior now matches S23 more closely during weekend/holiday and wrapper-
  exit audits
- the next Tuesday, July 21, 2026 reconciliation slice now also adds an
  explicit startup audit for persisted state-versus-ledger authority: TFIS
  now checks each persisted paper position state against the latest ledger row
  for the same trade, fails closed if active state disagrees with terminal
  ledger truth or terminal state disagrees with non-terminal ledger truth, and
  the repo readiness pass is currently clean on that expanded gate after BOM-
  tolerant JSONL handling was added for older Windows-written ledger files
- that same Monday, July 20, 2026 reconciliation pass also tightened shared
  runtime target discovery: only same-day waiting orders are now eligible
  watch targets, while prior-session waiting orders remain historical/review
  artifacts instead of being carried forward into the shared supervisor loop
- the next Monday, July 20, 2026 reconciliation slice then removed another
  split-brain runtime seam: blocked fresh-entry promotion now uses the shared
  position-discovery layer to find open or reverse-entry-required positions
  that still block new-entry promotion, instead of maintaining its own local
  filesystem walk and predicate
- the next Monday, July 20, 2026 runtime refactor slice then removed another
  supervisor-script decision seam: fresh-entry-required handoff now runs
  through a shared paper helper that owns idempotent marker-path resolution,
  blocked-decision promotion-first behavior, and runner-launch marker writes,
  while the supervisor script now only supplies task-spec and subprocess
  wiring
- the next Monday, July 20, 2026 runtime metadata slice then removed another
  S21/S23 ownership seam: shared lifecycle-supervisor targets now carry the
  relaunch runner/wrapper script paths needed for fresh-entry handoff, the
  supervisor task builder now consumes that shared target metadata instead of
  maintaining a hardcoded strategy-to-script map, and the reusable execution-
  plan surface now normalizes the old `s23_morning_supervised` label onto the
  generic paper-morning-supervised executor contract
- the next Monday, July 20, 2026 artifact-discovery slice then removed another
  split-brain filesystem seam: TFIS now has shared paper-session discovery
  helpers for strategy-day ordering, latest supervised-session lookup, stage
  snapshot directory discovery, and branch summary enumeration, and the
  operator dashboard plus blocked fresh-entry promotion now share that same
  artifact-truth path with focused regressions still green
- the next Monday, July 20, 2026 dashboard-order slice then removed another
  duplicated monitor seam: active dashboard trade rows now read pending and
  not-filled orders through the shared typed paper-order discovery path first,
  with raw-order fallback preserved for sparse historical artifacts, and the
  shared order-status helpers now normalize enum and string values the same
  way so typed discovery cannot silently hide valid monitor rows
- the next Monday, July 20, 2026 decision-summary slice then removed another
  duplicated artifact-read seam: TFIS now has shared trade-decision summary
  discovery for branch-level `trade_decision_summary.json` payloads, and both
  the dashboard plus blocked fresh-entry promotion now share that same
  payload/summary extraction path with focused regressions still green
- the next Monday, July 20, 2026 trade-ledger slice then removed another
  dashboard-local filesystem seam: shared trade-ledger helpers now own the
  discovery of session and global `paper_trade_ledger.jsonl` paths, and the
  operator dashboard consumes that shared path selection instead of rebuilding
  it locally
- the next Tuesday, July 21, 2026 ledger-authority slice then removed another
  dashboard-only truth rule: shared paper trade-ledger helpers now decide when
  a terminal trade row remains displayable after its live
  `paper_position_state.json` has been cleaned up, so historical closed-trade
  visibility no longer depends on a dashboard-local filesystem existence check
- the same Tuesday, July 21, 2026 session-discovery slice then removed another
  dashboard-local selection rule: shared paper-session discovery now owns the
  preferred-stage lookup that selects the `09:30` stage snapshot when present
  and otherwise falls back to the latest available stage for that session day
- the next Tuesday, July 21, 2026 decision-summary slice then removed another
  dashboard-local read-model seam: shared decision-summary helpers now expose
  reusable selected-contract symbol discovery, and the dashboard consumes that
  shared symbol list instead of re-looping parsed summary payloads to rebuild
  final session contract symbols
- the same Tuesday, July 21, 2026 session-read-model slice then removed the
  next dashboard-local merge seam: shared session-contract discovery now owns
  the union of typed order-state symbols, raw order-state fallback symbols,
  and branch-summary symbols used to reconstruct final session contracts
- the next Tuesday, July 21, 2026 final-summary slice then removed another
  dashboard-local read-model seam: shared decision-summary helpers now own the
  resolved final artifact directory plus parsed final summary view for a
  supervised session, so the dashboard no longer reopens and reshapes the
  final `trade_decision_summary.json` artifact on its own
- the next Monday, July 20, 2026 dashboard-discovery slice then removed two
  more dashboard-local filesystem seams: shared paper-session helpers now own
  branch-explainer path discovery for final versus latest-stage
  `trade_decision_explainer*.json` artifacts, and the shared paper-order layer
  now owns reusable raw `paper_order_state.json` candidate-path discovery used
  by dashboard historical/order fallbacks
- the next Monday, July 20, 2026 decision-summary slice then removed another
  neighboring-artifact seam: shared decision-summary discovery candidates now
  carry their resolved branch directory plus sibling `paper_order_state.json`
  path, and both the operator dashboard plus blocked fresh-entry promotion now
  use that shared sibling-artifact truth instead of rebuilding it from
  `summary_path.parent`
- the next Tuesday, July 21, 2026 stage-artifact slice then removed one more
  dashboard-local naming seam: shared paper-session helpers now resolve the
  finalized-session `monthly_status_stage_<key>.json` and
  `trade_decision_explainer_stage_<key>.json` paths for a stage key, and the
  operator dashboard now consumes that shared naming path instead of
  reconstructing those filenames inline
- the next Tuesday, July 21, 2026 final-artifact slice then removed one more
  dashboard-local authority seam: shared decision-summary discovery now
  resolves the authoritative final trade-decision artifact directory for a
  supervised session, preferring a session-level summary when present and
  otherwise falling back to the matching branch-summary directory, and the
  operator dashboard now consumes that shared resolution path instead of
  carrying the policy inline
- the next Tuesday, July 21, 2026 session-completeness slice then removed one
  more dashboard-local session-state seam: shared paper-session helpers now
  resolve the `scheduled_run_metadata.json` path and expose the derived
  supervised-session completion check, and the operator dashboard now consumes
  that shared rule instead of inlining the metadata-filename test
- the same Tuesday, July 21, 2026 executor-contract slice then removed one
  more half-shared runtime seam: canonical paper supervised executor naming
  now lives in one shared `tfis.strategy` helper, lifecycle-supervisor target
  loading now normalizes legacy executor aliases the same way as strategy
  execution-plan validation, and the repo paper configs plus supervisor target
  metadata now declare the generic `paper_morning_supervised` contract
- the same Tuesday, July 21, 2026 selected-contract event slice then removed
  another artifact-handling seam: shared paper helpers now own
  `selected_contract_market_events.jsonl` path discovery, append/load
  behavior, and supervisor-vs-watcher PID interpretation, and the shared
  supervisor, legacy S23 compatibility watcher, operator dashboard, and
  captured-session validator now all consume that same helper instead of
  maintaining separate local event-artifact logic
- the same Tuesday, July 21, 2026 watcher-recovery slice then removed another
  compatibility seam: the legacy S23 watch script now resolves same-day
  waiting orders through the shared paper-order discovery helper instead of
  scanning `paper_order_state.json` files inline, so current-session waiting
  order recovery and stale previous-session filtering now follow the same
  shared discovery rule
- the same Tuesday, July 21, 2026 morning-bootstrap slice then removed
  another S23-shaped public seam: shared paper aliases now expose neutral
  morning supervised checkpoint/result/runner names, both the S21 and S23
  morning launcher scripts now call that generic runner directly, and the two
  launcher scripts now also share the same market-closed no-action rule plus
  process-lock path helper instead of carrying separate local copies
- the same Tuesday, July 21, 2026 timeline-and-live-check slice then removed
  another shared-paper naming seam: the timeline builder/checkpoint/stage/
  result contract now has generic paper aliases used by the operator
  dashboard and morning supervised runner, the legacy S23 watch path now uses
  the shared live-state owner helper name directly, and the live-decision
  check now also exposes a neutral runner/result alias that the CLI entrypoint
  consumes instead of binding directly to an S23-only public name
- the same Tuesday, July 21, 2026 snapshot-and-prelude slice then removed
  another shared-paper naming seam: neutral paper aliases now exist for the
  reusable prelude builder/error/request/result/mode contract and the shared
  snapshot session read-models, while the shared decision builder, timeline
  builder, FYERS snapshot collector, generated prelude dry-run runner, and
  operator dashboard now consume those neutral aliases directly instead of
  binding only to S23-prefixed public names
- the same Tuesday, July 21, 2026 collector-and-preflight slice then removed
  another shared-paper naming seam: the FYERS snapshot collector/preflight
  artifact, error, issue, summary, and provenance types now also have neutral
  paper aliases, and the shared live-decision runner, snapshot-validation
  harness, and live-decision-check CLI now consume those neutral collector
  aliases directly instead of binding only to S23-prefixed public names
- the next Tuesday, July 21, 2026 runtime-input and live-reference slice then
  removed another shared-paper naming seam: the decision-reference loader,
  decision/monthly-status/market reference packets, derived runtime-input
  contracts, runtime-input derivation error/deriver, and live reference
  derivation error/result/deriver now also expose neutral paper aliases, and
  the shared live-decision builder, live-decision timeline, live-decision
  runner, operator dashboard, and S21 morning wrapper now consume those shared
  names directly while the timeline runner preserves one compatibility loader
  alias for older S23 hooks
- the same Tuesday, July 21, 2026 planning-foundation slice then removed
  another shared-paper naming seam: guardrail evaluator/settings, paper
  contract validator, paper session-manifest builder, paper order-plan,
  paper session orchestrator, and paper session snapshot now all expose
  neutral paper aliases, and the shared ingress dry-run and paper artifact
  surfaces now consume those planning aliases directly instead of binding only
  to S23-prefixed public contracts
- the next Tuesday, July 21, 2026 ingress dry-run/read-model slice then
  removed another shared-paper naming seam: ingress dry-run error/readiness,
  thresholds, timing audit, ingress health metrics, selected-contract audit,
  dry-run summary/artifact-set, normalized event loader, and ingress dry-run
  runner now all expose neutral paper aliases, and the shared `tfis.paper`
  surface can now present those ingress contracts without requiring S23-only
  public names
- the next Monday, July 20, 2026 reconciliation slice then removed one more
  dashboard-only rule: live trade-monitor order visibility for waiting and
  not-filled paper orders now comes from a shared paper-order helper keyed by
  latest-session date, so dashboard active-order filtering and reusable paper-
  order semantics no longer drift independently
- the next Monday, July 20, 2026 runtime-discovery slice then removed one
  more duplicated filesystem walk: the shared paper-order layer now exposes a
  reusable order-state discovery helper, and both lifecycle-supervisor target
  discovery plus the waiting-order finalizer now use that same helper instead
  of each scanning `paper_order_state.json` artifacts separately
- the next Monday, July 20, 2026 reconciliation slice then removed one more
  dashboard-only state scan: shared position discovery now exposes a lenient
  latest-terminal-position lookup for sparse historical position-state files,
  and the strategy dashboard now uses that shared lookup when overriding stale
  carry-forward blockers instead of walking raw `paper_position_state.json`
  files locally
- the next Monday, July 20, 2026 fresh-entry refactor slice then tightened the
  promotion path itself: blocked READY promotion now works from shared
  blocked-decision candidate records that carry parsed summary data plus any
  already-discovered order-state path for that branch, instead of passing raw
  summary-path tuples through the promotion loop
- offline TFIS architecture and backtest foundation is in place
- corrected S23 weekly option selling contract is documented and now supersedes
  older inferred branch mappings
- corrected S23 four-leg rule matrix is implemented and tested against the
  branch strategy folders
- S23 runtime derivation/prelude now validate loaded rules against the corrected
  matrix before decision generation, with `scripts/validate_s23_rule_matrix.py`
  available as a direct operator/developer check
- S23 live session dashboard stage cards now show rule-sheet steps and final
  weekly option decision context from existing artifacts
- S23 manual calculator now follows the corrected rule-sheet flow for date,
  monthly status, CE/PE branch selection, strike qualification, and final
  entry/target/SL review
- S23 operator dashboard latest-session summary and manifest now support plural
  final contracts for two-leg paper-order sessions
- S23 operator dashboard latest-session view now shows a visible calculation
  explanation section with Step 1-8 reasoning and per-leg formula traces from
  the final decision artifacts
- S23 operator dashboard now shows final CE/PE leg decisions with no-contract
  rows, failure codes, selected/failed-leg explanations, and final trade levels
  only when an actual contract qualifies
- S23 operator dashboard now also accepts latest stage-level explainers as
  review artifacts for no-contract legs, so failed CE/PE calculations remain
  visible even when no final selected-leg summary artifact was written.
- Phase 2 paper runtime-contract/read-model consolidation is now complete for
  the current scope: TFIS has neutral intent/fill/lifecycle/shell contracts,
  review/parity/fill-simulation/lifecycle/execution-journal consumers now use
- Phase 4 broker/data-source separation has progressed by another safe
  additive slice during the Friday, July 17, 2026 market session: the shared
  paper lifecycle runtime-config layer now owns broker-runtime environment
  preparation as well as broker-adapter construction, so the shared TFIS
  lifecycle supervisor no longer imports FYERS token/bootstrap helpers
  directly and now deduplicates broker-environment preparation once per
  provider before connecting adapters
- a second additive Phase 4 slice is now prepared for a later cutover: TFIS
  has a shared `src/tfis/paper/lifecycle_market_events.py` selected-contract
  quote/bar fetch-policy abstraction with focused tests, and after market on
  Friday, July 17, 2026, the shared supervisor was cut over to that path while
  preserving the prior SL-reset bar-fetch warning behavior
- the legacy S23 compatibility watcher was then aligned to that same shared
  fetched quote/bar policy on Friday, July 17, 2026, while still preserving
  its separate stream-tick-first fallback behavior for operator continuity
- the S21/S23 recovery launchers were then relabeled on Friday, July 17, 2026
  as supervisor-compatibility launchers rather than watcher launchers, so the
  operator-facing wrapper layer now better reflects the current one-supervisor
  TFIS runtime model
- the S23 morning supervised wrapper then dropped its dead pre-supervisor
  `Start-S23PaperWatchProcess` fallback on Friday, July 17, 2026, and updated
  its surviving startup logs from watcher wording to supervisor wording
- the same S23 morning wrapper then centralized its shared-supervisor launch
  path on Friday, July 17, 2026 behind one local `Start-TfisSharedSupervisor`
  helper instead of duplicating the launcher block across metadata and
  discovery-mode branches
- the S21 supervised Python entrypoint then renamed its shared lifecycle
  bootstrap path away from watcher wording on Friday, July 17, 2026, and the
  market-closed no-action messages for both S21 and S23 now state that no
  supervisor startup was triggered
- the TFIS reset/recovery script then updated its operator-facing wording on
  Friday, July 17, 2026 so stale waiting-order skips, duplicate targets, and
  launched compatibility processes are described as supervisor recovery actions
  rather than watcher startup
- the same TFIS reset/recovery script then renamed its internal helper surface
  from `Watcher` wording to `Recovery` wording on Friday, July 17, 2026 for
  those compatibility-target scans and launches
- the same TFIS reset/recovery script then dropped its final dead inline
  per-target discovery/relaunch helper branch on Friday, July 17, 2026, so
  dashboard reset now cleanly delegates waiting-order and open-position
  recovery to `start_tfis_paper_lifecycle_supervisor.ps1`
- the reset path, S21/S23 supervisor-compatibility launchers, and S23 morning
  wrapper then switched on Friday, July 17, 2026 to one shared PowerShell
  supervisor-launch helper, `scripts/tfis_paper_lifecycle_supervisor_helpers.ps1`,
  so visible shared-supervisor startup arguments no longer drift across wrappers
- the shared paper-position helper then gained a generic resumable-position
  filesystem scan on Friday, July 17, 2026, and both the S21 and S23 morning
  wrappers switched to that helper instead of reimplementing the
  recurse/read/filter loop locally
- the same shared paper-position helper then absorbed the wrapper-level path
  normalization on Friday, July 17, 2026, with both S21 and S23 morning
  wrappers switching to shared `Resolve-TfisAbsolutePathText` and
  `Resolve-TfisPositionStateDirectoryPath` helpers instead of carrying their
  own local copies
- the S21/S23 morning-wrapper holiday calendar parsing then moved on Friday,
  July 17, 2026 into `scripts/tfis_trading_calendar_helpers.ps1`, so both
  wrappers now read holiday-date context through one shared helper seam
- that same shared trading-calendar helper then absorbed the generic
  effective-run-date and weekend/holiday no-run logic on Friday, July 17,
  2026 for the S23 morning wrapper and S23 paper-order finalizer, removing
  another duplicated S23 wrapper seam
- the S21 morning wrapper, S23 morning wrapper, and S23 paper-order finalizer
  then switched on Friday, July 17, 2026 to shared wrapper-task helpers for
  Python executable resolution and timestamped task-log context creation,
  trimming another repeated operational bootstrap seam
- that same wrapper-task helper then absorbed the common task-log write path on
  Friday, July 17, 2026, so the S21 morning wrapper, S23 morning wrapper, and
  S23 paper-order finalizer no longer each maintain their own timestamped
  log-write implementation
- the shared wrapper-task helper then also absorbed latest-session metadata
  file lookup on Friday, July 17, 2026 for day-scoped strategy artifact roots,
  and the S23 morning wrapper switched to that helper instead of keeping its
  own inline `scheduled_run_metadata.json` discovery walk
- the shared wrapper-task helper then also absorbed the visible task banner on
  Friday, July 17, 2026, and the S23 morning wrapper plus S23 paper-order
  finalizer switched to that one helper instead of duplicating the same banner
  block
- the two morning wrappers then also switched on Friday, July 17, 2026 to one
  shared hidden Python subprocess-launch helper for redirected stdout/stderr
  execution, trimming another repeated operational wrapper seam
- the legacy S23 compatibility watch script then switched on Friday, July 17,
  2026 to the shared paper runtime-config bootstrap for broker-environment
  preparation and broker adapter construction, removing another direct FYERS
  bootstrap dependency from that fallback operational path
- the shared paper runtime-config layer then also absorbed broker-runtime
  assembly on Friday, July 17, 2026 through `load_paper_broker_runtime`, so
  config load, timezone resolution, and broker adapter construction now come
  from one shared builder used by both the shared supervisor and the legacy
  S23 compatibility watch script
- the shared lifecycle runtime paths then also switched on Friday, July 17,
  2026 to an explicit `build_paper_position_manager` factory keyed by strategy
  code, so the shared supervisor and legacy S23 compatibility watch path no
  longer hardwire `S23PaperPositionManager` directly in their reusable
  bootstrap
- the same shared-runtime cleanup then advanced on Friday, July 17, 2026 with
  one more additive seam removal: the legacy S23 compatibility watch now uses
  the shared `build_paper_live_state_store_from_yaml(...)` alias, the shared
  lifecycle supervisor now resolves its default position manager through the
  explicit strategy-code factory instead of `S23PaperPositionManager()`
  inline, and both the shared supervisor plus the legacy compatibility watch
  now resolve expiry governance through a shared
  `build_paper_expiry_governance(...)` factory keyed by strategy code
- the reusable lifecycle type surface then took another additive Phase 4 step
  on Friday, July 17, 2026: TFIS now exports neutral
  `PaperPositionManager*` aliases over the existing S23 implementation, and
  the shared lifecycle supervisor now types itself against neutral paper
  position-manager and expiry-governance aliases instead of exposing the S23
  names directly in that reusable layer
- the legacy S23 compatibility watch then also dropped its remaining
  `S23LivePaperIngressConfig` bootstrap dependency on Friday, July 17, 2026,
  and now resolves timezone plus lifecycle runtime settings directly from the
  shared paper runtime-config layer
- the S23 live-decision and timeline entrypoints then also moved another
  additive Phase 4 bootstrap seam on Friday, July 17, 2026: shared broker
  runtime-environment preparation now lives behind
  `prepare_live_decision_runtime_environment(...)`, and both
  `run_s23_live_decision_check(...)` plus the morning timeline runner now use
  that shared helper instead of calling the FYERS auth/bootstrap function
  directly
- the operator dashboard then took the same additive Phase 4 bootstrap step on
  Friday, July 17, 2026: its monthly-status API path now uses the shared
  live-decision runtime-prep helper rather than a direct FYERS bootstrap call,
  and `serve_operator_dashboard.py` now accepts an explicit `--runtime-config`
  argument for that shared preparation path
- the inner ingress-config surface then took its first additive neutralization
  step on Friday, July 17, 2026: TFIS now exports neutral
  `Paper*IngressConfig` aliases over the existing S23 ingress config
  dataclasses, and the live-decision runner plus morning timeline runner now
  load config through `PaperLiveIngressConfig` instead of naming the S23
  ingress config directly
- the same inner ingress/runtime surface then advanced one layer deeper on
  Friday, July 17, 2026: the FYERS snapshot collector and generated-prelude
  dry-run runner now use the neutral `PaperLiveIngressConfig` and
  `PaperExpiryGovernance` aliases for shared config/governance plumbing, which
  narrows the remaining S23-shaped surface toward genuinely strategy-specific
  prelude and read-model behavior
- the reusable live-prelude and paper position-manager layers then followed on
  Friday, July 17, 2026 by typing their shared expiry-governance dependency
  through the neutral `PaperExpiryGovernance` alias, leaving the remaining
  direct S23 naming concentrated mostly inside the intentionally strategy-
  specific live-ingress implementation
- the live-ingress module then took the same internal signature cleanup on
  Friday, July 17, 2026: its reusable loader/preflight/helper methods now type
  config through the neutral `PaperLiveIngressConfig` alias, while the module
  still keeps its S23-specific runtime behavior and outward class names intact
- the shared `tfis.paper` import surface then followed on Friday, July 17,
  2026 by exporting neutral `PaperBrokerPaperIngressRunner` and
  `PaperLiveIngress*` aliases over the existing S23 ingress runner and
  preflight types, so future strategies can consume that reusable seam without
  binding directly to S23 naming
- the same ingress surface then completed its current low-risk alias cleanup on
  Friday, July 17, 2026 by exposing neutral `PaperLiveIngressSummary` and
  `PaperLiveIngressArtifactSet` aliases and using those names in the ingress
  runner signatures, leaving the remaining Phase 4 work as a true behavioral
  extraction question rather than more naming/export cleanup
- the focused ingress regression then switched on Friday, July 17, 2026 to the
  neutral `Paper*` ingress imports as well, proving the reusable ingress seam
  is exercised by callers rather than only exported as an alias layer
- the last safe ingress/governance consumers then followed on Friday,
  July 17, 2026: the ingress CLI wrapper switched to the neutral paper-ingress
  runner/error symbols, and the operator dashboard switched to the neutral
  `PaperExpiryGovernance` alias for shared expiry-governance behavior, leaving
  the remaining Phase 4 work as a true deeper behavioral extraction question
- the shared ingress and expiry-governance modules then completed their final
  low-risk surface refactor on Friday, July 17, 2026 by making the neutral
  `Paper*` classes canonical at the definition layer and preserving the older
  `S23*` names as compatibility aliases only
  those contracts, and persisted stage-specific artifacts now outrank fragile
  single-source dependence on partial `execution_summary.json` payloads.
  Focused runtime regressions and the TFIS guard suite remain the acceptance
  gate before the later Phase 3 lifecycle-supervisor consolidation begins.
- As of Friday, July 17, 2026, the first full Phase 3 lifecycle-supervisor
  cutover is now complete for the current TFIS paper scope: one shared
  lifecycle supervisor process discovers and manages S21/S23 waiting orders
  plus open positions from persisted artifacts, the legacy S21/S23 watcher
  launcher commands now delegate to that shared supervisor as compatibility
  shims, `reset_tfis_dashboard_and_watchers.ps1` now starts one shared
  supervisor instead of one watcher per target, and the prod-paper readiness
  gate now validates `config/paper_lifecycle_supervisor_targets.yaml` along
  with the existing strategy and dashboard configs.
- As of Friday, July 17, 2026, the first post-cutover Phase 4 broker/data-
  source separation slice is now complete for the shared paper lifecycle
  supervisor runtime: the bootstrap path no longer hardcodes
  `FyersBrokerAdapter` or the S23 ingress config type directly, and instead
  resolves broker provider, timezone, payload fixture, and lifecycle slippage
  settings through the shared `src/tfis/paper/lifecycle_runtime_config.py`
  layer while preserving the current S21/S23 paper behavior and focused
  supervisor regressions.
- TFIS reset/recovery now uses one explicit dashboard build plus
  `serve_operator_dashboard.py --skip-build`, and the reset script now also
  narrows process discovery to likely TFIS host processes, stops matched TFIS
  process trees directly, and waits for the dashboard port to accept
  connections before declaring startup complete
- As of Tuesday, July 21, 2026, the shared paper runtime reconciliation gate
  is now operator-visible as well as readiness-visible: the same helper that
  checks persisted paper position state against latest ledger truth now also
  feeds `scripts/show_tfis_runtime_status.ps1`, so runtime state-vs-ledger
  conflicts can be inspected from one read-only TFIS operator console without
  restarting the supervisor
- TFIS operator dashboard builds now reuse in-process caches for parsed JSONL
  artifacts, selected-contract stream health, and trade-row collections, which
  cuts repeated rereads of large market-event and ledger files during one reset
  or rebuild cycle
- Historical-trades dashboard rendering now skips live stream-health and
  pending-order scans, reducing operator-dashboard rebuild time further on real
  TFIS artifact sets
- Phase 1 shared-paper-lifecycle refactor has started with additive,
  strategy-neutral entrypoint aliases for the order finalizer and lifecycle
  supervisor, giving later S21/Sxx work a neutral import seam without changing
  the current S23 runtime behavior
- Phase 1 now also exposes strategy-neutral aliases for shared paper order and
  position state models/stores, extending the neutral seam without changing the
  current S23-backed runtime behavior
- Phase 1 now also has its first shared order-status helper extraction, with
  the existing paper finalizer and lifecycle supervisor switching from
  duplicated literal waiting-status checks to one shared helper and no runtime
  behavior change
- Phase 1 now also has matching shared position-status helpers, with the
  existing open-position discovery and position-manager closed-state gate
  switching from duplicated literal status sets to one shared helper layer and
  no runtime behavior change
- Phase 1 now also has shared trade terminal/open/action-required helpers, with
  the operator dashboard switching from duplicated row-classification logic to
  the shared helper layer and no runtime behavior change
- Phase 1 now also shares paper-trade status-label normalization and row-state
  bucketing, with the operator dashboard switching from inline waiting/not-filled
  label mapping and row-tone decision trees to shared trade-ledger helpers and
  no runtime behavior change
- Phase 1 now also shares latest-session trade visibility rules, with the
  operator dashboard switching from inline session-filter interpretation to a
  shared trade-ledger helper and no runtime behavior change
- the July 16, 2026 S23 runtime recovery path is now proven on real TFIS
  artifacts: Windows dead-PID process locks are reclaimed correctly, the S23
  supervised wrapper writes a fresh same-day session again, the TFIS-only reset
  script restarts one dashboard plus fresh S21/S23 order watchers, and the
  live monitor now keeps prior closed S23 rows in historical review instead of
  showing them beside current-day waiting entries
- Phase 2 contract work has now begun with a small additive shared runtime
  layer: TFIS now exposes strategy-neutral paper trade intent, fill, and
  lifecycle contract dataclasses plus S23 adapter builders that project the
  current S23 execution-journal, fill, and lifecycle artifacts onto that
  neutral shape without changing live paper behavior
- Phase 2 now also has its first real consumer boundary: the S23 paper review
  surface projects available intent/fill/lifecycle artifacts into the neutral
  runtime-contract shape for operator/read-model use, while incomplete
  planned-only review sessions deliberately keep those contract slots empty
  instead of inventing partial runtime data
- Phase 2 now also has its next read-side consumer boundary: the
  paper-vs-historical/parity layer prefers neutral runtime-contract fields for
  intent/fill/lifecycle facts and only falls back to older S23 payload reads
  when needed, while still preserving the stricter rule that a planned-only
  session is not execution-journal `INTENT_READY`
- Phase 2 now also reaches the simulator runtime loaders: the Phase 1 fill
  simulator and Phase 2 lifecycle simulator prefer neutral review/runtime
  contracts for intent/fill/lifecycle inputs and only fall back to older
  S23-shaped review fields when needed, keeping current TFIS behavior stable
  while shrinking direct strategy-shaped reads
- Phase 2 now also reaches one narrow post-planning execution-journal seam:
  `execution_journal.py` now preserves `INTENT_READY` shell continuity from an
  intact persisted intent artifact when `execution_summary.json` is missing
  only that status field, and it uses the neutral runtime-contract intent
  symbol as a fallback only when the raw intent artifact is unavailable,
  reducing one more brittle dependency on scattered S23-shaped summary fields
  without changing live paper behavior
- Phase 2 now also centralizes the first remaining execution-journal
  post-planning summary reads: dispatch/handoff handling and the related
  guardrail-validation paths now share helper methods for current
  execution-shell and historical-comparison fields instead of repeatedly
  reading those values inline from `execution_summary.json`, shrinking the
  remaining status-reconstruction surface without changing live paper behavior
- Phase 2 now also centralizes the remaining selected-contract symbol and
  comparison-presence reads in the post-planning execution-journal flow:
  execution arming, dispatch, and handoff now share helper methods for current
  intent symbol, execution-summary selected contract, dispatch-summary
  selected contract, and whether historical comparison has already been
  recorded, reducing another batch of inline S23-shaped summary reads without
  changing live paper behavior
- Phase 2 now also adds a neutral post-planning shell contract:
  `PaperTradeShellContract` now carries intent/execution/dispatch/handoff
  status plus historical-comparison state, the S23 review layer projects that
  contract, and `execution_journal.py` uses it as a fallback post-planning
  status source when raw summary artifacts are absent, extending the shared
  runtime boundary without changing live paper behavior
- Phase 2 now also moves the paper-vs-historical comparison layer onto that
  shell contract for post-planning readiness state: `paper_vs_historical.py`
  now prefers the neutral shell contract for execution/dispatch/handoff and
  historical-comparison fields before falling back to raw summary payloads,
  shrinking another shared S23-shaped read surface without changing live paper
  comparison behavior
- Phase 2 now also moves the Phase 1 fill simulator onto that shell contract
  for post-planning readiness state: `fill_simulator.py` now prefers the
  neutral shell contract for handoff/execution/dispatch and
  historical-comparison checks before falling back to raw summary payloads,
  and the review layer can now rebuild missing shell fields from
  dispatch/handoff summary artifacts when `execution_summary.json` is
  incomplete
- Phase 2 now also closes one more lifecycle guardrail dependency on raw
  summary payloads: `lifecycle.py` now prefers the neutral runtime fill
  contract for `fill_status` before falling back to
  `execution_summary.json`, and a focused regression proves same-day lifecycle
  simulation still reaches the correct close outcome when that one raw field
  is missing
- Phase 2 now also hardens armed-session shell reconstruction: `review.py`
  now uses `execution_arm_summary.json` as a fallback source for shell and
  historical-comparison state when `execution_summary.json` is incomplete, and
  `execution_journal.py` now prefers the projected shell contract when a
  present-but-partial execution summary loses execution-shell,
  dispatch/handoff, selected-contract, or historical-comparison fields
- Phase 2 now also broadens that same fallback rule across operator review
  fields: `review.py` now rebuilds armed-session order-intent message, reason,
  guardrail, operator-action, disclaimer, and future-fill-eligibility fields
  from persisted arm/dispatch/handoff summaries when `execution_summary.json`
  is partial, and a direct review regression proves armed-session shell state
  still reconstructs from `execution_arm_summary.json`
- Phase 2 now also extends partial-summary recovery into lifecycle review:
  `review.py` now rebuilds lifecycle status, exit reason/message, exit
  price/timestamp, warning flags, and disclaimer from `paper_exit.json`,
  `paper_pnl_summary.json`, and `paper_position.json` when
  `execution_summary.json` is partial, and a direct lifecycle-review
  regression proves a closed paper session still reconstructs the correct exit
  outcome from those stage-specific artifacts
- Phase 2 now also extends partial-summary recovery into fill review:
  `review.py` now rebuilds fill status, reason/message, fill price/timestamp,
  provenance, spread/slippage, and disclaimer from `paper_fill.json`,
  `paper_no_fill.json`, `paper_fill_abort_summary.json`, or
  `paper_order_pending.json` when `execution_summary.json` is partial, and a
  direct fill-review regression proves a filled paper session still
  reconstructs the correct Phase 1 outcome from the persisted fill artifact
- Phase 2 now also restores persisted-intent continuity in review/parity
  summaries: `review.py` now treats a persisted paper intent artifact as
  enough proof to keep `order_intent.status=INTENT_READY` when
  `execution_summary.json` loses only `intent_status`, and
  `paper_vs_historical.py` now preserves that same intent-ready view in a
  later handoff-ready comparison
- Phase 2 now also hardens parity-summary fallback for staged shell-comparison
  fields: `paper_vs_historical.py` now reuses the staged shell/comparison
  helper path for `historical_comparison_status_used`,
  `historical_comparison_go_no_go_used`, and
  `historical_comparison_reason_used` instead of reading those fields only
  from `execution_summary.json`, so a handoff-ready comparison still reports
  the persisted comparison outcome when the raw summary loses only those
  fields
- Phase 2 now also hardens lifecycle provenance fallback from the persisted
  fill artifact path: `lifecycle.py` now rebuilds `fill_source_type` and
  `fill_source_id` from the reviewed fill-phase artifact when
  `execution_summary.json` is partial, so the opened paper position still
  records correct provenance in the lifecycle artifacts
- Phase 1 now also shares multi-event trade display-row preference, with the
  operator dashboard switching from inline "prefer latest terminal row"
  selection to a shared trade-ledger helper and no runtime behavior change
- Phase 1 now also shares latest-trade summary counting, with the operator
  dashboard switching from inline open/action/closed summary count rules to a
  shared trade-ledger helper and no runtime behavior change
- Phase 1 now also shares trade status-label lists and closed-row follow-up
  note wording, with the operator dashboard switching from inline badge/note
  construction to shared trade-ledger helpers and no runtime behavior change
- Phase 1 now also shares trade message normalization, with the operator
  dashboard switching from inline S23-specific message cleanup to a shared
  trade-ledger helper and no runtime behavior change
- Phase 1 now also shares option and branch display labels, with the operator
  dashboard switching from inline option/branch label mapping to shared
  trade-ledger helpers and no runtime behavior change
- Phase 1 now also shares P&L tone selection, with the operator dashboard
  switching from inline positive/negative CSS-class selection to a shared
  trade-ledger helper and no runtime behavior change
- Phase 1 now also shares paper position-manager status classification across
  the trade layer, position manager, and lifecycle supervisor, replacing
  duplicated manager-status interpretation with shared helpers and no runtime
  behavior change
- Phase 1 now also shares paper-order-to-trade-row mapping, with the operator
  dashboard switching from inline waiting/not-filled order rewrites to shared
  order-state helpers and no runtime behavior change
- Phase 1 now also aligns dashboard carry-forward override checks with the
  shared position-state active helper, replacing a local active-status list
  with shared lifecycle vocabulary and no runtime behavior change
- Phase 1 now also shares pending-order trade-monitor visibility, with the
  operator dashboard switching from a local waiting/not-filled order-status set
  to a shared order-state helper and no runtime behavior change
- Phase 1 now also closes a remaining S21/S23 final-leg parity gap, with the
  operator dashboard switching from S23-only branch-prefix normalization and
  rule-folder lookup to strategy-aware branch normalization/loading so S21
  failed-leg rows still render correctly when artifacts mix prefixed and
  unprefixed branch names
- Phase 1 now also exposes neutral open-position discovery aliases, with the
  S23 position-watch entrypoint switching to that neutral seam while
  preserving the same watcher behavior and focused test coverage
- Phase 1 now also exercises neutral lifecycle/finalizer aliases in the live
  TFIS paper entrypoints, with the S23 position-watch and stale-order
  finalizer scripts switching to the shared alias layer while preserving the
  same runtime behavior
- Phase 1 now also centralizes resumable paper-position eligibility in the
  recovery/startup wrappers, with S21, S23, and TFIS reset flows switching to
  one shared PowerShell helper for open/carried/resumed plus carry-forward and
  expiry checks instead of re-declaring that rule in each wrapper
- Phase 1 now also aligns blocked-fresh-order recovery and captured-session
  replay with the shared lifecycle vocabulary, with
  `paper_position_blocks_new_entry` owning the "still blocks a fresh order"
  rule and the promotion/validation scripts switching away from local status
  sets while preserving runtime behavior
- Phase 1 runtime-consistency refactor is complete for the current scope:
  shared lifecycle vocabulary now spans the meaningful duplicated S21/S23
  dashboard read-model, Python entrypoint, replay, and startup/recovery seams,
  so the next architecture move is Phase 2 contract design rather than more
  Phase 1 micro-extractions
- S23 operator dashboard strike audit now shows rule-sheet search order,
  side-filtered and expiry-scoped full strike scans, derived rejection reasons,
  and explicit qualification reasons for `PASSED` and `SELECTED` rows
- FYERS-backed S23 option-chain collection now requests expiry-specific chains
  with a configurable wider strike count, so Step 8c near-then-next expiry
  fallback can be populated by broker data rather than relabeled/default
  near-expiry responses
- S23 FYERS snapshot collection now verifies that the next-expiry request
  contains contracts whose normalized symbols truly belong to the requested
  next weekly expiry; relabeled/default near-expiry responses fail closed with
  `NEXT_WEEKLY_OPTION_CHAIN_UNAVAILABLE`
- Monthly Status Calculator now includes daily, weekly, and monthly
  market-structure candlestick charts with reference lines, hover inspection,
  fixed inspector context, visibility controls, review-date marker, and color
  legend for manual validation
- S23 scheduled startup now launches separate paper watcher processes for every
  produced paper order or open paper position instead of skipping automatic
  watching when a two-leg session creates both CE and PE orders
- S23 paper mode now has a post-cutoff waiting-order finalizer and registerable
  Windows task wrapper, so same-session paper orders that never triggered can be
  marked `PAPER_ORDER_NOT_FILLED` even if a watcher process exits before cutoff
- S23 scheduled startup now exits cleanly with `MARKET_CLOSED_NO_ACTION` when
  the supervised snapshot window has no intraday FYERS candles, so holidays or
  closed-market days do not register as failed scheduled-task runs
- S23 Windows Scheduled Task registration now creates a Monday-Friday trigger,
  and the wrapper uses a local NSE holiday calendar to skip weekends/holidays
  before token refresh or watcher startup
- S23 scheduled-task registration now defaults `IfPast` to `run_now`, matching
  the Python and wrapper entrypoints and preventing the false late-checkpoint
  abort that could leave the morning session without fresh artifacts or
  watchers after a normal 09:08 startup
- S21 now has TFIS-only Windows startup wrappers for daily supervised paper
  runs: `start_s21_fyers_morning_supervised_decision.ps1`,
  `register_s21_fyers_morning_supervised_task.ps1`, and
  `check_s21_fyers_morning_supervised_task.ps1`. This closes the gap where S21
  had a runnable Python entrypoint but no durable scheduled-task bootstrap
  comparable to S23
- S23 supervised live paper finalization now keeps the ORPT-selected base
  strike/order when the selected option has not missed entry, and uses RC only
  for the revised missed-entry recalculation path
- S23 paper position management now persists strategy parameters and next-day
  stoploss reset state for carried positions. After a 15:00 carry-forward, the
  next trading day keeps target active, holds SL inactive through the opening
  window, reactivates original SL at ORPT when `09:15` high does not miss SL,
  or recalculates revised SL from RC high plus configured `sl_reference_pct`
  when the `09:15` high misses SL.
- S23 carried-position state transitions now preserve strategy parameters and
  next-day SL-reset metadata across explicit carry-forward and resume calls.
  This gives offline restart-safety proof that an overnight carried paper
  position does not accidentally lose ORPT/RC reset times, reset buffer,
  stoploss inactive/pending state, or reset reference price before the next
  session watcher manages it.
- S23 runtime/timeline reconstruction now supports ORPT-stage evaluation before
  RC exists, so the dashboard and scheduled runner do not fail with missing RC
  bars during the live `09:25` window
- S23 scheduled startup wrapper now captures the supervised Python process into
  TFIS stdout/stderr launch logs before scanning metadata and starting watchers,
  avoiding a stalled PowerShell pipeline that could leave valid paper orders
  without current-price monitoring
- S23 scheduled startup wrapper now scopes watcher startup metadata discovery
  to the current run date, preventing a later-touched stale session from
  launching or confusing watcher windows for the current market day
- S23 now has `scripts/start_s23_paper_watchers_from_metadata.ps1`, a TFIS-only
  recovery launcher that starts watcher windows from produced paper
  order/position metadata without rerunning the morning decision
- S23 watcher launchers now handle mixed waiting-order and open-position branch
  state, deriving state mode from an existing `paper_position_state.json` when
  a branch fills after the original scheduled-run metadata was written
- S23 scheduled startup now discovers persisted open/carry-forward
  `paper_position_state.json` files under the durable S23 artifact root, passes
  the latest open position into the supervised decision runner as carry-forward
  context, and starts state watchers for all eligible open positions alongside
  fresh current-day order watchers
- S23 Trades Taken dashboard now shows selected-contract stream health from
  persisted watcher evidence: event count, latest quote/bar timestamp,
  age/staleness, watcher PID, source, and a direct Market Events artifact link.
  This makes current-price freshness auditable without changing strategy
  selection, order routing, or watcher lifecycle behavior.
- Operator dashboard JSONL readers now stream line-by-line instead of loading
  the whole file into memory first. This reduces reset/build stalls when large
  selected-contract market-event logs are present beside active paper states.
- TFIS dashboard startup no longer pays the full rebuild cost twice during the
  normal reset flow. `reset_tfis_dashboard_and_watchers.ps1` now performs the
  single explicit build and launches `serve_operator_dashboard.py` with
  `--skip-build`, so the server opens port `8765` without repeating the same
  dashboard generation step in-process.
- The local pre-live readiness gate is currently green for the prod-paper
  profile. On `2026-07-16`,
  `scripts/pre_live_readiness.py --profile prod --require-token --json`
  returned `overall_status=PASS` across project structure, strategy config,
  dashboard config, monthly-status config, and TFIS FYERS token checks.
- On `2026-07-16`, TFIS also closed a same-day runtime/dashboard consistency
  gap: the S23 morning wrapper now allows benign stale-lock reclaim stderr to
  pass through normal exit-code handling instead of aborting the wrapper early,
  and the shared live-monitor visibility rule now keeps closed rows with event
  dates newer than the latest completed strategy session out of the live trades
  view so they remain historical-only until a fresh session is produced
- S23 captured-session replay validation now covers expiry force-close and
  next-day stoploss reset states. Expiry force-close is confirmed from persisted
  position-manager events plus expiry date/force-close time, and next-day SL
  reset pending/completed states are reported distinctly from generic open
  position replay.
- TFIS Manual Operator Guide now includes a money-readiness command reference
  table covering focused tests, syntax checks, captured-session replay
  validation, dashboard launch, scheduled-task checks, watcher recovery, and
  pre-live readiness checks with purpose, timing, expected checks, and safety
  notes.
- S23 supervised decision and paper watcher startup now enforce PID-aware
  single-instance process locks, fail duplicate live-PID launches with
  `CRITICAL_DUPLICATE_PROCESS_SHUTDOWN`, and reclaim stale dead-PID locks with
  an auditable `STALE_PROCESS_LOCK_RECLAIMED` message
- S23 supervised decision and paper watcher single-instance guards now have
  offline proof at the S23 entrypoint level. Tests verify stable lock identity,
  branch/prefix isolation, duplicate live-PID fail-closed behavior, and
  retained lock metadata for operator diagnosis without launching live
  processes.
- S23 scheduled startup now preserves single discovered carry-forward state
  paths as arrays, preventing the 2026-07-03 PowerShell scalar edge case where
  one Windows path was truncated to its drive letter before Python invocation.
  The wrapper also normalizes carry-forward state arguments to absolute
  directories before Python/watch subprocess handoff.
- S23 carry-forward resume now still computes same-day fresh CE/PE leg
  decisions for audit, while fresh paper order creation during an existing open
  position is controlled by the configurable
  `allow_fresh_entry_with_open_position` strategy flag. Decision summaries and
  scheduled-run metadata now expose `order_placement_blocked` details so the
  dashboard can show calculated daily candidates without implying an order was
  routed.
- S23 now has a guarded post-carry-exit promotion utility:
  `scripts/promote_s23_blocked_fresh_order.py`. It promotes an already
  calculated same-day S23 `READY` decision that was blocked by an active
  carry-forward position into a normal waiting paper order only after scanning
  durable S23 artifacts and proving no active S23 paper position remains. The
  2026-07-06 carried PE target-hit case used this path to promote the fresh
  Bear Call decision while preserving the existing
  `allow_fresh_entry_with_open_position=false` execution gate.
- S23 Trades Taken dashboard now renders target/SL exits that also require a
  fresh-entry recalculation as clean closed rows. The fresh-entry requirement is
  retained as follow-up text, and any new waiting entry remains represented by
  its own paper-order row.
- S23 Calculation Explanation now shows CE/PE stepwise cards side by side on
  wide screens, with direct CE/PE leg links before the detailed cards, making
  both branch calculations easy to locate even when the first branch's inline
  strike audit is long.
- S23 captured-session validation and dashboard final-leg review now include
  latest stage-level no-contract calculations when no final
  `trade_decision_summary.json` exists for a branch. This keeps CE/PE review
  complete on carry-forward days and on failed-leg days: selected branches show
  final contracts, while no-contract branches show failure code and formula
  audit context instead of disappearing from the operator view.
- S21 BankNifty monthly option-selling is now implemented as a controlled
  paper-mode candidate for all four rule-sheet legs, with configurable
  parameters, a dedicated `tfis.rules.s21_rule_matrix`, focused unit coverage,
  `ACTIVE_CANDIDATE` registry entries, an S21 paper config/runner wrapper, and
  dashboard multi-strategy registration.
- Generic enabled-strategy execution planning now exists under
  `tfis.strategy.execution_plan`. It builds a broker-agnostic plan from runtime
  config, skips disabled strategies, checks registry status and supported
  executor names, and fails closed for unsupported enabled strategies. Current
  S23 paper configs declare their enabled S23 entry, branch registry IDs, and
  strategy paths for later runner wiring.
- S23 captured-session validation now has a repeatable offline command that
  summarizes durable supervised-session artifacts by date/branch, reconstructs
  blocked fresh CE/PE calculations from captured 09:30 option-chain snapshots,
  and separates decision/order evidence from missing full selected-contract
  price-stream evidence.
- S23 paper watcher runs now write selected-contract quote/bar observations to
  `selected_contract_market_events.jsonl`, giving future market sessions a
  replayable evidence trail for entry, target, stoploss, and dashboard current
  price updates.
- S23 captured-session validation now replays waiting paper-order outcomes from
  persisted selected-contract quote/bar observations, confirming filled,
  not-filled, or still-waiting outcomes offline and flagging mismatches between
  the market evidence stream and persisted paper order state.
- S23 captured-session validation now also replays persisted position threshold
  outcomes from selected-contract quote/bar observations, confirming target,
  stop/FSL, or still-open/carry-forward states and flagging lifecycle
  mismatches for manual review.
- S23 dashboard strike qualification and Step 8 audit tables now include
  candidate expiry and wrap long rejection reasons, improving manual validation
  when near and next expiry rows contain overlapping strikes
- S23 dashboard final leg decisions now show selected contract expiry, and
  strike-range explanation text derives the buffer percentage from the resolved
  strategy formula instead of hardcoded workbook wording
- strategy and workbook normalization work is established for the S23 family
- reference materials are now indexed and reviewable through archive metadata
- deterministic monthly-status classification is implemented for the confirmed threshold rules
- optional monthly-status-driven branch selection is available in historical backtests
- opt-in S23 missed-entry detection and recalculation is available in historical backtests
- opt-in S23 current-day FSL / TRP missed / not-missed handling is available in historical backtests
- dedicated spot intraday sourcing is available for the opt-in S23 recalculation path
- S23 put-side recalculated strike wording is resolved as a confirmed workbook correction
- S23 option rollover is clarified as not applicable
- `AB6 OS` current-day FSL / TRP rows `183-188` are now cell-audited and implemented only within their confirmed workbook-backed scope
- a broader `AB6 OS` recalculation audit across rows `162-191` is now captured, confirming no extra target override formulas in that block and identifying `Z183:Z186` as workbook-backed current-day entry cells
- workbook-backed current-day option-entry overrides from `AB6 OS!Z183:Z186` are now implemented for supported rows `183-186`
- expiry-day lifecycle review is available in historical reports when selected contract expiry metadata exists
- opt-in option-chain contract selection realism is available in historical backtests
- opt-in contract-specific lifecycle pricing is available when symbol-keyed intraday bars exist for the selected contract
- contract-specific lifecycle provenance now records selected symbol, bar availability, fallback reason, and actual lifecycle price source per trade
- a normalized apples-to-apples lifecycle-source report pair is now in place; on the current fixture set it now isolates 10 trades using real selected-contract bars, 0 explicit fallback, 100.0% lifecycle coverage, and one lifecycle-source-only P&L delta
- a dedicated S23 contract archive ingestion plan is now documented so the next realism step can move from deterministic fixtures toward normalized real/archive contract bars without changing S23 logic
- an S23-only paper-trading readiness audit is now documented, and the current readiness conclusion is explicitly `NO-GO` until paper-runtime data, execution, visibility, and failure-handling gaps are closed
- S23 live-paper normalized data contract and session state-machine blueprints are now documented, defining the next safe implementation boundary for paper runtime scaffolding
- S23 live-paper schema scaffolding and required-field validation are now implemented under `src/tfis/paper`, including normalized event models, no-trade or abort validation results, and session manifest building
- S23 paper-session orchestrator skeleton is now implemented under `src/tfis/paper/orchestrator.py`, with deterministic transitions through `ORDER_PLANNED`, `NO_TRADE`, and `ABORTED`
- S23 paper-session persistent artifacts and journaling shell are now implemented under `src/tfis/paper/artifacts.py`
- S23 paper kill-switch and failure-handling guardrails are now implemented under `src/tfis/paper/guardrails.py` and integrated before `ORDER_PLANNED`
- S23 paper replayable session bundles are now implemented under `src/tfis/paper/replay_bundle.py`
- S23 paper operator-facing review summaries are now implemented under `src/tfis/paper/review.py` and `scripts/review_paper_session.py`
- S23 paper order-intent and execution-journal shell is now implemented under `src/tfis/paper/execution_journal.py`
- S23 paper post-planning failure handling and kill-switch controls are now implemented over the intent shell
- S23 paper-vs-historical replay comparison over the persisted intent shell is now implemented under `src/tfis/paper/paper_vs_historical.py` and `scripts/compare_paper_to_historical.py`
- S23 later-phase execution-shell controls beyond `INTENT_READY` are now implemented over the persisted intent shell
- S23 paper-vs-historical replay comparison is now execution-shell-aware, so it can distinguish planning parity from later pre-execution readiness outcomes
- S23 fillless dispatch shell beyond `EXECUTION_ARMED` is now implemented, and replay comparison now distinguishes later dispatch readiness from earlier arming readiness
- S23 final no-fill execution handoff boundary after `ORDER_INTENT_DISPATCHED` is now implemented, and replay comparison now distinguishes later handoff readiness from earlier execution-shell and dispatch-shell outcomes
- S23 Paper Trading MVP v1 fill simulator and lifecycle-loop design is now documented, so the no-fill shell has a reviewed implementation target instead of an open-ended future phase
- S23 Paper Trading MVP v1 Phase 1 fill simulator is now implemented, so the paper shell can record deterministic `filled`, `not filled`, or `aborted` outcomes without yet opening a paper position
- S23 Paper Trading MVP v1 Phase 2 same-day lifecycle loop is now implemented, so a filled paper order can now open a paper-only position, close on target or stoploss, square off at EOD, or abort explicitly on lifecycle-time data failure
- a broker-agnostic live-paper ingress foundation is now implemented, with `src/tfis/brokers/base.py` defining the adapter boundary, `src/tfis/brokers/fyers.py` providing the first FYERS market-data adapter, and `src/tfis/paper/live_ingress.py` reusing the normalized S23 paper ingress path without exposing S23 to raw broker payloads
- the first broker-backed S23 ingress runner now persists `broker_health.json`, `normalized_events.jsonl`, `ingress_summary.json`, and `no_trade_or_order_plan_summary.json`, while still blocking any broker order placement and stopping at planning by default
- the FYERS ingress runner now also has a strict `--preflight-only` mode plus a dedicated live runbook, so a local operator can validate credentials, paper-only scope, kill-switch posture, and required prelude snapshots before any broker connection attempt
- a read-only TradingEngine capture adapter audit plus prototype now exists, proving that `ticks_context.csv` and `NIFTY50_option_quotes_YYYYMMDD.csv` can feed the S23 market-data leg as normalized TFIS events while still requiring TFIS-side prelude inputs for monthly status and workbook trade plans
- a paired TradingEngine capture plus TFIS prelude ingress-only suite now exists, and the first six real-date run showed that the capture timing path is operationally sound but still `NO_GO` because the raw option quote archives carry blank `oi` at decision time
- read-only shared captured-data adapter is available for normalized CSV roots
- comparison reporting across historical backtest modes is available as a read-only reporting tool
- S23 mode comparison reporting is now bounded, deterministic, and summary-based rather than relying on unbounded raw JSON comparison
- S23 mode comparison now records input-dataset paths, cost settings, and apples-to-apples status; the earlier row-183 `current_day_fsl_trp` exit flip did not reproduce after rerunning all six modes on one shared dataset set
- quality snapshot:
  - last full-suite snapshot before the S21 scaffold: tests passing `426`
  - S21/strategy focused validation for this task: `20 passed`
  - `python scripts/validate_project.py`: passed

## Completed

- S23 live ORPT/RC timing recalculation is now implemented in the supervised
  live decision path: provisional base selection, selected-contract option-bar
  collection through the broker adapter, fail-closed missing-timing behavior,
  missed-entry recalculation, and final near/next contract reselection are
  covered by focused unit tests.
- S23 missed-entry recalculation now uses loaded strategy parameters for strike
  buffer, premium thresholds, entry discount, target percentage, and SL entry
  percentage, removing duplicate hardcoded recalculation constants while
  preserving the canonical S23 YAML formula contract. The opt-in current-day
  FSL/TRP overlay now uses the same parameter handoff for its confirmed
  workbook-backed strike, premium, entry, and FSL calculations.
- S23 paper position management now implements the rule-sheet 15:00
  continuation decision after target/SL/FSL/expiry checks, with an auditable
  carry-forward reason when overnight SL is inactive.
- Earlier S23 15:00 continuation ambiguity is now resolved by the updated rule
  sheet: TFIS applies the 15:00 original-SL comparison and carries forward with
  overnight SL inactive when the option price is not above original SL.
- broker-agnostic architecture
- strategy folder layout
- S23 all four branches
- Excel cross-checks
- formula safety validation
- branch selector
- strategy registry governance
- strategy registry enforcement
- shared market-data direction
- reference materials indexed
- review workflow added
- archive governance added
- historical lifecycle backtesting
- EOD policies
- cost and slippage model
- rupee P&L reporting
- equity curve and drawdown reporting
- monthly-status thresholds
- monthly-status decision table
- monthly-status engine
- optional monthly-status-driven historical branch selection
- monthly-status CLI report
- monthly-status manual scenarios
- S23 missed-entry detection foundation
- opt-in S23 historical recalculation mode
- dedicated spot intraday sourcing for opt-in S23 recalculation
- opt-in S23 current-day FSL / TRP missed / not-missed handling
- opt-in option-chain contract selection realism foundation
- opt-in contract-specific lifecycle pricing foundation
- contract-specific lifecycle provenance now records selected symbol, bar availability, fallback reason, and actual lifecycle price source per trade
- a normalized apples-to-apples lifecycle-source report pair is now in place; on the current fixture set it now isolates 10 trades using real selected-contract bars, 0 explicit fallback, 100.0% lifecycle coverage, and one lifecycle-source-only P&L delta
- read-only shared captured-data adapter foundation
- S23 option rollover clarified as not applicable
- expiry-day lifecycle review and audit for selected contracts
- cell-level audit for S23 current-day FSL / TRP rows `183-188`
- comparison reporting across historical backtest modes
- bounded and deterministic S23 historical mode comparison reporting
- apples-to-apples S23 mode comparison rerun with shared datasets and shared cost settings
- deterministic apples-to-apples applied-case fixture added for S23 current-day FSL / TRP row-183 validation
- broader `AB6 OS` rows `162-191` recalculation audit completed, confirming no workbook-backed target overrides in that block and flagging `Z183:Z186` as workbook-backed current-day entry cells
- workbook-backed current-day option-entry overrides from `AB6 OS!Z183:Z186` implemented for supported rows `183-186`
- S23 live-paper normalized data contract blueprint documented
- S23 paper-session state-machine blueprint documented
- S23 live-paper schema scaffolding and required-field validation implemented
- S23 paper-session orchestrator skeleton implemented through `ORDER_PLANNED` / `NO_TRADE` / `ABORTED`
- S23 paper-session persistent artifacts and journaling shell implemented
- S23 paper kill-switch and failure-handling guardrails implemented before planning
- S23 paper replay-bundle manifests, validation, and readback summaries implemented
- S23 paper operator-facing review summaries implemented
- S23 paper order-intent and execution-journal shell implemented
- S23 paper post-planning failure handling and kill-switch controls implemented
- S23 paper-vs-historical replay comparison over the persisted intent shell implemented
- S23 later-phase execution-shell controls beyond `INTENT_READY` implemented
- S23 paper-vs-historical replay comparison extended through the execution-shell readiness layer
- S23 fillless dispatch shell beyond `EXECUTION_ARMED` implemented
- S23 final no-fill execution handoff boundary after `ORDER_INTENT_DISPATCHED` implemented
- S23 Paper Trading MVP v1 fill simulator and lifecycle-loop design documented
- S23 Paper Trading MVP v1 Phase 1 fill simulator implemented
- S23 Paper Trading MVP v1 Phase 2 same-day lifecycle loop implemented
- broker-agnostic live-paper ingress foundation implemented with FYERS as the first market-data adapter
- S23 FYERS live-paper preflight-only safety gate and local runbook implemented
- read-only TradingEngine capture audit and market-event adapter prototype implemented for one-session S23 dry-run inputs
- TradingEngine capture plus TFIS prelude ingress-only suite implemented and exercised across six real captured dates; all six sessions ended `ABORTED` with `missing_contract_oi`, confirming that this path is currently limited by raw option-quote OI completeness rather than by timing or selected-contract discovery
- S23 morning supervised operational artifacts now default to durable storage
  under `data/strategies/S23/fyers_morning_supervised_decision`, keeping
  option-chain snapshots, decisions, paper orders, paper positions, and
  ledger/state files out of temp-only storage while leaving rebuildable
  dashboard HTML and short-lived launch logs in `tmp`
- S21 BankNifty monthly option-selling rule/config scaffold implemented for
  Bull Call, Bull Put, Bear Call, and Bear Put with configurable rule-sheet
  parameters and focused validation tests
- TFIS-only reboot recovery script now waits for prior TFIS runtime processes
  to exit and skips starting duplicate dashboard servers or duplicate watcher
  targets when the same reset path is rerun after a delayed startup or reboot
- TFIS reboot recovery now also starts dashboard and watcher/runtime consoles
  as visible windows instead of hidden background processes, making the active
  TFIS runtime discoverable to the operator after restart
- S23 paper waiting-order and open-position lifecycle handling now runs through
  one shared supervisor module, reducing watcher-script branching while
  preserving existing state, ledger, market-event, and dashboard artifacts
- TFIS now has `scripts/pre_live_readiness.py`, a repo-local pre-market audit
  that verifies core imports, strategy execution plans, dashboard config,
  monthly-status config, and optional FYERS token availability without placing
  orders
- TFIS reset/recovery now restores watcher windows only for same-day waiting
  orders and for live carry-forward/open/resumed positions; prior-session
  waiting orders are no longer relaunched after reboot/reset, and live carried
  positions are rediscovered from the full strategy artifact root instead of
  only from the latest session metadata
- the operator dashboard now resolves stale S23 carry-forward blockers against
  the latest persisted position state, so closed carry-forward trades show
  `PAPER_FRESH_ENTRY_REQUIRED` instead of misleading `OPEN_CARRY_FORWARD_POSITION`,
  and shared paper-order cutoff messages are now strategy-neutral for S21/S23
- the operator dashboard now includes a dedicated historical closed-trades page
  under `trades/history/index.html`, with cross-strategy strategy/date filters
  and consolidated entry/exit/P&L review sourced from persisted trade ledgers
- the live all-trades monitor now keeps post-session terminal closes visible for
  multi-session paper trades, so next-day S23 target/SL exits remain visible in
  `trades/index.html` even when the latest decision session is still the prior day
- the trade monitors now add consistent row/status color coding for closed,
  waiting, not-filled, open, and action-needed trade states, improving operator
  scanability without changing lifecycle logic
- the S23 scheduled-task checker wrappers now use deterministic task lookup and
  the full `System32\\schtasks.exe` path, surfacing access-denied or shell-level
  query failures explicitly instead of silently matching the wrong task-name
  variable
- a readiness-focused regression slice now passes with `77` targeted tests, the
  dashboard build succeeds for S21/S23/all-trades pages, and the latest
  captured-session validator confirms `2026-07-08` as a clean
  `PAPER_ORDER_NOT_FILLED` waiting-order outcome from persisted market-event
  evidence
- TFIS morning startup now reaches the real provider auth preparation step
  without the embedded Python quoting failure previously seen as
  `print(fPrepared`, and auth preparation now runs before dashboard build/start
  in morning-startup mode; the remaining proof point is an operator-shell rerun
  that can access FYERS over HTTPS and either reuse a valid token or complete
  the refresh.
- TFIS morning startup now parses configured strategy wrappers robustly from
  `config/paper_lifecycle_supervisor_targets.yaml`: S23 and S21 are invoked as
  separate wrappers, failures are recorded per wrapper, and the shared
  supervisor is still started for operator visibility and recovery evidence.
- Operator dashboard readability improved: the status panel now uses a compact
  health strip, grouped operational sections, collapsed diagnostics for long
  runtime paths, and a cleaner neutral visual system while preserving the
  existing operator labels and strategy-aware dashboard evidence.
- Operator dashboard post-market status wording is now market-phase aware:
  stale selected-contract streams and stale-only filesystem supervisor
  heartbeats after the `15:30` lifecycle cutoff are shown as closed/final
  snapshot evidence, while active-market stale evidence remains a warning.
- FYERS-backed S23 morning snapshot preflight now retries transient malformed
  quote/option-chain snapshot reads, records retry success as operator-visible
  preflight evidence, and preserves fail-closed `BROKER_SNAPSHOT_FAILED`
  behavior after bounded retry exhaustion.
- Paper trade ledger append safety is now hardened with per-ledger lock files,
  append-only JSONL writes, stale-lock cleanup, timeout errors for held locks,
  and focused concurrent-write coverage.
- Runtime status process reporting now prints both raw `RuntimeProcesses` and
  `RuntimeProcessComponents`, while dashboard/supervisor counts use logical
  components to avoid double-counting PowerShell launcher plus Python child
  pairs.
- Active-market shared-supervisor-only recovery is now documented and wired
  into `reset_tfis_dashboard_and_watchers.ps1 -RecoverSharedSupervisor` with
  guardrail, waiting-order, reconciliation, and order-routing safety checks.

## Next Recommended Priorities

- validate the corrected S23 paper flow on the next real NSE trading day,
  including watcher startup, current-price updates, fill status, P&L, and
  cancellation/non-carry-forward of unfilled waiting orders
- keep monthly-status calculation independent and reusable for future enabled
  strategies
- validate the durable S23 data-root default on the next scheduled market run
  and decide whether to backfill older tmp-based sessions into the new
  `data/strategies/S23/fyers_morning_supervised_decision` layout
- introduce generic enabled-strategy execution through registry/config before
  enabling S21 or other strategies operationally
- run further real local FYERS market-data-only ingress sessions under the
  preflight runbook during market hours
- broaden the broker-backed S23 ingress-only validation set across more normalized archive and replay sessions
- decide whether TradingEngine option-quote captures can be enriched with reliable OI before using them for ingress-only acceptance
- run the first tightly controlled broker-backed live-like fill and same-day lifecycle rehearsal only after ingress thresholds stay green
- broader real/archive contract-specific coverage pilot
- raw shared capture-format adapters beyond normalized CSV roots

## Explicitly Pending

- tighter same-day S23 paper lifecycle parity policy and operator close-out rules
- first real local FYERS market-data-only ingress session under operator sign-off
- fuller strike-availability realism and broader contract-specific archive coverage
- OI-enriched TradingEngine capture path if we want those sessions to qualify for ingress-only acceptance rather than market-data-leg validation only
- raw shared capture-format adapters beyond normalized CSV roots
- futures rollover lifecycle module
- monthly option buying engine
- broad multi-broker live runtime beyond the current market-data-only FYERS adapter

## Notes

- The current project is strong on offline rule validation, workbook tracing, and structural backtesting.
- Production-grade runtime behavior is intentionally deferred until broader broker-backed ingress evidence, operator close-out enforcement, and controlled live-like paper rehearsals are clarified.
