# AI Change Agreement

This agreement defines the non-negotiable architecture and operating contract
for any AI-assisted change in `TradingEngineTFIS`.

Every AI coding agent must read this agreement before changing code,
configuration, scripts, tests, or operational documentation in this repository.

## Project Intent

TFIS is intended to remain:

- broker-agnostic at the core
- capable of supporting multiple strategies over time
- config-driven and auditable
- independent from sibling projects such as `TradingEngineProd`
- safe for paper trading and research before any live-order capability is
  considered

S23 on FYERS is the first operational path. It must not become the hidden shape
of the whole system.

## Architecture Contract

Core TFIS modules must not be tightly coupled to any one broker, strategy, or
symbol family.

Core means, at minimum:

- `src/tfis/domain`
- `src/tfis/strategy`
- `src/tfis/formulas`
- `src/tfis/risk`
- `src/tfis/storage`
- `src/tfis/monthly_status`
- shared dashboard/data models that are not explicitly strategy-specific

Core modules may depend on TFIS interfaces, typed domain models, normalized
events, and repository-local abstractions. They must not import broker SDKs or
hardcode FYERS, S23, NIFTY, or any future broker/strategy as a default behavior.

## Broker Contract

Broker-specific behavior must live behind adapter boundaries.

Required rules:

- Use broker interfaces/protocols for core market-data access.
- Keep real broker SDK usage inside dedicated adapter modules.
- FYERS may be the first adapter, but it must not be assumed by core strategy,
  formula, monthly-status, lifecycle, or storage code.
- Scripts may choose a concrete broker for an operational run, but reusable
  services should accept a broker adapter or resolve one from configuration.
- Unit tests must not require live broker/network access.
- Live broker checks must be explicit readiness/preflight steps.

## Strategy Contract

Strategies must be represented by explicit configuration and typed strategy
rules, not by hidden code branches.

Required rules:

- S23-specific rules may live in S23-specific modules, configs, tests, and
  scripts.
- Generic strategy evaluation, formula execution, monthly status, persistence,
  and dashboard infrastructure must remain reusable for other strategies.
- Do not add a new strategy by copying S23 live-paper code and renaming pieces.
  Extract shared lifecycle/order/dashboard behavior first when it is reusable.
- Strategy-specific behavior must be named as such.
- Shared behavior must not contain S23-only assumptions.
- Enabled/disabled strategy execution must come from strategy registry/config,
  so adding S21, S23, or any later strategy does not require changing generic
  engine flow.
- Strategy dashboards should show the strategy rule process, not merely the
  final runtime artifact.

## Monthly-Status Driven Strategy Contract

Monthly-status driven strategies are not monthly strategies merely because they
use monthly status. Monthly status is an independent market-context input.

These strategies must follow this shared flow:

1. calculate monthly status for the selected instrument/date/source through the
   independent monthly-status service
2. map the status to the strategy's configured rule group
3. evaluate each configured strategy leg independently
4. search near contract first, then next contract only if near fails
5. produce auditable orders/no-trade reasons with all intermediate values

For S23, which is a NIFTY weekly option selling strategy, the source
implementation contract is
`docs/architecture/s23_weekly_option_selling_engine_contract.md`. AI agents must
not replace that matrix with directional inference or older branch labels.

## Monthly Status Contract

Monthly status is an independent TFIS service, not part of S23.

Required rules:

- Monthly status must support instrument-driven calculation.
- The calculation path must be usable by any strategy that needs monthly
  status.
- S23 option-chain data must not be mixed with monthly-status data storage.
- Monthly-status capture, review, and test tooling must remain separate from
  strategy option-chain capture.
- Data source choice, such as spot or futures continuous data, must be explicit
  and configurable.
- Business display statuses are `BULLISH`, `BULLISH_CONFIRMED`, `BEARISH`, and
  `BEARISH_CONFIRMED`; `UNKNOWN` is allowed only for incomplete/error cases.
- Monthly-status results must include step-by-step explanation and provenance.

