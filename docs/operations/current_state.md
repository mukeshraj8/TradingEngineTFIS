# Current State

This is the living operational snapshot for TFIS. It should be updated whenever
implemented behavior, architecture shape, test posture, or known limitations
change in a meaningful way.

## Current Focus

- execute the weekend live-money-readiness track in
  [`docs/operations/next_steps.md`](docs/operations/next_steps.md), while
  respecting the repository contract that TFIS remains paper-safe until live
  capability is explicitly proven and approved
- close remaining paper-runtime gaps that would block a credible live-money
  decision: lifecycle correctness, trade-state reconciliation, supervisor
  recovery, broker-ingress failure handling, and operator guardrails
- keep broker neutrality intact while hardening live readiness: FYERS remains
  the default configured provider, but reusable runtime, dashboard, and chart
  flows must stay provider-agnostic; `D:\TradingEngineProd` may be used only
  as read-only implementation reference
- complete each checklist item with focused tests and operator-facing
  verification before moving to the next item, then finish with a broader
  readiness pass and explicit go/no-go risk review
- improve the operator dashboard into a multi-strategy control surface with
  clear navigation for strategy pages, all trades, historical trades, and
  chart review, including selected-scrip and NIFTY chart visibility
- as of Saturday, July 18, 2026, the live trade-monitor rendering now treats
  terminal trade rows as historical-only display candidates by default, so
  closed rows no longer compete with waiting/open/action-needed rows inside the
  active strategy and all-trades monitors; the remaining Step 2 work is the
  actual fresh-entry handoff and supervisor-state correctness after terminal
  exits
- the shared lifecycle supervisor groundwork now also carries explicit
  relaunch metadata per strategy target and exposes a broker-neutral paper
  supervised-task launcher seam for both S21 and S23, so the remaining Step 2
  runtime work can wire fresh-entry handoff through shared runtime metadata
  instead of wrapper-specific script assumptions
- the shared lifecycle supervisor now also has a first automated
  `PAPER_POSITION_FRESH_ENTRY_REQUIRED` handoff path: when a terminal fresh
  entry result is emitted, TFIS can build and launch one fresh supervised
  decision request through shared per-strategy runtime metadata rather than
  stopping at a passive terminal flag; as of Saturday, July 18, 2026, that
  launch is also guarded by a durable per-session marker so restart or repeat
  polling cannot spawn the same fresh decision twice for one closed trade;
  and the supervisor now prefers promoting an already-calculated blocked
  same-day READY decision through the shared fresh-entry promotion helper
  before it falls back to spawning a brand-new supervised run
- the final weekend Step 2 dashboard-truth slice is now in place too: live
  trade rows no longer present a concrete current price when no selected-
  contract stream evidence exists, and stale live quotes are explicitly marked
  as stale instead of looking silently current
- the first weekend Step 3 operator-control slice is now in place as well:
  TFIS now has a dedicated `scripts/stop_tfis_runtime.ps1` command, and the
  runtime-process detection/stop logic used by dashboard reset now lives in one
  shared PowerShell helper so reset and manual stop follow the same TFIS-only
  process ownership rules
- keep monthly status independent and reusable while improving generic
  enabled-strategy execution and durable calculation storage
- validate the newly enabled S21 BankNifty monthly paper-mode path tomorrow as
  an `ACTIVE_CANDIDATE`, including reference-packet freshness, monthly-expiry
  selection, dashboard page rendering, and watcher/order-state visibility
- harden the TFIS-only restart/bootstrap path so rerunning the recovery script
  after a workstation reboot yields one dashboard server and one watcher per
  persisted order/position target instead of stacking duplicate processes
- keep the local pre-live gate green before market open: as of `2026-07-16`,
  `scripts/pre_live_readiness.py --profile prod --require-token --json`
  returns `overall_status=PASS` with project structure, strategy configs,
  dashboard config, monthly-status config, and TFIS FYERS token checks all
  passing
- keep same-day runtime and dashboard truth aligned when a strategy session
  stalls: as of `2026-07-16`, the S23 morning wrapper now suppresses
  PowerShell native-command exceptions from benign stderr-only process-lock
  reclaim messages, and the shared live-trade visibility rule now hides closed
  rows whose event date is newer than the latest completed strategy session so
  stale closed trades stay in historical review instead of leaking into the
  live monitor
- keep Phase 4 broker/data-source separation moving in small safe slices: as
  of Friday, July 17, 2026, the shared TFIS paper lifecycle supervisor no
  longer hardcodes `FyersBrokerAdapter` or the S23 ingress config type inside
  its runtime bootstrap path, and now resolves its broker adapter plus minimal
  runtime config through a strategy-neutral shared paper lifecycle config layer
- keep that same Phase 4 bootstrap refactor moving without disturbing the live
  market session: as of Friday, July 17, 2026, the shared lifecycle runtime
  config layer now also owns broker-runtime environment preparation, so
  `scripts/run_tfis_paper_lifecycle_supervisor.py` no longer imports FYERS
  token/bootstrap helpers directly and now deduplicates broker-environment
  preparation once per provider before connecting adapters
- continue the same Phase 4 work in additive, non-cutover slices during market
  hours: as of Friday, July 17, 2026, TFIS now also has a shared
  `lifecycle_market_events.py` abstraction for selected-contract quote/bar
  fetch policy, including next-day SL-reset bar-fetch gating; after market,
  the shared paper lifecycle supervisor was cut over to that shared fetch path
  while preserving the existing SL-reset bar-fetch warning behavior
- the first explicit weekend Step 4 ingress-health slice is now also in place:
  as of Saturday, July 18, 2026, TFIS has shared live-state store diagnostics,
  pre-live readiness now reports and fails clearly when a configured live-
  state backend is unavailable, and both the shared supervisor plus the S23
  compatibility watcher now fail closed during bootstrap instead of silently
  falling back to a null live-state store when Redis was configured but
  unreachable
- the next Step 4 readiness slice is now in place as of Sunday, July 19,
  2026: TFIS has a local filesystem live-state backend for the supported paper
  configs, so Monday paper startup no longer depends on a local Redis service;
  the same readiness gate now also verifies that each configured paper broker
  runtime can be assembled through the shared runtime path, and when
  `--require-token` is supplied it also prepares broker auth prerequisites
  through that same shared bootstrap seam
- the next runtime-posture slice is now in place too as of Sunday, July 19,
  2026: both the shared supervisor and the S23 compatibility watcher now use
  the same shared broker runtime connect/health helper, so actual adapter
  startup failures are surfaced with strategy/provider context instead of
  falling through as generic runtime errors during live paper startup
- the same Sunday, July 19, 2026 runtime-safety pass now also removes the
  old compatibility-watch loophole where selected-contract quote fetch failure
  could leave the S23 watcher alive without trustworthy fresh evidence; if the
  watcher has no usable stream evidence and the shared quote fetch fails, it
  now fails closed instead of idling optimistically
- the operator control surface now also distinguishes between full TFIS reset
  and dashboard-only refresh as of Monday, July 20, 2026. A new
  `scripts/refresh_tfis_operator_dashboard.ps1` rebuilds/reuses the operator
  dashboard without stopping the shared supervisor, while
  `scripts/reset_tfis_dashboard_and_watchers.ps1` now explicitly warns that it
  is a full runtime restart command intended for pre-market recovery rather
  than in-market dashboard refresh
- the remaining legacy S23 compatibility watcher now also uses that shared
  selected-contract fetch-policy path for fetched quote/bar behavior while
  preserving its separate stream-tick-first fallback logic, so the selected-
  contract fetch policy is no longer duplicated across the consolidated
  supervisor and the older S23 watch script
- the remaining S21/S23 recovery launchers now identify themselves explicitly
  as supervisor-compatibility launchers instead of watcher launchers, so the
  operator-facing wrapper layer matches the current one-supervisor runtime
  model more closely during restart and recovery flows
- the S23 morning supervised wrapper no longer carries its dead pre-supervisor
  `Start-S23PaperWatchProcess` fallback, and its remaining startup logs now
  describe supervisor startup rather than watcher startup, further reducing
  wrapper-era drift from the current shared-supervisor runtime model
- that same S23 morning wrapper now also routes all shared-supervisor starts
  through one local `Start-TfisSharedSupervisor` helper instead of duplicating
  the same launcher block across metadata and discovery-mode branches
- the S21 supervised Python entrypoint now names its shared lifecycle bootstrap
  path as supervisor startup rather than watcher startup, and the market-closed
  no-action messages for both S21 and S23 now state that no supervisor startup
  was triggered, which better matches the current runtime model
- the TFIS reset/recovery script now describes stale waiting-order skips,
  duplicate targets, and launched compatibility processes as supervisor
  recovery actions rather than watcher startup, which brings the recovery
  console output closer to the actual one-supervisor runtime model
- the same reset/recovery script now also uses `Recovery` helper naming
  internally instead of `Watcher` helper naming for those compatibility-target
  scans and launches, reducing another small source of watcher-era drift in the
  implementation
- that same reset/recovery script no longer carries its old inline
  order/position-target discovery branch at all; it now rebuilds the dashboard,
  starts the local dashboard server, and hands all waiting-order/open-position
  recovery to `start_tfis_paper_lifecycle_supervisor.ps1`, which keeps reset
  ownership aligned with the current one-supervisor runtime model
- the reset flow, S21/S23 supervisor-compatibility launchers, and S23 morning
  wrapper now all share one tiny PowerShell launcher seam in
  `scripts/tfis_paper_lifecycle_supervisor_helpers.ps1`, so the visible
  supervisor process startup contract now lives in one place instead of being
  rebuilt by hand in each wrapper
- the shared paper-position helper now also owns the generic resumable-position
  filesystem scan in `Get-TfisResumablePaperPositionStatePaths`, and both the
  S21 and S23 morning wrappers now use that shared scan instead of each
  carrying its own recurse/read/filter eligibility loop locally
- the wrapper-level path normalization has also moved into the shared
  paper-position helper: both S21 and S23 morning wrappers now use the shared
  `Resolve-TfisAbsolutePathText` and
  `Resolve-TfisPositionStateDirectoryPath` helpers instead of maintaining
  separate local path-resolution functions
- the trading-holiday calendar read path now lives in one shared PowerShell
  helper, `scripts/tfis_trading_calendar_helpers.ps1`, and both S21/S23
  morning wrappers now use that shared helper for holiday-date checks instead
  of parsing the holiday JSON separately
- that same shared trading-calendar helper now also owns the generic
  `Get-TfisEffectiveRunDate` and `Get-TfisNoRunReason` logic used by the S23
  morning wrapper and S23 paper-order finalizer, so weekend/holiday no-run
  gating no longer lives in two separate S23 wrapper scripts
- the remaining Python/bootstrap task setup is also starting to consolidate:
  S21 morning, S23 morning, and the S23 paper-order finalizer now use shared
  wrapper-task helpers for Python executable resolution and timestamped task
  log-context creation instead of hand-rolling those steps separately
- the wrapper-task helper now also owns the common task-log write path, so the
  S21 morning wrapper, S23 morning wrapper, and S23 paper-order finalizer no
  longer each maintain their own timestamped log-write implementation
- the shared wrapper-task helper now also owns latest-session metadata file
  lookup for day-scoped strategy artifact roots, and the S23 morning wrapper
  now uses that helper instead of maintaining its own inline
  `scheduled_run_metadata.json` discovery walk
- the operator-facing task banner is now shared as well: the S23 morning
  wrapper and S23 paper-order finalizer both use one shared
  `Show-TfisTaskBanner` helper instead of duplicating the same visible banner
  block
- the two morning wrappers now also share the hidden Python subprocess launch
  helper in `scripts/tfis_wrapper_task_helpers.ps1`, so redirected
  stdout/stderr process startup no longer lives in duplicate S21/S23 wrapper
  blocks
- the legacy S23 compatibility watch script now also uses the shared paper
  runtime-config bootstrap path for broker-environment preparation and broker
  adapter construction, so that fallback operational path no longer imports
  `prepare_fyers_env_from_tfis` or constructs `FyersBrokerAdapter` directly in
  its top-level bootstrap
- the shared paper runtime-config layer now also owns broker-runtime assembly
  as one reusable bundle: config load, timezone resolution, and broker adapter
  construction now come from `load_paper_broker_runtime`, and both the shared
  supervisor plus the legacy S23 compatibility watch script now use that
  shared builder instead of reassembling those pieces inline
- the shared lifecycle runtime paths no longer hardwire
  `S23PaperPositionManager` directly inside the supervisor/watch bootstrap:
  both now route through an explicit shared `build_paper_position_manager`
  factory keyed by strategy code, with current S21/S23 behavior preserved
- the same shared-runtime bootstrap cleanup now also covers the remaining live
  state and expiry-governance seams: the legacy S23 compatibility watch now
  uses `build_paper_live_state_store_from_yaml(...)` instead of the S23-named
  builder alias directly, the shared lifecycle supervisor now resolves its
  default position manager through the explicit strategy-code factory instead
  of instantiating `S23PaperPositionManager()` inline, and both the shared
  supervisor plus the legacy compatibility watch now resolve expiry governance
  through a shared `build_paper_expiry_governance(...)` factory keyed by
  strategy code
