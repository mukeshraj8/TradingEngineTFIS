# Next Steps

This document is the execution queue for TFIS. It should be updated whenever
task ordering, blockers, or the recommended next action change in a meaningful
way.

## Immediate Next Priorities

1. Validate S23 live ORPT/RC timing finalization during the next real market
   session. The supervised live decision path now builds a provisional base
   selection at ORPT, finalizes and places the waiting paper order from that
   ORPT selection when the selected option has not missed entry, and reserves
   RC for the missed-entry recalculation path only. The remaining work is live
   market evidence across CE/PE and near/next-expiry cases.
2. Validate S23 next-day SL reset after a 15:00 carry-forward in a real market
   session. The paper position manager now records overnight SL inactive
   carry-forward when price is not above original SL, keeps target active the
   next day, reactivates the original SL at ORPT when `09:15` high does not
   miss SL, and recalculates revised SL from RC high plus configured
   `sl_reference_pct` when the `09:15` high misses SL. Offline restart-safety
   tests now also prove that carry/resume transitions preserve the SL-reset
   metadata instead of reactivating SL by default. Remaining work is live
   evidence from FYERS quotes/bars and dashboard review of the resulting state.
3. Validate S23 live order-watcher/current-price visibility end to end.
   The scheduled startup wrapper now starts one paper watcher per produced order
   or open position, scans the durable S23 artifact root for persisted
   open/carry-forward positions, and captures the supervised Python process
   through TFIS stdout/stderr log files before scanning the current run-date metadata.
   This should prevent a stalled PowerShell output pipeline or later-touched
   stale session from leaving valid waiting orders without the correct watcher.
   A separate post-cutoff finalizer marks still-waiting same-session orders as
   `PAPER_ORDER_NOT_FILLED` if a watcher exits before cutoff. The remaining
   operational validation is to prove automatic watcher startup, quote updates,
   fill status, dashboard rebuilds, and finalizer cleanup from live FYERS
   quotes/artifacts during market hours, and to confirm that the FYERS
   option-chain snapshot passes the new true-next-expiry verification instead
   of failing closed with `NEXT_WEEKLY_OPTION_CHAIN_UNAVAILABLE`, without
   changing strategy rules. The watcher now persists selected-contract
   quote/bar observations to `selected_contract_market_events.jsonl`, and the
   captured-session validator can replay waiting-order fill/not-filled/waiting
   outcomes from that evidence. The validator now also replays persisted
   position threshold outcomes for target, active SL/FSL, and still-open or
   carry-forward states. The remaining validation is to prove that this stream
   is populated continuously during a real market watch. The Trades Taken
   dashboard now surfaces that stream as event count, latest timestamp,
   age/staleness, watcher PID, source, and Market Events artifact link, so the
   live validation should check those fields alongside price and P&L. The
   captured-session validator now also recognizes expiry force-close and
   next-day SL reset replay outcomes from persisted artifacts. Improve
   TFIS-only watcher observability so an
   operator can see branch, contract, parent/child process relationship, and
   last quote timestamp without confusing a normal wrapper/child pair for two
   independent strategy watchers. Offline unit tests now prove the watcher and
   supervised-decision PID-lock identities and duplicate live-PID fail-closed
   behavior; remaining proof is a real Windows restart attempt with live
   process inspection. The manual operator guide now has a
   money-readiness command table for the dashboard, replay validator, focused
   tests, syntax checks, scheduled-task checks, watcher recovery, and pre-live
   readiness checks; use that table as the first human-run test checklist.
4. Keep monthly status as an independent service and improve its explanation/provenance output.
   Monthly-status calculation must support selected instrument, selected date, and configured price source. It must produce one of the four business statuses or `UNKNOWN` only for incomplete/error cases, and it must remain reusable by future strategies such as S21.
5. Introduce generic strategy-registry execution for enabled strategies.
   The generic execution-plan contract now exists under
   `tfis.strategy.execution_plan`, and current S23 paper configs declare an
   enabled S23 entry with branch registry IDs and strategy paths. It can skip
   disabled strategies and fail closed for unsupported enabled executors without
   broker imports. Remaining work is wiring the supervised live-paper runner to
   consume this plan directly and call strategy modules through a shared
   interface. S23/FYERS can remain the first operational path, but not as a core
   engine assumption.
