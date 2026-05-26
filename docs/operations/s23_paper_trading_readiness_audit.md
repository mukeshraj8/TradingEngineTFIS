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
- several execution-safety and operator-safety layers are missing entirely

High-level split:

- offline S23 research and replay logic: strong
- S23 contract/lifecycle realism on deterministic fixtures: strong
- paper runtime data contracts: partial
- paper execution, operator control, and failure handling: missing to partial

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
| 9. Paper order simulation | MISSING | High | TFIS does not yet have an S23 paper execution loop. | Build S23-only paper execution simulation with explicit paper-only mode tags, order intents, and lifecycle events. |
| 10. Fill/slippage model | PARTIAL | Medium | Historical cost/slippage assumptions exist, but they are not execution-grade and not live-paper fill rules. | Define a paper fill policy using bid/ask or last-traded-price rules and keep it visibly separate from historical cost assumptions. |
| 11. Spread/liquidity/OI validation | PARTIAL | High | Offline option-chain selection already uses OI and spread as ranking signals. Live-paper pre-trade guards are not formalized. | Define hard no-trade gates for spread, zero bid, low OI, missing volume, stale quotes, and untradable books. |
| 12. Expiry-day and holiday handling | PARTIAL | High | Expiry-day review exists in historical reports. Holiday/session-calendar handling for paper runtime is not defined. | Add session calendar rules, expiry-day paper restrictions, holiday skips, and pre-expiry market-open checks. |
| 13. Position-open / EOD handling | PARTIAL | High | Historical EOD policies exist. Workbook rows `190-191` remain process-only and do not give numeric next-day continuation logic. | Choose an explicit paper-mode policy: either same-day square-off only for initial rollout or block next-day continuation until workbook evidence exists. |
| 14. Logging and audit reports | PARTIAL | Medium | Historical reports are strong. Live-paper session logs, decision journals, and operator close-out reports are not yet defined in TFIS. | Define paper-session journal format, decision log schema, and end-of-session audit report. |
| 15. Dashboard / operator visibility | MISSING | High | TFIS has no dedicated operator dashboard. | Provide at least a minimal operator surface for selected branch, selected contract, live-paper status, warnings, fallback state, and active position state. |
| 16. Failure handling | MISSING | Critical | TFIS does not yet define S23 paper-mode handling for stale data, missing option chain, missing selected contract quote, broker/API outage, partial data, or rate limits. | Add explicit no-trade, degrade, or safe-exit rules for each failure mode. |
| 17. Replayability | PARTIAL | High | Historical comparison tooling is strong, but TFIS does not yet define how a paper session is captured and replayed end to end. | Define a paper-session truth journal and a replay path that can compare paper decisions against expected S23 historical logic. |
| 18. Kill-switch / no-trade guardrails | PARTIAL | Critical | Risk policy and rejection logic exist offline, but paper runtime kill-switch and operator no-trade controls are not present. | Add explicit session kill-switch, branch-level disable, quote-quality no-trade gates, and fallback refusal rules. |

## Key Risks

### Critical

- no paper execution simulator yet
- no explicit live-paper failure-handling contract
- no operator kill-switch / no-trade control surface
- no TFIS-native dashboard/operator visibility

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

### 4. Build S23-only paper execution and journaling

Needed outputs:

- paper order intent
- accepted or blocked reason
- active selected contract state
- lifecycle events
- operator warnings
- end-of-session summary

### 5. Add hard failure-handling and no-trade guardrails

Minimum first-wave rules:

- stale spot or option data -> no trade
- missing option chain -> no trade
- missing selected contract quote -> no trade or explicit fallback refusal
- broker/API outage -> no trade
- quote-quality or rate-limit degradation -> no trade
- operator kill-switch -> immediate paper session halt

### 6. Add replayability and operator comparison

Each paper session should be replayable and comparable against:

- expected S23 branch
- expected trade plan
- expected recalculation path
- expected selected contract and lifecycle source

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
10. paper sessions can be compared back to expected historical logic

If any of these are missing, S23 paper mode should remain `NO-GO`.

## What Must Be True Before Any Real-Money Live Test

No real-money S23 live test should happen until all paper `GO` criteria are
met, plus:

1. repeated clean paper sessions across multiple days
2. replay-confirmed agreement between paper decisions and expected S23 logic
3. operator dashboard or equivalent session visibility is stable
4. explicit quote-quality and rate-limit handling is validated
5. paper fill model and realized paper outcomes are understood well enough to
   separate logic defects from market-friction drift
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
5. replayability and comparison back to expected S23 logic
