# S23 Trade Decision Stage Explainer

- Session Date: `2026-05-28`
- Strategy: `S23` / `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL`
- Stage: `RC Snapshot` at `09:30`
- This report is written immediately after the stage completes so monthly status can be checked without waiting for later checkpoints.

## RC Snapshot (09:30)
- Captured At: `2026-05-28T09:30:00+05:30`
- NIFTY Spot Used: `23780.0`
- Available Checkpoints: `0915, ORPT, RC`
- Waiting For: `none`
- Current Day High So Far (`CDHH`): `23920.0`
- Current Day Low So Far (`CDLL`): `23882.0`
- Monthly Status Price Used: `23907.0`
- Monthly Status: `BEAR_CF` via `BEAR_CF_CONTINUES`
- Monthly Status Notes: `Effective bearish confirmed monthly status remains bearish confirmed.`
- Monthly Status Lookback Used: `False`
- Monthly Status Resolution Reason: `Current month resolved directly from monthly structure rules.`
- Can Finalize Trade Decision: `True`

### Snapshot Logic
- `0915` from `2026-05-28T09:14:00+05:30` to `2026-05-28T09:14:59+05:30`: open `23895.0`, high `23910.0`, low `23882.0`, close `23902.0` -> used at this stage
- `ORPT` from `2026-05-28T09:24:00+05:30` to `2026-05-28T09:24:59+05:30`: open `23902.0`, high `23918.0`, low `23890.0`, close `23912.0` -> used at this stage
- `RC` from `2026-05-28T09:29:00+05:30` to `2026-05-28T09:29:59+05:30`: open `23912.0`, high `23920.0`, low `23896.0`, close `23907.0` -> used at this stage

### Monthly Status Trace
- `current` (2026-05 / 2026-W22) @ `2026-05-28T09:29:59+05:30` -> base=`BEAR_CF` normalized=`BEAR_CF` via `BEAR_CF_B_THRESHOLD` (used=`True`)
  Levels: PMH `24900.0`, PML `24580.0`, CMH `24680.0`, CML `23882.0`, PWH `24680.0`, PWL `24220.0`, CWH `24410.0`, CWL `23882.0`, close `23907.0`

### Market Reference Values
- `PRV_2DHH` = `24410.0` from `tfis_live_daily_history`
- `PRV_2DLL` = `24010.0` from `tfis_live_daily_history`
- `PRV_3DHH` = `24510.0` from `tfis_live_daily_history`
- `PRV_3DLL` = `24010.0` from `tfis_live_daily_history`
- `PRV_4DHH` = `24620.0` from `tfis_live_daily_history`
- `PRV_4DLL` = `24010.0` from `tfis_live_daily_history`
- `CDHH` = `23920.0` from `derived_from_available_checkpoints`
- `CDLL` = `23882.0` from `derived_from_available_checkpoints`

### Option Reference Values
- `OPT_PRV_2DHH` = `242.0` from `tfis_reference_packet`
- `OPT_PRV_2DLL` = `210.0` from `tfis_reference_packet`
- `OPT_PRV_3DHH` = `260.0` from `tfis_reference_packet`
- `OPT_PRV_3DLL` = `230.0` from `tfis_reference_packet`

### Provisional Formula Evaluation
- `start_strike`
  Formula: `ROUND_DOWN(PRV_2DLL + PARAM(strike_buffer_pct)%)`
  Resolved: `ROUND_DOWN(24010.0 + 5.0%)`
  Result: `25200.0`
- `end_strike`
  Formula: `ROUND_DOWN(PRV_2DLL) - PARAM(strike_step)`
  Resolved: `ROUND_DOWN(24010.0) - 50.0`
  Result: `23950.0`
- `ideal_premium`
  Formula: `PRV_2DLL * PARAM(ideal_premium_pct)%`
  Resolved: `24010.0 * 1.2%`
  Result: `288.12`
- `minimum_premium`
  Formula: `PRV_2DLL * PARAM(minimum_premium_pct)%`
  Resolved: `24010.0 * 0.9%`
  Result: `216.09000000000003`
- `entry`
  Formula: `OPT_PRV_2DLL - PARAM(entry_discount_pct)%`
  Resolved: `210.0 - 7.5%`
  Result: `194.25`
- `target`
  Formula: `ENTRY - PARAM(target_pct)%`
  Resolved: `194.25 - 60.0%`
  Result: `77.7`
- `stoploss`
  Formula: `MIN(ENTRY + PARAM(sl_entry_pct)%, OPT_PRV_3DHH + PARAM(sl_reference_pct)%)`
  Resolved: `MIN(194.25 + 60.0%, 260.0 + 10.0%)`
  Result: `286.0`

### Final Decision At This Stage
- Selected Contract: `NIFTY_20260604_25000_CE`
- Expiry: `2026-06-04`
- Strike: `25000.0`
- Option Type: `CALL`
- Premium: `285.0`
- OI: `1200.0`
- Entry: `194.25`
- Target: `77.7`
- Stoploss: `286.0`
- Selection Reason: `Selected first strike meeting minimum premium in reverse rule-sheet search order.`
