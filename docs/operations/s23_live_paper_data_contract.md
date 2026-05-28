# S23 Live-Paper Data Contract

## Purpose

This document defines the normalized live-paper data contract for `S23` only.

It is a blueprint for deterministic paper-trading orchestration, not a live
broker integration spec.

The intent is to make paper sessions:

- replayable
- auditable
- comparable to historical S23 logic
- safe to reject when required data is stale, incomplete, or unsupported

## Initial Scope

The first supported paper-trading scope should remain deliberately narrow:

- strategy family: `S23`
- symbol: `NIFTY`
- segment: weekly options sell
- mode: paper only
- strategy semantics: carry-forward is valid before expiry when the strategy
  and instrument rules allow it
- current runtime limitation: multi-session carry-forward is not yet implemented
- EOD policy for the current runtime: same-day square-off only for the first
  rollout until expiry-safe carry-forward and rollover handling exist

Anything outside that scope should emit `NO_TRADE` or `ABORTED`, not a best
effort guess.

## Design Principles

- Excel-backed S23 formulas remain the source of truth.
- The normalized contract must be strategy-neutral enough to audit, but the
  first implementation target is S23 only.
- All timestamps must be explicit and timezone-safe.
- Provenance must explain what source produced each decision input.
- Missing or stale required data must block trading rather than trigger silent
  fallback.

## Common Event Envelope

Every normalized live-paper input event should carry the following fields,
regardless of event type.

| Field | Required | Notes |
| --- | --- | --- |
| `event_type` | yes | One of the event types listed below. |
| `session_date` | yes | Local India trading date in `YYYY-MM-DD`. |
| `effective_timestamp` | yes | The market timestamp this event represents. |
| `captured_at` | yes | When TFIS received or normalized the data. |
| `timezone` | yes | Must be `Asia/Kolkata` for normalized paper events. |
| `source_type` | yes | Example: `normalized_csv`, `normalized_jsonl`, `archive_export`, `paper_fixture`. |
| `source_id` | yes | Stable source identifier or file/session path reference. |
| `source_sequence` | no | Monotonic sequence number if the upstream source supports one. |
| `synthetic_fixture` | yes | `true` for fixtures, `false` for archive or live-paper sources. |
| `normalized_by` | yes | Adapter or tool name/version that produced the event. |
| `data_quality_flags` | no | Array of non-fatal warnings such as `missing_volume` or `late_arrival`. |
| `integrity_hash` | no | Optional event payload hash for replay verification. |

## Required Event Types

The first paper-mode implementation should normalize the following event types.

### `UNDERLYING_QUOTE`

Point-in-time underlying or index quote used for freshness and current spot
checks.

Required fields:

| Field | Notes |
| --- | --- |
| `symbol` | `NIFTY` in the initial rollout. |
| `ltp` | Current last traded or equivalent normalized price. |
| `bid` | Optional if available. |
| `ask` | Optional if available. |
| `volume` | Optional. |
| `source_latency_ms` | Optional but recommended. |

### `UNDERLYING_SNAPSHOT`

Aggregated underlying snapshot used for workbook-driven time gates such as
`09:15:00`, `09:24:59`, and `09:29:59`.

Required fields:

| Field | Notes |
| --- | --- |
| `snapshot_label` | One of `PRE_OPEN`, `0915`, `ORPT`, `RC`, `EOD`. |
| `open` | Optional for `0915`, `ORPT`, `RC`; useful for provenance. |
| `high` | Required. |
| `low` | Required. |
| `close` | Optional but recommended. |
| `bar_start` | Start of the aggregation interval. |
| `bar_end` | End of the aggregation interval. |
| `complete` | Must be `true` before the snapshot is used for decisions. |

### `OPTION_CHAIN_SNAPSHOT`

Full or filtered option-chain snapshot used for realistic contract selection.

Required fields:

| Field | Notes |
| --- | --- |
| `underlying_symbol` | `NIFTY` in the initial rollout. |
| `expiry` | Weekly expiry date used for selection. |
| `contracts` | Normalized contract rows. |

Each normalized contract row must include:

