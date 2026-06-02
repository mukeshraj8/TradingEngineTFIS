# Monthly Status Engine Design

## Current Status

- `StrategyBranchSelector` already exists and filters folder-based strategies by `MonthlyStatus`.
- `MonthlyStatusEngine` is now implemented for the currently confirmed threshold rules.
- `MonthlyStatus` can still be supplied externally or manually where needed.
- gap-up / gap-down behavior remains separate and is not part of the current engine.

## Implemented Deterministic Rules

The current engine classifies these statuses:

- `BULL`
- `BULL_CF`
- `BEAR`
- `BEAR_CF`
- `UNKNOWN`

Confirmed derived values:

- `bullish_value = PMH + a%`
- `bearish_value = PML - a%`

Confirmed trigger rules:

- `BULL`
  - `current_price >= PMH + a%`
- `BEAR`
  - `current_price <= PML - a%`
- `BULL_CF`
  - `current_price >= bullish_value + b%`
- `BEAR_CF`
  - `current_price <= bearish_value - b%`
- reversal bullish
  - `current_price >= MAX(PWH, CWH) + c%`
- reversal bearish
  - `current_price <= MIN(PWL, CWL) - c%`

Priority order:

1. reversal bearish -> `BEAR`
2. reversal bullish -> `BULL`
3. `BEAR_CF`
4. `BULL_CF`
5. `BEAR`
6. `BULL`
7. `UNKNOWN`

If reversal and continuation conflict, reversal dominates.

The current engine does not require monthly close confirmation.

## Inputs

The deterministic engine currently depends on:

- reference levels:
  - `PMH`
  - `PML`
  - `CMH`
  - `CML`
  - `PWH`
  - `PWL`
  - `CWH`
  - `CWL`
  - `current_price`
- configured thresholds from:
  - `config/monthly_status_thresholds.yaml`

## Engine Output

Current output model:

`MonthlyStatusResult`

- `status`
- `trigger_name`
- `threshold_value`
- `reversal_dominated`
- `candidates`
- `notes`

Current engine interface:

`MonthlyStatusEngine.classify(instrument_group, levels) -> MonthlyStatusResult`

The `candidates` field preserves the underlying monthly-status decision-table
rows for auditability.

## Relationship To The Decision Table

The decision table remains a diagnostic layer that exposes all candidate rows.

The engine now consumes those candidate rows plus the confirmed threshold
derivations to produce a final deterministic classification.

This keeps two separate but related artifacts:

- decision table:
  - transparent candidate visibility
- status engine:
  - final priority-based status selection

## UNKNOWN Lookback Resolution

When the threshold-only current monthly-status context remains `UNKNOWN`, TFIS
may replay the same monthly-status rules on prior historical contexts.

This lookback is monthly/weekly-context based, not daily-candle based.

For live and replay use, each lookback step must be built from a complete
historical context containing:

- previous month high / low
- current month high / low for that context
- previous week high / low
- current week high / low for that context
- the checkpoint close used as `current_price`

The expected sequence is:

1. current month/week context
2. previous month/week context
3. previous-to-previous month/week context

up to the configured safe lookback limit.

Normalization remains directional only:

- `BULL` or `BULL_CF` resolves to `BULL`
- `BEAR` or `BEAR_CF` resolves to `BEAR`

## Still Pending

The current engine intentionally does not implement:

- gap-up / gap-down overlays
- monthly close confirmation
- prior-status persistence
- carry-forward state logic
- rollover effects on monthly status
- any mandatory backtest coupling beyond consumers optionally using the engine output

An integration path now exists from:

- `MonthlyStatusEngine.classify(...)`
- to `StrategyBranchSelector.select(...)`

An opt-in historical backtest integration path now exists:

- backtests may provide monthly and weekly reference CSVs
- the engine may classify status per historical step
- eligible branch folders may then be selected from a strategy root

Default backtest behavior still remains manual and unchanged:

- `--strategy-path` continues to run one explicitly chosen strategy folder
- monthly-status-driven branch selection is enabled only when its dedicated CLI flags are supplied

## Safety Principles

- Do not infer more monthly-status logic than the confirmed threshold rules support.
- Keep completed monthly and weekly reference semantics explicit.
- Keep reason and audit evidence visible through candidate rows and selected trigger metadata.
- Treat gap logic as a separate overlay until explicitly confirmed.
