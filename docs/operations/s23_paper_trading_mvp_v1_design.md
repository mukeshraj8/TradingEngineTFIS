# S23 Paper Trading MVP v1 Fill Simulator And Lifecycle Loop

## Purpose

This document defines the first actual S23 paper-trading execution model after
the completed no-fill shell.

It starts from the current boundary:

- `PAPER_EXECUTION_HANDOFF_READY`

It does not authorize live trading, broker connectivity, or real-money flow.

## Implementation Status

Current status:

- Phase 1 is now implemented:
  - `PAPER_ORDER_PENDING`
  - `PAPER_ORDER_FILLED`
  - `PAPER_ORDER_NOT_FILLED`
  - `PAPER_FILL_ABORTED`
  - `paper_order_pending.json`
  - `paper_fill.json`
  - `paper_no_fill.json`
  - `paper_fill_abort_summary.json`
- Phase 2 same-day lifecycle is now implemented:
  - `PAPER_POSITION_OPEN`
  - `PAPER_EXIT_PENDING`
  - `PAPER_POSITION_CLOSED`
  - `PAPER_EOD_SQUARE_OFF`
  - `PAPER_LIFECYCLE_ABORTED`
  - `paper_position.json`
  - `lifecycle_events.jsonl`
  - `paper_exit.json`
  - `paper_pnl_summary.json`
- still no broker connectivity
- still no multi-session carry-forward runtime
- still no multi-position runtime

The next implementation phase should convert the completed archive-backed pilot
suite into explicit operator close-out thresholds, manual-review policy, and a
first live-paper data-ingress-only dry run before broadening paper-runtime
scope again.

That lifecycle parity and same-day drift policy is now implemented in the
paper-vs-historical comparator:

- exact contract and planning fields remain blocker-level comparisons
- explicit lifecycle reason or outcome mismatches are blockers when both sides
  expose them
- bounded same-day drift is now allowed for:
  - paper fill price versus historical entry price
  - exit price
  - exit timestamp
  - net P&L
- comparator outcomes now distinguish:
  - `MATCH`
  - `MATCH_WITH_ACCEPTABLE_DRIFT`
  - `PARTIAL_MATCH`
  - `MISMATCH`
  - `UNCOMPARABLE`

A first deterministic fixture-backed pilot remains available under
`D:/TradingEngineTFIS/tmp/s23_paper_pilots/2026-05-27/s23-lifecycle-parity-pilot` and returned `MATCH` on the selected-contract
target-hit path. The first normalized archive-backed pilot now also exists under
`D:/TradingEngineTFIS/tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot`; it used direct selected-contract archive ticks for `NIFTY_20260512_25000_PE`, reached a filled same-day target-hit close, and returned `MATCH` with no drift outside policy. A first multi-session archive-backed suite now also exists under `D:/TradingEngineTFIS/tmp/s23_paper_pilot_suite/2026-05-27/s23-archive-suite-v2`; it covered bull/bear, call/put, target-hit, stoploss-hit, EOD square-off, no-fill, current-day FSL / TRP, and ORPT recalculation paths and returned `5 MATCH`, `1 PARTIAL_MATCH`, `0 MISMATCH`, and `0 UNCOMPARABLE`. The next paper-runtime step should turn those suite results into explicit operator close-out thresholds and a live-paper data-ingress-only dry run rather than broadening the fill or lifecycle model first.

## Scope

The first supported runtime remains tightly constrained:

- `S23` only
- `NIFTY` only
- weekly options only
- paper mode only
- one planned order per session max
- current paper runtime uses same-day square-off only
- multi-session carry-forward remains a runtime gap
- no broker API
- no real order placement
- no real-money flow

## Non-Goals

This MVP v1 design does not include:

- broker adapters
- exchange acknowledgements
- real order placement
- partial fills
- multi-order scaling
- implementation of multi-session carry-forward
- position averaging
- multiple strategy sessions in one loop

## Starting Boundary

This design assumes the following already exist and are valid:

- paper-session artifacts
- replay bundle
- operator review summary
- paper-vs-historical comparison
- order intent
- `EXECUTION_ARMED`
- `ORDER_INTENT_DISPATCHED`
- `PAPER_EXECUTION_HANDOFF_READY`

The MVP v1 fill simulator should begin only after those controls pass.

## Operating Policy

### First-Rollout Rules

- side is always `SELL`
- only one simulated entry attempt per session
- only one open position at a time
- no generic strategy fallback once contract selection is frozen
- the current runtime must not continue positions into the next session until
  multi-session carry-forward is implemented
- if data quality is not good enough for a safe same-day simulation, end the
  session as `NO_FILL`, `BLOCKED`, or `ABORTED` rather than inventing a result

### Price-Source Policy

The first rollout should prefer selected-contract data only.

Recommended order of use:

1. selected-contract quote snapshot with bid/ask and timestamp
2. selected-contract OHLC bar covering the evaluation timestamp

The MVP v1 should not silently fall back to:

- generic option-series lifecycle bars
- chain midpoint estimates
- reconstructed prices from unrelated contracts