## Paper Trading Contract

Paper trading must mimic real execution behavior as closely as practical while
remaining safe.

Required rules:

- Do not open a paper position merely because a strategy selected a contract.
  A selected trade first becomes a waiting paper order.
- A paper order fills only when market quote/bar data satisfies the entry rule.
- Position state must persist across process restarts and market days.
- Trade ledger/history must persist every meaningful trade lifecycle event.
- Same-day square-off must not be assumed unless the strategy config requires
  it.
- Expiry, rollover, force-close, target, stoploss, and fresh/reverse-entry
  behavior must be explicit, configurable where appropriate, and tested.

## S23 Current Operating Contract

Current S23 paper mode uses these rules unless explicitly changed by the user
and tests:

- Fresh S23 entries on expiry day `T` or `T-1` must select the next weekly
  expiry, not the current weekly expiry.
- Existing S23 positions opened on or before `T-2` may continue through `T-1`.
- S23 positions must not carry past expiry.
- On expiry day, target/SL/FSL handling is checked first.
- If target/SL/FSL does not close the position, expiry force-close happens at
  the configured `forced_close_time`, currently `12:00:00`.
- S23 paper mode currently uses FYERS as the first market-data adapter, but this
  must remain an adapter choice, not a core assumption.

## Data Storage Contract

Captured and persisted data must be organized for future multi-strategy use.

Required rules:

- Do not mix monthly-status capture with strategy option-chain capture.
- Do not store long-lived business data only in disposable temp folders unless
  it is clearly marked temporary and migration is planned.
- Strategy data should include strategy code, date, instrument, contract,
  expiry, strike, option side, premium, OI, entry, target, SL, lifecycle status,
  and provenance where relevant.
- Storage design must avoid key/path collisions with sibling projects,
  especially `TradingEngineProd`.
- If Valkey or any shared service is used, TFIS must use its own namespace and
  must not read or write another project's keys.

## Dashboard Contract

Dashboard work must preserve operational clarity.

Required rules:

- Dashboard sections should be strategy-aware, not hardcoded to one strategy
  unless clearly labeled as S23-specific.
- Trades, orders, positions, current price, fill status, P&L, target, SL,
  expiry, and required operator action must be visible where relevant.
- Manual review/test pages must clearly separate user input, fetched/captured
  data, calculated intermediate values, final decision, and explanation.
- Monthly-status review must remain separate from S23 option-chain review.

## Change Discipline

Before changing files, an AI agent must:

1. Read this agreement.
2. Inspect the existing code path and local patterns.
3. Identify whether the change is generic, broker-specific, strategy-specific,
   or operational.
4. Keep the change in the correct layer.
5. Ask before changing strategy behavior, rollover behavior, or live/paper
   execution behavior unless the user explicitly requested that exact change.

After changing files, an AI agent must:

1. Run focused tests for the changed area.
2. Add or update tests for any changed behavior.
3. Report any tests that were not run.
4. State whether the change preserved broker-agnostic and multi-strategy
   boundaries.
5. Update operational documentation when behavior, limitations, or next steps
   changed.

## Prohibited Shortcuts

Do not:

- import a broker SDK into core strategy/monthly-status/formula/risk logic
- hardcode FYERS behavior outside adapter or FYERS-specific scripts
- hardcode S23 behavior into generic lifecycle/dashboard/storage code
- silently change rollover, square-off, entry, target, SL, or expiry behavior
- use live market/network calls in unit tests
- interfere with `TradingEngineProd` or other sibling project processes
- use shared Valkey keys or shared filesystem paths without TFIS namespacing
- treat temp artifacts as durable business records without explicit migration
  planning

## Current Known Deviation

The repository has a broker-agnostic and multi-strategy foundation, but the
current live-paper operational path is still S23 plus FYERS first.

This is acceptable as the first implemented path, but future work should move
shared paper lifecycle, order state, dashboard, broker resolution, and storage
concerns toward generic services before adding more strategies.
