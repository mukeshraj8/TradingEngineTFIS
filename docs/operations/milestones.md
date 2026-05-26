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
- a broader `AB6 OS` recalculation audit across rows `162-191` is now captured, confirming no extra target override formulas in that block and identifying `Z183:Z186` as workbook-backed current-day entry cells
- workbook-backed current-day option-entry overrides from `AB6 OS!Z183:Z186` are now implemented for supported rows `183-186`
- expiry-day lifecycle review is available in historical reports when selected contract expiry metadata exists
- opt-in option-chain contract selection realism is available in historical backtests
- opt-in contract-specific lifecycle pricing is available when symbol-keyed intraday bars exist for the selected contract
- contract-specific lifecycle provenance now records selected symbol, bar availability, fallback reason, and actual lifecycle price source per trade
- a normalized apples-to-apples lifecycle-source report pair is now in place; on the current fixture set it now isolates 10 trades using real selected-contract bars, 0 explicit fallback, 100.0% lifecycle coverage, and one lifecycle-source-only P&L delta
- a dedicated S23 contract archive ingestion plan is now documented so the next realism step can move from deterministic fixtures toward normalized real/archive contract bars without changing S23 logic
- an S23-only paper-trading readiness audit is now documented, and the current readiness conclusion is explicitly `NO-GO` until paper-runtime data, execution, visibility, and failure-handling gaps are closed
- S23 live-paper normalized data contract and session state-machine blueprints are now documented, defining the next safe implementation boundary for paper runtime scaffolding
- read-only shared captured-data adapter is available for normalized CSV roots
- comparison reporting across historical backtest modes is available as a read-only reporting tool
- S23 mode comparison reporting is now bounded, deterministic, and summary-based rather than relying on unbounded raw JSON comparison
- S23 mode comparison now records input-dataset paths, cost settings, and apples-to-apples status; the earlier row-183 `current_day_fsl_trp` exit flip did not reproduce after rerunning all six modes on one shared dataset set
- quality snapshot:
  - tests passing: `274`
  - `python scripts/validate_project.py`: passed

## Completed

- S23 15:00 position-open continuation audited as process-only; numeric continuation rule remains blocked pending new workbook evidence.
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
- contract-specific lifecycle provenance now records selected symbol, bar availability, fallback reason, and actual lifecycle price source per trade
- a normalized apples-to-apples lifecycle-source report pair is now in place; on the current fixture set it now isolates 10 trades using real selected-contract bars, 0 explicit fallback, 100.0% lifecycle coverage, and one lifecycle-source-only P&L delta
- read-only shared captured-data adapter foundation
- S23 option rollover clarified as not applicable
- expiry-day lifecycle review and audit for selected contracts
- cell-level audit for S23 current-day FSL / TRP rows `183-188`
- comparison reporting across historical backtest modes
- bounded and deterministic S23 historical mode comparison reporting
- apples-to-apples S23 mode comparison rerun with shared datasets and shared cost settings
- deterministic apples-to-apples applied-case fixture added for S23 current-day FSL / TRP row-183 validation
- broader `AB6 OS` rows `162-191` recalculation audit completed, confirming no workbook-backed target overrides in that block and flagging `Z183:Z186` as workbook-backed current-day entry cells
- workbook-backed current-day option-entry overrides from `AB6 OS!Z183:Z186` implemented for supported rows `183-186`
- S23 live-paper normalized data contract blueprint documented
- S23 paper-session state-machine blueprint documented

## Next Recommended Priorities

- S23 live-paper schema scaffolding and required-field validation
- S23 paper-session orchestrator skeleton and session manifest writer
- S23 paper execution journaling and operator-facing session artifacts
- broader real/archive contract-specific coverage pilot
- raw shared capture-format adapters beyond normalized CSV roots

## Explicitly Pending

- S23 live-paper schema scaffolding and required-field validation
- S23 paper-session orchestrator skeleton and session manifest writer
- S23 paper execution journaling and operator-facing session artifacts
- fuller strike-availability realism and broader contract-specific archive coverage
- raw shared capture-format adapters beyond normalized CSV roots
- futures rollover lifecycle module
- monthly option buying engine
- broker adapters
- paper runtime
- live runtime

## Notes

- The current project is strong on offline rule validation, workbook tracing, and structural backtesting.
- Production-grade runtime behavior is intentionally deferred until the remaining governance, paper-session orchestration, failure handling, and market-data layers are clarified.