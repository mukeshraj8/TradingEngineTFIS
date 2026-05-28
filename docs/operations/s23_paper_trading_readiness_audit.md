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
- paper runtime data contracts: partial but now exercised through one normalized ingress-only dry run
- paper execution and operator review surfaces: partial
- paper failure handling and kill-switch controls through the final no-fill handoff boundary: partial

Recent pilot baseline:

- the first deterministic fixture-backed same-day lifecycle parity pilot remains available under
  `D:/TradingEngineTFIS/tmp/s23_paper_pilots/2026-05-27/s23-lifecycle-parity-pilot`
- the first normalized archive-backed same-day lifecycle parity pilot now exists under
  `D:/TradingEngineTFIS/tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot`
- the first multi-session archive-backed suite now exists under
  `D:/TradingEngineTFIS/tmp/s23_paper_pilot_suite/2026-05-27/s23-archive-suite-v2`
- that suite covered bull/bear, call/put, target-hit, stoploss-hit, EOD square-off, no-fill, current-day FSL / TRP, and ORPT recalculation paths
- the suite returned `5 MATCH`, `1 PARTIAL_MATCH`, `0 MISMATCH`, and `0 UNCOMPARABLE`
- the suite recommendation is `LIMITED_GO` for continued archive-backed validation only
- the first normalized live-paper ingress-only dry run now exists under
  `D:/TradingEngineTFIS/tmp/s23_live_paper_dry_runs/2026-05-08/s23-archive-ingress-dry-run`
- that dry run consumed deterministic archive-export JSONL, reached `ORDER_PLANNED`, produced an `INTENT_READY` shell, and returned ingress readiness `PASS`
- the first broadened ingress-only suite now exists under
  `D:/TradingEngineTFIS/tmp/s23_live_paper_dry_runs/2026-05-27/s23-ingress-validation-suite-v1`
- that suite returned `4 PASS`, `1 WARNING`, and `0 NO_GO`, with an aggregate recommendation of `LIMITED_GO`
- a broker-agnostic live-paper ingress foundation now exists under
  `src/tfis/brokers/` and `src/tfis/paper/live_ingress.py`, with FYERS as the
  first market-data adapter and explicit no-order safety
- a strict local FYERS ingress preflight path now also exists via
  `scripts/run_s23_fyers_paper_ingress.py --preflight-only`, and the operator
  procedure is now documented in
  `docs/operations/s23_fyers_ingress_live_runbook.md`
- S23 paper remains `NO-GO` for broad live-paper rollout until multi-date ingress evidence exists and the close-out policy is enforced operationally beyond this first archive-derived suite

## Readiness Checklist