6. Validate the new durable S23 artifact layout through the next scheduled
   market run. The morning supervised workflow, watcher, dashboard source, and
   finalizer now default to
   `data/strategies/S23/fyers_morning_supervised_decision` for option-chain,
   decision, order, position, and ledger/state artifacts, while rebuildable
   dashboard HTML and PowerShell launch logs remain under `tmp`. Remaining
   work is live-run validation and optional historical migration/backfill from
   older `tmp/s23_fyers_morning_supervised_decision` sessions after confirming
   no process is using them.
7. Decide whether TradingEngine option-quote captures can be enriched with reliable selected-contract OI before using them for TFIS ingress-only acceptance.
   The paired suite under `D:/TradingEngineTFIS/tmp/s23_tradingengine_capture_dry_runs` proved that six real captured dates can be converted, paired with TFIS preludes, and fed through the ingress-only runner without touching `D:\TradingData`, but all six sessions still ended `ABORTED` with `missing_contract_oi`. The new audit in `docs/operations/s23_tradingengine_capture_oi_audit.md` makes the blocker explicit: the six audited quote archives have `0` non-blank `oi` rows overall and `0` non-blank `oi` rows in the RC window, while `option_positioning` journal events are only near-spot summaries and not a selected-contract-safe substitute.
8. Replace the current TFIS decision reference packet with fully TFIS-native sourcing for monthly-status and prior-session reference levels.
   `src/tfis/paper/runtime_input_derivation.py` and `scripts/run_s23_fyers_live_decision_check.py` now prove that TFIS can derive `09:15`, `ORPT`, and `RC` checkpoints from normalized morning bars and build a supervised paper decision summary from live FYERS snapshots. The main remaining TFIS decision gap is the reference packet itself: monthly-status levels, `d2/d3/d4` levels, and option aliases such as `OPT_PRV_2DHH` and `OPT_PRV_3DLL` still need a TFIS-native sourcing path rather than a manual packet.
9. Broaden the supervised FYERS live-decision evidence set across more dates and branch shapes before introducing any continuous socket/session orchestration.
   The new supervised path now exists under `src/tfis/paper/runtime_input_derivation.py`, `src/tfis/paper/live_decision.py`, and `scripts/run_s23_fyers_live_decision_check.py`. The next safe step is to prove the same TFIS-native decision summary works cleanly across more market dates, more branch fixtures, and more option-chain shapes while keeping OI validation strict.
10. Broaden the broker-backed S23 ingress-only validation set across multi-date normalized archive and replay sessions before enabling any broker-backed fill or lifecycle rehearsal.
   The broker-agnostic ingress layer still exists under `src/tfis/brokers/` and `src/tfis/paper/live_ingress.py`, with FYERS as the first market-data adapter and explicit order-placement blocking. `D:/TradingEngineTFIS/tmp/s23_live_paper_dry_runs/2026-05-27/s23-ingress-validation-suite-v1` remains the first operator-grade baseline: `5` sessions, `4 PASS`, `1 WARNING`, `0 NO_GO`, `80.0%` pass rate, `100.0%` selected-contract availability, and a `LIMITED_GO` recommendation.
11. If the broader supervised decision and ingress suites stay within the close-out thresholds, run the first tightly controlled live-like S23 paper fill and same-day lifecycle rehearsal under operator sign-off.
   The operator policy now exists in `docs/operations/s23_operator_closeout_policy.md`, and the new broker-backed ingress design now exists in `docs/operations/s23_fyers_paper_ingress_design.md`. The next rehearsal should happen only after broader multi-date decision and ingress suites still preserve `0` NO_GO sessions and keep warning cases bounded and reviewed.
12. Continue extracting generic paper lifecycle pieces after S23 market
   validation. S23 and similar option-selling strategies are carry-forward
   capable before expiry. The paper runtime now has multi-day foundation
   pieces, visible watcher windows, expiry force-close governance,
   session-only waiting-order behavior, and next-day SL reset. The next
   architecture step is to lift shared lifecycle concepts into strategy-neutral
   services only after the S23 behavior is proven in live paper operation.
13. Broader real/archive contract-specific intraday coverage for S23.
   The deterministic fixture set is fully covered at 100.0%; the next safe step is to widen real session coverage while keeping TFIS runtime on the existing contract-intraday CSV contract.
14. If an OI-enrichment source is found, rerun the TradingEngine capture ingress suite before attempting any fill or lifecycle replay from captures.
   `scripts/run_s23_tradingengine_capture_ingress_suite.py` now proves that the raw capture path itself is operationally read-only and deterministic. The blocker is not prelude pairing, timing, or selected-contract identity alone; it is the absence of usable selected-contract `oi` in the option-quote archives at decision time.