- the shared lifecycle type surface is also becoming less S23-shaped where the
  behavior is already shared: TFIS now exports neutral
  `PaperPositionManager*` aliases over the existing S23 implementation, and
  `src/tfis/paper/lifecycle_supervisor.py` now uses those neutral aliases plus
  the neutral `PaperExpiryGovernance` alias in its reusable type surface
- the legacy S23 compatibility watch has now also dropped its remaining
  bootstrap dependency on `S23LivePaperIngressConfig` for timezone/runtime
  setup: it now resolves timezone, broker runtime, and lifecycle cost settings
  directly from the shared paper runtime-config layer, leaving the older watch
  path more aligned with the consolidated supervisor bootstrap
- the S23 live-decision/timeline bootstrap now also shares broker-runtime
  environment preparation through the paper runtime-config layer: the live
  decision runner exposes `prepare_live_decision_runtime_environment(...)`,
  `run_s23_live_decision_check(...)` now uses that shared helper instead of
  direct FYERS auth bootstrap, and the morning timeline runner now uses the
  same helper for its pre-collector runtime prep
- the operator dashboard monthly-status API path now also uses that shared
  live-decision runtime-prep helper instead of calling FYERS auth bootstrap
  directly, with `scripts/serve_operator_dashboard.py` accepting an explicit
  `--runtime-config` path so the shared runtime-config layer owns broker-env
  preparation consistently across dashboard, lifecycle, watch, and live-
  decision entrypoints
- the remaining S23-only ingress config surface is now also starting to thin
  where it is truly just runtime/config shape rather than strategy behavior:
  TFIS now exports neutral `Paper*IngressConfig` aliases over the existing S23
  live-ingress config dataclasses, and the S23 live-decision runner plus
  morning timeline runner now consume the neutral `PaperLiveIngressConfig`
  alias for config loading instead of naming the S23 ingress config directly
- that same ingress/runtime neutralization has now advanced one layer deeper as
  of Friday, July 17, 2026: the FYERS snapshot collector and generated-prelude
  dry-run runner now use the neutral `PaperLiveIngressConfig` and
  `PaperExpiryGovernance` aliases for shared config/governance plumbing, so the
  remaining S23-shaped ingress surface is narrowing toward truly strategy-
  specific prelude/read-model behavior rather than reusable runtime bootstrap
- the reusable prelude/position-management layer has now taken the same neutral
  typing step as of Friday, July 17, 2026: `src/tfis/paper/live_prelude.py`
  and `src/tfis/paper/position_manager.py` now type their shared expiry
  governance dependency through `PaperExpiryGovernance`, leaving the remaining
  direct S23 naming concentrated in the still-intentionally strategy-shaped
  live-ingress implementation itself
- the live-ingress module has now taken that same low-risk internal signature
  cleanup as of Friday, July 17, 2026: the reusable loader/preflight/helper
  methods inside `src/tfis/paper/live_ingress.py` now type their config
  dependency through `PaperLiveIngressConfig`, while the module still keeps its
  S23-specific runtime behavior and outward class names intact
- the shared import surface now matches that cleanup too as of Friday,
  July 17, 2026: `tfis.paper` now exports neutral `PaperBrokerPaperIngressRunner`
  plus `PaperLiveIngress*` aliases over the existing S23 ingress runner and
  preflight types, so future strategies can import the reusable seam without
  binding directly to S23 names
- the same ingress surface is now neutral end to end for its non-strategy-
  specific summary/artifact types as of Friday, July 17, 2026:
  `src/tfis/paper/live_ingress.py` and `tfis.paper` now expose
  `PaperLiveIngressSummary` and `PaperLiveIngressArtifactSet` aliases and use
  those neutral names in runner signatures, which effectively completes the
  current low-risk Phase 4 naming/plumbing cleanup around paper ingress
- the reusable ingress seam is now also exercised that way in tests as of
  Friday, July 17, 2026: the focused live-paper ingress regression file now
  imports and runs through the neutral `PaperBrokerPaperIngressRunner`,
  `PaperLiveIngressConfig`, and `PaperLiveIngressError` symbols instead of the
  S23-named imports, which proves the shared ingress surface is consumable
  without binding callers to S23 naming
- the last safe shared-surface consumers have now followed on Friday,
  July 17, 2026 as well: `scripts/run_s23_fyers_paper_ingress.py` now drives
  the ingress CLI through the neutral paper-ingress runner/error symbols, and
  the operator dashboard now resolves shared expiry-governance behavior through
  `PaperExpiryGovernance` rather than the S23-named class, leaving the
  remaining direct S23 names concentrated in the intentionally strategy-shaped
  class definitions and compatibility exports
- the shared paper ingress and expiry-governance layers have now crossed the
  final low-risk refactor boundary as of Friday, July 17, 2026: their canonical
  class definitions are now the neutral `Paper*` types in
  `src/tfis/paper/live_ingress.py` and `src/tfis/paper/expiry_governance.py`,
  with the older `S23*` names preserved strictly as compatibility aliases for
  existing callers and tests
- prove the corrected July 16, 2026 S21/S23 paper runtime on real artifacts:
  the S23 supervised wrapper now reclaims dead Windows process-lock PIDs
  correctly by checking process exit state instead of handle existence alone,
  writes a fresh `2026-07-16` session when no S23 position is open, and starts
  fresh S23 order watchers; after a TFIS-only reset, the live trades monitor
  now shows fresh `ORDER_WAITING_FOR_TRIGGER` rows for both S21 and S23 while
  the prior S23 close remains only on `trades/history/index.html`
- restore reliable daily supervised startup across both active paper strategies:
  S23 now registers with `IfPast=run_now` by default so the 09:08 wrapper does
  not fail late at the 09:30 checkpoint after a normal pre-open wait, and S21
  now has matching Windows task registration/check/start wrappers instead of
  relying on ad hoc manual invocation only
- reduce TFIS dashboard startup delay: the reset flow now builds the operator
  dashboard once and starts `serve_operator_dashboard.py` in `--skip-build`
  mode so the local server does not repeat the same expensive artifact rebuild
- as of Friday, July 17, 2026, the first full Phase 3 lifecycle-supervisor
  cutover is in place: TFIS now has one shared paper lifecycle supervisor
  process that discovers and manages S21/S23 waiting orders plus open positions
  from persisted artifacts, the S21/S23 recovery launchers now act as
  compatibility shims into that shared supervisor, the TFIS reset flow now
  starts one shared supervisor instead of one watcher process per target, and
  the local readiness gate now validates the new
  `config/paper_lifecycle_supervisor_targets.yaml` entrypoint alongside the
  dashboard and strategy configs
- execute the runtime refactor in controlled phases: Phase 1 stabilizes the
  shared paper lifecycle and dashboard consistency across S21/S23, Phase 2
  introduces a strategy-neutral trade-intent/runtime contract, Phase 3 replaces
  scattered watcher thinking with one reusable lifecycle supervisor, and Phase 4
  separates broker adapters from lifecycle management
- the planned Phase 1 runtime-consistency refactor track is now complete for
  the current scope:
  shared lifecycle vocabulary is exercised through dashboard reconstruction,
  Python runtime entrypoints, blocked-fresh-order recovery, captured-session
  validation, and S21/S23/reset startup wrappers without changing strategy
  formulas
- the next architecture move is now Phase 4 rather than more Phase 3
  micro-slices: the strategy-neutral paper runtime/read contract is in place
  across the intended Phase 2 boundaries, and the current S21/S23 paper
  lifecycle now runs through one shared supervisor process for the supported
  TFIS operational paths. The next architectural gain comes from separating
  broker/data-source adapters more cleanly from that shared lifecycle engine
  while continuing real-market validation of the new supervisor path
- Phase 2 began with its first additive contract slice: TFIS has a
  new shared paper runtime-contract layer for trade intent, fill outcome, and
  lifecycle outcome plus S23 adapter helpers that map the existing S23
  execution-journal, fill-simulator, and lifecycle artifacts onto that neutral
  shape; this is scaffolding only and does not change the current S21/S23 live
  paper behavior
- Phase 2 now also has its first consumer boundary on the read side:
  `S23PaperSessionReviewer` projects intent/fill/lifecycle review summaries
  into the neutral runtime-contract shape when the underlying persisted
  artifacts contain enough data, while incomplete planned-only review fixtures
  continue to return `None` rather than invent partial contracts; this keeps
  current TFIS runtime behavior unchanged and makes the review surface less
  S23-shaped internally
- Phase 2 now also has its second read-side consumer boundary:
  `paper_vs_historical.py` prefers the neutral review/runtime contracts for
  intent, fill, and lifecycle facts before falling back to older scattered
  S23 payload reads, while still preserving the distinction between a planned
  session and a true execution-journal `INTENT_READY` state; current TFIS live
  paper behavior remains unchanged
- Phase 2 now also reaches the simulator runtime loaders:
  `fill_simulator.py` and `lifecycle.py` prefer the neutral review/runtime
  contracts for planned entry, reference time, side/size, fill details,
  targets, stop levels, and provenance fields while keeping the old review
  fields as fallback; this moves another shared runtime boundary off
  S23-shaped reads without changing current TFIS behavior
- Phase 2 now also reaches the post-planning execution-journal runtime path in
  one small slice: `execution_journal.py` now treats an intact persisted paper
  intent artifact as enough proof to keep the post-planning shell
  `INTENT_READY` when `execution_summary.json` is missing only that field, and
  it now uses the neutral runtime-contract intent symbol only as a fallback
  when the raw intent artifact is unavailable; this preserves current TFIS
  behavior while shrinking one more fragile dependency on scattered S23-shaped
  summary reads
- Phase 2 now also centralizes the first remaining execution-journal
  post-planning summary reads: dispatch/handoff paths and their guardrail
  validations now go through shared helper methods for current execution-shell
  status and historical-comparison fields instead of repeatedly reading those
  values inline from `execution_summary.json`; runtime behavior remains
  unchanged while the remaining status reconstruction surface gets smaller
- Phase 2 now also centralizes the remaining selected-contract symbol and
  comparison-presence reads across the post-planning execution-journal path:
  execution arming, dispatch, and handoff checks now use shared helpers for
  current intent symbol, execution-summary selected contract, dispatch-summary
  selected contract, and whether historical comparison has already been
  recorded, further shrinking inline S23-shaped summary reads without changing
  TFIS runtime behavior
- Phase 2 now also introduces a neutral post-planning shell contract:
  `runtime_contract.py` defines `PaperTradeShellContract`, the S23 review layer
  now projects shell status and comparison state into that shared contract, and
  `execution_journal.py` uses the projected shell as a fallback source for
  post-planning intent/execution/dispatch/handoff status and comparison fields
  when raw summary artifacts are absent; this extends the neutral runtime
  boundary without changing live paper behavior
- Phase 2 now also has the next shared consumer of that shell contract:
  `paper_vs_historical.py` prefers the neutral shell contract for
  execution/dispatch/handoff readiness plus historical-comparison status
  fields before falling back to raw `execution_summary.json` payload reads,
  extending the strategy-neutral post-planning read boundary without changing
  TFIS paper-vs-historical comparison outcomes
- Phase 2 now also moves the Phase 1 fill simulator onto the neutral shell
  contract for post-planning shell state: `fill_simulator.py` now prefers the
  projected shell contract for handoff/execution/dispatch and
  historical-comparison readiness checks before falling back to raw
  `execution_summary.json` fields, and the review layer now rebuilds missing
  shell fields from dispatch/handoff summary artifacts when possible; runtime
  behavior remains unchanged after focused validation
- Phase 2 now also closes one more lifecycle guardrail dependency on scattered
  S23-shaped summary fields: `lifecycle.py` now prefers the neutral runtime
  fill contract for `fill_status` before falling back to
  `execution_summary.json`, so a same-day lifecycle simulation still proceeds
  correctly when the raw summary loses only that field; focused runtime
  regressions and the TFIS guard suite remain green
- Phase 2 now also hardens armed-session shell reconstruction across review and
  execution-journal paths: `review.py` now uses
  `execution_arm_summary.json` as an intermediate fallback source for
  post-planning shell/comparison fields, and `execution_journal.py` now
  prefers the projected shell contract whenever `execution_summary.json`
  exists but is missing execution-shell, dispatch/handoff, selected-contract,
  or historical-comparison fields; focused runtime regressions and the TFIS
  guard suite remain green
- Phase 2 now also broadens that armed-session fallback rule across the review
  summary itself: `review.py` now rebuilds order-intent message, reason,
  guardrail, operator-action, disclaimer, and future-fill-eligibility fields
  from persisted arm/dispatch/handoff summary artifacts when
  `execution_summary.json` is present but partial, and a direct review
  regression now proves an armed session still reconstructs its shell state
  from `execution_arm_summary.json`; focused runtime regressions and the TFIS
  guard suite remain green
