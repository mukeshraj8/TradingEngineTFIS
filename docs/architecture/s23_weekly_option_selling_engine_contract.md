# S23 Weekly Option Selling Engine Contract

## Purpose

This document is the implementation contract for correcting S23 without losing
the TFIS goals.

S23 is a **NIFTY weekly option selling strategy**. It is not a monthly strategy.
Monthly status is an independent market-context input used by S23 to choose the
correct weekly option selling rule group.

- broker-agnostic core
- strategy-specific rules isolated in strategy modules/configuration
- reusable monthly-status service for market-context calculation
- auditable paper trading and review dashboards
- no hidden S23 or FYERS assumptions in shared services

The source rule reference is `rules/S23Rules.jpg` plus
`rules/S23_NIFTY_Weekly_Option_Selling_Codex_Spec_REVIEWED.md`. If these
conflict with older docs or inferred branch mappings, these rules win.

## Strategy Flow

S23 must follow the rule-sheet steps in order.

1. Preparation date
   - Operator selects the date/day/time being prepared.
   - Default is the current trading date.
   - Historical dates are allowed only when required captured data is available.
2. Monthly status
   - Invoke the independent monthly-status service for the selected instrument,
     selected date, and configured price source.
   - Valid business statuses are `BULLISH`, `BULLISH_CONFIRMED`, `BEARISH`,
     and `BEARISH_CONFIRMED`.
   - `UNKNOWN` is an error/incomplete-data status, not a valid trading status.
   - The dashboard must show the monthly-status calculation explanation step by
     step.
3. S23 rule group
   - `BULLISH` and `BULLISH_CONFIRMED` use the bullish CE and PE sell rules.
   - `BEARISH` and `BEARISH_CONFIRMED` use the bearish CE and PE sell rules.
   - CE and PE are evaluated independently. Both can produce orders if both
     qualify.
4. Strike qualification
   - Calculate strike range for each side from the branch matrix below.
   - Check minimum OI.
   - Search near weekly contract first.
   - If near fails, repeat the same search in the next weekly contract.
   - If both near and next fail, no order is placed for that side.
5. Trade levels
   - For each final side, calculate entry, target, SL, and all explanation
     values from the branch matrix.
   - A selected S23 trade becomes a waiting paper order first. A position opens
     only after market data satisfies the entry trigger.

## Monthly Status Boundary

Monthly status is a standalone service.

Required service contract:

```text
MonthlyStatusService.calculate(
  instrument,
  as_of_date,
  price_source,
  candles_or_reference_levels
) -> MonthlyStatusResult
```

`MonthlyStatusResult` must include:

- normalized status
- display status
- input levels used
- thresholds used
- lookback/borrow details, if any
- current-price transition rule applied
- step-by-step explanation
- data provenance

Monthly-status storage must be separate from strategy option-chain storage.
Monthly status may be used by S23, S21, or future strategies, but it must not
depend on any S23 option-chain data.

## S23 Branch Matrix

Use this exact matrix. Do not infer references from option side alone.

| Monthly Group | Side | Trade | Spot Range Reference | Entry Premium Reference | Structure SL Reference | Structure SL Buffer |
|---|---|---|---|---|---|---|
| Bullish | CE | Sell Call | Spot previous 3DLL | Final strike previous 3DLL premium | Final strike previous 2DHH premium | 7% |
| Bullish | PE | Sell Put | Spot previous 2DHH | Final strike previous 2DLL premium | Final strike previous 3DHH premium | 10% |
| Bearish | CE | Sell Call | Spot previous 2DLL | Final strike previous 2DLL premium | Final strike previous 3DHH premium | 10% |
| Bearish | PE | Sell Put | Spot previous 3DHH | Final strike previous 3DLL premium | Final strike previous 2DHH premium | 7% |

Strike range rules:

- CE start = round down `(spot reference + 5%)`
- CE end = round down `spot reference` minus one strike
- PE start = round up `(spot reference - 5%)`
- PE end = round up `spot reference` plus one strike

Qualification rules:

- minimum OI = `500 lots * lot_size`
- ideal premium = `spot range reference * 1.20%`
- minimum premium = `spot range reference * 0.90%`
- ideal search = start to end
- minimum search = end to start
- near contract is searched first
- next contract is searched only if near contract has no qualifying strike

Trade level rules:

- entry = entry premium reference * `0.925`
- target = entry * `0.40`
- percent SL = entry * `1.60`
- structure SL = structure SL reference * configured buffer
- final SL = `min(percent SL, structure SL)`

