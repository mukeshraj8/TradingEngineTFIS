# S23 Paper Session Review

## Session

- Session ID: `cli-review-session`
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
- Symbol: `NIFTY_20260528_22400_PE`
- Option Type: `PUT`
- Strike: `22400.0`
- Expiry: `2026-05-28`
- LTP: `199.5`

## Order Plan

- Available: `True`
- Selected Contract Symbol: `NIFTY_20260528_22400_PE`
- Monthly Status: `BULL`
- Planning Timestamp: `2026-05-27T09:30:10+05:30`
- Overlays Enabled: `S23_CURRENT_DAY_FSL_TRP`
- Required Snapshots: `0915, ORPT, RC`

## Order Intent

- Available: `False`
- Summary: no execution-journal intent shell is present for this session.

## Fill Phase 1

- Available: `False`
- Summary: no Phase 1 fill or no-fill artifact is present for this session yet.

## Lifecycle Phase 2

- Available: `False`
- Summary: no Phase 2 same-day lifecycle artifact is present for this session yet.

## Provenance

- Cost/Slippage Version: `paper-cost-v1`
- Data Source Count: `8`
- Source Types: `paper_fixture`
- Source IDs: `calendar_context-source, cost_slippage_settings-source, monthly_status_input-source, option_chain_snapshot-source, paper_session_config-source, selected_contract_quote-source, underlying_quote-source, underlying_snapshot-source`
- Synthetic Fixture Used: `True`

## Freshness

- Selected Contract Quote Present: `True`
- Quote Effective Timestamp: `2026-05-27T09:29:59+05:30`
- Quote Captured Timestamp: `2026-05-27T09:30:00+05:30`
- Planning Timestamp: `2026-05-27T09:30:10+05:30`
- Quote Age Seconds At Planning: `10.0`
- Warning Flags: `none`
- Stale Warning Present: `False`

## Replay Bundle

- Bundle Manifest Present: `True`
- Validation Performed: `True`
- Bundle Valid: `True`
- Bundle Errors: `none`
- Bundle Warnings: `none`

## Audit Timeline

- `2026-05-27T09:03:01+05:30` `NOT_STARTED->PRE_MARKET_READY` `COST_SLIPPAGE_SETTINGS` reason=`pre_market_inputs_ready` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:03:01+05:30` `PRE_MARKET_READY->WAITING_FOR_0915` `COST_SLIPPAGE_SETTINGS` reason=`awaiting_0915_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:15:01+05:30` `WAITING_FOR_0915->WAITING_FOR_ORPT` `UNDERLYING_SNAPSHOT` reason=`awaiting_orpt_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:25:00+05:30` `WAITING_FOR_ORPT->WAITING_FOR_RC` `UNDERLYING_SNAPSHOT` reason=`awaiting_rc_snapshot` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:30:00+05:30` `WAITING_FOR_RC->DECISION_READY` `SELECTED_CONTRACT_QUOTE` reason=`planning_inputs_ready` terminal=`n/a` guardrail=`n/a`
- `2026-05-27T09:30:10+05:30` `DECISION_READY->ORDER_PLANNED` `NONE` reason=`paper_order_plan_created` terminal=`n/a` guardrail=`n/a`

## Safety Note

- No order was placed, no fill was simulated, no position was opened, and no lifecycle monitoring occurred yet; this review covers planning and fillless pre-execution shell artifacts only.