- Phase 2 now also extends that partial-summary recovery into lifecycle review:
  `review.py` now rebuilds lifecycle status, exit reason/message, exit price,
  exit timestamp, warning flags, and disclaimer from `paper_exit.json`,
  `paper_pnl_summary.json`, and `paper_position.json` when
  `execution_summary.json` is present but missing lifecycle fields, and a
  direct lifecycle-review regression proves a closed paper session still
  reconstructs the correct exit outcome from those stage-specific artifacts;
  focused runtime regressions and the TFIS guard suite remain green
- Phase 2 now also extends partial-summary recovery into fill review:
  `review.py` now rebuilds fill status, reason/message, fill price/timestamp,
  provenance, spread/slippage, and disclaimer from `paper_fill.json`,
  `paper_no_fill.json`, `paper_fill_abort_summary.json`, or
  `paper_order_pending.json` when `execution_summary.json` is present but
  missing fill fields, and a direct fill-review regression proves a filled
  paper session still reconstructs the correct Phase 1 outcome from the
  persisted fill artifact; focused runtime regressions and the TFIS guard
  suite remain green
- Phase 2 now also restores persisted-intent continuity in review/parity
  summaries: `review.py` now treats a persisted paper intent artifact as
  enough proof to keep `order_intent.status=INTENT_READY` when
  `execution_summary.json` loses only `intent_status`, and
  `paper_vs_historical.py` now preserves that same intent-ready view in a
  later handoff-ready comparison. Direct review and parity regressions confirm
  the fallback, and focused runtime regressions plus the TFIS guard suite
  remain green
- Phase 2 now also hardens parity-summary fallback for staged shell-comparison
  fields: `paper_vs_historical.py` now reuses the existing shell/comparison
  helper path for `historical_comparison_status_used`,
  `historical_comparison_go_no_go_used`, and
  `historical_comparison_reason_used` instead of reading those fields only
  from `execution_summary.json`, so a later handoff-ready comparison still
  reports the persisted comparison outcome when the raw summary loses only
  those fields; direct parity regression plus focused runtime regressions and
  the TFIS guard suite remain green
- Phase 2 now also hardens lifecycle provenance fallback from the persisted
  fill artifact path: `lifecycle.py` now rebuilds `fill_source_type` and
  `fill_source_id` from the reviewed fill-phase artifact when
  `execution_summary.json` is present but missing those fields, so the opened
  paper position still records correct provenance in the lifecycle artifacts.
  A direct lifecycle regression proves the persisted position keeps the fill
  provenance from the Phase 1 fill artifact, and focused runtime regressions
  plus the TFIS guard suite remain green
- the planned Phase 2 runtime-contract/refactor track is now complete for the
  current scope: the shared paper intent/fill/lifecycle/shell contracts are
  consumed across review, parity, fill-simulation, lifecycle, and
  post-planning execution-journal boundaries, while equivalent persisted
  arm/dispatch/handoff/fill/exit artifacts now outrank fragile single-source
  dependence on partial `execution_summary.json` payloads. Focused Phase 2
  regressions and the TFIS guard suite remain the acceptance gate before the
  Phase 3 lifecycle-supervisor consolidation starts
- the planned Phase 3 lifecycle-supervisor cutover is now complete for the
  current scope: TFIS has a shared multi-target paper lifecycle supervisor
  entrypoint, shared target-config/discovery loading, generic live-state alias
  imports, compatibility launcher shims for the older S21/S23 watcher
  commands, and a reset/startup path that now launches one shared supervisor
  process instead of one watcher process per order or position. Focused Phase 3
  runtime/config tests, the TFIS guard suite, and the Friday, July 17, 2026
  prod-paper readiness run are green

## Money-Ready Phase Milestones

TFIS is not money-ready yet. The current target is to make S23 paper mode
auditable, replayable, and operationally reliable enough to justify later
live-order design. This checklist must be updated after each completed slice.

### Phase 1 - Paper Evidence And Replayability

- `DONE`: Persist selected-contract quote/bar observations consumed by S23
  paper watchers into `selected_contract_market_events.jsonl` beside the
  order/position state. This gives future sessions raw evidence for current
  price, entry trigger, target, SL/FSL, and dashboard-price review.
- `DONE`: Extend `scripts/run_s23_captured_session_validation.py` to report
  selected-contract market-event counts/latest timestamps and to keep the
  missing price-stream gap open for older sessions without this file.
- `DONE`: Extend offline replay validation so it reads
  `selected_contract_market_events.jsonl` and independently verifies whether
  each waiting order should have filled, remained waiting, or been marked not
  filled. The validator now reports `REPLAY_CONFIRMED_FILLED`,
  `REPLAY_CONFIRMED_NOT_FILLED`, `REPLAY_CONFIRMED_WAITING`, or mismatch
  verdicts from persisted quote/bar evidence without live broker access.
- `DONE`: Extend replay validation for open positions so target and active
  SL/FSL threshold decisions are checked from persisted selected-contract
  quote/bar evidence. The validator now reports position replay confirmations
  or mismatches for target exits, stop/FSL exits, and still-open/carry-forward
  states.
- `DONE`: Extend replay validation for expiry force-close and next-day SL reset
  decisions, which require calendar/session-time context in addition to the
  selected-contract event stream. The captured-session validator now recognizes
  expiry force-close manager events as legitimate non-price-threshold exits
  when expiry date and configured force-close time support them, and it reports
  next-day stoploss reset pending/completed states separately from generic
  still-open position replay.
- `DONE`: Add dashboard visibility for selected-contract stream health:
  event count, latest event timestamp, quote age/staleness, watcher PID, and
  last update source. The Trades Taken table now includes a Stream column built
  from `selected_contract_market_events.jsonl`, plus a direct Market Events
  artifact link for operator audit. This slice only surfaces already-persisted
  watcher evidence; it does not change strategy selection, order routing, or
  watcher lifecycle behavior.
- `DONE`: Phase 1 now also shares dashboard/runtime paper-trade label and row
  classification helpers. `src/tfis/paper/trade_ledger.py` exports
  `paper_trade_display_status_label` and `paper_trade_status_kind`, and the
  operator dashboard now uses them for waiting/not-filled label normalization
  plus closed/action/waiting/open/not-filled row classification instead of
  carrying those decisions inline. Runtime behavior is unchanged.
- `DONE`: Phase 1 now also shares latest-session trade visibility rules.
  `src/tfis/paper/trade_ledger.py` exports
  `paper_trade_visible_for_latest_session`, and the operator dashboard now uses
  that shared helper for deciding whether a trade row stays visible on the
  live all-trades monitor when the latest strategy session changes. Runtime
  behavior is unchanged.
- `DONE`: Phase 1 now also shares multi-event trade display-row selection.
  `src/tfis/paper/trade_ledger.py` exports
  `paper_trade_select_display_row`, and the operator dashboard now uses that
  shared helper to prefer the latest terminal row for a trade, or the latest
  row when no terminal event exists. Runtime behavior is unchanged.
- `DONE`: Phase 1 now also shares latest-trade summary counting.
  `src/tfis/paper/trade_ledger.py` exports `paper_trade_summary_counts`, and
  the operator dashboard now uses that shared helper for `Unique Trades`,
  `Open Positions`, `Action Required`, and `Closed Trades` counts instead of
  carrying those count rules inline. Runtime behavior is unchanged.
- `DONE`: Phase 1 now also shares trade status-badge and follow-up-note
  rendering rules. `src/tfis/paper/trade_ledger.py` exports
  `paper_trade_status_labels` and `paper_trade_followup_note`, and the
  operator dashboard now uses those shared helpers instead of carrying the
  closed-row badge and follow-up-note wording rules inline. Runtime behavior is
  unchanged.
- `DONE`: Phase 1 now also shares trade message normalization.
  `src/tfis/paper/trade_ledger.py` exports
  `paper_trade_normalized_message`, and the operator dashboard now uses that
  shared helper instead of carrying the S23-specific `READY decision created`
  wording cleanup inline. Runtime behavior is unchanged.
- `DONE`: Phase 1 now also shares option and branch display labels.
  `src/tfis/paper/trade_ledger.py` exports `paper_trade_option_label` and
  `paper_trade_branch_label`, and the operator dashboard now uses those shared
  helpers so live and historical trade views rely on one common option/branch
  label mapping path. Runtime behavior is unchanged.
- `DONE`: Phase 1 now also shares P&L tone selection.
  `src/tfis/paper/trade_ledger.py` exports `paper_trade_pnl_tone`, and the
  operator dashboard now uses that shared helper instead of carrying the
  positive/negative P&L CSS-class choice inline. Runtime behavior is unchanged.
- `DONE`: Phase 1 now also shares paper position-manager status classification
  used by the trade layer and lifecycle supervisor. `src/tfis/paper/trade_ledger.py`
  now owns the shared mapping for manager-status open/display-terminal/lifecycle-terminal
  checks plus trade-event-type conversion, `src/tfis/paper/position_manager.py`
  now uses that shared mapping for ledger event selection, and
  `src/tfis/paper/lifecycle_supervisor.py` now derives its terminal manager
  status set from the same shared lifecycle-terminal helper. Runtime behavior
  is unchanged after focused runtime tests.
- `DONE`: Phase 1 now also shares paper-order-to-trade-row mapping.
  `src/tfis/paper/order_state.py` now exports shared helpers for translating
  order status into trade-row event type and lifecycle status, and the operator
  dashboard now uses those helpers instead of carrying waiting/not-filled
  rewrites inline. Runtime behavior is unchanged after focused tests.
- `DONE`: Phase 1 now also aligns dashboard carry-forward override checks with
  the shared position-state vocabulary. The operator dashboard now uses
  `paper_position_is_active(...)` when deciding whether a strategy still has an
  active carried/open/resumed position that should preserve
  `OPEN_CARRY_FORWARD_POSITION`, instead of carrying a local active-status set.
  Runtime behavior is unchanged after focused tests.
- `DONE`: Phase 1 now also shares pending-order trade-monitor visibility.
  `src/tfis/paper/order_state.py` exports
  `paper_order_visible_in_trade_monitor(...)`, and the operator dashboard now
  uses that helper instead of carrying a local waiting/not-filled order-status
  set when reconstructing pending trade rows. Runtime behavior is unchanged
  after focused tests.
- `DONE`: Phase 1 now also closes a remaining S21/S23 dashboard parity gap in
  final-leg reconstruction. The operator dashboard now normalizes branch names
  and reloads branch rules with the active strategy code instead of assuming an
  `S23_` prefix, so S21 failed-leg rows still render correctly when summary
  artifacts, explainer artifacts, and config folders mix prefixed and
  unprefixed branch names. Runtime behavior is unchanged after focused tests.
- `DONE`: Phase 1 now also exposes a neutral open-position discovery seam.
  `src/tfis/paper/position_discovery.py` exports
  `PaperOpenPositionCandidate` / `PaperOpenPositionDiscovery`, and the S23
  paper position-watch script now imports that neutral alias without changing
  watcher runtime behavior. Focused shared-alias, dashboard, and
  position-manager tests remain green.
- `DONE`: Phase 1 now also exercises neutral paper entrypoint seams in TFIS
  scripts. `scripts/run_s23_paper_position_watch.py` now uses
  `PaperLifecycleSupervisor`, `PaperLifecycleSupervisorContext`, and
  `PaperOpenPositionDiscovery`, while
  `scripts/finalize_s23_pending_paper_orders.py` now uses
  `PaperOrderFinalizer`. Runtime behavior is unchanged; syntax checks and
  focused shared-alias/position-manager tests remain green.
- `DONE`: Phase 1 now also centralizes resumable paper-position recovery rules
  across TFIS startup/reset wrappers. The new shared PowerShell helper
  `scripts/tfis_paper_position_state_helpers.ps1` owns the common
  `PAPER_POSITION_OPEN` / `PAPER_POSITION_CARRIED_FORWARD` /
  `PAPER_POSITION_RESUMED` plus carry-forward/expiry eligibility check, and
  `start_s23_fyers_morning_supervised_decision.ps1`,
  `start_s21_fyers_morning_supervised_decision.ps1`, and
  `reset_tfis_dashboard_and_watchers.ps1` now use that one helper instead of
  re-declaring the rule separately. Focused wrapper tests and PowerShell parse
  checks remain green.
- `DONE`: Phase 1 now also aligns blocked-fresh-order recovery and captured
  session replay with shared lifecycle vocabulary. `paper_position_blocks_new_entry`
  now owns the “still blocks a fresh order” status rule, the blocked-fresh
  promotion script uses it instead of a local status set, and the captured
  session validator now uses shared position/order status truth where that was
  already safe. Focused alias, promotion, captured-session, and wrapper tests
  remain green.

### Phase 2 - Watcher And Position Reliability

