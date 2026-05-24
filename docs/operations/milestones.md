# Milestones

## Current Snapshot

- offline TFIS architecture and backtest foundation is in place
- strategy and workbook normalization work is established for the S23 family
- reference materials are now indexed and reviewable through archive metadata
- deterministic monthly-status classification is implemented for the confirmed threshold rules
- quality snapshot:
  - tests passing: `196`
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
- monthly-status CLI report
- monthly-status manual scenarios

## Next Recommended Priorities

- gap-up / gap-down engine
- missed-entry / recalculation engine
- shared captured-data adapter from `TradingEngine`
- rollover lifecycle module
- monthly option buying engine

## Explicitly Pending

- gap-up / gap-down engine
- missed-entry / recalculation engine
- shared captured-data adapter from `TradingEngine`
- rollover lifecycle module
- monthly option buying engine
- real option-chain and strike-availability simulation
- broker adapters
- paper runtime
- live runtime

## Notes

- The current project is strong on offline rule validation, workbook tracing, and structural backtesting.
- Production-grade runtime behavior is intentionally deferred until the remaining governance, monthly-status, lifecycle, and market-data layers are clarified.
