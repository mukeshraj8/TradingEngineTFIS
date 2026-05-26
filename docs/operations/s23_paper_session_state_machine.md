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
- same-day square-off only
- no next-day continuation

If the session encounters a condition outside that scope, it should transition
to `NO_TRADE` or `ABORTED`.

## Session Phases

The paper session should move through these high-level phases:

1. pre-market readiness
2. `09:15` snapshot readiness
3. ORPT readiness at `09:24:59`
4. RC readiness at `09:29:59` when needed
5. decision planning
6. paper order open and paper position open
7. lifecycle monitoring
8. exit or EOD square-off
9. session close and artifact finalization

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
| Failure / no-trade condition | holiday, kill-switch engaged, paper mode disabled, malformed config |

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
| Failure / no-trade condition | stale quote, missing selected contract, chain validation failure, unsupported next-day continuation path |

### `ORDER_PLANNED`

| Category | Definition |
| --- | --- |
| Required inputs | finalized trade plan, selected contract, cost model, paper execution policy |
| Transition trigger | TFIS creates a paper order intent |
| Validation checks | original vs overridden entry recorded, selected contract symbol frozen for the decision |
| Audit event emitted | `PAPER_ORDER_PLANNED` |
| Failure / no-trade condition | plan incomplete, selected contract quote stale, operator kill-switch toggled before open |

### `PAPER_ORDER_OPEN`

| Category | Definition |
| --- | --- |
| Required inputs | paper order intent, selected contract quote or first executable bar |
| Transition trigger | paper order becomes eligible to be treated as opened under the paper fill model |
| Validation checks | fill model policy explicit, no duplicate open event, quote still tradable |
| Audit event emitted | `PAPER_ORDER_OPENED` |
| Failure / no-trade condition | data disappears before simulated fill, quote fails spread or liquidity gates |

### `PAPER_POSITION_OPEN`

| Category | Definition |
| --- | --- |
| Required inputs | filled paper order, selected contract lifecycle source, active target / stoploss / FSL fields |
| Transition trigger | simulated fill accepted and active position begins |
| Validation checks | selected contract lifecycle source must be explicit, unsupported continuation must remain disabled |
| Audit event emitted | `PAPER_POSITION_OPENED` |
| Failure / no-trade condition | invalid lifecycle source, missing bar stream, malformed active position state |

### `EXIT_PENDING`

| Category | Definition |
| --- | --- |
| Required inputs | active contract lifecycle bars or quotes, exit thresholds, EOD calendar context |
| Transition trigger | target, stoploss, FSL, expiry restriction, or EOD condition approaches |
| Validation checks | events monotonic, no duplicate closes, EOD policy known |
| Audit event emitted | `EXIT_PENDING` |
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
| Required inputs | open paper position near market close, explicit same-day square-off policy |
| Transition trigger | session reaches EOD cutoff with an open paper position |
| Validation checks | initial rollout must square off rather than continue next day |
| Audit event emitted | `EOD_SQUARE_OFF_TRIGGERED` |
| Failure / no-trade condition | missing EOD quote or bar, unsupported next-day carry path requested |

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
- unsupported next-day continuation
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
- Rows `190-191` remain process-only; the initial paper rollout should not
  allow next-day continuation based on those notes.

## First Safe Implementation Boundary

The first runtime step after this blueprint should be:

1. schema or dataclass stubs for the normalized inputs
2. state-enum scaffolding
3. transition validation for required inputs
4. session manifest and no-trade artifact creation

The first runtime step should not include broker integration or a full paper
execution loop.