# Current State

This is the living operational snapshot for TFIS. It should be updated whenever
implemented behavior, architecture shape, test posture, or known limitations
change in a meaningful way.

## Current Focus

- S23 option-selling family completion

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
- opt-in option-chain contract selection realism foundation
- Excel ambiguity audit
- reference-material indexing

## Current Architecture Flow

Current high-level offline path:

`MonthlyStatusEngine`
-> `StrategyBranchSelector`
-> strategy evaluation
-> historical lifecycle backtest

Current notes:

- monthly status can now drive branch selection in historical mode
- S23 recalculation is opt-in and remains a diagnostic overlay
- the recalculation overlay can now consume a dedicated spot intraday CSV when provided
- historical backtests can now opt into offline option-chain contract selection after the trade plan is computed
- option-chain selection can reject otherwise acceptable candidates when no chain contract satisfies range, OI, and premium constraints
- selected contract metadata is currently audit and candidate-selection realism only; lifecycle prices still come from the generic intraday option series
- if no spot intraday CSV is supplied, recalculation keeps an explicit current-day market-level fallback and records that choice in audit output
- base strategy formulas remain the canonical source for normal evaluation

## Current Safety Rules

- Excel is source of truth
- no silent ambiguity normalization
- governance before implementation
- reference materials are not automatic specs
- reversal dominates continuation

## Current Open Ambiguities

- none currently tracked in the S23 recalculation layer

## Current Deferred Systems

- rollover lifecycle
- monthly option buying
- TradingEngine capture adapter
- contract-specific option-chain intraday pricing and fuller strike-availability realism
- live runtime
- paper runtime
- broker adapters

## Current Quality Snapshot

- tests passing: `236`
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
