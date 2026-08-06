# S23 Trade Decision Explainer

## Session
- Strategy: `S23` / `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT`
- Session Date: `2026-05-28`
- Underlying Spot: `23780.0`

## Checkpoints
- `0915`: open `23895.0`, high `23910.0`, low `23882.0`, close `23902.0`
- `ORPT`: open `23902.0`, high `23918.0`, low `23890.0`, close `23912.0`
- `RC`: open `23912.0`, high `23920.0`, low `23896.0`, close `23907.0`

## Monthly Status
- Current Price Used: `23907.0`
- Source: `tfis_live_daily_history`
- Trigger: `BEAR_CF_CONTINUES`
- Result: `BEAR_CF`
- Notes: `Effective bearish confirmed monthly status remains bearish confirmed.`
- Lookback Used: `False`
- Resolution Reason: `Current month resolved directly from monthly structure rules.`

### Monthly Status Trace
- `current` (2026-05 / 2026-W22) @ `2026-05-28T09:29:59+05:30` -> base=`BEAR_CF` normalized=`BEAR_CF` via `BEAR_CF_B_THRESHOLD` (used=`True`)
  Levels: PMH `24900.0`, PML `24580.0`, CMH `24680.0`, CML `23882.0`, PWH `24680.0`, PWL `24220.0`, CWH `24410.0`, CWL `23882.0`, close `23907.0`

## Reference Levels
- `CDHH` = `23920.0` from `derived_from_checkpoints`
- `CDLL` = `23882.0` from `derived_from_checkpoints`
- `PRV_2DHH` = `24410.0` from `tfis_live_daily_history`
- `PRV_2DLL` = `24010.0` from `tfis_live_daily_history`
- `PRV_3DHH` = `24510.0` from `tfis_live_daily_history`
- `PRV_3DLL` = `24010.0` from `tfis_live_daily_history`
- `PRV_4DHH` = `24620.0` from `tfis_live_daily_history`
- `PRV_4DLL` = `24010.0` from `tfis_live_daily_history`

## Derived Current-Day Levels
- `CDHH`: `max(0915.high=23910.0, ORPT.high=23918.0, RC.high=23920.0)` = `23920.0`
- `CDLL`: `min(0915.low=23882.0, ORPT.low=23890.0, RC.low=23896.0)` = `23882.0`

## Option Reference Values
- `ENTRY` = `212.75` from `tfis_reference_packet`
- `OPT_PRV_2DHH` = `242.0` from `tfis_reference_packet`
- `OPT_PRV_3DLL` = `230.0` from `tfis_reference_packet`

## Formula Evaluation
- `start_strike`
  Formula: `ROUND_UP(PRV_3DHH - PARAM(strike_buffer_pct)%)`
  Resolved: `ROUND_UP(24510.0 - 5.0%)`
  Result: `23300.0`
- `end_strike`
  Formula: `ROUND_UP(PRV_3DHH) + PARAM(strike_step)`
  Resolved: `ROUND_UP(24510.0) + 50.0`
  Result: `24600.0`
- `ideal_premium`
  Formula: `PRV_3DHH * PARAM(ideal_premium_pct)%`
  Resolved: `24510.0 * 1.2%`
  Result: `294.12`
- `minimum_premium`
  Formula: `PRV_3DHH * PARAM(minimum_premium_pct)%`
  Resolved: `24510.0 * 0.9%`
  Result: `220.59000000000003`
- `entry`
  Formula: `OPT_PRV_3DLL - PARAM(entry_discount_pct)%`
  Resolved: `230.0 - 7.5%`
  Result: `212.75`
- `target`
  Formula: `ENTRY - PARAM(target_pct)%`
  Resolved: `212.75 - 60.0%`
  Result: `85.10000000000001`
- `stoploss`
  Formula: `MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_2DHH + PARAM(sl_reference_pct)%)`
  Resolved: `MIN(212.75 + 60.0%, 242.0 + 7.0%)`
  Result: `258.94`

## Contract Selection
- Range `23300` to `24600`, ideal premium `294.12`, minimum premium `220.59000000000003`, minimum OI `500`
- Selected: `NIFTY_20260604_23750_PE`
- Reason: `Selected first strike meeting ideal premium in rule-sheet search order.`

## Candidates
- `NIFTY_20260604_23650_PE` strike `23650.0` premium `221.0` OI `400.0` -> `REJECTED` (minimum_oi_not_met)
- `NIFTY_20260604_23700_PE` strike `23700.0` premium `285.0` OI `900.0` -> `PASSED` (passed)
- `NIFTY_20260604_23750_PE` strike `23750.0` premium `300.0` OI `1200.0` -> `SELECTED` (passed)
