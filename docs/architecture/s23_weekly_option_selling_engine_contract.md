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
6. ORPT / RC entry timing
   - Build the base trade plan and base selected contract first.
   - At ORPT (`09:24:59`), test the selected option contract against the base
     entry rule.
   - For CE sell, entry is missed when the ORPT selected-contract low is below
     the base CE entry.
   - For PE sell, entry is missed when the ORPT selected-contract low is below
     the base PE entry, matching the workbook row:
     `For Put Sell Entry Check If 09:24:59 AM LL < Put Sell Entry`.
   - If entry is not missed, keep the base selected contract and place the
     waiting paper order at ORPT.
   - If entry is missed, wait for RC (`09:29:59`), recalculate the branch's
     strike range, ideal premium, minimum premium, entry, target, and SL using
     the updated rule-sheet formulas, then re-run contract selection against
     the available option-chain data.
   - If any required ORPT/RC selected-contract or underlying candle data is
     missing, fail closed with an auditable no-order reason instead of silently
     using stale base values.
7. Carry-forward stop handling
   - If an open position has not hit target or SL by `15:00:00`, compare the
     selected option close at `15:00:00` with the original SL.
   - If the option close is above original SL, square off at CMP at `15:00:00`.
   - If the option close is not above original SL, carry the position forward
     and mark the stoploss inactive overnight.
   - On the next trading day, keep the target active while stoploss remains
     inactive through the opening window.
   - At ORPT, compare the `09:15` selected-option high with the original SL.
     If the high did not exceed original SL, reactivate the original SL.
   - If the `09:15` selected-option high exceeded original SL, wait until RC and
     set revised SL as `RC selected-option high + configured sl_reference_pct`.
     The buffer percentage comes from the selected strategy branch parameters
     so future strategies can reuse the lifecycle flow with different figures.
   - Missing selected-option bars required for this reset must hold the position
     with an auditable reason instead of applying stale SL evidence.

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

- authoritative strike buffer = `5%` from the NIFTY weekly option selling
  rule sheet.
- CE start = round down `(spot reference + 5%)`
- CE end = round down `spot reference` minus one strike
- PE start = round up `(spot reference - 5%)`
- PE end = round up `spot reference` plus one strike

Qualification rules:

- minimum OI = `500 lots`
- historical minimum OI units = `500 * effective historical lot size`
- January 2024 NIFTY lot-size authority is `50`, so HSRE uses
  `minimum_oi_units = 25000` for January 2024 contract selection.
- January 2026 NIFTY lot-size authority is `65`, so current-date S23 may use
  `minimum_oi_units = 32500`.
- ideal premium = `spot range reference * 1.20%`
- minimum premium = `spot range reference * 0.90%`
- ideal search = start to end
- minimum search = start to end
- near contract is searched first
- next contract is searched only if near contract has no qualifying strike
- selected-contract option history must use the same final option contract:
  same expiry, same strike, and same CE/PE. If three completed prior sessions
  are unavailable for the final selected contract, historical S23 fails closed.

Trade level rules:

- entry = entry premium reference * `0.925`
- target = entry * `0.40`
- percent SL = entry * `1.60`
- structure SL = structure SL reference * configured buffer
- final SL = `min(percent SL, structure SL)`

## ORPT / RC Recalculation Matrix

These rules apply after the base S23 branch has selected an initial contract.
The selected-contract intraday candles are separate from the NIFTY spot
reference candles.

| Monthly Group | Side | Missed-entry test at ORPT | RC strike / premium reference | RC entry reference | RC SL reference |
|---|---|---|---|---|---|
| Bullish | CE | ORPT option low `<` base CE entry | `MIN(PRV_3DLL, RC spot low)` | `MIN(OPT_PRV_3DLL, RC option low)` | `MIN(RC entry * 1.60, RC option high * 1.07)` |
| Bullish | PE | ORPT option low `<` base PE entry | strike uses `MAX(PRV_2DHH, RC spot high)`; premium uses `MIN(PRV_2DHH, RC spot low)` | `MIN(OPT_PRV_2DLL, RC option low)` | `MIN(RC entry * 1.60, RC option high * 1.10)` |
| Bearish | CE | ORPT option low `<` base CE entry | `MIN(PRV_2DLL, RC spot low)` | `MIN(OPT_PRV_2DLL, RC option low)` | `MIN(RC entry * 1.60, RC option high * 1.10)` |
| Bearish | PE | ORPT option low `<` base PE entry | strike uses `MAX(PRV_3DHH, RC spot high)`; premium uses `MIN(PRV_3DHH, RC spot low)` | `MIN(OPT_PRV_3DLL, RC option low)` | `MIN(RC entry * 1.60, RC option high * 1.07)` |

For recalculated CE legs:

- start strike = round down `(RC reference + 5%)`
- end strike = round down `RC reference` minus one strike

For recalculated PE legs:

- start strike = round up `(RC strike reference - 5%)`
- end strike = round up `RC strike reference` plus one strike

After recalculation, the near-contract 8a/8b and next-contract 8c search rules
remain unchanged. The final waiting paper order must be created from the
recalculated selected contract and recalculated entry/target/SL, not from the
base missed contract.

Current implementation note:

- The supervised live decision runner now performs a provisional base
  selection, fetches the selected contract's ORPT/RC option bars through the
  broker adapter, then rebuilds the final decision with timing evidence.
- Missing ORPT/RC selected-contract bars fail closed with a decision failure.
- If ORPT marks entry as missed, TFIS recalculates the trade plan from RC spot
  and selected-option candles and reruns normal near/next contract selection.
- Next-day SL reset after an overnight 15:00 carry remains the next lifecycle
  validation/refinement item.

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
- The paper runtime now has S23-specific 15:00 continuation handling, but
  next-day SL reset after overnight carry still needs a clean auditable flow
  before the lifecycle can be called complete.

## Minimum Acceptance Tests

Before claiming S23 complete, tests must prove:

- monthly status maps to exactly the correct bullish or bearish group
- Bullish CE uses spot 3DLL and final-strike previous 3DLL entry premium
- Bullish PE uses spot 2DHH and final-strike previous 2DLL entry premium
- Bearish CE uses spot 2DLL and final-strike previous 2DLL entry premium
- Bearish PE uses spot 3DHH and final-strike previous 3DLL entry premium
- each side searches near first, then next
- failed near and next contracts produce no order for that side
- minimum OI uses `500 lots * effective lot size` for the session date
- selected trade becomes waiting order before any paper position is opened
- broker adapter can be mocked in unit tests
- live final decisions fail closed when selected-contract ORPT/RC bars are
  missing
- missed ORPT entries recalculate strike range, premium filters, entry, target,
  and SL before final contract selection
- 15:00 continuation keeps positions open with overnight SL inactive when the
  option price is not above original SL
