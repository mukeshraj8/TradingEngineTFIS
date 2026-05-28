# Current State

This is the living operational snapshot for TFIS. It should be updated whenever
implemented behavior, architecture shape, test posture, or known limitations
change in a meaningful way.

## Current Focus

- resolve the TradingEngine-capture `oi` blocker or keep those captures limited to the market-data leg, while continuing to broaden broker-backed S23 ingress-only evidence before enabling any controlled live-like fill or lifecycle rehearsal

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
- read-only TradingEngine capture-session audit and market-event adapter prototype for S23 dry runs
- TradingEngine capture plus TFIS prelude ingress-only dry-run suite for S23

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
- rows `190-191` add position-open missed-SL process notes, and the new `s23_position_open_1500_audit.md` confirms they are still process-only in this workbook area rather than hidden continuation-stoploss math
- if no spot intraday CSV is supplied, recalculation keeps an explicit current-day market-level fallback and records that choice in audit output
- base strategy formulas remain the canonical source for normal evaluation

## Current Safety Rules

- Excel is source of truth
- no silent ambiguity normalization
- governance before implementation
- reference materials are not automatic specs
- reversal dominates continuation

## Current Open Ambiguities

- no active workbook blocker currently prevents the implemented S23
  current-day FSL / TRP layer
- broader recalculation refinement is now constrained by workbook coverage rather
  than by unresolved mapping ambiguity:
  - `AB6 OS!Z183:Z186` are now implemented as workbook-backed current-day
    option-entry overrides for the supported `183-186` rows
  - `AB6 OS!190:191` only describe position-open process flow; the dedicated
    15:00 audit found no linked numeric continuation-stoploss rule elsewhere in
    the inspected workbook ranges
  - no additional target override formulas were found in `AB6 OS!162:191`
- unsupported paths are now explicit implementation boundaries, not silent
  ambiguities:
  - Bull / Bull CF Put not-missed remains unchanged because the workbook does
    not confirm a populated current-day row for that path
  - Bear / Bear CF Call not-missed remains unchanged for the same reason

## Current Deferred Systems

- futures rollover lifecycle
- monthly option buying
- fuller strike-availability realism and broader contract-specific archive coverage
- broader multi-date TradingEngine capture normalization beyond the new read-only market-event adapter prototype
- broad multi-broker live runtime beyond the current market-data-only FYERS ingress foundation

## Current Quality Snapshot

- tests passing: `426`
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
- `docs/operations/s23_operator_closeout_policy.md` now codifies ingress-only session acceptance as `PASS`, `WARNING`, or `NO_GO`, including hard blockers for timezone mismatch, unsupported continuation, missing chain or selected contract, stale data, and ORPT / RC lag beyond `5.0s`.
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
- S23 option-selling rollover is now explicitly classified as not applicable:
  target, stoploss, or expiry-day exit closes the whole position, and any later
  trade must be a fresh calculation rather than a carried option rollover.
- Expiry-day review is now explicitly visible in historical reports when option-chain expiry metadata is available, which makes S23 no-rollover governance easier to verify without changing the core lifecycle mechanics.
