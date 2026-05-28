# S23 Fyers Paper Ingress Design

## Purpose

This document defines the first broker-backed live-paper ingress foundation for
TFIS.

Scope:

- S23 only
- NIFTY only
- weekly options only
- paper mode only
- market-data only
- no broker order placement
- no real-money execution

## Architecture

The required boundary is:

`Broker Adapter -> Normalized Market Event Layer -> TFIS Paper Engine`

Concrete first adapter:

- `src/tfis/brokers/fyers.py`

Stable broker-agnostic contract:

- `src/tfis/brokers/base.py`

The S23 paper engine must never consume raw FYERS payloads directly. It only
accepts TFIS-normalized event dataclasses.

## First Implementation Shape

The first runtime path is intentionally narrow:

1. load normalized non-broker prelude events
2. load broker config
3. connect to a broker adapter
4. fetch normalized market-data events from the adapter
5. merge them into one normalized TFIS event stream
6. feed that stream into the existing ingress-only paper runner
7. stop at `ORDER_PLANNED`, `NO_TRADE`, or `ABORTED`

This first implementation does not enable:

- live order placement
- broker execution APIs
- fill simulation from broker data
- lifecycle monitoring from broker data

## Why Prelude Events Still Exist

The current S23 paper orchestrator still requires strategy-side context that is
not broker market data:

- `CALENDAR_CONTEXT`
- `MONTHLY_STATUS_INPUT`
- `UNDERLYING_SNAPSHOT` for `0915`, `ORPT`, and `RC`
- `TRADE_PLAN_INPUT`

To keep S23 logic broker-agnostic and avoid duplicating strategy logic inside
the broker layer, the first broker-backed ingress runner accepts a normalized
prelude JSONL for these non-broker inputs.

The broker adapter currently supplies only market-data events:

- `UNDERLYING_QUOTE`
- `OPTION_CHAIN_SNAPSHOT`
- `SELECTED_CONTRACT_QUOTE`
- optional `SELECTED_CONTRACT_BAR` observations for later phases

Prelude files are rejected if they try to smuggle broker-owned market-data
events into the runner.

Paper-only update:

- TFIS now has a normalized-runtime prelude builder in
  `src/tfis/paper/live_prelude.py`
- TFIS also now has an offline generated-prelude dry-run command in
  `scripts/run_s23_live_prelude_dry_run.py`
- it can generate the S23 paper prelude from deterministic strategy inputs,
  option-chain records, carry-forward state, and expiry governance
- it does not yet replace the FYERS ingress runner with a full socket or
  session orchestrator
- static selected-contract config remains a smoke override only

Snapshot-preflight bridge:

- TFIS now also has a one-shot FYERS snapshot collector in
  `src/tfis/paper/fyers_snapshot_collector.py`
- the collector fetches normalized underlying and option-chain snapshots only
- it can optionally build generated S23 paper prelude artifacts from those
  collected inputs plus a deterministic runtime fixture
- it does not start the FYERS socket loop
- it does not run lifecycle execution
- it does not place broker orders
- it still fails closed when option-chain OI is missing

## Broker Adapter Contract

The generic adapter interface currently exposes:

- `connect()`
- `disconnect()`
- `subscribe_symbols(symbols)`
- `get_underlying_quote(symbol)`
- `get_option_chain(symbol, expiry)`
- `get_option_quote(option_symbol)`
- `stream_ticks()`
- `health()`
- `reconnect()`

Order methods are explicitly blocked:

- `place_order()`
- `modify_order()`
- `cancel_order()`

Attempting any of these in paper ingress raises
`BrokerOrderPlacementBlockedError`.

## Normalized Event Contract

The broker layer must emit only TFIS-normalized events:

- `UnderlyingQuoteEvent`
- `OptionChainSnapshotEvent`
- `SelectedContractQuoteEvent`
- `SelectedContractBarEvent`
- `CalendarContextEvent` if a future broker-backed calendar adapter is ever added

For the first FYERS adapter:

- underlying symbol normalization:
  - `NSE:NIFTY50-INDEX` -> `NIFTY`
- option symbol normalization:
  - `NSE:NIFTY2651225000PE` -> `NIFTY_20260512_25000_PE`

