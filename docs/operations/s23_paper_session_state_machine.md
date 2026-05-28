# S23 Paper Session State Machine

## Purpose

This document defines the S23-only paper-session state machine.

It is the orchestration blueprint that sits on top of the normalized live-paper
data contract. It does not authorize live trading, and it does not replace the
existing workbook-backed strategy logic.

## Scope

The first supported paper-session scope should remain:

- `S23` only
- `NIFTY` only
- weekly options only
- paper mode only
- current paper runtime uses same-day square-off only
- multi-session carry-forward is not yet implemented in this runtime

If the session encounters a condition outside that scope, it should transition
to `NO_TRADE` or `ABORTED`.

## Current Scaffold Status

The first runtime scaffold is now implemented under `src/tfis/paper/`:

- normalized event schemas and validation live in `models.py` and `validation.py`
- `orchestrator.py` now implements deterministic transitions through:
  - `PRE_MARKET_READY`
  - `WAITING_FOR_0915`
  - `WAITING_FOR_ORPT`
  - `WAITING_FOR_RC`
  - `DECISION_READY`
  - `ORDER_PLANNED`
  - `NO_TRADE`
  - `ABORTED`
- the current orchestrator also maintains an in-memory audit trail and session
  manifest updates
- `guardrails.py` now adds deterministic pre-planning kill-switch and failure-handling
  decisions for global disable, S23 disable, manual aborts, stale data, missing
  option-chain or selected-contract inputs, and one-planned-order-per-session
  enforcement
- `artifacts.py` now persists deterministic terminal planning artifacts for
  `ORDER_PLANNED`, `NO_TRADE`, and `ABORTED` sessions, including guardrail codes,
  messages, blocking sources, and operator-action hints in the terminal summaries
- `replay_bundle.py` now seals those persisted session folders into deterministic
  replay-bundle manifests with stable hashes, terminal-state checks, and replay
  readback summaries
- `review.py` and `scripts/review_paper_session.py` now turn those artifacts and
  replay bundles into deterministic JSON and Markdown operator review summaries
- `execution_journal.py` now turns an `ORDER_PLANNED` paper session into an
  intent-only handoff shell with `paper_order_intent.json`,
  `execution_journal.jsonl`, and `execution_summary.json`, while `NO_TRADE` and
  `ABORTED` sessions emit explicit skipped-intent summaries
- the same shell now applies post-planning intent statuses
  (`INTENT_READY`, `INTENT_BLOCKED`, `INTENT_ABORTED`, `INTENT_SKIPPED`) before
  any future execution or fill loop exists
- the execution-journal shell now also supports a later pre-execution arming
  layer with deterministic `EXECUTION_ARMED`, `EXECUTION_BLOCKED`,
  `EXECUTION_ABORTED`, and `EXECUTION_SKIPPED` outcomes based on replay-bundle
  validity, acceptable paper-vs-historical comparison status, selected-contract
  freshness, operator review completion, and same-day-only policy confirmation
- the same shell now extends one step further into a fillless dispatch-only
  layer with deterministic `ORDER_INTENT_DISPATCH_READY`,
  `ORDER_INTENT_DISPATCHED`, `ORDER_INTENT_DISPATCH_BLOCKED`,
  `ORDER_INTENT_CANCELLED`, and `ORDER_INTENT_DISPATCH_SKIPPED` outcomes,
  which mark the intent as handed off to a future execution loop without
  placing any order or simulating any fill
- `paper_vs_historical.py` and `scripts/compare_paper_to_historical.py` now
  compare persisted `INTENT_READY` paper sessions against expected historical
  S23 trade-plan output, returning deterministic `MATCH`, `PARTIAL_MATCH`,
  `MISMATCH`, or `UNCOMPARABLE` results with field-level mismatch reporting
- the same comparison layer now also understands later execution-shell
  readiness artifacts (`EXECUTION_ARMED`, `EXECUTION_BLOCKED`,
  `EXECUTION_ABORTED`, `EXECUTION_SKIPPED`) and separates planning parity from
  later pre-execution safety outcomes