If the selected-contract source is missing or stale at a required decision
point, the simulator should block or abort instead of manufacturing a fill.

## Fill Simulation Policy

### When Intent Becomes A Simulated Paper Order

The first fill-simulator phase should begin when all of these are true:

- session state is `PAPER_EXECUTION_HANDOFF_READY`
- selected contract is still fresh
- order intent artifact is valid
- replay bundle is valid
- paper-vs-historical comparison remains acceptable
- same-day-only policy is still confirmed
- current wall-clock or replay clock is still inside the same session day

At that moment the session should move to:

- `PAPER_ORDER_PENDING`

### Entry Price Source

Recommended conservative rule for S23 option sells:

- if a fresh selected-contract quote exists:
  - use the bid as the candidate sell fill price
- if only a fresh selected-contract OHLC bar exists:
  - use a conservative bar-based fill rule, such as requiring the planned entry
    price to be reachable inside the bar and then filling at the worse of:
    planned entry price or bar low-touch-derived executable sell price

The implementation must make the chosen policy explicit in artifacts.

### Slippage Policy

The MVP v1 should keep slippage simple and explicit:

- separate execution slippage from historical cost assumptions
- define a configurable absolute or percentage slippage add-on for sell-entry
  execution
- record whether slippage was applied
- never hide slippage inside the raw fill price

### Spread And Quote Quality Gates

Before fill simulation, reject the fill if any configured rule fails:

- quote is stale beyond threshold
- ask or bid missing
- bid is zero
- spread exceeds absolute limit
- spread exceeds percentage limit
- OI/liquidity placeholder gates fail

If these fail before fill:

- transition to `PAPER_ORDER_NOT_FILLED` or `PAPER_EXECUTION_ABORTED`
- do not open a simulated position

### Missed-Fill Handling

If no acceptable fill is available during the allowed entry window:

- mark session `PAPER_ORDER_NOT_FILLED`
- record explicit reason:
  - stale selected contract quote
  - spread too wide
  - planned entry not reachable
  - lifecycle source missing

This is a valid terminal outcome and must not be treated as an error.

## Paper Position Model

Once a fill is accepted, create one immutable paper position record with:

- strategy
- session id
- session date
- symbol
- selected contract symbol
- option type
- side
- lots
- quantity
- planned entry price
- simulated fill price
- target price
- stoploss price
- FSL price if distinct
- entry timestamp
- source workbook row
- source rule / branch
- monthly status
- recalculation flags
- current-day overlay flags
- cost/slippage settings
- provenance for quote or bar source

The position becomes active only after:

- `PAPER_ORDER_FILLED`
- then `PAPER_POSITION_OPEN`

## Lifecycle Monitoring Policy

### Supported Exit Conditions

The first lifecycle loop should support only:

- target hit
- stoploss hit
- FSL hit where distinct
- manual kill-switch forced close
- EOD forced square-off

### Unsupported Conditions

The first lifecycle loop must reject:

- multi-session carry-forward in the current same-day runtime
- partial exits
- multi-leg recovery logic
- automatic rollover behavior that is not explicitly strategy-implemented

### Monitoring Source

Use only the selected-contract lifecycle source:

- selected-contract quotes if available
- otherwise selected-contract OHLC bars

The source used for each lifecycle decision must be recorded.

### EOD Policy

First rollout should enforce:

- same-day square-off only in the current runtime

If a paper position remains open near cutoff:

- move to `PAPER_EXIT_PENDING`
- attempt `PAPER_EOD_SQUARE_OFF`
- if no acceptable selected-contract price exists at the cutoff window:
  - transition to `PAPER_EXECUTION_ABORTED`
  - record operator action required

### Stale Data During Open Position

If lifecycle data becomes stale while position is open:

- do not fabricate an exit
- transition to `PAPER_EXECUTION_ABORTED`
- record the last good quote timestamp
- mark the session as replayable but operationally unsafe

## Execution States

Recommended first execution-phase states:

- `PAPER_ORDER_PENDING`
- `PAPER_ORDER_FILLED`
- `PAPER_ORDER_NOT_FILLED`
- `PAPER_POSITION_OPEN`
- `PAPER_EXIT_PENDING`
- `PAPER_POSITION_CLOSED`
- `PAPER_EOD_SQUARE_OFF`
- `PAPER_EXECUTION_ABORTED`

Suggested meanings:

- `PAPER_ORDER_PENDING`
  - handoff-ready intent is waiting for a valid simulated fill
- `PAPER_ORDER_FILLED`
  - one simulated entry is accepted
- `PAPER_ORDER_NOT_FILLED`
  - entry window closed without a valid fill
- `PAPER_POSITION_OPEN`
  - simulated position is active and must be lifecycle-monitored
- `PAPER_EXIT_PENDING`
  - one or more valid exit conditions are under evaluation
- `PAPER_POSITION_CLOSED`
  - simulated exit completed with explicit reason and source
- `PAPER_EOD_SQUARE_OFF`
  - forced same-day close path
