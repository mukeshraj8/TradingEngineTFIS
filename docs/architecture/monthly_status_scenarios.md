# Monthly Status Scenarios

## Purpose

These monthly-status scenarios are human-review fixtures for the diagnostic
decision-table layer.

They are intended to make the current threshold behavior reviewable without
pretending that TFIS already has a finished `MonthlyStatusEngine`.

## What These Scenarios Are

The scenario fixture file records:

- instrument group
- monthly and weekly reference levels
- expected candidate-row outcomes
- optional reference inputs such as `bullish_value` and `bearish_value`
- `expected_final_status: null`

The fixture path is:

- `tests/fixtures/monthly_status/monthly_status_scenarios.yaml`

## What These Scenarios Are Not

These scenarios are not:

- final monthly-status labels
- backtest inputs
- branch-selector inputs
- proof that transition rules are complete

They only validate the current decision-table candidate rows.

## Why Final Status Is Still Null

Each scenario keeps:

- `expected_final_status: null`

on purpose.

That makes the current project boundary explicit:

- candidate rows are reviewable now
- final status selection is deferred
- transition rules still require confirmation

## How These Fixtures Should Evolve Later

Once the monthly-status transition rules are confirmed, these same scenarios can
be extended with:

- expected final status
- expected previous-status interactions
- expected carry-forward reasoning
- expected gap-overlay effects where applicable

Until then, they remain diagnostic review artifacts only.