- the same comparison layer now also understands the new fillless dispatch-only
  shell and separates planning parity, later arming outcome, and later
  dispatch readiness before any future execution handoff exists
- the fillless shell now also includes a final handoff-only layer with
  deterministic `PAPER_EXECUTION_HANDOFF_READY`,
  `PAPER_EXECUTION_HANDOFF_BLOCKED`, `PAPER_EXECUTION_HANDOFF_ABORTED`, and
  `PAPER_EXECUTION_HANDOFF_SKIPPED` outcomes, which mark whether a dispatched
  intent is eligible for a future fill simulator without placing any order,
  simulating any fill, or opening any position
- that means the current fillless shell can now prove both plan parity and the
  later arming plus dispatch plus handoff outcome before any future fill
  simulator exists
- `docs/operations/s23_paper_trading_mvp_v1_design.md` now defines the first
  actual fill-simulator and same-day lifecycle-loop plan that should begin only
  after `PAPER_EXECUTION_HANDOFF_READY`
- `fill_simulator.py` now implements Phase 1 of that design through:
  - `PAPER_ORDER_PENDING`
  - `PAPER_ORDER_FILLED`
  - `PAPER_ORDER_NOT_FILLED`
  - `PAPER_FILL_ABORTED`
  - without broker connectivity, real order placement, or live position state
- `ingress_dry_run.py` now consumes deterministic normalized archive-export JSONL,
  drives the orchestrator only through `ORDER_PLANNED`, `NO_TRADE`, or
  `ABORTED`, builds the intent shell, and persists review plus ingress-health
  summaries without starting any fill or lifecycle execution
- `src/tfis/brokers/base.py`, `src/tfis/brokers/fyers.py`, and
  `src/tfis/paper/live_ingress.py` now add the first broker-backed ingress path,
  where broker market data is normalized before it reaches the paper engine and
  the runtime still stops at planning by default
- `lifecycle.py` now implements the first same-day lifecycle slice through:
  - `PAPER_POSITION_OPEN`
  - `PAPER_EXIT_PENDING`
  - `PAPER_POSITION_CLOSED`
  - `PAPER_EOD_SQUARE_OFF`
- `paper_vs_historical.py` now also treats that Phase 2 same-day lifecycle as
  a first-class parity surface, with explicit same-day-only drift rules for
  fill price, exit price, exit timestamp, and net P&L plus blocker handling
  for selected-contract or explicit exit-reason divergence when both sides
  expose those fields
  - `PAPER_LIFECYCLE_ABORTED`
  - `paper_position.json`
  - `lifecycle_events.jsonl`
  - `paper_exit.json`
  - `paper_pnl_summary.json`
  - while still lacking multi-session carry-forward and multi-position handling

States beyond `ORDER_PLANNED` remain blueprint-only for actual execution,
fills beyond the current same-day paper slice, and broker connectivity. The
current scaffold now includes pre-execution arming controls, fill or no-fill
simulation, and a first same-day paper lifecycle loop, but still no live
broker integration, no multi-session carry-forward runtime, and no
multi-position runtime.

## Session Phases

The paper session should move through these high-level phases:

1. pre-market readiness
2. `09:15` snapshot readiness
3. ORPT readiness at `09:24:59`
4. RC readiness at `09:29:59` when needed
5. decision planning
6. paper order pending or filled, then paper position open
7. lifecycle monitoring
8. exit or EOD square-off
9. session close and artifact finalization
10. replay-bundle sealing and readback validation
11. planning-state paper-vs-historical parity verification
12. later-phase execution-shell arming before any future execution handoff
13. fillless dispatch-only handoff after arming
14. final no-fill execution handoff readiness before any future fill simulator
15. Phase 1 fill or no-fill simulation
16. Phase 2 same-day lifecycle loop and paper-only exit or P&L artifacts
17. lifecycle-aware paper-vs-historical parity verification

## States

### `NOT_STARTED`