- `DONE`: Centralize S23 waiting-order and open-position lifecycle decisions in
  `tfis.paper.lifecycle_supervisor`. The watcher script still owns process
  locks, market-event persistence, and dashboard rebuilds, but the shared
  supervisor now drives expiry checks, waiting-order fill/not-filled decisions,
  open-position session handling, and fresh-entry-required transitions through
  one reusable path that preserves existing paper artifacts and tests.
- `DONE`: TFIS reboot/recovery no longer revives stale prior-session waiting
  orders. `scripts/reset_tfis_dashboard_and_watchers.ps1` now restores watcher
  processes only for same-day waiting orders and for genuinely live
  carry-forward/open/resumed position states. Prior-day `paper_order_state.json`
  files are treated as session-only artifacts and are skipped during reset,
  while live `paper_position_state.json` files are discovered from the full
  strategy artifact root instead of only from the latest session metadata.
- `DONE`: Add a money-readiness operator command reference to
  `docs/operations/tfis_manual_operator_guide.md`. It explains dashboard launch,
  captured-session replay validation, focused tests, syntax checks, scheduled
  task checks, watcher recovery, and pre-live readiness commands in table form,
  including purpose, usage timing, expected checks, and safety notes.
- `DONE`: Add offline restart-safety proof for multi-day carried paper
  positions. `S23PaperPositionStateStore.carry_forward()` and
  `resume_position()` now preserve strategy parameters, stoploss-active state,
  pending SL-reset flags, ORPT/RC reset times, reset reference price, and
  reset buffer metadata instead of rebuilding state with defaults. Focused
  tests prove a carried position remains target-active but SL-inactive until
  the next-day reset flow explicitly reactivates or recalculates SL.
- `DONE`: Strengthen offline single-instance proof for S23 supervised decision
  and paper watcher locks. Unit tests now prove lock identity is stable for the
  same engine/order-position scope, different branches/prefixes get different
  lock files, duplicate live PIDs fail closed with
  `CRITICAL_DUPLICATE_PROCESS_SHUTDOWN`, and original lock metadata is retained
  for operator diagnosis.
- `TODO`: Prove automatic scheduled watcher startup on a real market day for
  every current-day waiting order and every valid carry-forward position.
- `TODO`: Validate the new dashboard Stream column during a live market watch
  and confirm current-day rows move between `OK` and `STALE` as selected-contract
  evidence is written or stops arriving.
- `TODO`: Prove single-instance watcher behavior against real Windows process
  restart attempts: valid duplicate launches fail closed, stale locks are
  reclaimed, and no duplicate rows/events are produced.
- `TODO`: Prove overnight carry-forward in a real market session by
  stopping/restarting the engine after market close and confirming the next-day
  watcher resumes the persisted open position with target and reset-SL handling
  intact.
- `TODO`: Prove session-only waiting orders are always marked not-filled after
  cutoff and never carry forward as pending orders.

### Phase 3 - Operator Safety Controls

- `TODO`: Add and validate operator-visible kill switches at global and
  strategy scope.
- `TODO`: Add configurable risk limits for max daily loss, max trades per day,
  max open positions, max order quantity, stale quote no-trade, and broker-data
  inconsistency no-trade.
- `TODO`: Add dashboard/operator alerts for stale quote stream, stopped
  watcher, duplicate process shutdown, missing next expiry, and blocked order
  placement.

### Phase 4 - Broker Reconciliation Before Any Live Money

- `DONE`: The first Phase 4 separation slice is now in place for the shared
  paper lifecycle supervisor runtime. It no longer hardcodes the FYERS adapter
  class or the S23 ingress config type directly in its bootstrap path, and now
  resolves broker provider, timezone, payload fixture, and lifecycle slippage
  settings through `src/tfis/paper/lifecycle_runtime_config.py`.
- `TODO`: Design live-order adapter boundary behind explicit config flags; do
  not reuse paper state as live truth.
- `TODO`: Add broker order/position reconciliation model before any real order
  placement: broker order id, broker position quantity, average price,
  open/closed status, and fail-closed mismatch handling.
- `TODO`: Require supervised small-quantity dry/live checklist only after
  paper evidence gates pass.

## Operational Status And TODO

Current S23 paper-mode posture:

- `DONE`: Windows Scheduled Task is installed as weekday-only and the wrapper
  skips weekends and configured NSE holidays before FYERS login or watcher
  startup.
- `DONE`: Closed-market/no-candle days now exit cleanly with
  `MARKET_CLOSED_NO_ACTION`; this no-action path no longer starts watchers
  against stale prior-session orders.
- `DONE`: S23 rule interpretation, CE/PE leg visibility, failed-leg reasons,
  calculation explanations, visible watcher windows, and waiting-order behavior
  are implemented and committed.
- `DONE`: S23 live paper finalization now follows the revised ORPT/RC timing
  contract. The runner builds a provisional base selection at ORPT, fetches the
  selected option's `09:24` bar through the broker adapter, and finalizes that
  base selection immediately when ORPT proves the entry was not missed. RC is
  used only when ORPT marks the base entry as missed and recalculation evidence
  is needed. Missing required timing bars fail closed instead of silently
  placing a base order.
- `DONE`: S23 timeline/dashboard reconstruction can now evaluate the ORPT stage
  before the RC checkpoint exists. ORPT-stage decisions require only `0915` and
  `ORPT` snapshots, while RC/final stages still require all checkpoints.
- `DONE`: S23 scheduled startup wrapper no longer depends on a live PowerShell
  output pipeline to reach watcher startup. The supervised decision process now
  writes stdout/stderr to TFIS launch logs, then the wrapper deterministically
  scans the current run-date metadata and starts paper order/position watchers.
  This addresses the 2026-06-30 issue where valid waiting orders were present
  but no watcher was left running to update current prices, and prevents a
  later-touched stale session from being chosen during watcher startup.
- `DONE`: S23 watcher launchers now handle mixed branch state correctly. If one
  branch has become an open paper position and another branch remains a waiting
  order, TFIS starts a state watcher for the position branch and an order
  watcher for the waiting branch instead of letting the position branch suppress
  the order branch. If original metadata only contains order state but a branch
  directory now has `paper_position_state.json`, the launcher derives state mode
  from the branch directory.
- `DONE`: S23 scheduled startup now scans the durable S23 artifact root for
  persisted open/carry-forward `paper_position_state.json` files and starts a
  state watcher for each eligible non-expired open position in addition to any
  fresh current-day waiting orders. The latest discovered open position is also
  passed into the supervised decision runner as carry-forward context when no
  explicit `-CarryForwardStateDir` is supplied.
- `DONE`: S23 supervised decision and paper watcher startups now have
  PID-aware single-instance guards under `tmp/process_locks`. A second
  supervised decision run for the same configured S23 engine, or a second
  watcher for the same order/position, fails closed before broker connection
  with `CRITICAL_DUPLICATE_PROCESS_SHUTDOWN`, while stale dead-PID locks are
  reclaimed with `STALE_PROCESS_LOCK_RECLAIMED`.
- `DONE`: S23 paper waiting-order and open-position lifecycle supervision is
  now centralized in `src/tfis/paper/lifecycle_supervisor.py`. The watcher
  script still owns process locks, broker connectivity, selected-contract event
  capture, and dashboard rebuild triggers, but the actual pending-order,
  fill-to-position promotion, cutoff no-fill handling, and open-position
  session management now run through one reusable supervisor path without
  changing the persisted paper artifacts.
- `DONE`: `scripts/reset_tfis_dashboard_and_watchers.ps1` now launches the
  TFIS dashboard server and TFIS watcher/runtime consoles as visible windows
  instead of hidden background processes, matching the operator-facing manual
  watcher launchers so active TFIS runtime can be found after reboot/recovery.
- `DONE`: `scripts/reset_tfis_dashboard_and_watchers.ps1` now narrows runtime
  discovery to likely TFIS host processes, stops matched TFIS process trees via
  `taskkill /T /F`, waits on the exact stopped PIDs instead of repeatedly
  rescanning the whole machine, and confirms when the dashboard port is
  accepting connections before the reset flow reports success.
- `DONE`: `src/tfis/dashboard/operator_dashboard.py` now caches parsed JSONL
  artifacts, selected-contract stream-health calculations, and per-strategy
  trade-row collections within a single dashboard build so the reset flow does
  not reread the same large market-event and ledger files repeatedly while
  rendering strategy, all-trades, and historical-trades pages.
- `DONE`: Historical closed-trade rendering no longer computes live
  selected-contract stream health or scans pending-order state while building
  `trades/history/index.html`. That path now reads only the closed-ledger data
  it needs, which removes one major rebuild hotspot from
  `reset_tfis_dashboard_and_watchers.ps1`.
- `DONE`: Phase 1 shared-lifecycle refactor has started with additive,
  strategy-neutral module aliases only. `src/tfis/paper/order_finalizer.py`,
  `src/tfis/paper/lifecycle_supervisor.py`, and `src/tfis/paper/__init__.py`
  now export generic `PaperOrderFinalizer*` and `PaperLifecycleSupervisor*`
  names that resolve to the existing S23 implementations. This changes no
  runtime behavior, but creates a safer module boundary for later S21/Sxx
  adoption work.
- `DONE`: The next additive Phase 1 seam extends that neutral boundary to
  shared order and position state types. `src/tfis/paper/order_state.py`,
  `src/tfis/paper/position_state.py`, and `src/tfis/paper/__init__.py` now
  export generic `PaperOrder*` and `PaperPositionState*` names that resolve to
  the existing S23-backed implementations. This is still a no-behavior-change
  refactor step meant to keep tomorrow's TFIS run on the proven path while
  making later multi-strategy adoption less invasive.
- `DONE`: Phase 1 now includes the first shared paper lifecycle helper
  extraction. `src/tfis/paper/order_state.py` exports
  `paper_order_is_waiting_for_trigger` and `paper_order_is_terminal`, and the
  existing finalizer/supervisor code paths now use that shared helper instead
  of duplicating literal waiting-status checks. Runtime behavior is unchanged;
  this just reduces status-check duplication before broader multi-strategy
  lifecycle work.
- `DONE`: Phase 1 now has matching shared paper position-status helpers.
  `src/tfis/paper/position_state.py` exports
  `paper_position_is_active` and `paper_position_is_no_longer_open`, and the
  existing open-position discovery / position-manager early-exit paths now use
  those helpers instead of carrying duplicated literal status sets. Runtime
  behavior is unchanged; the goal is a cleaner shared seam before broader
  multi-strategy lifecycle adoption.
- `DONE`: Phase 1 now includes a shared paper trade-classification helper layer.
  `src/tfis/paper/trade_ledger.py` exports `paper_trade_is_terminal`,
  `paper_trade_is_open`, and `paper_trade_action_required`, and the operator
  dashboard now uses those helpers for open/terminal/action-required summary and
  row-visibility decisions instead of maintaining its own duplicated
  classification logic. This is still a no-behavior-change refactor slice.
- `DONE`: Phase 1 now also shares the dashboard/runtime status-label
  normalization for paper trade rows. `src/tfis/paper/trade_ledger.py` exports
  `paper_trade_display_status_label`, and the operator dashboard now uses that
  helper for `PAPER_ORDER_WAITING_FOR_TRIGGER -> ORDER_WAITING_FOR_TRIGGER` and
  `PAPER_ORDER_NOT_FILLED -> ORDER_NOT_FILLED` mapping instead of carrying that
  mapping inline. Runtime behavior is unchanged.
- `DONE`: The 2026-07-03 scheduled startup failure was traced to a PowerShell
  scalar/array edge case when exactly one open carry-forward state was
  discovered. The wrapper now preserves discovered state paths as arrays in the
  carry-forward handoff, metadata watcher startup, and fallback discovery paths.
  It also normalizes explicit and discovered carry-forward state paths to full
  absolute state-directory strings before passing them to Python or watcher
  subprocesses, preventing a single Windows path from being truncated to only
  its drive letter.
- `DONE`: S23 carry-forward resume no longer suppresses same-day CE/PE
  calculation. When an open S23 position exists, TFIS still computes and
  persists the fresh leg decision artifacts for the active rule group. Fresh
  paper order creation is separately controlled by the strategy boolean
  `allow_fresh_entry_with_open_position`, currently configured as `false` for
  all S23 legs so no new order is placed until the open position exits. The
  decision summary, explanation, scheduled-run metadata, and dashboard state now
  carry an explicit `order_placement_blocked` flag/reason so calculated daily
  CE/PE symbols remain visible while the execution gate stays locked.
- `DONE`: `scripts/promote_s23_blocked_fresh_order.py` can safely promote a
  same-day S23 `READY` decision that was blocked only by
  `OPEN_CARRY_FORWARD_POSITION` after the carry-forward position exits. The
  script scans the durable S23 artifact root, fails closed if any active S23
  paper position still exists, writes a normal waiting `paper_order_state.json`
  through `S23PaperOrderStateStore`, and updates scheduled-run metadata with
  promotion provenance. On 2026-07-06 this was used after the carried PE hit
  target to promote the fresh Bear Call decision
  `NIFTY_20260714_24150_CE` into a waiting paper order without changing S23
  selection rules or enabling fresh entries while a position is still active.
