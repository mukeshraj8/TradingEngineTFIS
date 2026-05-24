# Next Steps

This document is the execution queue for TFIS. It should be updated whenever
task ordering, blockers, or the recommended next action change in a meaningful
way.

## Immediate Next Priorities

1. TradingEngine shared-data adapter.
2. Rollover lifecycle module.
3. Gap-up / gap-down refinement.
4. Broader recalculation refinement beyond the current S23 opt-in path.
5. Contract-specific option-chain intraday pricing and strike-availability realism.

## Blocked / Pending Clarification

- any later expansion of recalculated target / stoploss behavior still needs
  workbook-backed confirmation beyond the current strike / premium / entry scope
- contract-specific lifecycle pricing still needs symbol-keyed intraday option data before the new option-chain selector can become execution-realistic

## Deferred

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