| Category | Definition |
| --- | --- |
| Required inputs | none |
| Transition trigger | session creation request for a valid S23 paper session |
| Validation checks | strategy code must be S23, paper mode must be explicit |
| Audit event emitted | `SESSION_CREATED` |
| Failure / no-trade condition | unsupported strategy, invalid config, missing operator identity |

### `PRE_MARKET_READY`

| Category | Definition |
| --- | --- |
| Required inputs | `CALENDAR_CONTEXT`, `PAPER_SESSION_CONFIG`, `COST_SLIPPAGE_SETTINGS`, `MONTHLY_STATUS_INPUT` when available |
| Transition trigger | all mandatory pre-open controls loaded |
| Validation checks | not a holiday, same-day square-off policy explicit, kill-switch state known |
| Audit event emitted | `PRE_MARKET_READY` |
| Failure / no-trade condition | holiday -> `NO_TRADE`; kill-switch engaged, paper mode disabled, requested multi-session continuation in the current same-day runtime, or malformed config -> `ABORTED` |

### `WAITING_FOR_0915`

| Category | Definition |
| --- | --- |
| Required inputs | readiness inputs plus `UNDERLYING_SNAPSHOT` for `0915` |
| Transition trigger | complete `09:15` snapshot received |
| Validation checks | snapshot complete, timezone valid, no duplicate conflicting snapshot |
| Audit event emitted | `WAITING_FOR_0915` then `SNAPSHOT_0915_READY` |
| Failure / no-trade condition | required `09:15` snapshot missing or stale for an enabled current-day FSL / TRP session |

### `WAITING_FOR_ORPT`

| Category | Definition |
| --- | --- |
| Required inputs | complete `0915` snapshot, option chain candidate source, underlying ORPT snapshot readiness |
| Transition trigger | complete ORPT snapshot at `09:24:59` is available |
| Validation checks | monthly status must be known, branch path must be supported, option-chain source available |
| Audit event emitted | `WAITING_FOR_ORPT` then `ORPT_READY` |
| Failure / no-trade condition | monthly status `UNKNOWN`, unsupported workbook path, missing ORPT snapshot |

### `WAITING_FOR_RC`

| Category | Definition |
| --- | --- |
| Required inputs | ORPT decision context plus complete RC snapshot |
| Transition trigger | RC snapshot at `09:29:59` is available when missed-entry or current-day FSL / TRP logic requires recalculation |
| Validation checks | only enter this state when recalculation or current-day FSL / TRP is enabled and needed |
| Audit event emitted | `WAITING_FOR_RC` then `RC_READY` |
| Failure / no-trade condition | required RC snapshot missing, stale, or incomplete |

### `DECISION_READY`

| Category | Definition |
| --- | --- |
| Required inputs | monthly status, supported branch, relevant snapshots, option chain snapshot, selected contract quote, calendar context |
| Transition trigger | all data needed to produce one deterministic S23 paper decision is present |
| Validation checks | quote freshness, OI and spread guards, selected contract present, no source mismatch |
| Audit event emitted | `DECISION_READY` |
| Failure / no-trade condition | stale quote or missing selected contract -> `NO_TRADE`; requested multi-session continuation in the current same-day runtime and integrity failures -> `ABORTED` |

### `ORDER_PLANNED`

| Category | Definition |
| --- | --- |
| Required inputs | finalized trade plan, selected contract, cost model, paper execution policy |
| Transition trigger | TFIS creates a paper order intent |
| Validation checks | original vs overridden entry recorded, selected contract symbol frozen for the decision |
| Audit event emitted | `PAPER_ORDER_PLANNED` |
| Failure / no-trade condition | plan incomplete, selected contract quote stale, operator kill-switch toggled before open |

### `PAPER_ORDER_PENDING`

| Category | Definition |
| --- | --- |
| Required inputs | paper order intent, selected contract quote or first executable bar |
| Transition trigger | handoff-ready paper intent enters the first fill simulator and waits for a valid paper fill |
| Validation checks | fill model policy explicit, no duplicate pending event, quote still tradable |
| Audit event emitted | `PAPER_ORDER_PENDING` |
| Failure / no-trade condition | data disappears before simulated fill, quote fails spread or liquidity gates, or entry window expires without acceptable fill |

