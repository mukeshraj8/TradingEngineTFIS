# S23 Paper Trading Readiness Audit

## Purpose

This document audits whether TFIS is ready to run S23 end to end in a paper
trading context.

The audit is intentionally S23-only.

It assumes:

- S23 workbook-backed offline logic is already mature
- no new strategy work should be added before S23 is operationally safe
- offline historical realism and provenance are stronger than paper/live runtime
  readiness

## Overall Conclusion

Current S23 paper-trading disposition: `NO-GO`

Reason:

- S23 offline research and backtest logic is strong
- S23 paper/live runtime orchestration is still only partially defined
- several execution-safety and operator-safety layers are still incomplete beyond the current pre-execution shell

High-level split:

- offline S23 research and replay logic: strong
- S23 contract/lifecycle realism on deterministic fixtures: strong
- paper runtime data contracts: partial
- paper execution and operator review surfaces: partial
- paper failure handling and kill-switch controls through the final no-fill handoff boundary: partial

## Readiness Checklist

| Area | Current Status | Risk | Current Position | Required Tasks |
| --- | --- | --- | --- | --- |
| 1. S23 configuration completeness | READY | Medium | All four branches exist, workbook-backed logic is traced, registry/governance exists, monthly-status routing exists. | Freeze the paper-trading strategy set to S23 only and keep config promotion controlled. |
| 2. Live/paper input data requirements | PARTIAL | High | Historical CSV contracts are clear; live-paper source contracts are not yet finalized. | Define the live-paper normalized data contract for daily, option levels, option chain, spot intraday, option intraday, and selected-contract intraday inputs. |
| 3. Option-chain live selection readiness | PARTIAL | High | Offline option-chain selection logic exists with OI, premium, and spread-aware tie-breaking. No live-paper chain ingestion path is finalized. | Specify live-paper chain refresh cadence, stale-chain handling, expiry metadata requirements, and selected-contract provenance rules. |
| 4. ORPT timing handling | PARTIAL | High | ORPT behavior is workbook-backed in historical mode. No live-paper scheduler/clock contract is defined yet. | Define exact session clock behavior at `09:24:59`, delayed-start policy, and what happens if inputs arrive late or out of order. |
| 5. Missed-entry recalculation handling | PARTIAL | High | Historical ORPT missed-entry detection and recalculation exist. No live-paper orchestration path exists. | Define how live-paper mode detects missed entry, snapshots ORPT data, schedules RC recalculation, and preserves audit. |
| 6. Current-day FSL / TRP handling | PARTIAL | High | Historical workbook-backed rows `183-188` exist and are tested. No paper-runtime timing flow exists. | Define whether paper mode will support current-day FSL / TRP from day one and how required `09:15`, ORPT, and RC snapshots are captured. |
| 7. `Z183:Z186` entry override behavior | PARTIAL | Medium | Workbook-backed current-day entry overrides are implemented in historical mode. No live-paper application contract exists. | Define when paper mode applies these overrides and how original vs overridden entry is shown to operators. |
| 8. Selected-contract lifecycle tracking | PARTIAL | High | Historical selected-contract lifecycle tracking is strong and provenance-rich. No paper session selected-contract state model exists yet. | Define active selected-contract state, symbol continuity, price-source labels, and lifecycle quote freshness requirements. |
| 9. Paper order simulation | PARTIAL | High | TFIS now has a complete no-fill shell through `PAPER_EXECUTION_HANDOFF_READY`, Phase 1 fill simulation through `PAPER_ORDER_PENDING`, `PAPER_ORDER_FILLED`, `PAPER_ORDER_NOT_FILLED`, and `PAPER_FILL_ABORTED`, a first same-day lifecycle slice through `PAPER_POSITION_OPEN`, `PAPER_POSITION_CLOSED`, `PAPER_EOD_SQUARE_OFF`, and `PAPER_LIFECYCLE_ABORTED`, and an explicit paper-vs-historical same-day drift policy with `MATCH`, `MATCH_WITH_ACCEPTABLE_DRIFT`, `PARTIAL_MATCH`, `MISMATCH`, and `UNCOMPARABLE` outcomes. | Apply the new drift policy to archive-backed paper sessions, define pilot-day thresholds for acceptable drift, and tighten operator close-out rules before any broader paper rollout. |
| 10. Fill/slippage model | PARTIAL | Medium | Historical cost/slippage assumptions exist, and the Phase 1 paper fill simulator now applies a separate conservative selected-contract quote/bar fill policy with explicit spread and freshness gates. Lifecycle-time execution friction is still undefined. | Keep the Phase 1 fill policy stable, then define lifecycle-time exit pricing rules separately from historical cost assumptions. |
| 11. Spread/liquidity/OI validation | PARTIAL | High | Offline option-chain selection already uses OI and spread as ranking signals. Live-paper pre-trade guards are not formalized. | Define hard no-trade gates for spread, zero bid, low OI, missing volume, stale quotes, and untradable books. |
| 12. Expiry-day and holiday handling | PARTIAL | High | Expiry-day review exists in historical reports. Holiday/session-calendar handling for paper runtime is not defined. | Add session calendar rules, expiry-day paper restrictions, holiday skips, and pre-expiry market-open checks. |
| 13. Position-open / EOD handling | PARTIAL | High | Historical EOD policies exist. Workbook rows `190-191` remain process-only and do not give numeric next-day continuation logic. | Choose an explicit paper-mode policy: either same-day square-off only for initial rollout or block next-day continuation until workbook evidence exists. |
| 14. Logging and audit reports | PARTIAL | Medium | Historical reports are strong. TFIS now persists session manifests, audit trails, terminal summaries, replay-bundle manifests, operator review outputs, an execution-journal intent shell, later execution-arm or execution-block summaries, fillless dispatch summaries, final handoff summaries, Phase 1 fill/no-fill artifacts, Phase 2 paper position / exit / P&L artifacts, and lifecycle-aware paper-vs-historical comparison summaries. | Add an end-of-session operator close-out report and define which lifecycle deviations should escalate to paper-runtime NO-GO. |
| 15. Dashboard / operator visibility | PARTIAL | Medium | TFIS now has operator-facing JSON and Markdown review summaries over persisted paper-session artifacts, replay bundles, execution-journal intent shells, execution-shell readiness outcomes, fillless dispatch-only outcomes, final handoff outcomes, Phase 1 fill/no-fill outcomes, and Phase 2 same-day lifecycle / P&L outcomes. | Add an operator-facing close-out surface and explicit lifecycle warning severity model. |
| 16. Failure handling | PARTIAL | Critical | TFIS now has explicit pre-planning guardrails plus post-planning intent-shell controls, later execution-shell arming controls, fillless dispatch-only guardrails, final no-fill handoff guardrails, Phase 1 fill guardrails, and a first lifecycle-time shell for missing lifecycle data, conservative same-bar conflict handling, explicit EOD square-off, and lifecycle abort visibility. | Harden stale-data, manual-kill, and parity-escalation policy during the open-position phase before any broader paper rollout. |
| 17. Replayability | PARTIAL | Medium | TFIS now has persisted paper-session artifacts, deterministic replay-bundle manifests with file hashes and terminal-state checks, operator-facing review summaries over those bundles, an execution-journal intent shell, later execution-shell readiness outcomes, fillless dispatch-only outcomes, final handoff outcomes, Phase 1 fill/no-fill artifacts, Phase 2 same-day lifecycle artifacts, and a deterministic paper-vs-historical comparison runner that now understands planning parity plus execution, dispatch, handoff, fill, and lifecycle outcome status. | Define acceptable lifecycle drift and which lifecycle mismatches should block paper-runtime readiness. |
| 18. Kill-switch / no-trade guardrails | PARTIAL | High | TFIS now has deterministic pre-planning kill-switch controls plus post-planning intent-shell, pre-execution-shell, fillless dispatch-shell, final handoff-shell, Phase 1 fill-shell guardrails, and a first same-day lifecycle shell that can abort or conservatively close based on lifecycle-time data quality. | Refine manual lifecycle kill-switch policy and preserve every later guardrail trigger in operator close-out artifacts. |

