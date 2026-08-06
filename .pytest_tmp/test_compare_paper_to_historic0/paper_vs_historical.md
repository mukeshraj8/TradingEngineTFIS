# S23 Paper vs Historical Comparison

## Summary

- Status: `MATCH`
- Go / No-Go: GO: the persisted paper intent matches the expected historical trade-plan decision and the execution, dispatch, and handoff shells are acceptable.
- Reason: All compared planning fields matched and the execution, dispatch, and handoff shells are acceptable.
- Session ID: `cli-paper-compare`
- Session Date: `2026-05-27`
- Strategy: `S23`
- Paper Terminal State: `ORDER_PLANNED`
- Paper Intent Status: `INTENT_READY`
- Execution Shell Status: `EXECUTION_ARMED`
- Dispatch Shell Status: `ORDER_INTENT_DISPATCHED`
- Handoff Shell Status: `PAPER_EXECUTION_HANDOFF_READY`
- Fill Status: `n/a`
- Fill Reason Code: `n/a`
- Fill Price: `n/a`
- Fill Timestamp: `n/a`
- Lifecycle Status: `n/a`
- Exit Reason Code: `n/a`
- Historical Trade Key: `2026-05-27T15:30:00|NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT|PUT`
- Historical Timestamp: `2026-05-27T15:30:00`
- Bundle Validation Performed: `True`
- Bundle Valid: `True`
- Lifecycle Comparable: `True`
- Same-Day Policy: This parity policy applies only to same-day S23 paper lifecycle sessions. Strategy-level carry-forward may be valid, but this comparison path does not yet support multi-session carry-forward outcomes.

## Planning Comparison

| Field | Paper | Historical | Matched | Severity | Notes |
| --- | --- | --- | --- | --- | --- |
| `strategy_code` | `S23` | `S23` | `True` | `blocker` | Values matched. |
| `symbol` | `NIFTY` | `NIFTY` | `True` | `blocker` | Values matched. |
| `option_type` | `PUT` | `PUT` | `True` | `blocker` | Values matched. |
| `selected_contract_symbol` | `NIFTY_20260528_22400_PE` | `NIFTY_20260528_22400_PE` | `True` | `blocker` | Values matched. |
| `source_branch_unique_code` | `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT` | `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT` | `True` | `blocker` | Values matched. |
| `workbook_row_number` | `186` | `186` | `True` | `blocker` | Numeric fields matched within tolerance 0.0100. |
| `source_rule` | `AB6_OS_Z186` | `AB6_OS_Z186` | `True` | `blocker` | Values matched. |
| `entry_price` | `199.5000` | `199.5000` | `True` | `blocker` | Numeric fields matched within tolerance 0.0100. |
| `target_price` | `80.0000` | `80.0000` | `True` | `blocker` | Numeric fields matched within tolerance 0.0100. |
| `stoploss_price` | `320.0000` | `320.0000` | `True` | `blocker` | Numeric fields matched within tolerance 0.0100. |
| `fsl_price` | `n/a` | `n/a` | `True` | `warn` | Both paper and historical values are unavailable. |
| `start_strike` | `21470.0000` | `21470.0000` | `True` | `warn` | Numeric fields matched within tolerance 0.0100. |
| `end_strike` | `22601.0000` | `22601.0000` | `True` | `warn` | Numeric fields matched within tolerance 0.0100. |
| `ideal_premium` | `271.2000` | `271.2000` | `True` | `warn` | Numeric fields matched within tolerance 0.0100. |
| `minimum_premium` | `203.4000` | `203.4000` | `True` | `warn` | Numeric fields matched within tolerance 0.0100. |
| `current_day_fsl_trp_overlay_enabled` | `True` | `True` | `True` | `blocker` | Boolean field matched. |
| `recalculation_overlay_enabled` | `False` | `False` | `True` | `blocker` | Boolean field matched. |
| `option_chain_selected` | `True` | `True` | `True` | `blocker` | Boolean field matched. |
| `slippage_entry_points` | `1.0000` | `1.0000` | `True` | `warn` | Numeric fields matched within tolerance 0.0100. |
| `slippage_exit_points` | `1.0000` | `1.0000` | `True` | `warn` | Numeric fields matched within tolerance 0.0100. |

