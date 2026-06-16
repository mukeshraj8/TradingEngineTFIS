# Monthly Status Logic

This document is the clean text version of the workbook/classroom monthly-status
logic currently implemented in TFIS.

## Reference Terms

- `PMH` = Previous Month High
- `PML` = Previous Month Low
- `CMH` = Current Month High
- `CML` = Current Month Low
- `PWH` = Previous Week High
- `PWL` = Previous Week Low
- `CWH` = Current Week High
- `CWL` = Current Week Low
- `Price` = current spot / checkpoint close used for the day

For NIFTY / BANKNIFTY:

- `a = 0.75%`
- `b = 0.75%`
- `c = 0.15%`

## Step 1: Determine Direct Monthly Structure

Derived values:

- `Bullish Value = PMH + a%`
- `Bearish Value = PML - a%`
- `Bullish Confirmed Value = Bullish Value + b%`
- `Bearish Confirmed Value = Bearish Value - b%`

Direct monthly structure:

- `BULL`
  - if `CMH >= Bullish Value`
- `BULL_CF`
  - if `CMH >= Bullish Confirmed Value`
- `BEAR`
  - if `CML <= Bearish Value`
- `BEAR_CF`
  - if `CML <= Bearish Confirmed Value`
- `UNKNOWN`
  - if neither side is breached decisively

## Step 2: Borrow If Current Month Is UNKNOWN

If the current month is `UNKNOWN`:

1. treat the previous month as the current month
2. compare it against its own previous month
3. keep going month by month backward
4. stop when a resolved status is found or when the safe lookback limit is hit

Borrowing preserves the historical resolved state:

- `BULL` stays `BULL`
- `BULL_CF` stays `BULL_CF`
- `BEAR` stays `BEAR`
- `BEAR_CF` stays `BEAR_CF`

## Step 3: Apply Current-Price Transition Rules

Once an effective state exists, evaluate today’s price.

### If effective state is `BULL`

- if `Price >= Bullish Confirmed Value`
  - status = `BULL_CF`
- else if `Price <= min(PWL, CWL) - c%`
  - status = `BEAR`
- else
  - status remains `BULL`

### If effective state is `BULL_CF`

- if `Price <= Bearish Value`
  - status = `BEAR`
- else
  - status remains `BULL_CF`

### If effective state is `BEAR`

- if `Price <= Bearish Confirmed Value`
  - status = `BEAR_CF`
- else if `Price >= max(PWH, CWH) + c%`
  - status = `BULL`
- else
  - status remains `BEAR`

### If effective state is `BEAR_CF`

- if `Price >= Bullish Value`
  - status = `BULL`
- else
  - status remains `BEAR_CF`

## Important Distinction

Weekly reversal checks are only for non-confirmed states:

- `BULL` -> `BEAR` via `min(PWL, CWL) - c%`
- `BEAR` -> `BULL` via `max(PWH, CWH) + c%`

Confirmed states reverse only via the stronger monthly threshold:

- `BULL_CF` -> `BEAR` via `PML - a%`
- `BEAR_CF` -> `BULL` via `PMH + a%`

## June 3, 2026 Worked Example

From the manually prepared workbook note:

- June 2026 = `UNKNOWN`
- borrow May 2026
- May 2026 = `UNKNOWN`
- borrow April 2026
- April 2026 = `UNKNOWN`
- borrow March 2026
- March 2026 = `BEAR_CF`

Therefore:

- as of `2026-06-03`, monthly status = `BEAR_CF`