## Key Risks

### Critical

- no paper execution simulator yet
- no TFIS-native dashboard/operator visibility
- no fill simulator or lifecycle loop beyond the current final no-fill handoff boundary

### High

- no finalized live-paper data contract
- no live-paper ORPT / RC scheduler contract
- current-day FSL / TRP paper flow not orchestrated
- next-day continuation remains unsupported because workbook rows `190-191`
  are still process-only in inspected ranges

### Medium

- historical cost model exists but is not yet a paper execution fill model
- logging and provenance are strong offline but not yet session-oriented for
  live paper

## Recommended Priority Order

### 1. Freeze S23 paper-mode scope

Define the initial operational scope explicitly:

- S23 only
- NIFTY only
- weekly options only
- paper mode only
- no real money
- no new strategy work
- preferred initial EOD policy:
  - same-day square-off only
  - no next-day continuation until numeric continuation rules are proven

### 2. Finalize the live-paper data contract

Define the required normalized inputs and freshness rules for:

- spot/index intraday bars
- option reference levels
- live option chain
- selected contract quote stream or contract intraday stream
- monthly/weekly reference context

### 3. Build S23 paper-session orchestration

Define one session state machine covering:

- monthly-status selection
- branch selection
- ORPT
- missed-entry recalculation
- current-day FSL / TRP checks
- selected-contract tracking
- expiry/EOD close behavior

