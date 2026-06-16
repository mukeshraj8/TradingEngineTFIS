# Monthly Status Engine Design

## Current Status

- `StrategyBranchSelector` already exists and filters folder-based strategies by `MonthlyStatus`.
- `MonthlyStatusEngine` now follows the clarified classroom / workbook-aligned two-layer flow:
  - direct monthly structure
  - then current-price transition rules from the effective monthly state
- `MonthlyStatusLookbackResolver` now borrows prior **monthly/weekly contexts**, not prior trading-day anchors.
- gap-up / gap-down behavior remains separate and is still not implemented in this layer.

## Inputs

The engine uses these reference values:

- `PMH` = Previous Month High
- `PML` = Previous Month Low
- `CMH` = Current Month High
- `CML` = Current Month Low
- `PWH` = Previous Week High
- `PWL` = Previous Week Low
- `CWH` = Current Week High
- `CWL` = Current Week Low
- `current_price` = checkpoint close / current spot used for the day

Configured thresholds come from:

- `config/monthly_status_thresholds.yaml`

For NIFTY / BANKNIFTY today this means:

- `a = 0.75%`
- `b = 0.75%`
- `c = 0.15%`

## Layer 1: Direct Monthly Structure

Direct monthly status is determined from current-month extremes versus previous-month
extremes.

Derived values:

- `bullish_value = PMH + a%`
- `bearish_value = PML - a%`
- `bullish_confirmed_value = bullish_value + b%`
- `bearish_confirmed_value = bearish_value - b%`

Direct monthly structure rules:

- `BULL`
  - `CMH >= bullish_value`
- `BULL_CF`
  - `CMH >= bullish_confirmed_value`
- `BEAR`
  - `CML <= bearish_value`
- `BEAR_CF`
  - `CML <= bearish_confirmed_value`
- `UNKNOWN`
  - no decisive monthly threshold is breached

When the current month breaches both bullish and bearish directions in the same
window, TFIS treats that as ambiguous monthly structure and only resolves directly
if the current price clearly sits beyond one side’s monthly threshold. Otherwise it
remains `UNKNOWN`.

## Layer 2: UNKNOWN Borrowing

If the current month remains `UNKNOWN`, TFIS borrows from prior historical
month/week contexts.

This lookback is:

- month/week-context based
- not previous-trading-day based

Expected sequence:

1. current month/week context
2. previous month/week context
3. previous-to-previous month/week context

up to:

- `max_monthly_status_lookback_windows`

Borrowing preserves the actual historical monthly state:

- `BULL` stays `BULL`
- `BULL_CF` stays `BULL_CF`
- `BEAR` stays `BEAR`
- `BEAR_CF` stays `BEAR_CF`

If no historical context resolves within the safe limit, the result remains
`UNKNOWN`.

## Layer 3: Current-Price Transitions From Effective State

Once an effective monthly status exists, TFIS applies the current day’s price
transition rules.

### If effective state is `BULL`

- remain `BULL` by default
- become `BULL_CF` if:
  - `current_price >= bullish_confirmed_value`
- reverse to `BEAR` if:
  - `current_price <= min(PWL, CWL) - c%`

### If effective state is `BULL_CF`

- remain `BULL_CF` by default
- reverse to `BEAR` if:
  - `current_price <= bearish_value`

### If effective state is `BEAR`

- remain `BEAR` by default
- become `BEAR_CF` if:
  - `current_price <= bearish_confirmed_value`
- reverse to `BULL` if:
  - `current_price >= max(PWH, CWH) + c%`

### If effective state is `BEAR_CF`

- remain `BEAR_CF` by default
- reverse to `BULL` if:
  - `current_price >= bullish_value`

## Important Distinction

Weekly reversal checks apply only to the non-confirmed states:

- `BULL` -> weekly bearish reversal via `min(PWL, CWL) - c%`
- `BEAR` -> weekly bullish reversal via `max(PWH, CWH) + c%`

Confirmed states reverse only on the stronger monthly threshold:

- `BULL_CF` -> `BEAR` via `PML - a%`
- `BEAR_CF` -> `BULL` via `PMH + a%`

This is the key behavior that corrected the earlier TFIS implementation.

## Engine Output

Current output model:

`MonthlyStatusResult`

- `status`
- `trigger_name`
- `threshold_value`
- `reversal_dominated`
- `candidates`
- `notes`

Current resolver output:

`MonthlyStatusResolutionResult`

- `current_window_result`
- `borrowed_window_result`
- `resolved_result`
- `trace`
- `lookback_used`
- `reason`
- `checked_lookback_windows`

## Trace Output

Each trace entry includes:

- `lookback_index`
- `window_label`
- `reference_timestamp`
- `context_month_label`
- `context_week_label`
- `PMH`
- `PML`
- `CMH`
- `CML`
- `PWH`
- `PWL`
- `CWH`
- `CWL`
- `current_price`
- base monthly-status result
- normalized / borrowed status
- trigger metadata
- whether that window was used for resolution

## Safety Principles

- Do not infer more monthly-status logic than the confirmed classroom/workbook rules support.
- Keep direct monthly structure separate from borrowed-state current-price transitions.
- Keep historical borrowing month/week-context based.
- Keep weekly reversal logic limited to non-confirmed states.
- Treat gap logic as a separate overlay until explicitly confirmed.
