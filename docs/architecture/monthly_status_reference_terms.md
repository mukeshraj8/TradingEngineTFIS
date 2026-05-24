# Monthly Status Reference Terms

This document records terminology and threshold references for future monthly
status implementation without defining the full transition engine yet.

## Reference Terms

- `PMH` / `PML`
  - previous month high / previous month low
- `CMH` / `CML`
  - current month high / current month low
- `PWH` / `PWL`
  - previous week high / previous week low
- `CWH` / `CWL`
  - current week high / current week low

## Threshold Vocabulary

- `a`
- `b`
- `c`

These threshold values are now captured in config by instrument group, but their
exact use in monthly-status transitions is still pending final confirmation.

At a minimum, they should be treated as configurable reference percentages
rather than hard-coded logic.

## Graph Or Reference Source Guidance

- futures strategies should use the futures graph
- option selling should use the spot or equity graph
- stock option buying should use the stock or equity graph

## Reversal Month Note

- `CMH` and `CML` data is used until the reversal month date for reversal months
- the exact reversal transition rules are still pending confirmation and should
  not be guessed into code yet

## Current Status

- threshold configuration is captured
- full monthly status transition logic is still pending
- gap-up and gap-down handling remains a separate overlay