### `PAPER_ORDER_FILLED`

| Category | Definition |
| --- | --- |
| Required inputs | valid selected-contract quote or selected-contract bar satisfying the paper fill policy |
| Transition trigger | one deterministic paper fill is accepted |
| Validation checks | one fill only, fill source explicit, slippage treatment explicit |
| Audit event emitted | `PAPER_ORDER_FILLED` |
| Failure / no-trade condition | conflicting quote sources or duplicate fill attempt |

### `PAPER_ORDER_NOT_FILLED`

| Category | Definition |
| --- | --- |
| Required inputs | enough context to explain why entry was not simulated |
| Transition trigger | entry window closes without an acceptable simulated fill |
| Validation checks | no-fill reason explicit, not generic |
| Audit event emitted | `PAPER_ORDER_NOT_FILLED` |
| Failure / no-trade condition | not applicable; this is a valid terminal no-fill outcome unless later artifact integrity breaks |

### `PAPER_POSITION_OPEN`

| Category | Definition |
| --- | --- |
| Required inputs | filled paper order, selected contract lifecycle source, active target / stoploss / FSL fields |
| Transition trigger | `PAPER_ORDER_FILLED` is accepted and active position begins |
| Validation checks | selected contract lifecycle source must be explicit, and the current runtime must still enforce its same-day-only lifecycle limit |
| Audit event emitted | `PAPER_POSITION_OPENED` |
| Failure / no-trade condition | invalid lifecycle source, missing bar stream, malformed active position state |

### `PAPER_EXIT_PENDING`

| Category | Definition |
| --- | --- |
| Required inputs | active contract lifecycle bars or quotes, exit thresholds, EOD calendar context |
| Transition trigger | target, stoploss, FSL, expiry restriction, or EOD condition approaches |
| Validation checks | events monotonic, no duplicate closes, EOD policy known |
| Audit event emitted | `PAPER_EXIT_PENDING` |
| Failure / no-trade condition | lifecycle data stalls, selected contract source becomes ambiguous, kill-switch forces exit handling |

### `PAPER_POSITION_CLOSED`

| Category | Definition |
| --- | --- |
| Required inputs | exit event, exit price source, final realized paper P&L |
| Transition trigger | simulated target, stoploss, FSL, or other supported exit closes the position |
| Validation checks | one close per open position, close reason supported, lifecycle source preserved |
| Audit event emitted | `PAPER_POSITION_CLOSED` |
| Failure / no-trade condition | conflicting exit signals, missing exit price source, duplicate closure |

### `EOD_SQUARE_OFF`

| Category | Definition |
| --- | --- |
| Required inputs | open paper position near market close, explicit current-runtime same-day square-off policy |
| Transition trigger | session reaches EOD cutoff with an open paper position |
| Validation checks | current runtime must square off rather than continue into the next session |
| Audit event emitted | `EOD_SQUARE_OFF_TRIGGERED` |
| Failure / no-trade condition | missing EOD quote or bar, or requested multi-session carry-forward in the current runtime |

### `SESSION_COMPLETE`

| Category | Definition |
| --- | --- |
| Required inputs | final session manifest, decision log, paper order journal, lifecycle event log, P&L summary |
| Transition trigger | position closed or valid no-trade outcome fully recorded |
| Validation checks | all terminal artifacts written, replay references preserved |
| Audit event emitted | `SESSION_COMPLETE` |
| Failure / no-trade condition | terminal artifact write failure or incomplete session journal |

### `NO_TRADE`

| Category | Definition |
| --- | --- |
| Required inputs | enough context to explain why TFIS refused to trade |
| Transition trigger | any deterministic guardrail rejects the session before paper position open |
| Validation checks | no-trade reason must be explicit, not generic |
| Audit event emitted | `NO_TRADE` |
| Failure / no-trade condition | not applicable; this is a terminal no-trade state |