- `PAPER_EXECUTION_ABORTED`
  - execution or lifecycle integrity failed

## Artifact Plan

The MVP v1 should add these persistent artifacts:

- `paper_fill.json`
- `paper_position.json`
- `lifecycle_events.jsonl`
- `paper_pnl_summary.json`

### `paper_fill.json`

Should include:

- planned entry price
- simulated fill price
- fill timestamp
- quote or bar source
- spread at fill if known
- slippage applied
- fill rule version
- explicit disclaimer:
  - paper-only simulated fill

### `paper_position.json`

Should include:

- immutable position fields
- target
- stoploss
- FSL if distinct
- open timestamp
- workbook/source provenance

### `lifecycle_events.jsonl`

Should append deterministic events such as:

- `PAPER_ORDER_PENDING`
- `PAPER_ORDER_FILLED`
- `PAPER_POSITION_OPEN`
- `TARGET_HIT`
- `STOPLOSS_HIT`
- `FSL_HIT`
- `EOD_SQUARE_OFF_TRIGGERED`
- `PAPER_POSITION_CLOSED`
- `PAPER_EXECUTION_ABORTED`

### `paper_pnl_summary.json`

Should include:

- session id
- selected contract
- entry price
- exit price
- gross paper P&L
- paper costs/slippage assumptions
- net paper P&L
- exit reason
- data-source provenance

## Guardrails

### Entry Guardrails

- selected contract quote freshness
- selected contract bar freshness
- spread threshold
- zero-bid rejection
- missing bid/ask rejection
- lifecycle-source presence
- duplicate fill prevention
- duplicate order-pending prevention

### Open-Position Guardrails

- duplicate open-position prevention
- duplicate exit prevention
- missing lifecycle bars
- current-runtime continuation hard block
- manual kill-switch during open position
- EOD forced square-off requirement

### Session Integrity Guardrails

- replay bundle hash mismatch
- order intent mismatch
- selected contract mismatch
- workbook/source rule mismatch
- comparison mismatch between paper plan and historical expectation

## Replay And Historical Comparison Policy

Once fill simulator and lifecycle artifacts exist, compare:

- selected contract
- source workbook row
- source rule / branch
- entry timestamp
- fill price
- target
- stoploss / FSL
- exit reason
- exit timestamp
- exit price
- net paper P&L
- source provenance

### Acceptable Differences

May be acceptable if explicitly explained:

- small numeric drift from conservative quote-based fill vs historical bar-based
  replay
- one-bar timestamp drift when both use the same contract and same threshold
- `PAPER_ORDER_NOT_FILLED` caused by stricter live-paper quote-quality gates

### Blockers

Must be treated as blocker-level mismatches:

- different selected contract
- different workbook row or source rule
- different target or stoploss policy
- simulated continuation beyond same-day cutoff
- synthetic fill created without selected-contract source support
- exit produced after stale-data abort conditions should have blocked the session

## Risk List

### High Risk

- bar-only fallback may overstate fillability if not conservative enough
- stale or sparse selected-contract quotes may produce false no-fill outcomes
- EOD square-off can become ambiguous if cutoff quotes are missing

### Medium Risk

- paper P&L may drift modestly from historical replay because quote-driven
  execution is intentionally stricter than bar-summary replay
- operator interpretation can blur no-fill vs aborted without strong summaries

### Control Principle

When realism and certainty conflict, prefer:

- explicit no-fill
- explicit abort
- explicit operator action required

over silently optimistic simulation.

## Phased Implementation Plan

### Phase 1: Fill Simulator Entry Shell

Implement:

- `PAPER_ORDER_PENDING`
- `PAPER_ORDER_FILLED`
- `PAPER_ORDER_NOT_FILLED`
- `paper_fill.json`
- quote/bar source labeling
- fill guardrails

Do not yet add full lifecycle loop.

Implementation status:

- complete

### Phase 2: Same-Day Lifecycle Loop

Implement:

- `PAPER_POSITION_OPEN`
- `PAPER_EXIT_PENDING`
- `PAPER_POSITION_CLOSED`
- `PAPER_EOD_SQUARE_OFF`
- `paper_position.json`
- `lifecycle_events.jsonl`
- `paper_pnl_summary.json`

Implementation status:

- complete

### Phase 3: Replay Parity Extension

Extend paper-vs-historical comparison to include:

- simulated fill result
- lifecycle path
- exit reason
- realized paper P&L

### Phase 4: Operator Close-Out Surface

Add final session review with:

- fill status
- lifecycle path
- exit reason
- paper P&L
- blocker summary
- strong disclaimer:
  - paper-only simulated execution

## Recommended First Implementation Slice

The safest first implementation slice is:

1. `PAPER_ORDER_PENDING`
2. `PAPER_ORDER_FILLED` or `PAPER_ORDER_NOT_FILLED`
3. `paper_fill.json`
4. fill guardrails
5. review and replay updates for no-fill vs filled outcome

This keeps the first execution model narrow, deterministic, and auditable
before adding an open-position lifecycle loop.

Current status:

- completed