- `DONE`: S23 Trades Taken dashboard rows now keep target/SL closed trades
  visually clean when the persisted lifecycle also records
  `PAPER_FRESH_ENTRY_REQUIRED`. The closed carried trade displays as a closed
  row with the target/SL reason, while the fresh-entry requirement is shown as
  a follow-up note and any promoted/calculated waiting entry remains its own
  separate paper-order row.
- `DONE`: The S23 Calculation Explanation panel now restores side-by-side
  CE/PE stepwise cards on wide screens and includes direct CE/PE leg links
  above the cards, so both leg calculations remain discoverable even when one
  leg's Step 8 audit is expanded and visually long.
- `DONE`: S23 dashboard and captured-session review now include stage-only
  no-contract leg calculations. If one leg writes a final
  `trade_decision_summary.json` and the other leg only has
  `trade_decision_explainer_stage_*.json` because no contract qualified, the
  validator and dashboard still show both active monthly-status branches. This
  fixes the 2026-07-06 visibility gap where the CE branch was visible but the
  PE `MINIMUM_PREMIUM_NOT_MET` calculation was hidden from the final CE/PE
  review section.
- `DONE`: S21 BankNifty monthly option-selling now has a validated
  rule/config scaffold for all four rule-sheet legs: Bull Call, Bull Put, Bear
  Call, and Bear Put. The branch folders are under
  `config/strategies/options_sell/banknifty`, use configurable rule
  parameters, validate against `tfis.rules.s21_rule_matrix`, and are now
  registered as `ACTIVE_CANDIDATE` for controlled TFIS paper-mode testing only.
- `DONE`: TFIS now has an S21 paper-mode config, reference packet placeholder,
  runner wrapper, and dashboard strategy registration. The shared supervised
  paper path accepts S21 scope validation, monthly expiry resolution, and a
  dedicated S21 dashboard page without reusing S23 labels in the final
  explanation panel.
- `DONE`: Captured S23 supervised sessions can now be validated offline with
  `scripts/run_s23_captured_session_validation.py`. The report walks durable
  captured sessions, summarizes CE/PE decisions, reconstructs review-only
  fresh CE/PE calculations from captured 09:30 option-chain snapshots when a
  carry-forward resume blocked order placement, reports paper orders/carried
  positions/stage coverage, and clearly flags replay gaps such as missing
  selected-contract intraday price streams.
- `DONE`: S23 paper watchers now persist every selected-contract quote/bar
  event they consume into `selected_contract_market_events.jsonl` beside the
  order or position state. The captured-session validator reports the event
  count/latest event timestamp and only clears the selected-contract price
  stream gap when this evidence exists.
- `DONE`: The captured-session validator now replays waiting paper orders from
  persisted selected-contract quote/bar events. It independently confirms
  filled, not-filled, or still-waiting order outcomes, and flags mismatch gaps
  when the event stream indicates a different outcome from the persisted paper
  order state.
- `DONE`: The captured-session validator now also replays open-position
  lifecycle thresholds from persisted selected-contract quote/bar events. It
  verifies target-hit, stop/FSL-hit, and still-open/carry-forward outcomes
  against persisted position state and flags mismatches for review.
- `DONE`: `scripts/start_s23_paper_watchers_from_metadata.ps1` is available as
  a TFIS-only recovery launcher. It reads the selected session metadata and
  starts watcher windows for produced paper orders or open paper positions
  without rerunning the strategy decision.
- `DONE`: S23 dashboard strike qualification and full Step 8 audit tables now
  show expiry per candidate row, and full-scan rejection reasons wrap inside the
  table instead of being clipped at the right edge.
- `DONE`: S23 dashboard strike-range explanation now derives the displayed
  buffer percentage from the resolved strategy formula, so a configured 1.2%
  strike buffer is no longer described as the older 5% workbook/default text.
  Final S23 leg decisions also show the selected contract expiry explicitly,
  which makes near/next-expiry selections easier to verify against broker
  charts.
- `DONE`: S23 missed-entry recalculation is now applied in the supervised live
  decision path. If ORPT marks the base entry as missed, TFIS recalculates the
  branch strike range, premium filters, entry, target, and SL from the RC spot
  and selected-option candles, then reruns normal near/next contract selection.
- `DONE`: S23 missed-entry recalculation now consumes the loaded strategy
  parameters for strike buffer, ideal/minimum premium percentages, entry
  discount, target percentage, and SL entry percentage instead of carrying
  duplicate hardcoded S23 constants in the recalculation path. The opt-in
  current-day FSL/TRP overlay now also receives loaded strategy parameters for
  its confirmed workbook-backed strike, premium, entry, and FSL calculations.
- `DONE`: S23 paper position management now applies the 15:00 continuation
  decision after target/SL/FSL/expiry checks. If the option price is not above
  original SL, the position remains open with an auditable
  `s23_1500_carry_forward_stop_inactive` reason; if above original SL, normal
  stop/force-close handling closes the paper position.
- `DONE`: S23 carried-forward positions now persist strategy parameters,
  ORPT/RC reset times, and stoploss-active state. On the next trading day the
  paper manager keeps the target active while the stoploss stays inactive until
  the rule-sheet reset flow runs: if the `09:15` selected-option high does not
  exceed the original SL, the original SL is reactivated at ORPT; if it does,
  TFIS waits until RC and sets revised SL as RC high plus the configured
  `sl_reference_pct` buffer. The watcher now fetches selected-option bars from
  `09:15` through RC when a carried position needs this reset evidence.
- `DONE`: S23 dashboard Step 8 strike audits now preserve the full reconstructed
  candidate set inside the rule-book Start-to-End range, scope rows to the
  attempted expiry for that step, and explicitly show missing strike-grid rows
  as rejected audit rows when the captured option chain does not include every
  strike in the displayed range.
- `DONE`: S23 waiting paper orders now have a post-cutoff finalizer safety net.
  `scripts/finalize_s23_pending_paper_orders.py` and
  `scripts/start_s23_paper_order_finalizer.ps1` scan TFIS S23 artifacts after
  the configured cutoff and mark same-session still-waiting orders as
  `PAPER_ORDER_NOT_FILLED` through the normal order-state store. This prevents
  dashboard/order-state drift when an individual watcher exits unexpectedly.
- `DONE`: FYERS option-chain collection now requests the specific weekly expiry
  timestamp using the FYERS/expiry-day `15:30 IST` convention and uses
  configurable `broker.option_chain_strike_count` for S23 paper snapshots, so
  near and next weekly expiry data can be collected for Step 8c fallback instead
  of repeatedly receiving only the default near chain.
- `DONE`: Near-vs-next expiry fallback now fails closed unless the second
  expiry request produces real next-weekly contracts after contract-symbol
  expiry normalization. Relabeled/default near-expiry responses no longer pass
  through as a partial Step 8c fallback; TFIS raises
  `NEXT_WEEKLY_OPTION_CHAIN_UNAVAILABLE` with observed expiries so the operator
  can see the broker-data issue clearly.
- `PARTIAL`: Paper order watcher/current-price/P&L behavior is implemented,
  and a post-cutoff finalizer now prevents unfilled waiting orders from
  lingering if a watcher crashes. Watchers were manually restarted on
  2026-06-30 for the active TFIS S23 paper orders and current prices began
  updating again. This still needs one clean market-day validation of automatic
  watcher startup after the latest wrapper fix. On 2026-07-02, Windows process
  inspection showed one TFIS watcher branch for the S23 BEAR_CALL order and one
  TFIS watcher branch for the S23 BEAR_PUT position, with each visible as a
  Python parent/child pair. No TradingEngineProd or sibling project process was
  touched.
- `PARTIAL`: Multi-day position lifecycle support exists in the paper runtime
  foundation, including target/SL/FSL, expiry force-close, session-only pending
  orders, the 15:00 carry-forward decision, and automatic watcher startup for
  persisted open positions. It still needs live-like validation on real market
  sessions, especially next-day SL reset/recalculation after an overnight carry.
- `TODO`: On the next real NSE trading day, validate the full S23 paper flow
  one step at a time:
  1. scheduled task starts at the configured pre-market time
  2. `09:16`, `09:25`, and `09:30` snapshots complete
  3. final CE/PE selections or no-trade reasons match the rule sheet
  4. watchers start only for that day's valid waiting orders or open positions
  5. dashboard current price, order status, fill status, and P&L update
  6. unfilled waiting orders are cancelled/not-filled after the entry session by
     the watcher or by the post-cutoff finalizer task
  7. filled/open positions persist for valid multi-day management
- `TODO`: Finish the post-target/post-SL fresh-entry automation path inside the
  shared supervisor flow. TFIS can now launch one fresh supervised decision
  automatically when a terminal fresh-entry-required result is emitted, and it
  persists a session-local marker so that relaunch is restart-safe. The
  shared supervisor can now also promote an already-calculated blocked same-day
  READY decision before spawning a new fresh run, using the same guarded rules
  as the operator promotion script. The remaining improvement is to broaden
  that shared promotion path beyond the current S23-shaped blocked-decision
  artifact conventions as more strategies come online.
- `TODO`: Move durable S23 option-chain, decision, order, trade-ledger, and
  monthly-status capture records out of temp-only storage into a structured
  `data` layout with strategy/date/instrument provenance.
- `DONE`: Add a generic enabled-strategy execution-plan contract in
  `tfis.strategy.execution_plan`. It reads runtime config, honors
  enabled/disabled strategy entries, checks registry status, checks supported
  executor names, skips disabled strategies, and fails closed for unsupported
  enabled strategies without importing broker adapters or executing strategy
  code. Current S23 paper configs now declare an explicit enabled S23 strategy
  entry with branch registry IDs and strategy paths.
- `TODO`: Wire the supervised live-paper runner to consume the generic
  execution plan directly before adding S21 or other strategies, so S23 remains
  the first operational path but not the hidden shape of the engine.
- `TODO`: Review and refresh the local NSE holiday calendar each year, and
  preferably replace the static file with a maintained calendar source when the
  broader runtime is generalized.

## Implemented Systems

- broker-agnostic architecture
- strategy registry governance
- S23 all 4 branches
- monthly status thresholds
- `MonthlyStatusEngine`
- `BranchSelector`
- historical lifecycle backtesting
- costs and slippage model
- rupee P&L reporting
- equity curve and drawdown reporting
- missed-entry recalculation foundation
- opt-in historical S23 recalculation
- entry-missed detection
- dedicated spot intraday sourcing for opt-in recalculation
- opt-in S23 current-day FSL / TRP missed / not-missed handling
- opt-in option-chain contract selection realism foundation
- opt-in contract-specific lifecycle pricing foundation
- expiry-day lifecycle review and audit
- read-only shared captured-data adapter foundation
- bounded comparison reporting across historical backtest modes
- apples-to-apples comparison integrity reporting for historical backtest modes
- Excel ambiguity audit
- reference-material indexing
- S23 live-paper normalized data contract blueprint
- S23 paper-session state-machine blueprint
- S23 live-paper schema scaffolding and required-field validation foundation
- S23 paper-session orchestrator skeleton through `ORDER_PLANNED` / `NO_TRADE` / `ABORTED`
- S23 paper-session persistent artifacts and journaling shell
- S23 paper kill-switch and failure-handling guardrails before planning
- S23 paper replayable session bundle manifests and validation
- S23 paper operator-facing session review summaries over artifacts and replay bundles
- S23 paper order-intent and execution-journal shell
- S23 paper post-planning failure handling and kill-switch controls
- S23 paper-vs-historical replay comparison over the persisted intent shell
- S23 later-phase execution-shell controls beyond `INTENT_READY`
- execution-shell-aware S23 paper-vs-historical replay comparison beyond planning-state intent shells
- fillless S23 order-intent dispatch shell beyond `EXECUTION_ARMED`
- final no-fill S23 execution handoff boundary after `ORDER_INTENT_DISPATCHED`
- S23 Paper Trading MVP v1 fill simulator and lifecycle-loop design blueprint
- S23 Paper Trading MVP v1 Phase 1 fill simulator through `PAPER_ORDER_FILLED` / `PAPER_ORDER_NOT_FILLED` / `PAPER_FILL_ABORTED`
- S23 Paper Trading MVP v1 Phase 2 same-day lifecycle loop through `PAPER_POSITION_OPEN` / `PAPER_POSITION_CLOSED` / `PAPER_EOD_SQUARE_OFF` / `PAPER_LIFECYCLE_ABORTED`
- same-day S23 paper-vs-historical lifecycle parity and drift policy with deterministic `MATCH`, `MATCH_WITH_ACCEPTABLE_DRIFT`, `PARTIAL_MATCH`, `MISMATCH`, and `UNCOMPARABLE` outcomes
- first normalized archive-backed S23 same-day paper lifecycle parity pilot
- first multi-session archive-backed S23 same-day paper lifecycle parity suite
- first normalized live-paper ingress-only S23 dry run over deterministic archive-export JSONL
- S23 operator close-out policy for ingress-only validation
- broadened multi-session S23 ingress-only dry-run suite with aggregate PASS / WARNING / NO_GO close-out metrics
- broker-agnostic live-paper ingress foundation for S23 paper mode
- FYERS market-data adapter as the first concrete broker-backed ingress adapter
- broker-backed normalized event persistence through `broker_health.json`, `normalized_events.jsonl`, and `ingress_summary.json`
- S23 FYERS live-paper preflight-only safety gate and operator runbook
- TFIS-native S23 runtime-input derivation from normalized underlying morning
  bars and TFIS reference packets