### `ABORTED`

| Category | Definition |
| --- | --- |
| Required inputs | enough context to explain why the paper session was halted |
| Transition trigger | session integrity breaks after start, or operator / kill-switch aborts |
| Validation checks | abort reason must be explicit and high-signal |
| Audit event emitted | `SESSION_ABORTED` |
| Failure / no-trade condition | not applicable; this is a terminal abort state |

## Guardrail-Driven No-Trade Or Abort Rules

The state machine should explicitly reject or abort on:

- stale underlying or selected contract quote
- missing option chain at decision time
- missing selected contract in the chain
- missing required `09:15`, ORPT, or RC snapshot for an enabled path
- monthly status `UNKNOWN`
- unsupported workbook branch
- requested multi-session carry-forward in the current same-day paper runtime
- failed spread, liquidity, or OI guardrails
- timezone or clock mismatch
- duplicate or late events that invalidate ordering
- source mismatch inside one paper session
- operator kill-switch activation

## Audit Events And Output Artifacts

The state machine must emit enough information to produce:

- session manifest
- decision log
- selected contract log
- paper order journal
- lifecycle event log
- P&L summary
- replay input manifest
- replay output summary
- no-trade reason summary

For the current scaffold, the persisted artifact set now includes the
terminal planning artifacts, replay bundles, operator review summaries, the
intent-only execution-journal shell, post-planning intent-block summaries,
later execution-arm or execution-block summaries, dispatch summaries, and final
handoff summaries, but it still does not claim any order execution, fills, or
position lifecycle monitoring.

Minimum per-event audit fields:

- `state_from`
- `state_to`
- `transition_timestamp`
- `trigger_event_type`
- `source_id`
- `selected_contract_symbol` if relevant
- `warning_flags`
- `terminal_reason` for `NO_TRADE` or `ABORTED`

## S23-Specific Operating Notes

- Current-day FSL / TRP should only run when the required `09:15`, ORPT, and RC
  snapshots exist in normalized form.
- `AB6 OS!Z183:Z186` entry overrides should be visible in operator audit as
  original entry versus overridden entry.
- Unsupported workbook paths must remain blocked, not silently substituted.
- Rows `190-191` remain process-only for runtime implementation purposes; they
  must not be treated as permission to improvise continuation logic, but S23
  itself remains a carry-forward strategy family that needs explicit
  multi-session implementation with expiry-safe exits and T-1/T-2 rollover
  handling.

## Current Safe Implementation Boundary

The current runtime scaffold now includes:

1. schema or dataclass stubs for the normalized inputs
2. required-field validation
3. deterministic state transitions through `ORDER_PLANNED` / `NO_TRADE` / `ABORTED`
4. explicit pre-planning kill-switch and failure-handling guardrails
5. session manifest updates, persistent terminal planning artifacts, and an in-memory audit trail
6. deterministic replay-bundle manifests, validation, and readback summaries
7. operator-facing JSON and Markdown review summaries over artifacts and bundles
8. later-phase execution-shell arming controls beyond `INTENT_READY`
9. final no-fill handoff controls beyond `ORDER_INTENT_DISPATCHED`
10. execution-shell-aware parity comparison over the persisted paper shell
11. Phase 1 fill-simulator outcomes through `PAPER_ORDER_FILLED`,
    `PAPER_ORDER_NOT_FILLED`, and `PAPER_FILL_ABORTED`
12. normalized live-paper ingress-only dry runs over deterministic archive-export JSONL
    with persisted freshness metrics, ORPT / RC timing audit, selected-contract
    audit, and intent-shell review outputs

The design for the next runtime phase now exists in
`docs/operations/s23_paper_trading_mvp_v1_design.md`.

The next runtime step should operationalize the current dry-run and paper
artifacts rather than broadening lifecycle behavior again:

- explicit pilot-day thresholds
- operator close-out policy
- broader normalized ingress-only source coverage

It should still avoid broker integration, real order placement, and real-money flow.
