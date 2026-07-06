# Milestones

## Current Snapshot

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
- S23 captured-session validation and dashboard final-leg review now include
  latest stage-level no-contract calculations when no final
  `trade_decision_summary.json` exists for a branch. This keeps CE/PE review
  complete on carry-forward days and on failed-leg days: selected branches show
  final contracts, while no-contract branches show failure code and formula
  audit context instead of disappearing from the operator view.
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
  - tests passing: `426`
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
  adding S21 or other strategies
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