| Area | Current Status | Risk | Current Position | Required Tasks |
| --- | --- | --- | --- | --- |
| 1. S23 configuration completeness | READY | Medium | All four branches exist, workbook-backed logic is traced, registry/governance exists, monthly-status routing exists. | Freeze the paper-trading strategy set to S23 only and keep config promotion controlled. |
| 2. Live/paper input data requirements | PARTIAL | High | Historical CSV contracts are clear, one deterministic normalized archive-export JSONL dry run now exists under `tmp/s23_live_paper_dry_runs/2026-05-08/s23-archive-ingress-dry-run`, one broadened archive-derived ingress suite now exists under `tmp/s23_live_paper_dry_runs/2026-05-27/s23-ingress-validation-suite-v1`, a broker-agnostic live-paper ingress runner now exists for normalized prelude events plus broker market data, and a strict FYERS preflight gate now exists for local operator runs. Live-paper source contracts are still not finalized beyond this first safe normalized source family. | Broaden the ingress suite across multiple dates and source shapes, then decide whether append-style normalized CSV, replayed normalized session feed, or a larger normalized archive export set is the operational default. |
| 3. Option-chain live selection readiness | PARTIAL | High | Offline option-chain selection logic exists with OI, premium, and spread-aware tie-breaking. A first live-paper chain ingestion path now exists through the FYERS market-data adapter, but broader source validation and cadence policy are still pending. | Specify live-paper chain refresh cadence, stale-chain handling, expiry metadata requirements, and selected-contract provenance rules. |
| 4. ORPT timing handling | PARTIAL | High | ORPT behavior is workbook-backed in historical mode. No live-paper scheduler/clock contract is defined yet. | Define exact session clock behavior at `09:24:59`, delayed-start policy, and what happens if inputs arrive late or out of order. |
| 5. Missed-entry recalculation handling | PARTIAL | High | Historical ORPT missed-entry detection and recalculation exist. No live-paper orchestration path exists. | Define how live-paper mode detects missed entry, snapshots ORPT data, schedules RC recalculation, and preserves audit. |
| 6. Current-day FSL / TRP handling | PARTIAL | High | Historical workbook-backed rows `183-188` exist and are tested. No paper-runtime timing flow exists. | Define whether paper mode will support current-day FSL / TRP from day one and how required `09:15`, ORPT, and RC snapshots are captured. |
| 7. `Z183:Z186` entry override behavior | PARTIAL | Medium | Workbook-backed current-day entry overrides are implemented in historical mode. No live-paper application contract exists. | Define when paper mode applies these overrides and how original vs overridden entry is shown to operators. |
| 8. Selected-contract lifecycle tracking | PARTIAL | High | Historical selected-contract lifecycle tracking is strong and provenance-rich. No paper session selected-contract state model exists yet. | Define active selected-contract state, symbol continuity, price-source labels, and lifecycle quote freshness requirements. |
| 9. Paper order simulation | PARTIAL | High | TFIS now has a complete no-fill shell through `PAPER_EXECUTION_HANDOFF_READY`, Phase 1 fill simulation through `PAPER_ORDER_PENDING`, `PAPER_ORDER_FILLED`, `PAPER_ORDER_NOT_FILLED`, and `PAPER_FILL_ABORTED`, a first same-day lifecycle slice through `PAPER_POSITION_OPEN`, `PAPER_POSITION_CLOSED`, `PAPER_EOD_SQUARE_OFF`, and `PAPER_LIFECYCLE_ABORTED`, an explicit paper-vs-historical same-day drift policy with `MATCH`, `MATCH_WITH_ACCEPTABLE_DRIFT`, `PARTIAL_MATCH`, `MISMATCH`, and `UNCOMPARABLE` outcomes, a completed multi-session archive-backed suite that returned `5 MATCH`, `1 PARTIAL_MATCH`, `0 MISMATCH`, and `0 UNCOMPARABLE`, and a broadened ingress-only suite that returned `4 PASS`, `1 WARNING`, and `0 NO_GO` under the new operator close-out policy. | Enforce the close-out policy on broader multi-date ingress suites before allowing any controlled live-like fill or lifecycle rehearsal. |
| 10. Fill/slippage model | PARTIAL | Medium | Historical cost/slippage assumptions exist, and the Phase 1 paper fill simulator now applies a separate conservative selected-contract quote/bar fill policy with explicit spread and freshness gates. Lifecycle-time execution friction is still undefined. | Keep the Phase 1 fill policy stable, then define lifecycle-time exit pricing rules separately from historical cost assumptions. |
| 11. Spread/liquidity/OI validation | PARTIAL | High | Offline option-chain selection already uses OI and spread as ranking signals. Live-paper pre-trade guards are not formalized. | Define hard no-trade gates for spread, zero bid, low OI, missing volume, stale quotes, and untradable books. |
| 12. Expiry-day and holiday handling | PARTIAL | High | Expiry-day review exists in historical reports. Holiday/session-calendar handling for paper runtime is not defined. | Add session calendar rules, expiry-day paper restrictions, holiday skips, and pre-expiry market-open checks. |
| 13. Position-open / EOD handling | PARTIAL | High | Historical EOD policies exist. Workbook rows `190-191` remain process-only and do not give numeric next-day continuation logic. | Choose an explicit paper-mode policy: either same-day square-off only for initial rollout or block next-day continuation until workbook evidence exists. |
| 14. Logging and audit reports | PARTIAL | Medium | Historical reports are strong. TFIS now persists session manifests, audit trails, terminal summaries, replay-bundle manifests, operator review outputs, an execution-journal intent shell, later execution-arm or execution-block summaries, fillless dispatch summaries, final handoff summaries, Phase 1 fill/no-fill artifacts, Phase 2 paper position / exit / P&L artifacts, and lifecycle-aware paper-vs-historical comparison summaries. | Add an end-of-session operator close-out report and define which lifecycle deviations should escalate to paper-runtime NO-GO. |
| 15. Dashboard / operator visibility | PARTIAL | Medium | TFIS now has operator-facing JSON and Markdown review summaries over persisted paper-session artifacts, replay bundles, execution-journal intent shells, execution-shell readiness outcomes, fillless dispatch-only outcomes, final handoff outcomes, Phase 1 fill/no-fill outcomes, and Phase 2 same-day lifecycle / P&L outcomes. | Add an operator-facing close-out surface and explicit lifecycle warning severity model. |
| 16. Failure handling | PARTIAL | Critical | TFIS now has explicit pre-planning guardrails plus post-planning intent-shell controls, later execution-shell arming controls, fillless dispatch-only guardrails, final no-fill handoff guardrails, Phase 1 fill guardrails, a first lifecycle-time shell for missing lifecycle data, conservative same-bar conflict handling, explicit EOD square-off, lifecycle abort visibility, and a no-connect FYERS preflight that fails closed on missing credentials or unsafe scope. | Harden stale-data, manual-kill, and parity-escalation policy during the open-position phase before any broader paper rollout. |
| 17. Replayability | PARTIAL | Medium | TFIS now has persisted paper-session artifacts, deterministic replay-bundle manifests with file hashes and terminal-state checks, operator-facing review summaries over those bundles, an execution-journal intent shell, later execution-shell readiness outcomes, fillless dispatch-only outcomes, final handoff outcomes, Phase 1 fill/no-fill artifacts, Phase 2 same-day lifecycle artifacts, and a deterministic paper-vs-historical comparison runner that now understands planning parity plus execution, dispatch, handoff, fill, and lifecycle outcome status. | Define acceptable lifecycle drift and which lifecycle mismatches should block paper-runtime readiness. |
| 18. Kill-switch / no-trade guardrails | PARTIAL | High | TFIS now has deterministic pre-planning kill-switch controls plus post-planning intent-shell, pre-execution-shell, fillless dispatch-shell, final handoff-shell, Phase 1 fill-shell guardrails, and a first same-day lifecycle shell that can abort or conservatively close based on lifecycle-time data quality. | Refine manual lifecycle kill-switch policy and preserve every later guardrail trigger in operator close-out artifacts. |