All emitted events must include:

- session date
- effective timestamp
- captured timestamp
- timezone
- source type
- source id
- normalized-by marker

## First Live Runner

Primary runtime module:

- `src/tfis/paper/live_ingress.py`

CLI:

- `scripts/run_s23_fyers_paper_ingress.py`

Safe preflight mode:

- `scripts/run_s23_fyers_paper_ingress.py --preflight-only`

Config:

- `config/paper.s23.yaml`

The first runner:

- loads YAML config
- can run a no-connect preflight before any broker session starts
- builds `PAPER_SESSION_CONFIG` and `COST_SLIPPAGE_SETTINGS`
- loads prelude JSONL
- fetches FYERS-backed normalized market-data events
- optionally records streamed normalized events for audit
- reuses `S23PaperIngressDryRunRunner`
- writes live-paper ingress artifacts

## Persisted Artifacts

The first broker-backed ingress pass writes:

- `broker_health.json`
- `normalized_events.jsonl`
- `ingress_summary.json`
- `selected_contract_audit.json`
- `paper_session_review.md`
- `no_trade_or_order_plan_summary.json`

It also reuses the existing paper shell outputs such as:

- `session_manifest.json`
- `decision_summary.json`
- `audit_events.jsonl`
- `paper_order_plan.json` when planned
- `no_trade_summary.json` or `abort_summary.json`
- replay bundle and review artifacts
- execution-journal intent shell outputs

## Safety Guardrails

The first broker-backed ingress layer must fail closed when:

- broker credentials are missing and no payload-fixture mode is enabled
- market data is stale
- required option chain is missing
- selected contract quote is missing
- timezone is unsupported or mismatched
- multi-session continuation is requested in the current same-day runtime
- any broker order-placement function is attempted

The local preflight must also fail closed when:

- FYERS credentials are missing for live mode
- `no_live_orders_allowed` is false
- paper mode is disabled
- strategy scope is not `S23`
- symbol scope is not `NIFTY`
- contract cycle is not `WEEKLY`
- required prelude snapshots are missing
- the session kill switch is already active

Additional first-pass behaviors:

- missing broker events are allowed to flow into the paper engine as missing
  normalized inputs so the session becomes deterministic `NO_TRADE` or
  `ABORTED` instead of silently fabricating data
- stale quote ingestion may abort before later selected-contract-specific
  readiness checks, which is acceptable and safer for the first live runner
- `kill_switch_enabled` in the ingress config represents operator safety
  availability, while `session_kill_switch_active` determines whether the paper
  session is actively aborted

## FYERS-Specific Notes

The first FYERS adapter supports two modes:

1. payload-fixture mode for deterministic tests
2. SDK-backed live market-data mode when credentials and the FYERS SDK are
   available

The adapter currently normalizes:

- quote payloads
- option-chain payloads
- selected-contract quote payloads
- selected-contract bar payloads from stream batches
- broker health diagnostics

It also records:

- connection state
- cooldown seconds when available
- reconnect attempts
- rate-limit diagnostics when available

## Adding Future Brokers

A future broker should only need to:

1. implement `BrokerAdapter`
2. normalize its payloads into TFIS event dataclasses
3. expose health and reconnect diagnostics
4. avoid any direct strategy dependency

S23 logic should not change.

## Current Limitations

- the first broker-backed ingress path still relies on a normalized prelude for
  non-broker planning context
- selected-contract determination is now available in the paper-only prelude
  builder from normalized option-chain inputs, but it is still external to the
  FYERS broker adapter and live socket orchestration path for the first rollout
- this first runner stops at `ORDER_PLANNED`, `NO_TRADE`, or `ABORTED`
- no live-like fill or lifecycle is enabled by default through this entrypoint
- no broker order-routing path exists

## Implementation Status

Current state:

- broker abstraction layer: implemented
- FYERS market-data adapter: implemented
- broker-backed ingress runner: implemented
- broker health and normalized-event artifacts: implemented
- deterministic fixture coverage: implemented
- no-order safety enforcement: implemented

Still intentionally out of scope here:

- order placement
- broker execution APIs
- live fills
- live lifecycle monitoring
- multi-broker orchestration