Comparison reporting note:

- the bounded S23 comparison tool is now in place for the current historical modes
- the comparison layer now records input-dataset paths, cost settings, and apples-to-apples status
- the normalized lifecycle-source runbook now compares a matched option-chain baseline against contract-specific lifecycle mode, so lifecycle-source P&L differences can be reviewed without cost or spot-input drift
- future comparison work should extend reporting depth without regressing the new file-size, trade-count, timeout, and integrity safeguards
- the row-183 `current_day_fsl_trp` loss flip seen in an older comparison was not reproduced after rerunning all six modes on one shared dataset set and one shared cost model
- the new S23 paper-vs-historical comparator now reuses the historical normalized trade summaries and compares persisted S23 paper sessions through planning, arming, dispatch, handoff, fill, and same-day lifecycle outcome with deterministic `MATCH`, `MATCH_WITH_ACCEPTABLE_DRIFT`, `PARTIAL_MATCH`, `MISMATCH`, or `UNCOMPARABLE` statuses
- the new S23 operator close-out policy now classifies ingress-only sessions as `PASS`, `WARNING`, or `NO_GO`, with `LIMITED_GO` or `GO_FOR_CONTROLLED_PAPER` reserved for aggregate suite interpretation rather than individual-session state

## Blocked / Pending Clarification

- no workbook-backed recalculated target formulas were found in `AB6 OS` rows `162-191`; any target override work remains blocked until new workbook evidence appears
- `AB6 OS!Z183:Z186` are now implemented as workbook-backed current-day option-entry overrides for the supported `183-186` rows
- `AB6 OS!190:191` still describe 15:00 position-open process flow only in the
  older workbook, and `docs/importers/s23_position_open_1500_audit.md` found no
  linked numeric continuation-stoploss formulas there. The newer S23
  gap-up/gap-down text file now defines the 15:00 original-SL comparison rule
  implemented in paper position management.
- a deterministic applied-case fixture now exists for current-day FSL / TRP (`tests/fixtures/backtest/s23_current_day_applied/`), so future row-183 or row-185 timing investigations should start from that same apples-to-apples dataset before using any synthetic scenario variants
- if we later want to study whether current-day FSL / TRP can change lifecycle exits under broader market conditions, the next data need is wider non-synthetic intraday coverage rather than new workbook mapping assumptions
- current-day S23 FSL / TRP unsupported paths remain intentionally unchanged until the workbook confirms additional rows:
  - Bull / Bull CF Put not missed
  - Bear / Bear CF Call not missed
- the new S23 live-paper data contract and session state machine now have matching schema scaffolding, required-field validation, an in-memory orchestrator, pre-planning kill-switch and failure-handling guardrails, persisted terminal planning artifacts, replay-bundle manifests, operator-facing review summaries, an execution-journal intent shell, post-planning intent guardrails, planning-state paper-vs-historical replay comparison, later-phase execution-shell arming controls, a fillless dispatch-only shell, a final no-fill handoff boundary, execution-shell-aware parity summaries under `src/tfis/paper`, a documented MVP v1 fill-simulator design, Phase 1 fill or no-fill simulation, Phase 2 same-day lifecycle simulation with paper exit and P&L artifacts, visible watcher-window paper monitoring, expiry governance, session-only waiting-order cancellation, and a broker-agnostic live-paper ingress foundation with FYERS as the first market-data adapter; broker order placement remains blocked and multi-session carry-forward behavior still needs clean market-day validation before operational reliance
- fuller strike-availability realism still needs wider symbol/date coverage than the current fixture-backed contract-specific lifecycle foundation; the fixture gap is closed, but broader archive depth beyond the current S23 symbol/date set is still pending
- raw shared capture ingestion still needs broader normalization contracts for parquet/jsonl/session artifacts before TFIS should parse them directly at scale; the new TradingEngine capture adapter prototype is intentionally limited to one-session market-event conversion
- TradingEngine capture plus TFIS prelude ingress-only dry runs are now implemented and validated, but the first six real-date suite runs all ended `ABORTED` with `missing_contract_oi`; the new OI audit confirms this is a real source-data gap rather than a runner defect, so this path remains `NO_GO` for operational ingress acceptance and should be treated as market-data-leg timing validation only

## Deferred

- futures rollover module for future-based strategy families
- monthly option buying
- BankNifty weekly live support
- multi-broker live runtime beyond the current market-data-only FYERS adapter

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
