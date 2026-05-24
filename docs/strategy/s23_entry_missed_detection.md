# S23 Entry-Missed Detection

## Purpose

This document records the first TFIS foundation for automatic S23 entry-missed
detection at ORPT.

This layer is intentionally:

- diagnostic only
- separate from base strategy formulas
- separate from the S23 recalculation formulas
- separate from historical backtest behavior

## Excel Rule

Excel entry check for both call-sell and put-sell entry:

- if `ORPT-time LL < Sell Entry`:
  - entry is missed
  - wait until recalculation time and recalculate
- otherwise:
  - entry is not missed
  - place order at ORPT

For S23:

- `ORPT = 09:24:59`
- `recalculation time = 09:29:59`

## First Implemented Detection Rule

For S23 option-selling branches:

- `entry_missed = option_low < entry_price`

Current scope:

- uses only the ORPT snapshot
- uses only `option_low`
- works for both `CALL` and `PUT` option-sell entry

This first version does not:

- scan intraday bars automatically
- infer the ORPT snapshot from a larger bar series
- run recalculation automatically
- change historical backtest behavior

## API Shape

The entry-missed foundation introduces:

- `EntryMissedInput`
- `EntryMissedResult`
- `S23EntryMissedDetector`

Audit output includes:

- whether the entry was missed
- the compared ORPT option low
- the entry-price threshold
- timestamp notes for the ORPT snapshot

## Relationship To Recalculation

This layer answers only:

- "Was the original S23 entry missed at ORPT?"

The recalculation layer remains separate and answers:

- "If entry was missed, what recalculated strike/premium/entry values should be used?"

## Open Boundaries

- This detector does not resolve any workbook ambiguity about the put-branch
  recalculated strike wording.
- That ambiguity remains tracked in:
  - [excel_ambiguity_audit.md](../importers/excel_ambiguity_audit.md)
  - [importer_open_questions.yaml](../../config/importer_open_questions.yaml)