## Execution-Shell Readiness

- Intent Status: `INTENT_READY`
- Execution Shell Status: `EXECUTION_ARMED`
- Dispatch Shell Status: `ORDER_INTENT_DISPATCHED`
- Handoff Shell Status: `PAPER_EXECUTION_HANDOFF_READY`
- Fill Status: `n/a`
- Fill Reason Code: `n/a`
- Fill Message: n/a
- Lifecycle Status: `n/a`
- Exit Reason Code: `n/a`
- Exit Price: `n/a`
- Exit Timestamp: `n/a`
- Gross P&L (Rupees): `n/a`
- Net P&L (Rupees): `n/a`
- Historical Exit Price: `120.0`
- Historical Net P&L (Rupees): `3825.0`
- Execution Reason Code: `paper_execution_handoff_ready`
- Guardrail Code: `n/a`
- Guardrail Message: n/a
- Operator Action Required: n/a
- Historical Comparison Status Used For Arming: `MATCH`
- Historical Comparison Go / No-Go Used For Arming: GO: the persisted paper intent matches the expected historical trade-plan decision.
- Historical Comparison Reason Used For Arming: Paper and historical planning fields matched.

## Lifecycle Parity

- Comparable: `True`
- Parity Reason: No fill or lifecycle parity fields are applicable yet.
- Lifecycle Status: `n/a`
- Exit Reason Code: `n/a`
- Historical Exit Reason Code: `n/a`
- Historical Exit Outcome: `n/a`
- Exit Price: `n/a`
- Historical Exit Price: `120.0`
- Exit Timestamp: `n/a`
- Historical Exit Timestamp: `n/a`
- Exact Lifecycle Matches: `0`
- Acceptable Drift Fields: `0`
- Lifecycle Mismatches: `0`
- Lifecycle Partial Fields: `0`

| Field | Paper | Historical | Matched | Acceptable Drift | Severity | Tolerance | Explanation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `n/a` | n/a | n/a | `False` | `False` | `info` | n/a | No lifecycle parity fields were applicable for this session. |

## P&L Drift

- Paper Gross P&L (Rupees): `n/a`
- Paper Net P&L (Rupees): `n/a`
- Historical Net P&L (Rupees): `3825.0`
- Net P&L Drift (Paper - Historical): `n/a`
- Acceptable Drift Fields Count: `0`
- Go / No-Go Interpretation: GO: the persisted paper intent matches the expected historical trade-plan decision and the execution, dispatch, and handoff shells are acceptable.
- Same-Day Only Policy: This parity policy applies only to same-day S23 paper lifecycle sessions. Strategy-level carry-forward may be valid, but this comparison path does not yet support multi-session carry-forward outcomes.

## Provenance

- Paper Session Directory: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_compare_paper_to_historic0\paper_sessions\2026-05-27\cli-paper-compare`
- Replay Bundle Directory: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_compare_paper_to_historic0\paper_sessions\2026-05-27\cli-paper-compare`
- Historical Report: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_compare_paper_to_historic0\historical_cli.json`
- Paper Synthetic Fixture Used: `True`
- Historical Synthetic Fixture Used: `True`
- Paper Cost Version: `paper-cost-v1`
- Historical Cost Model: `{'slippage_points_per_side': 1.0, 'brokerage_points_per_trade': 0.5, 'other_cost_points_per_trade': 0.5}`

## Warnings

- None.

## Disclaimer

- No order was placed, no fill was simulated, no position was opened, and no lifecycle monitoring occurred yet; this comparison only checks whether the persisted paper intent aligns with the expected historical trade-plan output.
- No real broker order was placed, no real-money position was opened, and no lifecycle monitoring occurred outside the same-day paper-only simulator; this output validates planning parity, execution shell readiness, and same-day-only paper lifecycle drift policy.
