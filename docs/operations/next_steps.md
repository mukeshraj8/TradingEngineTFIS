# Next Steps

This document is the execution queue for TFIS. It should be updated whenever
task ordering, blockers, or the recommended next action change in a meaningful
way.

## Immediate Next Priorities

1. Run the first archive-backed S23 same-day paper lifecycle parity pilot.
   The comparator now has an explicit same-day drift policy with deterministic `MATCH`, `MATCH_WITH_ACCEPTABLE_DRIFT`, `PARTIAL_MATCH`, `MISMATCH`, and `UNCOMPARABLE` outcomes. The next safe step is to replay a small normalized non-fixture S23 paper session set and measure how often real archive sessions stay inside acceptable drift.
2. Broader real/archive contract-specific intraday coverage for S23.
   The deterministic fixture set is fully covered at 100.0%; the next safe step is a small normalized archive pilot using real session data while keeping TFIS runtime on the existing contract-intraday CSV contract.
3. Raw TradingEngine or NiftyTradingEngine capture-format adapters beyond normalized CSV roots.
4. Convert the same-day drift policy into explicit paper-session go/no-go operating thresholds.
   The comparator now distinguishes exact parity from acceptable same-day drift. The next governance step is to define how many `MATCH_WITH_ACCEPTABLE_DRIFT` sessions are acceptable in a pilot day and which `PARTIAL_MATCH` reasons are allowed versus rollout blockers.

Comparison reporting note:

- the bounded S23 comparison tool is now in place for the current historical modes
- the comparison layer now records input-dataset paths, cost settings, and apples-to-apples status
- the normalized lifecycle-source runbook now compares a matched option-chain baseline against contract-specific lifecycle mode, so lifecycle-source P&L differences can be reviewed without cost or spot-input drift
- future comparison work should extend reporting depth without regressing the new file-size, trade-count, timeout, and integrity safeguards
- the row-183 `current_day_fsl_trp` loss flip seen in an older comparison was not reproduced after rerunning all six modes on one shared dataset set and one shared cost model
- the new S23 paper-vs-historical comparator now reuses the historical normalized trade summaries and compares persisted `INTENT_READY` paper sessions against expected historical trade-plan output with deterministic `MATCH`, `PARTIAL_MATCH`, `MISMATCH`, or `UNCOMPARABLE` statuses, and it now also distinguishes later execution-shell, dispatch-shell, and final no-fill handoff readiness from the earlier arming layer

## Blocked / Pending Clarification

- no workbook-backed recalculated target formulas were found in `AB6 OS` rows `162-191`; any target override work remains blocked until new workbook evidence appears
- `AB6 OS!Z183:Z186` are now implemented as workbook-backed current-day option-entry overrides for the supported `183-186` rows
- `AB6 OS!190:191` still describe 15:00 position-open process flow only; the new
  `docs/importers/s23_position_open_1500_audit.md` found no linked numeric
  continuation-stoploss formulas in the inspected workbook ranges
- a deterministic applied-case fixture now exists for current-day FSL / TRP (`tests/fixtures/backtest/s23_current_day_applied/`), so future row-183 or row-185 timing investigations should start from that same apples-to-apples dataset before using any synthetic scenario variants
- if we later want to study whether current-day FSL / TRP can change lifecycle exits under broader market conditions, the next data need is wider non-synthetic intraday coverage rather than new workbook mapping assumptions
- current-day S23 FSL / TRP unsupported paths remain intentionally unchanged until the workbook confirms additional rows:
  - Bull / Bull CF Put not missed
  - Bear / Bear CF Call not missed
- the new S23 live-paper data contract and session state machine now have matching schema scaffolding, required-field validation, an in-memory orchestrator, pre-planning kill-switch and failure-handling guardrails, persisted terminal planning artifacts, replay-bundle manifests, operator-facing review summaries, an execution-journal intent shell, post-planning intent guardrails, planning-state paper-vs-historical replay comparison, later-phase execution-shell arming controls, a fillless dispatch-only shell, a final no-fill handoff boundary, execution-shell-aware parity summaries under `src/tfis/paper`, a documented MVP v1 fill-simulator design, Phase 1 fill or no-fill simulation, and Phase 2 same-day lifecycle simulation with paper exit and P&L artifacts, but no broker connectivity, no real order placement, and no next-day continuation support exist yet
- fuller strike-availability realism still needs wider symbol/date coverage than the current fixture-backed contract-specific lifecycle foundation; the fixture gap is closed, but broader archive depth beyond the current S23 symbol/date set is still pending
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
- [s23_live_paper_data_contract.md](s23_live_paper_data_contract.md)
- [s23_paper_session_state_machine.md](s23_paper_session_state_machine.md)
- [excel_ambiguity_audit.md](../importers/excel_ambiguity_audit.md)

## Operational Update Discipline

- after every meaningful task, review whether `current_state.md`,
  `next_steps.md`, and `milestones.md` need updates
- if priorities did not change, say so explicitly in the task close-out
- keep this file focused on sequencing and blockers rather than repeating all
  implementation detail

## Current Architectural Principle

`Evidence before behavior.`
