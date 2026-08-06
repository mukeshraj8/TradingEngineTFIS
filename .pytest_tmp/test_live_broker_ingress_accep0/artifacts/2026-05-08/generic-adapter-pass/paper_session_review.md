# S23 Paper Session Review

## Session

- Session ID: `generic-adapter-pass`
- Session Date: `2026-05-08`
- Strategy: `S23`
- Terminal State: `ORDER_PLANNED`
- Readiness Status: `READY`
- Terminal Reason Code: `paper_order_planned`
- Terminal Reason: Paper order plan created successfully; execution and fills have not started.

## Guardrails

- Guardrail Code: `n/a`
- Guardrail Message: n/a
- Blocking Event Type: `n/a`
- Blocking Source ID: `n/a`
- Operator Action Required: n/a

## Selected Contract

- Available: `True`
- Symbol: `NIFTY_20260512_25000_PE`
- Option Type: `PUT`
- Strike: `25000.0`
- Expiry: `2026-05-12`
- LTP: `799.1`

## Order Plan

- Available: `True`
- Selected Contract Symbol: `NIFTY_20260512_25000_PE`
- Monthly Status: `BEAR`
- Planning Timestamp: `2026-05-08T09:30:04+05:30`
- Overlays Enabled: `S23_CURRENT_DAY_FSL_TRP`
- Required Snapshots: `0915, ORPT, RC`

## Order Intent

- Available: `True`
- Status: `INTENT_READY`
- Execution Shell Status: `n/a`
- Dispatch Shell Status: `n/a`
- Handoff Shell Status: `n/a`
- Future Fill Simulation Eligible: `False`
- Order Side: `SELL`
- Lots: `1`
- Quantity: `100`
- Planned Entry Price: `798.3`
- Target Price: `791.85`
- Stoploss Price: `816.35`
- FSL Price: `816.35`
- Order Reference: `RC` at `2026-05-08T09:29:59+05:30`
- Source Branch: `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT`
- Source Workbook Rule: `AB6_OS_Z186`
- Bundle Validated: `True`
- Historical Comparison Status: `n/a`
- Historical Comparison Go / No-Go: n/a
- Historical Comparison Reason: n/a
- Latest Shell Guardrail Code: `n/a`
- Latest Shell Guardrail Message: n/a
- Blocking Event Type: `n/a`
- Blocking Source ID: `n/a`
- Operator Action Required: n/a
- Disclaimer: No order was placed, no fill was simulated, no position was opened, and no lifecycle monitoring occurred yet; this is a pre-execution paper-shell journal.

## Fill Phase 1

- Available: `False`
- Summary: no Phase 1 fill or no-fill artifact is present for this session yet.

## Lifecycle Phase 2

- Available: `False`
- Summary: no Phase 2 same-day lifecycle artifact is present for this session yet.

## Provenance

- Cost/Slippage Version: `paper-cost-v1`
- Data Source Count: `11`
- Source Types: `archive_export, live_paper_config, normalized_archive_export`
- Source IDs: `D:/TradingData/captures/context_sessions/2026-05-08/live_20260508_092504_prod_pid19984/monthly_status.json, D:/TradingData/captures/context_sessions/2026-05-08/live_20260508_092504_prod_pid19984/ticks_context.csv, D:\TradingEngineTFISRefactored\.pytest_tmp\test_live_broker_ingress_accep0\paper.s23.yaml, normalized_option_chain:2026-05-08, normalized_selected_contract:NSE:NIFTY2651225000PE, normalized_snapshot:0915, normalized_snapshot:orpt, normalized_snapshot:rc, normalized_trade_plan:s23_bear_put_row186, normalized_underlying_quote:nifty`
- Synthetic Fixture Used: `False`

## Freshness

- Selected Contract Quote Present: `True`
- Quote Effective Timestamp: `2026-05-08T09:29:59+05:30`
- Quote Captured Timestamp: `2026-05-08T09:30:02+05:30`
- Planning Timestamp: `2026-05-08T09:30:04+05:30`
- Quote Age Seconds At Planning: `2.0`
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
- `2026-05-08T09:30:02+05:30` `WAITING_FOR_RC->DECISION_READY` `SELECTED_CONTRACT_QUOTE` reason=`planning_inputs_ready` terminal=`n/a` guardrail=`n/a`
- `2026-05-08T09:30:04+05:30` `DECISION_READY->ORDER_PLANNED` `NONE` reason=`paper_order_plan_created` terminal=`n/a` guardrail=`n/a`

## Safety Note

- No order was placed, no fill was simulated, no position was opened, and no lifecycle monitoring occurred yet; this review covers planning and fillless pre-execution shell artifacts only.