- TFIS-native supervised live decision builder that writes
  `trade_decision_summary.json` and `trade_decision_summary.md`
- TFIS-native morning supervised decision runner that captures `09:16`,
  `09:25`, and `09:30`, plus `trade_decision_explainer.md` for operator
  cross-checks
- read-only TradingEngine capture-session audit and market-event adapter prototype for S23 dry runs
- TradingEngine capture plus TFIS prelude ingress-only dry-run suite for S23
- corrected S23 weekly option selling contract documented under
  `docs/architecture/s23_weekly_option_selling_engine_contract.md`
- corrected S23 four-leg rule matrix implemented under
  `src/tfis/rules/s23_rule_matrix.py` and cross-checked against strategy
  folders by unit tests
- S23 operator dashboard and manual calculator now show the corrected
  rule-sheet step process, including preparation date, monthly-status rule
  group, CE/PE strike search, final strike/premium/OI, and entry/target/SL
- S23 latest-session dashboard summary and manifest now expose plural final
  contracts for two-leg sessions while keeping the legacy single-contract field
  for compatibility
- S23 latest-session dashboard now includes a visible calculation explanation
  section that renders Step 1-8 reasoning from the final decision artifacts,
  including monthly-status mapping, CE/PE strike ranges, qualification outcome,
  formula traces, final selections, entry, target, SL, and order status
- S23 final leg dashboard reporting now shows both independently evaluated
  CE/PE legs; if a leg does not qualify, the table and explanation show
  `No contract selected`, the failure code, and the no-order reason instead of
  hiding that side
- S23 final leg dashboard reporting now also accepts latest stage-level
  explainers for no-contract branches when no final summary was written, so
  review pages can show failed CE/PE calculations from the captured snapshots
  instead of requiring a selected-contract summary artifact.
- S23 FYERS live snapshot collection now captures the resolved near weekly
  expiry plus the following weekly expiry in the same normalized option-chain
  snapshot, so rule-sheet fallback search can retry the next contract when the
  near contract fails
- S23 decision summaries, failure artifacts, markdown explainers, and dashboard
  explanations now persist/show attempted expiries and rejection counts, making
  near-vs-next expiry fallback auditable for both selected and no-order legs
- S23 strategy dashboard auto-refresh preserves expanded/collapsed explanation
  and snapshot panels per browser tab, so operator drill-down sections no
  longer collapse every time the page refreshes
- S23 trade dashboard summarization now prefers terminal close events over
  later stale non-terminal rows for the same trade, so expired/closed historical
  positions do not remain displayed as action-required rollover items
- S23 runtime derivation/prelude now fail closed if a loaded strategy rule does
  not match the corrected rule matrix
- `scripts/validate_s23_rule_matrix.py` validates configured S23 strategy
  folders against the corrected matrix
- S23 live session dashboard stage cards now include a rule-sheet step panel
  showing preparation snapshot, monthly status, rule group, strike range,
  near/next search, premium/OI, final weekly option, and entry/target/SL
- the S23 scheduled startup wrapper now launches one paper watcher process per
  produced paper order or open paper position, so two-leg sessions can update
  selected-contract current price, fill status, dashboard rebuilds, and open
  position P&L independently
- S23 pending paper entry orders are session-only: untriggered waiting orders
  are cancelled/not-filled after their entry session and must not carry forward
  or remain active on the next day's dashboard; only filled/open paper positions
  can carry forward for multi-day management
- S23 scheduled wrapper and paper watcher consoles now identify themselves as
  TFIS windows, print startup/status/exit messages, and keep visible watcher
  windows readable for operator review instead of leaving ambiguous blank
  PowerShell terminals
- S23 scheduled morning decision CLI treats a no-intraday-candles response for
  the supervised snapshot window as `MARKET_CLOSED_NO_ACTION` and exits cleanly,
  so market holidays/closed days do not appear as failed Windows Scheduled Task
  runs; other broker snapshot failures still fail closed
- S23 scheduled startup is now guarded at the Windows task and wrapper layers:
  the registered task runs only Monday-Friday, the wrapper exits before broker
  login on weekends or configured NSE trading holidays, and `MARKET_CLOSED_NO_ACTION`
  no longer starts watchers against stale prior-session orders
- Monthly Status Calculator current-data fetch now returns daily, weekly, and
  monthly candle series alongside the status result, and the dashboard renders
  an instrument-aware market-structure candlestick chart with high/low labels
  and PMH/PML/CMH/CML/PWH/PWL/CWH/CWL/current-price reference lines
- Monthly Status Calculator chart now supports Zerodha-like review aids:
  crosshair hover inspection, OHLC/reference-level tooltip, level visibility
  toggles, and a review-date marker across daily, weekly, and monthly views
- Monthly Status Calculator chart inspection now keeps full candle/reference
  context in a fixed top inspector strip, uses a small OHLC-only hover tooltip
  so candles are not obscured, and includes an inline color legend explaining
  monthly, weekly, current-price, and review-date reference lines; chart price
  values render with two decimal places for audit readability
- S23 dashboard eligible-strike comparison tables now display rows in
  rule-sheet search order using persisted start/end strike formulas when
  available, and state the final selected strike/reason above the table
- S23 dashboard leg explanations now include a collapsed full strike-scan
  audit table showing all persisted candidate strikes in rule-sheet search
  order, including rejected rows and reasons, while keeping the summary
  comparison table focused on audit candidates and the selected strike
- S23 full strike-scan audit now derives readable rejection reasons when older
  candidate rows only persisted `REJECTED`, including option-side mismatch,
  strike range, premium threshold, and OI threshold failures
- S23 full strike-scan audit filters rows to the leg's expected option side, so
  CE review does not show PE contracts and PE review does not show CE contracts
- S23 full strike-scan audit now explains `PASSED` and `SELECTED` rows with
  explicit qualification checks: option side, strike range, premium versus
  minimum/ideal premium, OI versus minimum OI, and why an audit candidate was
  not the final selected strike
- S23 final leg decisions now show contract, strike, premium, OI, entry,
  target, and SL only for legs with a selected final contract; failed/no-trade
  legs show `n/a` for those fields and keep provisional formula values only in
  the calculation explanation
- S23 calculation explanations now align leg-level dry-run numbering with the
  rule-book sequence: Step 3 spot data, Step 4 strike factor, Step 5 strike
  range, Step 6 minimum OI, Step 7a/7b premium thresholds, Step 8a/8b/8c/8d
  near/next contract qualification, and Step 9/10/11 entry/target/SL
- S23 Step 8 strike-matching audit tables now render inline directly under the
  matching Step 8a, 8b, or 8c explanation. When Step 8a selects the final
  strike, Step 8b and 8c show collapsed "not run" explanations instead of
  implying unnecessary fallback calculations were performed.
- S23 failed-leg dashboard audit now accepts reconstructed tuple-based
  candidate rows, so failed PE/CE legs can display the captured strike,
  premium, OI, status, and rejection reason instead of showing a blank
  "No candidate rows were persisted" table when the option-chain snapshot is
  available.
- S23 supervised live decisions now consume selected-contract ORPT/RC option
  bars through the broker adapter boundary, fail closed when those timing bars
  are missing, and apply the updated missed-entry recalculation before creating
  the final waiting paper order.
- S23 missed-entry recalculation now lives in the shared strategy layer
  (`tfis.strategy.s23_recalculation`) with a compatibility import kept at the
  old backtest path, so live paper and backtest consume the same strategy rule
  helper instead of paper importing from backtest.
- S23 missed-entry recalculation now receives the loaded strategy parameters
  from live decision and historical backtest callers, preserving the config
  contract for strategy experiments and future strategy variants. The
  current-day FSL/TRP overlay follows the same parameter handoff.
- S23 paper position management now implements the rule-sheet 15:00
  continuation decision after target/SL/FSL/expiry checks, recording whether a
  position was carried forward with overnight SL inactive or closed by the
  applicable exit rule.

## Current Architecture Flow

Current high-level offline path:

`MonthlyStatusEngine`
-> `StrategyBranchSelector`
-> strategy evaluation
-> historical lifecycle backtest

Current paper-foundation path:

`normalized paper events`
-> `S23PaperContractValidator`
-> `S23PaperSessionOrchestrator`
-> `S23PaperGuardrailEvaluator`
-> session manifest + in-memory audit trail
-> `S23PaperSessionArtifactWriter`
-> deterministic paper-session folder artifacts
-> `S23PaperReplayBundleManager`
-> deterministic replay-bundle manifest + validation/readback summary
-> `S23PaperSessionReviewer`
-> JSON/Markdown operator review summaries
-> `S23PaperExecutionJournalWriter`
-> deterministic order-intent + execution-summary shell
-> post-planning intent guardrails
-> explicit `INTENT_READY` / `INTENT_BLOCKED` / `INTENT_ABORTED` statuses
-> `paper_vs_historical.py`
-> deterministic paper-vs-historical replay parity summaries
-> later-phase execution-shell arming guardrails
-> explicit `EXECUTION_ARMED` / `EXECUTION_BLOCKED` / `EXECUTION_ABORTED` statuses
-> fillless order-intent dispatch shell
-> explicit `ORDER_INTENT_DISPATCH_READY` / `ORDER_INTENT_DISPATCHED` / `ORDER_INTENT_DISPATCH_BLOCKED` / `ORDER_INTENT_CANCELLED` statuses
-> final no-fill execution handoff boundary
-> explicit `PAPER_EXECUTION_HANDOFF_READY` / `PAPER_EXECUTION_HANDOFF_BLOCKED` / `PAPER_EXECUTION_HANDOFF_ABORTED` statuses
-> execution-shell-aware replay parity summaries over planning + arming + dispatch + handoff state
-> Phase 1 fill simulator
-> explicit `PAPER_ORDER_PENDING` / `PAPER_ORDER_FILLED` / `PAPER_ORDER_NOT_FILLED` / `PAPER_FILL_ABORTED` statuses
-> fill-status-aware review summaries and paper-vs-historical parity summaries
-> Phase 2 same-day lifecycle loop
-> explicit `PAPER_POSITION_OPEN` / `PAPER_EXIT_PENDING` / `PAPER_POSITION_CLOSED` / `PAPER_EOD_SQUARE_OFF` / `PAPER_LIFECYCLE_ABORTED` statuses
-> lifecycle-aware review summaries and paper-vs-historical parity summaries

Current broker-backed ingress path:

`BrokerAdapter`
-> broker-normalized TFIS market events
-> normalized non-broker prelude events
-> `S23BrokerPaperIngressRunner`
-> `S23PaperIngressDryRunRunner`
-> `S23PaperSessionOrchestrator`
-> paper intent shell only by default
-> `ORDER_PLANNED` / `NO_TRADE` / `ABORTED`

Current supervised live decision path:

`BrokerAdapter`
-> normalized underlying quote
-> normalized underlying morning bars
-> normalized option-chain snapshot
-> provisional base S23 selection
-> selected-contract ORPT/RC option bars
-> `S23RuntimeInputDeriver`
-> S23 ORPT/RC timing recalculation when needed
-> TFIS checkpoint snapshots + monthly status + runtime aliases
-> `S23PaperLivePreludeBuilder`
-> `S23PaperLiveDecisionBuilder`
-> `trade_decision_summary.json` / `trade_decision_summary.md`

Corrected target architecture for monthly-status strategies:

`StrategyRegistry`
-> enabled strategy modules
-> independent `MonthlyStatusService`
-> strategy-specific rule matrix (`src/tfis/rules/s23_rule_matrix.py` for S23)
-> normalized broker/data adapter inputs
-> auditable near/next contract qualification
-> waiting paper orders
-> durable ledger and dashboard review

Current TradingEngine capture ingress path:

`ticks_context.csv` + `NIFTY50_option_quotes_YYYYMMDD.csv`
-> `tradingengine_capture_adapter.py`
-> normalized TFIS market-event JSONL
-> TFIS prelude JSONL
-> `S23TradingEngineCaptureIngressSuiteRunner`
-> `S23PaperIngressDryRunRunner`
-> paper intent shell only by default
-> `ORDER_PLANNED` / `NO_TRADE` / `ABORTED`