## Strategy Registry Contract

The engine must load enabled strategies from configuration.

Required behavior:

- Disabled strategies are skipped.
- Enabled strategies expose a typed rule module/config.
- Strategy rules produce auditable decisions, not hidden code branches.
- Shared services provide market data, monthly status, storage, paper orders,
  ledger, and dashboard rendering.
- Strategy modules provide only strategy-specific rule evaluation.

Suggested strategy interface:

```text
Strategy.evaluate(context) -> StrategyDecision
```

`StrategyDecision` should include:

- strategy id/version
- selected date and instrument
- monthly status input/result
- evaluated legs
- near/next contract search trace
- final orders or no-trade reasons
- entry, target, SL, FSL/expiry policy where relevant
- data provenance

## Broker Boundary

The strategy engine must not call FYERS directly.

Required behavior:

- Broker-specific code stays under broker adapters.
- Strategy and monthly-status services receive normalized candles, quotes,
  option chains, and metadata.
- Runtime scripts may choose `fyers` from config, but core services must accept
  broker interfaces or preloaded data.
- Unit tests use fixtures or mock adapters, never live network calls.

## Dashboard Contract

The S23 review dashboard must mirror the rule sheet:

1. Step 1: selected preparation date/day/time
2. Step 2: monthly status result and explanation link/section
3. Step 3: rule group selected from monthly status
4. Step 4: strike range inputs per CE and PE
5. Step 5: near-contract qualification table
6. Step 6: next-contract qualification table if near fails
7. Step 7: final CE and final PE decisions
8. Step 8: entry, target, SL, status, current price, P&L, and action required

The dashboard must separate:

- manually entered inputs
- fetched current data
- captured historical data
- calculated intermediate values
- final orders/positions
- explanation and provenance

## Storage Contract

Durable business data should not live only in `tmp`.

Recommended layout:

```text
data/
  monthly_status/
    YYYY-MM-DD/
      <instrument>/
        <price_source>/
          inputs.json
          result.json
          explanation.md
  strategies/
    S23/
      YYYY-MM-DD/
        <instrument>/
          decision.json
          explanation.md
          option_chain_near.json
          option_chain_next.json
          orders.jsonl
          ledger.jsonl
```

Temporary launch logs and disposable generated dashboards may remain in `tmp`,
but the calculation records needed for review must be stored durably.

## Implementation Phases

1. Documentation and rule contract
   - Correct the S23 spec.
   - Update AI/project guardrails.
   - Record current deviations and next steps.
2. Rule model extraction
   - Move S23 matrix into a single typed config/module.
   - Add unit tests for all four legs.
3. Monthly-status service hardening
   - Keep it independent from S23.
   - Improve explanation output.
   - Support configured spot/futures-continuous source.
4. Strategy registry execution
   - Load enabled strategies.
   - Evaluate S23 through the generic strategy runner.
5. Dashboard rewrite
   - Rebuild S23 review page around rule-sheet steps.
   - Keep trade ledger and order/position monitoring separate.
6. Durable storage migration
   - Store monthly-status captures and S23 strategy captures under `data`.
   - Keep backward-compatible reads from current `tmp` paths during migration.
7. Paper lifecycle completion
   - Preserve waiting-order behavior.
   - Persist orders/positions/ledger.
   - Manage carry-forward positions and expiry policies only from explicit
     strategy configuration.

## Known Current Deviations

- Existing S23 configs are branch-shaped instead of rule-sheet-step shaped.
- Dashboard output still reflects runtime artifacts more than the rule-sheet
  process.
- Some current artifacts remain under `tmp`.
- Current operational scripts are FYERS-first, which is acceptable only at the
  script/adapter boundary.
- The paper runtime has partial carry-forward handling but still needs a clean
  generic lifecycle service before more strategies are added.

## Minimum Acceptance Tests

Before claiming S23 complete, tests must prove:

- monthly status maps to exactly the correct bullish or bearish group
- Bullish CE uses spot 3DLL and final-strike previous 3DLL entry premium
- Bullish PE uses spot 2DHH and final-strike previous 2DLL entry premium
- Bearish CE uses spot 2DLL and final-strike previous 2DLL entry premium
- Bearish PE uses spot 3DHH and final-strike previous 3DLL entry premium
- each side searches near first, then next
- failed near and next contracts produce no order for that side
- minimum OI uses current configured lot size
- selected trade becomes waiting order before any paper position is opened
- broker adapter can be mocked in unit tests
