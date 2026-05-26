# Milestones

## Current Snapshot

- offline TFIS architecture and backtest foundation is in place
- strategy and workbook normalization work is established for the S23 family
- reference materials are now indexed and reviewable through archive metadata
- deterministic monthly-status classification is implemented for the confirmed threshold rules
- optional monthly-status-driven branch selection is available in historical backtests
- opt-in S23 missed-entry detection and recalculation is available in historical backtests
- opt-in S23 current-day FSL / TRP missed / not-missed handling is available in historical backtests
- dedicated spot intraday sourcing is available for the opt-in S23 recalculation path
- S23 put-side recalculated strike wording is resolved as a confirmed workbook correction
- S23 option rollover is clarified as not applicable
- `AB6 OS` current-day FSL / TRP rows `183-188` are now cell-audited and implemented only within their confirmed workbook-backed scope
- expiry-day lifecycle review is available in historical reports when selected contract expiry metadata exists
- opt-in option-chain contract selection realism is available in historical backtests
- opt-in contract-specific lifecycle pricing is available when symbol-keyed intraday bars exist for the selected contract
- read-only shared captured-data adapter is available for normalized CSV roots
- comparison reporting across historical backtest modes is available as a read-only reporting tool
- quality snapshot:
  - tests passing: `265`
  - `python scripts/validate_project.py`: passed

## Completed

- broker-agnostic architecture
- strategy folder layout
- S23 all four branches
- Excel cross-checks
- formula safety validation
- branch selector
- strategy registry governance
- strategy registry enforcement
- shared market-data direction
- reference materials indexed
- review workflow added
- archive governance added
- historical lifecycle backtesting
- EOD policies
- cost and slippage model
- rupee P&L reporting
- equity curve and drawdown reporting
- monthly-status thresholds
- monthly-status decision table
- monthly-status engine
- optional monthly-status-driven historical branch selection
- monthly-status CLI report
- monthly-status manual scenarios
- S23 missed-entry detection foundation
- opt-in S23 historical recalculation mode
- dedicated spot intraday sourcing for opt-in S23 recalculation
- opt-in S23 current-day FSL / TRP missed / not-missed handling
- opt-in option-chain contract selection realism foundation
- opt-in contract-specific lifecycle pricing foundation
- read-only shared captured-data adapter foundation
- S23 option rollover clarified as not applicable
- expiry-day lifecycle review and audit for selected contracts
- cell-level audit for S23 current-day FSL / TRP rows `183-188`
- comparison reporting across historical backtest modes

## Next Recommended Priorities

- broader missed-entry / recalculation engine beyond the current S23 diagnostic mode
- fuller strike-availability realism and broader contract-specific archive coverage
- raw shared capture-format adapters beyond normalized CSV roots
- futures rollover lifecycle module

## Explicitly Pending

- broader missed-entry / recalculation engine beyond the current S23 diagnostic mode
- fuller strike-availability realism and broader contract-specific archive coverage
- raw shared capture-format adapters beyond normalized CSV roots
- futures rollover lifecycle module
- monthly option buying engine
- broker adapters
- paper runtime
- live runtime

## Notes

- The current project is strong on offline rule validation, workbook tracing, and structural backtesting.
- Production-grade runtime behavior is intentionally deferred until the remaining governance, monthly-status, lifecycle, and market-data layers are clarified.
