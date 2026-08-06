# S23 Extraction Comparison

Manual YAML: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_s23_extractor_writes_comp0\S23.yaml`

## Matched Fields
- `strategy_code` = `S23`
- `unique_code` = `NIFTY_OP_SELL_WK_DIFF_2D_3D`
- `symbol` = `NIFTY`
- `segment` = `OPTIONS_SELL`

## Mismatched Fields
- None

## Fields Missing From Excel Extraction
- `allowed_monthly_statuses`
- `option_type`
- `entry_time`
- `recalculation_time`
- `start_strike_formula`
- `end_strike_formula`
- `ideal_premium_formula`
- `minimum_premium_formula`
- `entry_formula`
- `target_formula`
- `stoploss_formula`
- `minimum_oi`
- `carry_forward_allowed`

## Fields Present Only In Manual YAML
- `allowed_monthly_statuses`
- `entry_time`
- `recalculation_time`
- `start_strike_formula`
- `end_strike_formula`
- `ideal_premium_formula`
- `minimum_premium_formula`
- `entry_formula`
- `target_formula`
- `stoploss_formula`
- `minimum_oi`
- `carry_forward_allowed`

## Recommendation
- `safe_to_generate_yaml`: `false`
- Reason: Formula, timing, and monthly-status fields are still unresolved.
