# Next Steps

This document is the execution queue for TFIS. It should be updated whenever
task ordering, blockers, or the recommended next action change in a meaningful
way.

## Immediate Next Priorities

1. Wider comparison reporting across S23 historical modes.
2. Broader recalculation refinement beyond the current S23 opt-in paths.
3. Fuller strike-availability realism and broader contract-specific archive coverage.
4. Raw TradingEngine or NiftyTradingEngine capture-format adapters beyond normalized CSV roots.
5. Futures rollover module for future-based strategy families.

## Blocked / Pending Clarification

- any later expansion of recalculated target / stoploss behavior still needs
  workbook-backed confirmation beyond the current strike / premium / entry scope
- current-day S23 FSL / TRP unsupported paths remain intentionally unchanged
  until the workbook confirms additional rows:
  - Bull / Bull CF Put not missed
  - Bear / Bear CF Call not missed
- fuller strike-availability realism still needs wider symbol/date coverage than the current fixture-backed contract-specific lifecycle foundation
- raw shared capture ingestion still needs explicit normalization contracts for parquet/jsonl/session artifacts before TFIS should parse them directly

## Deferred

- futures rollover module for future-based strategy families
- monthly option buying
- BankNifty weekly live support
- broker adapters
- live runtime

## Important Reading Before Any Change

- [project_rulebook.md](project_rulebook.md)
- [current_state.md](current_state.md)
- [next_steps.md](next_steps.md)
- [excel_ambiguity_audit.md](../importers/excel_ambiguity_audit.md)

## Operational Update Discipline

- after every meaningful task, review whether `current_state.md`,
  `next_steps.md`, and `milestones.md` need updates
- if priorities did not change, say so explicitly in the task close-out
- keep this file focused on sequencing and blockers rather than repeating all
  implementation detail

## Current Architectural Principle

`Evidence before behavior.`