Current notes:

- monthly status can now drive branch selection in historical mode
- S23 recalculation is opt-in and remains a diagnostic overlay
- S23 current-day FSL / TRP handling is now a separate opt-in overlay that uses
  workbook-backed `09:15 -> ORPT / RC` snapshots rather than the older ORPT
  missed-entry path
- the recalculation overlay can now consume a dedicated spot intraday CSV when provided
- historical backtests can now opt into offline option-chain contract selection after the trade plan is computed
- option-chain selection can reject otherwise acceptable candidates when no chain contract satisfies range, OI, and premium constraints
- selected contract metadata can now optionally drive lifecycle simulation through symbol-keyed contract intraday bars
- if contract-specific intraday bars are unavailable for the selected symbol, TFIS falls back to the generic option intraday series and now records explicit provenance including selected symbol, bar counts, fallback reason, and the lifecycle data source actually used
- the paper orchestrator now applies explicit pre-planning guardrails for global paper disable, S23 paper disable, manual operator abort, stale data, missing chain or selected-contract inputs, session terminality, and one-plan-per-session enforcement, and those guardrail decisions now flow into audit events and persisted terminal summaries
- TFIS can now derive `09:15`, `ORPT`, and `RC` checkpoints from normalized
  one-minute underlying bars instead of depending on prebuilt prelude
  snapshots
- TFIS can now classify monthly status inside the supervised live decision path
  when the required historical/reference levels are supplied through a TFIS
  reference packet
- the supervised decision path now produces paper decision artifacts with the
  selected contract, premium, OI, entry, target, stoploss, and workbook
  provenance visible for operator review
- the new morning explainer now shows what TFIS knows at `09:16`, `09:25`, and
  `09:30`, including available checkpoints, prior-day reference values,
  current-day high/low so far, option aliases, and provisional formula
  evaluations before the final RC-stage decision is allowed
- the supervised decision path remains bounded: no continuous socket loop, no
  lifecycle execution, and no broker orders
- FYERS auth is now TFIS-owned: the refresh helper reads
  `D:\TradingEngineTFIS\.env` and writes only
  `D:\TradingEngineTFIS\data\token_store.json` during scheduled morning snapshots
- `src/tfis/brokers/base.py` and `src/tfis/brokers/fyers.py` now add the first broker-agnostic market-data boundary, with order placement explicitly blocked and S23 consuming only normalized TFIS events
- `src/tfis/paper/live_ingress.py` and `scripts/run_s23_fyers_paper_ingress.py` now combine normalized non-broker prelude events with FYERS-backed normalized market-data events, then reuse the existing ingress-only paper runner so S23 logic stays broker-agnostic
- the same FYERS ingress runner now also supports `--preflight-only`, which validates credentials, paper-only scope, ingress-only mode, kill-switch posture, selected-contract configuration, required prelude snapshots, artifact-root writability, valid broker timezone, and real-run session-date alignment without connecting to FYERS
- the first broker-backed ingress path persists `broker_health.json`, `normalized_events.jsonl`, `ingress_summary.json`, `selected_contract_audit.json`, `paper_session_review.md`, and `no_trade_or_order_plan_summary.json` while still stopping at planning by default
- `src/tfis/paper/tradingengine_capture_adapter.py` plus `scripts/convert_tradingengine_capture_to_tfis_ingress.py` now provide a read-only bridge from TradingEngine `ticks_context.csv` plus `NIFTY50_option_quotes_YYYYMMDD.csv` into TFIS normalized market-event JSONL, while intentionally requiring TFIS-side prelude inputs for calendar, monthly status, paper config, costs, and workbook-backed trade plans
- the TradingEngine capture audit found that several dates do cover `09:15`, `ORPT`, and `RC`, but the raw captures do not reliably embed the selected contract at RC and do not contain standalone monthly-status or trade-plan artifacts, so they are suitable for the S23 market-data leg only, not for standalone end-to-end TFIS sessions
- `src/tfis/paper/tradingengine_capture_ingress_suite.py` plus `scripts/run_s23_tradingengine_capture_ingress_suite.py` now pair those converted market events with TFIS validation preludes and run ingress-only dry runs across multiple captured dates without writing anything back into `D:\TradingData`
- the first real paired TradingEngine-capture ingress suite now exists under `D:/TradingEngineTFIS/tmp/s23_tradingengine_capture_dry_runs`; it processed `2026-05-15`, `2026-05-20`, `2026-05-22`, `2026-05-25`, `2026-05-26`, and `2026-05-27` with `0` stale events, `0` timezone mismatches, `0` missing chains, `0` missing selected contracts, and `0.0s` ORPT / RC lag, but every session still ended `ABORTED` with `missing_contract_oi`
- that suite establishes a clear boundary: current TradingEngine captures are good enough for the underlying and option-quote timing leg, but the raw option quote archives still carry blank `oi` at decision time, which makes the paired ingress path operationally `NO_GO` until an OI-enrichment source or an explicitly approved validation policy change exists
- the follow-up OI audit in `docs/operations/s23_tradingengine_capture_oi_audit.md` confirmed that the six audited option quote archives contain `0` non-blank `oi` rows overall and `0` non-blank `oi` rows in the RC windows, while the only alternate OI-bearing source found (`option_positioning` in `captures/sessions/*/events.jsonl`) is a near-spot summary that is not selected-contract-safe for S23 validation
- the paper artifact layer can now be sealed into a deterministic replay bundle manifest with stable hashes, terminal-state checks, and readback summaries so `ORDER_PLANNED`, `NO_TRADE`, and `ABORTED` sessions can be reconstructed without rerunning execution logic
- `src/tfis/paper/review.py` and `scripts/review_paper_session.py` now add the first operator-facing review surface over those persisted artifacts and replay bundles, including terminal state, guardrails, selected-contract details, audit timeline, provenance, freshness, bundle validation, and an explicit no-execution disclaimer
- `src/tfis/paper/execution_journal.py` now turns an `ORDER_PLANNED` S23 paper session into a deterministic intent-only handoff shell with `paper_order_intent.json`, `execution_journal.jsonl`, and `execution_summary.json`, while `NO_TRADE` and `ABORTED` sessions now emit explicit skipped-intent summaries instead of pretending any order or fill occurred
- the execution-journal shell now also applies post-planning guardrails for manual operator aborts, execution-shell disable switches, replay-bundle integrity failure, stale selected-contract quotes, duplicate intent generation, missing or corrupt intent artifacts, and selected-contract mismatch before any future execution phase exists
- `src/tfis/paper/paper_vs_historical.py` and `scripts/compare_paper_to_historical.py` now compare persisted `INTENT_READY` paper sessions against expected historical S23 trade-plan output, returning deterministic `MATCH`, `PARTIAL_MATCH`, `MISMATCH`, or `UNCOMPARABLE` results with field-level mismatch reporting and explicit go or no-go language
- the paper-vs-historical comparator reuses the existing historical trade normalizer, matches same-date S23 candidates by branch, option type, selected contract, and workbook-rule signals, and refuses ambiguous or non-intent-ready sessions instead of guessing
- the paper shell now persists enough comparison metadata to check selected contract, branch, workbook row, source rule, strikes, premiums, entry, target, stoploss, overlay flags, slippage assumptions, and provenance where available, without claiming any fill or lifecycle execution
- the execution-journal shell now extends beyond `INTENT_READY` into a distinct pre-execution arming layer, which requires replay-bundle validation, an acceptable paper-vs-historical comparison result, selected-contract freshness, operator-review completion when configured, and same-day-only policy confirmation before the shell can be marked `EXECUTION_ARMED`
- later execution-shell attempts now persist deterministic `EXECUTION_ARMED`, `EXECUTION_BLOCKED`, `EXECUTION_ABORTED`, or `EXECUTION_SKIPPED` outcomes into the execution journal and review surface, while still refusing to simulate fills, place orders, or start lifecycle monitoring
- `paper_vs_historical.py` now also understands execution-shell readiness artifacts (`execution_summary.json`, `execution_arm_summary.json`, `execution_block_summary.json`, and execution journal events), so parity checks can distinguish planning agreement from later pre-execution safety blocks
- planning parity plus `EXECUTION_ARMED` now returns `MATCH`, while planning parity plus known non-strategy execution blocks returns `PARTIAL_MATCH`; incomplete or corrupt execution-shell artifacts now return `UNCOMPARABLE` instead of being silently ignored
- the same comparator now also applies an explicit same-day lifecycle drift policy for filled paper sessions, distinguishing exact lifecycle parity from bounded acceptable drift on fill price, exit price, exit timestamp, and net P&L while treating selected-contract and explicit exit-reason mismatches as blockers when comparable
- the fillless shell now extends one step beyond arming into explicit dispatch-only states, which mark the order intent as ready for handoff to a future execution loop or as blocked/cancelled before handoff, while still keeping order placement, fills, and open-position state explicitly false
- `src/tfis/paper/execution_journal.py` now persists `intent_dispatch_summary.json` plus dispatch-shell journal events, and `review.py` plus `paper_vs_historical.py` now surface dispatch-shell readiness separately from the earlier arming layer
- `src/tfis/paper/execution_journal.py` now also persists `execution_handoff_summary.json`, which marks whether a dispatched intent is eligible for a future fill simulator without claiming any order placement, fill, or open position
- `paper_vs_historical.py` now treats the new handoff boundary as the final acceptable no-fill readiness state; planning parity plus acceptable execution, dispatch, and handoff shells now returns `MATCH`, while blocked handoff for a non-strategy safety reason still returns `PARTIAL_MATCH`
- a normalized apples-to-apples lifecycle-source comparison runbook now exists: the fair baseline is the monthly-status plus recalculation plus option-chain path with identical spot, option, option-chain, contract-intraday, and cost inputs, differing only by the `--enable-contract-specific-lifecycle` flag
- on the current fixture set, that normalized comparison now shows 10 selected contracts, 10 trades using real selected-contract bars, 0 explicit generic fallbacks, 100.0% lifecycle coverage, and one isolated P&L delta attributable to lifecycle data source alone
- when selected contract expiry metadata is available, historical reports can now review expiry-day full-exit compliance for S23 without introducing any option rollover behavior
- shared-data roots can now supply normalized CSV inputs for snapshot and historical TFIS backtests without requiring any direct TradingEngine runtime import
- the shared-data adapter is intentionally limited to normalized CSV folder layouts for now; raw parquet/jsonl/capture-session parsing remains future work
- existing backtest JSON outputs can now be compared across historical modes through a separate reporting tool without rerunning strategy logic
- the comparison tool now extracts only normalized S23 summary fields, applies explicit file-size and trade-count limits, and fails clearly on malformed or oversized reports instead of attempting unbounded raw JSON comparison
- the comparison tool now also records input-dataset paths and cost settings, and explicitly flags whether compared reports are apples-to-apples or only partially comparable
- the regenerated apples-to-apples S23 comparison showed that the earlier row-183 exit flip was not reproduced on the shared fixture dataset; the current-day FSL / TRP mode kept the base trade plan because the shared fixture lacked the required aggregated 09:15 snapshot
- TFIS now also has a small deterministic applied-case fixture at `tests/fixtures/backtest/s23_current_day_applied/` that includes `09:15:00`, `09:24:59`, and `09:29:59` coverage on one evaluated day
- that applied-case fixture now proves row `183` can apply apples-to-apples against the same base dataset with workbook-backed `start_strike` / `ideal_premium` / `minimum_premium` and `entry_price` changes
- a broader `AB6 OS` recalculation audit across rows `162-191` now confirms no additional workbook-backed target override formulas in that block
- the same audit found populated current-day option-entry cells `Z183:Z186`, and TFIS now consumes those workbook-backed entry overrides inside the opt-in current-day FSL / TRP layer
- rows `190-191` in the older workbook add position-open missed-SL process
  notes, and `s23_position_open_1500_audit.md` found no hidden numeric
  continuation-stoploss formula there. The newer S23 gap-up/gap-down text file
  now supplies the operational 15:00 original-SL comparison rule implemented in
  the paper position manager.
- if no spot intraday CSV is supplied, recalculation keeps an explicit current-day market-level fallback and records that choice in audit output
- base strategy formulas remain the canonical source for normal evaluation

## Current Safety Rules

- Excel is source of truth
- no silent ambiguity normalization
- governance before implementation
- reference materials are not automatic specs
- reversal dominates continuation

## Current Open Ambiguities

- S21 BankNifty monthly option-selling is now represented as config and a rule
  matrix, but operational promotion is blocked until active BankNifty lot size,
  monthly expiry selection, futures-continuous monthly-status sourcing, ORPT/RC
  applicability, carry-forward, and force-close policy are confirmed.
- no active workbook blocker currently prevents the implemented S23
  current-day FSL / TRP layer