| Field | Notes |
| --- | --- |
| `symbol` | TFIS-normalized option symbol. |
| `option_type` | `CALL` or `PUT`. |
| `strike` | Numeric strike. |
| `expiry` | Contract expiry date. |
| `bid` | Required for spread validation when available. |
| `ask` | Required for spread validation when available. |
| `ltp` | Required for premium selection. |
| `oi` | Required for OI guardrails. |
| `volume` | Optional but recommended for liquidity checks. |

### `SELECTED_CONTRACT_QUOTE`

Point quote for the chosen option contract, used to validate whether the
selected contract is actually tradable at decision time.

Required fields:

| Field | Notes |
| --- | --- |
| `symbol` | Must match the selected option-chain contract exactly. |
| `option_type` | `CALL` or `PUT`. |
| `strike` | Numeric strike. |
| `expiry` | Expiry date. |
| `bid` | Required for spread checks. |
| `ask` | Required for spread checks. |
| `ltp` | Required for entry and lifecycle monitoring. |
| `oi` | Required for final pre-trade validation. |
| `volume` | Optional but recommended. |

### `SELECTED_CONTRACT_BAR`

Aggregated OHLC event for the selected contract. This is the paper-mode analog
of the current contract-specific lifecycle input.

Required fields:

| Field | Notes |
| --- | --- |
| `symbol` | Must match the selected contract. |
| `open` | Required. |
| `high` | Required. |
| `low` | Required. |
| `close` | Required. |
| `volume` | Optional but recommended. |
| `bar_start` | Start of aggregation interval. |
| `bar_end` | End of aggregation interval. |

### `CALENDAR_CONTEXT`

Session metadata needed to decide whether S23 is even allowed to run.

Required fields:

| Field | Notes |
| --- | --- |
| `session_date` | Trading date. |
| `is_holiday` | Must be `false` to trade. |
| `is_expiry_day` | Needed for expiry-day handling and operator visibility. |
| `weekly_expiry` | Relevant weekly expiry for the session. |
| `market_open` | Expected local market open time. |
| `market_close` | Expected local market close time. |

### `MONTHLY_STATUS_INPUT`

Normalized monthly-status input used before branch selection.

Required fields:

| Field | Notes |
| --- | --- |
| `monthly_status` | Must not be `UNKNOWN` for trading to proceed. |
| `status_source` | Example: `monthly_status_engine`, `manual_paper_override`. |
| `reference_date` | The date for which the status applies. |
| `threshold_version` | Provenance for the status decision table. |

### `PAPER_SESSION_CONFIG`

Paper-only session controls and guardrails.

Required fields:

| Field | Notes |
| --- | --- |
| `strategy_code` | Must identify S23. |
| `paper_mode_enabled` | Must be `true`. |
| `same_day_square_off_only` | Must be `true` for the first rollout of the current same-day paper runtime. This is a runtime guardrail, not a strategy rule. |
| `allow_recalculation` | Whether ORPT recalculation is enabled for the session. |
| `allow_current_day_fsl_trp` | Whether the current-day overlay is enabled. |
| `kill_switch_enabled` | Must be explicit. |
| `operator_id` | Required for paper-session accountability. |

### `COST_SLIPPAGE_SETTINGS`

Paper-mode transaction assumptions recorded for replayability and comparisons.

Required fields:

| Field | Notes |
| --- | --- |
| `brokerage_per_lot` | Required. |
| `slippage_entry_points` | Required. |
| `slippage_exit_points` | Required. |
| `spread_buffer_policy` | Required if spreads affect fills. |
| `version_label` | Stable identifier for the cost model. |

## Required Phases And Time Gates

The live-paper contract must support the following S23 phases.