## Key Risks

### Critical

- the ingress close-out policy now exists, but it has only been exercised against one archive-derived suite date and one normalized source family
- the current multi-session lifecycle suite still relies on normalized expectation artifacts and includes one manual-review no-fill case
- no broader multi-date operator close-out evidence exists yet

### High

- no finalized live-paper data contract
- no live-paper ORPT / RC scheduler contract
- current-day FSL / TRP paper flow is orchestrated in deterministic dry-run form, but not yet exercised over a broader live-paper ingress set
- next-day continuation remains unsupported because workbook rows `190-191`
  are still process-only in inspected ranges

### Medium

- historical cost model exists but is not yet a paper execution fill model
- logging and provenance are strong offline but not yet session-oriented for
  live paper

## Recommended Priority Order

### 1. Freeze S23 paper-mode scope

Keep the initial operational scope explicit:

- S23 only
- NIFTY only
- weekly options only
- paper mode only
- no real money
- same-day only
- no next-day continuation until workbook evidence changes

### 2. Operationalize the ingress close-out policy across more than one suite date

Keep the close-out policy in
`docs/operations/s23_operator_closeout_policy.md` as the governing rule set, then
apply it to a broader set of normalized ingress sessions.

### 3. Use the new preflight runbook for the first real local FYERS ingress-only session

Before any broader live-like rehearsal, use
`docs/operations/s23_fyers_ingress_live_runbook.md` and
`scripts/run_s23_fyers_paper_ingress.py --preflight-only` to verify:

- credentials are present
- paper-only scope is enforced
- kill-switch posture is safe
- required prelude events are complete
- selected-contract configuration is ready

### 4. Broaden the first live-paper data-ingress-only dry run

Exercise:

- normalized live-paper inputs
- stale-data handling
- operator review
- session close-out

across more than one normalized session source shape, still without broker
connectivity, real orders, or live-money flow.

### 5. Add an operator close-out surface

The persisted paper artifacts and replay bundles are strong enough now that the
next operational surface should summarize:

- session quality
- parity result
- drift details
- blocker codes
- operator action required

### 6. Keep same-day lifecycle scope fixed while broadening evidence

Do not add next-day continuation or extra strategy behavior yet. Broaden:

- archive-backed pilot-day count
- real selected-contract coverage
- live-paper ingress confidence

before broadening lifecycle behavior.

## Go / No-Go Criteria For Starting S23 Paper Trading

Current state: `NO-GO`

The minimum `GO` criteria for S23 paper trading should be:

1. live-paper normalized data contract is documented and implemented
2. selected option chain and selected-contract quote freshness checks exist
3. same-day-only paper fill and lifecycle loop exists and remains bounded
4. ORPT, RC, and current-day FSL / TRP timing flow are operationally defined
5. unsupported workbook paths remain blocked explicitly, not guessed
6. same-day square-off policy is enforced
7. session logging, replay bundles, review artifacts, and parity comparison exist
8. operator-visible warnings exist for stale or missing or partial data
9. kill-switch and no-trade guardrails exist through fill and lifecycle phases
10. a multi-session archive-backed suite meets the pilot-day thresholds with no blocker mismatches
11. repeated live-paper ingress-only dry runs succeed without broker connectivity or real order flow

If any of these are missing, S23 paper mode should remain `NO-GO`.

## What Must Be True Before Any Real-Money Live Test

No real-money S23 live test should happen until all paper `GO` criteria are
met, plus:

1. repeated clean archive-backed pilot days across multiple sessions
2. enforced pilot-day thresholds with documented operator close-out decisions
3. replay-confirmed agreement between paper decisions and expected S23 logic,
   including fill and same-day lifecycle outcomes
4. operator dashboard or equivalent close-out visibility is stable
5. repeated live-paper ingress-only dry runs succeed cleanly on normalized inputs
6. quote-quality and stale-data handling are validated operationally
7. unsupported continuation logic remains explicitly disabled

Current live-money disposition: `NO-GO`

## Current Recommendation

The best next implementation direction is still not more S23 formula work.

The best next direction is to keep the new operator close-out policy fixed,
keep the new broker-backed ingress foundation market-data-only, and broaden the
normalized live-paper ingress-only evidence across more than one archive-derived
suite date.

That means the immediate next build steps should focus on:

1. multi-date ingress-only dry-run evidence and source-shape coverage
2. operator-facing close-out enforcement using the new policy
3. the first tightly controlled live-like fill and same-day lifecycle rehearsal only after ingress thresholds stay green
4. broader archive-backed pilot-day coverage
5. stronger raw-capture normalization adapters only if the pilot evidence needs them