- broader recalculation refinement is now constrained by workbook coverage rather
  than by unresolved mapping ambiguity:
  - `AB6 OS!Z183:Z186` are now implemented as workbook-backed current-day
    option-entry overrides for the supported `183-186` rows
  - `AB6 OS!190:191` only describe position-open process flow in the older
    workbook; the updated S23 text file now defines the 15:00 original-SL
    comparison rule used by the paper position manager
  - no additional target override formulas were found in `AB6 OS!162:191`
- unsupported paths are now explicit implementation boundaries, not silent
  ambiguities:
  - Bull / Bull CF Put not-missed remains unchanged because the workbook does
    not confirm a populated current-day row for that path
  - Bear / Bear CF Call not-missed remains unchanged for the same reason

## Current Deferred Systems

- futures rollover lifecycle
- monthly option buying
- S21 BankNifty monthly live/paper runtime beyond rule/config validation
- fuller strike-availability realism and broader contract-specific archive coverage
- broader multi-date TradingEngine capture normalization beyond the new read-only market-event adapter prototype
- broad multi-broker live runtime beyond the current market-data-only FYERS ingress foundation
- fully TFIS-native sourcing for monthly-status and prior-session reference
  levels without the current decision reference packet
- historical S23 morning-supervised artifacts created before the durable data
  layout still live under `tmp/s23_fyers_morning_supervised_decision` until a
  deliberate after-hours migration/backfill is performed

## Current Quality Snapshot

- last full-suite snapshot before the S21 scaffold: tests passing `426`
- S21/strategy focused validation for this task: `20 passed`
- readiness-focused regression snapshot after the shared lifecycle supervisor
  and pre-live audit additions: `77 passed`
- `python scripts/pre_live_readiness.py --profile prod --json`: `PASS`
- `python scripts/pre_live_readiness.py --profile prod --require-token --json`:
  `PASS`
- `python scripts/build_operator_dashboard.py --output-root tmp/operator_dashboard`:
  `PASS`
- `python scripts/run_s23_captured_session_validation.py ...`: latest session
  `2026-07-08 ORDER_REVIEWABLE` with persisted outcome
  `REPLAY_CONFIRMED_NOT_FILLED` / `PAPER_ORDER_NOT_FILLED`
- `python scripts/validate_project.py`: passing

## Operational Coordination Discipline

- update this file after any meaningful task that changes implemented behavior,
  architecture, tests, or known limitations
- update `next_steps.md` when ordering, blockers, or recommended priorities move
- update `milestones.md` for historical progress tracking
- if this file does not need a change for a task, that should be stated
  explicitly in the task close-out

## Approximate Completion Estimate

- S23 family completion: about `90-95%`
- backtesting realism: about `65-70%`
- execution realism: about `60-65%`

## Notes

- The S23 family is now structurally complete enough for branch-aware historical
  backtesting, and the earlier put-side recalculated strike wording ambiguity
  is now resolved as a confirmed workbook correction.
- Historical backtesting is now strong on rule validation, lifecycle auditing,
  and reporting, but still simplified relative to real option-chain execution.
- The opt-in S23 recalculation path now preserves both base-plan and recalculated-plan audit state and can distinguish between explicit spot intraday sourcing and fallback sourcing.
- The new option-chain selection layer improves contract realism and candidate rejection quality without changing the default historical path or pretending to be full execution simulation.
- Contract-specific lifecycle mode now makes selected-contract provenance explicit per trade, so archive gaps are visible instead of being hidden behind a generic option series fallback.
- The current fixture-backed lifecycle archive now covers all 10 selected-contract evaluations with real symbol bars, so remaining realism work is broader archive depth rather than a missing-symbol gap in the normalized S23 fixture set.
- A dedicated S23 contract archive ingestion plan now exists; TFIS still consumes only normalized contract-intraday CSVs, and raw session/parquet/broker-export adapters remain planning-stage work rather than runtime behavior.
- A dedicated S23 paper-trading readiness audit now exists, and the current live-paper disposition remains `NO-GO` for broad rollout even though the new operator close-out policy is in place and the first broadened ingress-only suite reached `LIMITED_GO`.
- Two new operations blueprints now define the next paper-runtime foundation: `s23_live_paper_data_contract.md` covers normalized live-paper inputs and guardrails, while `s23_paper_session_state_machine.md` defines the S23-only session phases, terminal states, and no-trade or abort rules.
- TFIS now also has a small S23-only `tfis.paper` foundation with immutable normalized event models, required-field validation, readiness or no-trade result objects, and a session manifest builder; this creates the first deterministic paper-runtime contract layer without introducing broker connectivity or an execution loop.
- `src/tfis/paper/orchestrator.py` now layers a deterministic S23 paper-session orchestrator on top of that contract foundation, rejecting stale, duplicate, and out-of-order events and stopping cleanly at `ORDER_PLANNED`, `NO_TRADE`, or `ABORTED` without simulating any paper fills.
- `src/tfis/paper/artifacts.py` now persists deterministic terminal planning artifacts under a paper-session folder, including the session manifest, audit trail, decision summary, selected contract details, and terminal no-trade or abort summaries without claiming any execution or fills.
- `src/tfis/paper/guardrails.py` now adds deterministic kill-switch and failure-handling decisions before planning, including explicit codes, messages, blocking source metadata, and operator-action hints for both in-memory audit and persisted terminal summaries.
- `docs/operations/s23_operator_closeout_policy.md` now codifies ingress-only session acceptance as `PASS`, `WARNING`, or `NO_GO`, including hard blockers for timezone mismatch, requested multi-session continuation in the current same-day runtime, missing chain or selected contract, stale data, and ORPT / RC lag beyond `5.0s`.
- `docs/operations/s23_fyers_ingress_live_runbook.md` now defines the first local real-FYERS operator path, including environment requirements, the role of the normalized prelude JSONL, the `--preflight-only` command, and the `PASS` / `WARNING` / `NO_GO` interpretation for safe ingress-only runs.
- the broadened ingress-only suite under `D:/TradingEngineTFIS/tmp/s23_live_paper_dry_runs/2026-05-27/s23-ingress-validation-suite-v1` now provides the first aggregate operational baseline: `5` sessions, `4 PASS`, `1 WARNING`, `0 NO_GO`, `80.0%` pass rate, `100.0%` selected-contract availability, and a current rollout recommendation of `LIMITED_GO`
- `src/tfis/paper/replay_bundle.py` now builds and validates deterministic replay-bundle manifests from persisted paper-session folders, including stable file hashes, terminal-state checks, and readback summaries for `ORDER_PLANNED`, `NO_TRADE`, and `ABORTED` outcomes.
- `src/tfis/paper/review.py` and `scripts/review_paper_session.py` now turn those artifacts and replay bundles into deterministic operator-facing JSON and Markdown review summaries without implying any execution, fills, or lifecycle monitoring.
- `src/tfis/paper/paper_vs_historical.py` and `scripts/compare_paper_to_historical.py` now add the first deterministic replay-parity check from a persisted S23 paper intent shell back to expected historical output, which means TFIS can now prove planning-state agreement before any execution loop or lifecycle monitor exists.
- `src/tfis/paper/execution_journal.py` now also adds a second, later-phase execution-shell readiness layer after `INTENT_READY`, recording whether a persisted paper intent is armed, blocked, aborted, or skipped before any future execution handoff exists.
- `src/tfis/paper/paper_vs_historical.py` now extends that parity check through the execution-shell readiness layer, which means TFIS can now verify both the planned S23 decision and the later pre-execution arming outcome before any fill or lifecycle phase exists.
- `src/tfis/paper/execution_journal.py` now extends that same fillless shell one step further through deterministic dispatch-only states, so TFIS can mark an armed intent as handoff-ready or handed off to a future execution loop without claiming any order placement, fill simulation, or open position.
- `src/tfis/paper/execution_journal.py` now extends the fillless shell one final step further through deterministic handoff-only states, so TFIS can mark a dispatched intent as eligible for a future fill simulator without claiming any order placement, fill simulation, open position, or lifecycle monitoring.
- `src/tfis/paper/paper_vs_historical.py` now includes execution, dispatch, and handoff shell states in replay parity summaries, which means the persisted paper shell can now be checked through planning, arming, dispatch, and final no-fill handoff readiness before any future fill-simulator phase exists.
- `docs/operations/s23_paper_trading_mvp_v1_design.md` now defines the first actual S23 paper fill-simulator and same-day lifecycle-loop policy, including the recommended Phase 1 slice of `PAPER_ORDER_PENDING`, `PAPER_ORDER_FILLED`, and `PAPER_ORDER_NOT_FILLED` before any broker integration or real order flow is considered.
- `src/tfis/paper/fill_simulator.py` now implements that Phase 1 slice, consuming a handoff-ready paper intent plus selected-contract quote or bar evidence and recording a conservative `filled`, `not filled`, or `aborted` outcome without opening a paper position or starting lifecycle monitoring.
- `src/tfis/paper/review.py` and `src/tfis/paper/paper_vs_historical.py` now understand Phase 1 fill artifacts, so operator review and replay parity summaries can show fill-shell status without implying any target/SL lifecycle or paper P&L tracking.
- the first deterministic fixture-backed S23 same-day paper lifecycle parity pilot remains available under `D:/TradingEngineTFIS/tmp/s23_paper_pilots/2026-05-27/s23-lifecycle-parity-pilot`; it reached a target-hit close on `NIFTY_20260528_22400_PE` and returned `MATCH` against the historical expectation with no drift outside policy.
- the first normalized archive-backed S23 same-day paper lifecycle parity pilot now exists under `D:/TradingEngineTFIS/tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot`; it used direct selected-contract ticks for `NIFTY_20260512_25000_PE`, returned `PAPER_ORDER_FILLED` plus `PAPER_POSITION_CLOSED`, and matched the normalized historical expectation with parity result `MATCH` and no drift outside policy.
- the first multi-session archive-backed S23 same-day paper lifecycle parity suite now exists under `D:/TradingEngineTFIS/tmp/s23_paper_pilot_suite/2026-05-27/s23-archive-suite-v2`; it covered bull/bear, call/put, target-hit, stoploss-hit, EOD square-off, no-fill, current-day FSL / TRP, and ORPT recalculation paths and returned `5 MATCH`, `1 PARTIAL_MATCH`, `0 MISMATCH`, and `0 UNCOMPARABLE`, which supports a `LIMITED_GO` recommendation for continued archive-backed validation but not yet live-paper rollout.
- the first normalized live-paper ingress-only dry run now exists under `D:/TradingEngineTFIS/tmp/s23_live_paper_dry_runs/2026-05-08/s23-archive-ingress-dry-run`; it consumed deterministic archive-export JSONL, reached `ORDER_PLANNED`, emitted an `INTENT_READY` shell, returned ingress readiness `PASS`, and recorded `0` stale events, `0` late events, `0` missing chains, `0` missing selected contracts, and `ORPT / RC` arrival lags of `2.0s` inside the current `5.0s` threshold.
- The `AB6 OS` current-day FSL / TRP rows `183-188` are now implemented only
  within their confirmed workbook-backed scope:
  `183-186` use populated `R/S/U/W`, while `187-188` remain `FSL-only`.
- Row `184` is no longer treated as a blocker; TFIS preserves the mixed
  Call/Put evidence as a resolved workbook clarification in audit output
  instead of silently normalizing it away.
- S23 and similar option-selling strategies should be treated as
  carry-forward-capable before expiry, but the current TFIS paper runtime still
  stops at same-day execution and does not yet implement multi-session
  carry-forward or strategy-specific T-1 / T-2 expiry handling.
- Expiry-day review is now explicitly visible in historical reports when option-chain expiry metadata is available, which makes S23 no-rollover governance easier to verify without changing the core lifecycle mechanics.
- S23 morning supervised operational artifacts now default to
  `data/strategies/S23/fyers_morning_supervised_decision` for durable
  option-chain, decision, paper-order, paper-position, and ledger/state records.
  Rebuildable dashboard HTML remains under `tmp/operator_dashboard`, and
  short-lived PowerShell launch diagnostics remain under
  `tmp/s23_fyers_morning_supervised_decision/_task_launch_logs`.
- The operator dashboard now prefers current persisted paper-position truth over
  stale decision-time `OPEN_CARRY_FORWARD_POSITION` blockers when an older
  carry-forward trade has already closed, and shared paper-order cutoff
  messages no longer hardcode `S23` when rendered for other strategies such as
  `S21`.
- The operator dashboard now also publishes a dedicated
  `trades/history/index.html` page for closed-trade review across all enabled
  strategies, with client-side strategy and date-range filters plus consolidated
  entry, exit, contract, quantity, and realized P&L fields sourced from the
  persisted paper trade ledgers.
- The live `trades/index.html` monitor now keeps the latest terminal close
  event visible when a multi-session paper trade exits after the strategy's last
  decision-session date, so carried-forward S23 exits are not hidden merely
  because the close happened on the following trading day.
- The trade monitors now also use soft row tinting and stronger status badge
  colors to distinguish closed trades, waiting orders, not-filled orders, open
  positions, and action-required follow-ups more quickly during operator review.