### 4. Implement the same-day S23 paper lifecycle loop

The blueprint now exists in
`docs/operations/s23_paper_trading_mvp_v1_design.md`.

Phase 1 of that design is now implemented. The next runtime slice should cover:

- `PAPER_POSITION_OPEN`
- `PAPER_EXIT_PENDING`
- `PAPER_POSITION_CLOSED`
- `PAPER_EOD_SQUARE_OFF`
- `paper_position.json`
- `lifecycle_events.jsonl`
- `paper_pnl_summary.json`

### 5. Extend replay comparison into the lifecycle phase

The current planning, arming, dispatch, handoff, and first fill-status parity
layer now exists. After lifecycle artifacts exist, the next replay task should:

- compare future fill-simulator artifacts after `PAPER_EXECUTION_HANDOFF_READY`
- validate that acceptable historical parity remains visible once the shell
  moves into the first simulated execution phase
- keep refusing to imply broker placement or real fills

### 6. Extend the first-wave failure-handling guardrails into open-position paper phases

The first-wave planning, arming, dispatch, handoff, and Phase 1 fill guardrails
now exist for:

- stale spot or selected-contract data -> no trade
- missing option chain -> no trade
- missing selected contract quote -> no trade
- manual operator abort -> aborted
- global or S23 paper disable -> no trade or aborted
- unsupported continuation -> aborted

The next failure-handling work should cover later paper phases:

- quote-quality or rate-limit degradation during later phases -> safe abort
- active lifecycle data disappearance -> operator-visible halt or safe abort

## Go / No-Go Criteria For Starting S23 Paper Trading

Current state: `NO-GO`

The minimum `GO` criteria for S23 paper trading should be:

1. live-paper normalized data contract is documented and implemented
2. selected option chain and selected-contract quote freshness checks exist
3. paper order simulator exists and is tagged paper-only
4. ORPT, RC, and current-day FSL / TRP timing flow are operationally defined
5. unsupported workbook paths remain blocked explicitly, not guessed
6. same-day square-off or another explicit EOD policy is enforced
7. session logging and replay artifacts exist
8. operator-visible warnings exist for stale/missing/partial data
9. kill-switch and no-trade guardrails exist
10. paper sessions can be compared back to expected historical logic,
    including the current pre-execution arming, dispatch, and handoff shell

If any of these are missing, S23 paper mode should remain `NO-GO`.

## What Must Be True Before Any Real-Money Live Test

No real-money S23 live test should happen until all paper `GO` criteria are
met, plus:

1. repeated clean paper sessions across multiple days
2. replay-confirmed agreement between paper decisions and expected S23 logic,
   including the current pre-execution arming, dispatch, and handoff shell
3. operator dashboard or equivalent session visibility is stable
4. explicit quote-quality and rate-limit handling is validated
5. paper fill model and same-day lifecycle outcomes are understood well enough
   to separate logic defects from market-friction drift
6. any unsupported continuation logic is either proven from workbook evidence or
   explicitly disabled by operating policy

Current live-money disposition: `NO-GO`

## Current Recommendation

The best next implementation direction is not more S23 formula work.

The best next direction is to close the operational gap between:

- strong offline S23 logic
- and a safe, replayable, operator-visible S23 paper session

That means the immediate next build steps should focus on:

1. paper data contract
2. paper session state machine
3. paper execution/journaling
4. failure handling and kill-switches
5. Phase 1 fill simulation and no-fill outcomes
6. same-day lifecycle monitoring and replayability beyond the current final
   no-fill handoff boundary
