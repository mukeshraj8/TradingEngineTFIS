# Milestones

## Current Snapshot

- offline TFIS architecture and backtest foundation is in place
- strategy and workbook normalization work is established for the S23 family
- reference materials are now indexed and reviewable through archive metadata
- deterministic monthly-status classification is implemented for the confirmed threshold rules
- optional monthly-status-driven branch selection is available in historical backtests
- opt-in S23 missed-entry detection and recalculation is available in historical backtests
- dedicated spot intraday sourcing is available for the opt-in S23 recalculation path
- S23 put-side recalculated strike wording is resolved as a confirmed workbook correction
- opt-in option-chain contract selection realism is available in historical backtests
- quality snapshot:
  - tests passing: `236`
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
- opt-in option-chain contract selection realism foundation

## Next Recommended Priorities

- shared captured-data adapter from `TradingEngine`
- rollover lifecycle module
- gap-up / gap-down engine
- broader missed-entry / recalculation engine beyond the current S23 diagnostic mode
- contract-specific option-chain intraday pricing and strike-availability realism

## Explicitly Pending

- shared captured-data adapter from `TradingEngine`
- rollover lifecycle module
- gap-up / gap-down engine
- broader missed-entry / recalculation engine beyond the current S23 diagnostic mode
- contract-specific option-chain intraday pricing and strike-availability realism
- monthly option buying engine
- broker adapters
- paper runtime
- live runtime

## Notes

- The current project is strong on offline rule validation, workbook tracing, and structural backtesting.
- Production-grade runtime behavior is intentionally deferred until the remaining governance, monthly-status, lifecycle, and market-data layers are clarified.
