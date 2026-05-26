# Current State

This is the living operational snapshot for TFIS. It should be updated whenever
implemented behavior, architecture shape, test posture, or known limitations
change in a meaningful way.

## Current Focus

- S23 live-paper contract and session-orchestration foundation

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

## Current Architecture Flow

Current high-level offline path:

`MonthlyStatusEngine`
-> `StrategyBranchSelector`
-> strategy evaluation
-> historical lifecycle backtest

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
- raw TradingEngine or NiftyTradingEngine capture-format adapters
- live runtime
- paper runtime
- broker adapters

## Current Quality Snapshot

- tests passing: `274`
- `python scripts/validate_project.py`: passing

## Operational Coordination Discipline

- update this file after any meaningful task that changes implemented behavior,
  architecture, tests, or known limitations
- update `next_steps.md` when ordering, blockers, or recommended priorities move
- update `milestones.md` for historical progress tracking
- if this file does not need a change for a task, that should be stated
  explicitly in the task close-out

## Approximate Completion Estimate

- S23 family completion: about `85-90%`
- backtesting realism: about `65-70%`
- execution realism: about `10-15%`

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
- A dedicated S23 paper-trading readiness audit now exists, and the current disposition is `NO-GO` until paper-session orchestration, operator visibility, failure handling, and kill-switch guardrails are implemented.
- Two new operations blueprints now define the next paper-runtime foundation: `s23_live_paper_data_contract.md` covers normalized live-paper inputs and guardrails, while `s23_paper_session_state_machine.md` defines the S23-only session phases, terminal states, and no-trade or abort rules.
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



