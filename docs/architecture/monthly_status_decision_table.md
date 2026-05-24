# Monthly Status Decision Table

## Purpose

This document describes the monthly-status decision-table layer for TFIS.

The decision table is still a diagnostic and specification artifact. It now
supports the implemented `MonthlyStatusEngine`, but it is intentionally kept
separate from the final engine classification step.

## Current Scope

The current decision table:

- accepts configured threshold percentages by instrument group
- accepts transparent monthly and weekly reference levels
- computes candidate rows for observable threshold checks
- does not choose a final monthly status by itself
- does not persist prior state
- does not perform close-confirmation logic

The current branch selector can still accept externally supplied monthly status
without directly depending on this diagnostic layer.

## Reference Inputs

The current decision-table input model uses these observable reference levels:

- `PMH`
- `PML`
- `CMH`
- `CML`
- `PWH`
- `PWL`
- `CWH`
- `CWL`
- `current_price`

Threshold percentages come from:

- `config/monthly_status_thresholds.yaml`

## Candidate Rows Encoded

The decision table produces candidate rows only.

### Direct candidates

- `BULL_A_THRESHOLD`
  - condition: `current_price >= PMH + a%`
- `BEAR_A_THRESHOLD`
  - condition: `current_price <= PML - a%`

### Carry-forward style candidates

- `BULL_CF_B_THRESHOLD`
  - condition: `current_price >= bullish_value + b%`
- `BEAR_CF_B_THRESHOLD`
  - condition: `current_price <= bearish_value - b%`

If `bullish_value` or `bearish_value` is not yet available, the decision table
does not fail. Instead it emits:

- `condition_met = None`
- `threshold_value = None`
- `confidence = LOW`

This behavior is still important because it lets TFIS preserve unresolved
workbook logic without pretending the engine already knows a missing reference.

### Reversal-style candidates

- `REVERSAL_BULL_C_THRESHOLD`
  - condition: `current_price >= MAX(PWH, CWH) + c%`
- `REVERSAL_BEAR_C_THRESHOLD`
  - condition: `current_price <= MIN(PWL, CWL) - c%`

## Confidence Semantics

The current implementation uses intentionally simple confidence values:

- `HIGH`
  - direct `PMH` / `PML` observable threshold rows
- `MEDIUM`
  - reversal rows and resolved `BULL_CF` / `BEAR_CF` rows
- `LOW`
  - unresolved `BULL_CF` / `BEAR_CF` rows where the required reference input
    is not yet available

These confidence values remain diagnostic labels only. They are not
position-sizing inputs.

## Relationship To The Engine

The implemented `MonthlyStatusEngine` uses:

- configured thresholds
- reference levels
- candidate rows from this decision table
- deterministic trigger priority

The decision table itself still does not:

- choose one final monthly status
- resolve prior-state persistence
- apply gap overlays
- require monthly close confirmation

Keeping the decision table separate makes audit and test coverage easier:

- candidate rows remain visible
- final engine selection remains explicit

## What This Still Does Not Do

The decision table intentionally does not:

- choose one final monthly status on its own
- store previous status
- include gap-up or gap-down overlays
- include monthly close confirmation
- integrate directly with backtesting or branch selection

## Open Questions Still Pending

The main unresolved points now sit around the layers above the confirmed
threshold engine:

- how gap-up / gap-down logic modifies or overlays the base rules
- whether monthly close confirmation will ever be required later
- how previous-status persistence should be modeled
- how backtests should record and consume monthly-status reasons over time

## Review Benefit

This layer remains useful even after the engine exists because it provides:

- transparent candidate visibility
- straightforward fixture-based review
- a stable audit trail for final monthly-status selection