| Phase | Local Time | Required Inputs |
| --- | --- | --- |
| Pre-open readiness | before `09:15:00` | `CALENDAR_CONTEXT`, `PAPER_SESSION_CONFIG`, `COST_SLIPPAGE_SETTINGS` |
| `09:15` snapshot | `09:15:00` | complete `UNDERLYING_SNAPSHOT` with `snapshot_label=0915` |
| ORPT snapshot | `09:24:59` | complete `UNDERLYING_SNAPSHOT` with `snapshot_label=ORPT`, relevant option quote state |
| RC snapshot | `09:29:59` | complete `UNDERLYING_SNAPSHOT` with `snapshot_label=RC`, relevant option quote state |
| Entry decision | immediately after required ORPT or RC data | monthly status, branch context, option chain, selected contract quote |
| Active lifecycle monitoring | post entry | `SELECTED_CONTRACT_BAR` and quote freshness for the active contract |
| Exit monitoring | during open position | target / stoploss / FSL checks on selected contract data |
| EOD square-off | before session close | selected contract quote or bar for controlled paper close |
| Session close | after square-off or no-trade | final audit artifacts |

## Freshness And Validity Rules

The first implementation should enforce these contract-level guardrails.

### Timezone

- normalized `effective_timestamp` must be timezone-aware
- normalized timezone must be `Asia/Kolkata`
- mixed timezone sources must be normalized before orchestration
- a session with ambiguous or naive timestamps should abort

### Readiness

- `09:15`, ORPT, and RC snapshots must be complete before they are consumed
- monthly status must be available before branch selection
- option chain and selected contract quote must be fresh enough at decision time
- selected contract lifecycle bars must be monotonic and non-duplicated

### Data Quality

The session must emit `NO_TRADE` or `ABORTED` for:

- stale underlying quote at decision time
- stale selected contract quote at decision time
- missing option chain snapshot
- selected contract not present in the option chain
- missing required `09:15`, ORPT, or RC snapshots for an enabled overlay
- monthly status `UNKNOWN`
- unsupported workbook branch
- requested multi-session continuation in the current same-day paper runtime
- invalid bid/ask spread or missing required price fields
- low OI or failed liquidity validation
- duplicate or late events that make the sequence ambiguous
- data source mismatch inside one paper session

## Carry-Forward Semantics

The business semantics for S23 and similar TFIS option-selling strategies are:

- `carry_forward_allowed: true` means the strategy may carry positions across
  sessions when its rule set permits it
- no option position may ever be carried beyond its expiry
- expiry-near behavior must follow explicit strategy and instrument rollover
  policy such as `T-1` or `T-2` selection of the next-expiry instrument
- OI validation must remain enforced for selected-contract decisions and must
  not be weakened to enable continuation

This document therefore treats carry-forward as strategy-valid, while the
current paper runtime still stops at same-day square-off because the required
multi-session orchestration is not yet implemented.

## Mapping To Current TFIS Runtime Concepts

The live-paper contract is designed to align with current offline concepts
without changing them.

| Runtime Concern | Current TFIS Concept | Live-Paper Contract Equivalent |
| --- | --- | --- |
| Underlying intraday snapshot | spot intraday CSV | `UNDERLYING_SNAPSHOT` |
| Selected contract lifecycle bars | contract intraday CSV | `SELECTED_CONTRACT_BAR` |
| Option-chain realism | option-chain CSV | `OPTION_CHAIN_SNAPSHOT` |
| Monthly status driver | monthly-status CSV or engine | `MONTHLY_STATUS_INPUT` |
| Cost assumptions | CLI settings | `COST_SLIPPAGE_SETTINGS` |

## Paper-Session Provenance Expectations

Every paper session should produce enough metadata to answer:

- what data source drove each decision
- whether any fixture, archive, or live-paper normalized input was used
- whether any overlay was enabled
- whether any no-trade guardrail fired
- whether the paper decision is replayable against the same normalized inputs

Minimum provenance fields to preserve in downstream session artifacts:

- all source paths or source IDs for the normalized inputs
- overlay enablement flags
- selected contract symbol
- selected contract lifecycle source
- stale or fallback warnings
- operator-visible no-trade or abort reason

## First Safe Implementation Boundary

The first implementation step should not be a full execution loop.

It should be:

1. schema stubs for the normalized event types
2. validation for required fields and timestamps
3. session manifest creation
4. no-trade rejection for missing or stale critical inputs

Anything beyond that should wait until the session state machine is implemented.
