# S23 Paper Session Review

## Session

- Session ID: `stale-selected-quote`
- Session Date: `2026-05-08`
- Strategy: `S23`
- Terminal State: `ABORTED`
- Readiness Status: `ABORTED`
- Terminal Reason Code: `stale_ingest_quote`
- Terminal Reason: Paper quote event exceeded the allowed freshness window at ingestion time.

## Guardrails

- Guardrail Code: `stale_ingest_quote`
- Guardrail Message: Paper quote event exceeded the allowed freshness window at ingestion time.
- Blocking Event Type: `SELECTED_CONTRACT_QUOTE`
- Blocking Source ID: `n/a`
- Operator Action Required: Refresh the affected live-paper data source before planning S23.

## Selected Contract

- Available: `False`
- Symbol: `n/a`
- Option Type: `n/a`
- Strike: `n/a`
- Expiry: `n/a`
- LTP: `n/a`

## Order Plan

- Available: `False`
- Summary: no paper order plan was created for this session.

## Order Intent

- Available: `False`
- Status: `INTENT_SKIPPED`
- Execution Shell Status: `n/a`
- Dispatch Shell Status: `n/a`
- Handoff Shell Status: `n/a`
- Future Fill Simulation Eligible: `False`
- Order Side: `n/a`
- Lots: `n/a`
- Quantity: `n/a`
- Planned Entry Price: `n/a`
- Target Price: `n/a`
- Stoploss Price: `n/a`
- FSL Price: `n/a`
- Order Reference: `n/a` at `n/a`
- Source Branch: `n/a`
- Source Workbook Rule: `n/a`
- Bundle Validated: `True`
- Historical Comparison Status: `n/a`
- Historical Comparison Go / No-Go: n/a
- Historical Comparison Reason: n/a
- Latest Shell Guardrail Code: `n/a`
- Latest Shell Guardrail Message: n/a
- Blocking Event Type: `n/a`
- Blocking Source ID: `n/a`
- Operator Action Required: Refresh the affected live-paper data source before planning S23.
- Disclaimer: No order was placed, no fill was simulated, no position was opened, and no lifecycle monitoring occurred yet; this is a pre-execution paper-shell journal.

## Fill Phase 1

- Available: `False`
- Summary: no Phase 1 fill or no-fill artifact is present for this session yet.

## Lifecycle Phase 2

- Available: `False`
- Summary: no Phase 2 same-day lifecycle artifact is present for this session yet.

## Provenance

- Cost/Slippage Version: `paper-cost-v1`
- Data Source Count: `8`
- Source Types: `broker_fyers, live_paper_config, normalized_archive_export`
- Source IDs: `D:/TradingData/captures/context_sessions/2026-05-08/live_20260508_092504_prod_pid19984/monthly_status.json, D:/TradingData/captures/context_sessions/2026-05-08/live_20260508_092504_prod_pid19984/ticks_context.csv, D:\TradingEngineTFISRefactored\.pytest_tmp\test_stale_selected_contract_q0\paper.s23.yaml, fyers:quotes:nifty, normalized_snapshot:0915, normalized_snapshot:orpt, normalized_snapshot:rc`
- Synthetic Fixture Used: `True`

## Freshness

- Selected Contract Quote Present: `False`
- Quote Effective Timestamp: `n/a`
- Quote Captured Timestamp: `n/a`
- Planning Timestamp: `n/a`
- Quote Age Seconds At Planning: `n/a`
- Warning Flags: `none`
- Stale Warning Present: `False`

## Replay Bundle

- Bundle Manifest Present: `True`
- Validation Performed: `True`
- Bundle Valid: `True`
- Bundle Errors: `none`
- Bundle Warnings: `none`

## Audit Timeline

- `2026-05-08T09:00:51+05:30` `NOT_STARTED->PRE_MARKET_READY` `COST_SLIPPAGE_SETTINGS` reason=`pre_market_inputs_ready` terminal=`n/a` guardrail=`n/a`
- `2026-05-08T09:00:51+05:30` `PRE_MARKET_READY->WAITING_FOR_0915` `COST_SLIPPAGE_SETTINGS` reason=`awaiting_0915_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-08T09:15:01+05:30` `WAITING_FOR_0915->WAITING_FOR_ORPT` `UNDERLYING_SNAPSHOT` reason=`awaiting_orpt_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-08T09:25:01+05:30` `WAITING_FOR_ORPT->WAITING_FOR_RC` `UNDERLYING_SNAPSHOT` reason=`awaiting_rc_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-08T09:30:02+05:30` `WAITING_FOR_RC->ABORTED` `SELECTED_CONTRACT_QUOTE` reason=`ingest_guardrail_failed` terminal=`stale_ingest_quote` guardrail=`stale_ingest_quote`

## Safety Note

- No order was placed, no fill was simulated, no position was opened, and no lifecycle monitoring occurred yet; this review covers planning and fillless pre-execution shell artifacts only.
