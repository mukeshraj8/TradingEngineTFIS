# S23 Paper Session Review

## Session

- Session ID: `context_session`
- Session Date: `2026-05-27`
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
- Symbol: `NIFTY_20260602_23200_PE`
- Option Type: `PUT`
- Strike: `23200.0`
- Expiry: `2026-06-02`
- LTP: `774.8`

## Order Plan

- Available: `True`
- Selected Contract Symbol: `NIFTY_20260602_23200_PE`
- Monthly Status: `BEAR_CF`
- Planning Timestamp: `2026-05-27T09:30:02+05:30`
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
- Planned Entry Price: `773.4`
- Target Price: `768.2`
- Stoploss Price: `781.2`
- FSL Price: `781.2`
- Order Reference: `RC` at `2026-05-27T09:29:59+05:30`
- Source Branch: `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT`
- Source Workbook Rule: `TRADINGENGINE_CAPTURE_VALIDATION_PRELUDE`
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

- Cost/Slippage Version: `capture-suite-cost-v1`
- Data Source Count: `9`
- Source Types: `tfis_validation_prelude, tradingengine_capture`
- Source IDs: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\TradingData\captures\context_sessions\2026-05-27\context_session\ticks_context.csv, D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\TradingData\data\nifty\20260527\options\index\NIFTY50_option_quotes_20260527.csv, validation_calendar:2026-05-27, validation_costs:2026-05-27, validation_monthly_status:2026-05-27, validation_paper_config:2026-05-27, validation_trade_plan:2026-05-27`
- Synthetic Fixture Used: `False`

## Freshness

- Selected Contract Quote Present: `True`
- Quote Effective Timestamp: `2026-05-27T09:29:59+05:30`
- Quote Captured Timestamp: `2026-05-27T09:30:01+05:30`
- Planning Timestamp: `2026-05-27T09:30:02+05:30`
- Quote Age Seconds At Planning: `1.0`
- Warning Flags: `none`
- Stale Warning Present: `False`

## Replay Bundle

- Bundle Manifest Present: `True`
- Validation Performed: `True`
- Bundle Valid: `True`
- Bundle Errors: `none`
- Bundle Warnings: `none`

## Audit Timeline

- `2026-05-27T09:00:51+05:30` `NOT_STARTED->PRE_MARKET_READY` `COST_SLIPPAGE_SETTINGS` reason=`pre_market_inputs_ready` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:00:51+05:30` `PRE_MARKET_READY->WAITING_FOR_0915` `COST_SLIPPAGE_SETTINGS` reason=`awaiting_0915_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:15:00+05:30` `WAITING_FOR_0915->WAITING_FOR_ORPT` `UNDERLYING_SNAPSHOT` reason=`awaiting_orpt_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:24:59+05:30` `WAITING_FOR_ORPT->WAITING_FOR_RC` `UNDERLYING_SNAPSHOT` reason=`awaiting_rc_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:30:01+05:30` `WAITING_FOR_RC->DECISION_READY` `SELECTED_CONTRACT_QUOTE` reason=`planning_inputs_ready` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:30:02+05:30` `DECISION_READY->ORDER_PLANNED` `NONE` reason=`paper_order_plan_created` terminal=`n/a` guardrail=`n/a`

## Safety Note

- No order was placed, no fill was simulated, no position was opened, and no lifecycle monitoring occurred yet; this review covers planning and fillless pre-execution shell artifacts only.
