# S21 BankNifty Monthly Option Selling Contract

## Purpose

S21 is a BankNifty monthly option-selling strategy derived from
`d:/TFIS/Selected/Rules/strategies/BNF Monthly OS Rules.jpg`.

This document records the implemented rule-config foundation. It does not enable
BankNifty live or paper execution. The current operational runner remains
S23/NIFTY/FYERS-scoped until shared strategy execution, contract selection, and
paper lifecycle pieces are extracted behind generic interfaces.

## Strategy Flow

1. Record the next trading date, day, and preparation time.
2. Calculate monthly status from the BankNifty futures-continuous graph/source.
3. Map `BULLISH` or `BULLISH_CONFIRMED` to the bullish Call Sell and Put Sell
   legs.
4. Map `BEARISH` or `BEARISH_CONFIRMED` to the bearish Call Sell and Put Sell
   legs.
5. Evaluate CE and PE legs independently.
6. Search the near monthly contract first.
7. If near monthly has no qualifying strike, repeat the same scan in the next
   monthly contract.
8. If neither contract qualifies, do not place an order for that leg.

## Branch Matrix

| Monthly Group | Side | Trade | Spot Range Reference | Entry Premium Reference | Structure SL Reference | Structure SL Buffer |
|---|---|---|---|---|---|---|
| Bullish | CE | Sell Call | Spot previous 3DLL | Final strike previous 3DLL premium | Final strike previous 2DHH premium | 7% |
| Bullish | PE | Sell Put | Spot previous 2DHH | Final strike previous 2DLL premium | Final strike previous 3DHH premium | 10% |
| Bearish | CE | Sell Call | Spot previous 2DLL | Final strike previous 2DLL premium | Final strike previous 3DHH premium | 10% |
| Bearish | PE | Sell Put | Spot previous 3DHH | Final strike previous 3DLL premium | Final strike previous 2DHH premium | 7% |

Strike range rules:

- CE start = round down `spot reference + 5%`
- CE end = round down `spot reference` minus one strike
- PE start = round up `spot reference - 5%`
- PE end = round up `spot reference` plus one strike

Qualification rules:

- minimum OI = `500 lots * lot_size`
- ideal premium = `spot range reference * 2.0%`
- minimum premium = `spot range reference * 1.5%`
- ideal search = start strike to end strike
- minimum search = end strike to start strike
- near monthly contract is searched first
- next monthly contract is searched only if near monthly has no qualifying
  strike

Trade level rules:

- entry = entry premium reference minus `7.5%`
- target = entry minus `60.0%`
- percent SL = entry plus `60.0%`
- structure SL = structure SL reference plus the branch buffer
- final SL = `min(percent SL, structure SL)`

## Configurable Parameters

The S21 strategy folders keep the rule-sheet numbers in `parameters.yaml`:

- `strike_buffer_pct`
- `strike_step`
- `ideal_premium_pct`
- `minimum_premium_pct`
- `entry_discount_pct`
- `target_pct`
- `sl_entry_pct`
- `sl_reference_pct`
- `minimum_lots`
- `lot_size`

The current folder schema also requires a concrete `minimum_oi` field in
`strategy.yaml`, so the initial S21 folders store `minimum_oi: 17500` from the
configurable default `500 * 35`. Confirm the active BankNifty lot size before
promoting the strategy beyond config validation.

## Current Implementation Boundary

Implemented now:

- four S21 BankNifty monthly option-selling strategy folders
- a dedicated `tfis.rules.s21_rule_matrix` module
- unit tests that load all four folders, compare them to the S21 matrix, and
  evaluate sample formulas
- registry entries marked `UNKNOWN_REQUIRES_REVIEW`

Not implemented yet:

- BankNifty monthly contract discovery in a live/paper runner
- BankNifty futures-continuous monthly-status data sourcing for an operational
  run
- runtime handling for S21 ORPT/RC timing, if applicable
- S21 carry-forward, expiry, force-close, fresh-entry, and watcher lifecycle
  validation
- automatic derivation of `minimum_oi` from `minimum_lots * lot_size` in the
  strategy loader

Before any operational promotion, confirm:

- active BankNifty lot size and strike step
- exact monthly expiry selection and near/next monthly fallback policy
- whether S21 uses the same ORPT/RC timing model as S23
- whether S21 should allow carry-forward positions and what forced-close rules
  apply
