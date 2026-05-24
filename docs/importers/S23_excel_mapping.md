# S23 Excel Mapping

## Purpose

This document records the current workbook-to-YAML mapping for `S23` before any automated YAML generation is implemented.

The goal is to make the importer behavior explicit, reviewable, and broker-agnostic.

Workbook analyzed:
- `D:\TradingEngineTFIS\data\All in One - TFIS 26-12-2023.xlsx`

Reference artifacts:
- `tmp/S23_formula_block_discovery.json`
- `tmp/S23_formula_block_discovery.md`
- `config/strategies/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml`

## Metadata Source

Canonical identity and metadata anchors:

- `AB2!B28` -> `strategy_code`
- `AB2!C28` -> `segment`
- `AB2!E28` -> `symbol`
- `AB2!F28` -> `expiry_type`
- `AB6 OS!C164` -> `unique_code`

Observed values:

- `AB2!B28 = S23`
- `AB2!C28 = OPTIONS SELL`
- `AB2!E28 = NIFTY`
- `AB2!F28 = WEEKLY`
- `AB6 OS!C164 = NIFTY_OP_SELL_WK_DIFF_2D_3D`

## Canonical Rule Source

The canonical human-readable S23 rule block is on `AB6 OS`, especially rows `162-172`.

This block contains four rule branches:

1. Bull / Bull CF Call
   - rows `162-163`
2. Bull / Bull CF Put
   - rows `165-166`
3. Bear / Bear CF Call
   - rows `168-169`
4. Bear / Bear CF Put
   - rows `171-172`

Interpretation:

- The first row of each branch holds the main entry, target, premium, and OI rule values.
- The second row of each branch holds the paired end-strike, minimum-premium, and SL / TRP values.
- Rows `175-180` contain entry timing and recalculation variants.
- Rows `183-188` contain position-open gap logic and current-day variants.

## Current Manual YAML Branch

The current manual YAML in `config/strategies/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D.yaml` represents:

- `Bull / Bull CF`
- `Call`

This matches the workbook branch on:

- `AB6 OS!D162 = BULL / BULL CF`
- `AB6 OS!F162 = Call`

## Field Mapping Table

| StrategyRule field | Workbook cell | Workbook raw value | Normalized YAML value | Confidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `allowed_monthly_statuses` | `AB6 OS!D162` | `BULL / BULL CF` | `["BULL", "BULL_CF"]` | High | Current manual YAML uses the Bull / Bull CF Call branch only. |
| `option_type` | `AB6 OS!F162` | `Call` | `CALL` | High | Bull/Bull CF Call branch. |
| `entry_time` | `AB6 OS!L175` | `09:24:59.400000` | `"09:24:59"` | Medium | Time normalization should trim workbook microseconds. There are mirrored entry-time cells in row `176`. |
| `recalculation_time` | `AB6 OS!C176` | `09:29:59.400000` | `"09:29:59"` | High | Also mirrored in `L176` and `L177`. |
| `start_strike_formula` | `AB6 OS!G162` | `( SPT : PRV : 3DLL + 5.00% ) & Round Down` | `ROUND_DOWN(PRV_3DLL + 5%)` | High | Base Bull / Bull CF Call rule. Rows `176` and `183` are recalculation/current-day variants, not the base rule. |
| `end_strike_formula` | `AB6 OS!G163` | `( SPT : PRV : 3DLL ) & Round Down - 1` | `ROUND_DOWN(PRV_3DLL) - 1` | High | Second row of the Bull / Bull CF Call branch. |
| `ideal_premium_formula` | `AB6 OS!H162` | `SPT : PRV : 3DLL * 1.20%` | `PRV_3DLL * 1.20%` | High | This differs from the current manual YAML, which uses `+ 1.20%`. |
| `minimum_premium_formula` | `AB6 OS!H163` | `SPT : PRV : 3DLL * 0.90%` | `PRV_3DLL * 0.90%` | High | This differs from the current manual YAML, which uses `+ 0.90%`. |
| `entry_formula` | `AB6 OS!M162` | `OPT : PRV : 3DLL - 7.50%` | `OPT_PRV_3DLL - 7.50%` or unresolved | High | Workbook uses `OPT`, not `SPT`, so formula normalization needs a clear premium-reference rule. |
| `target_formula` | `AB6 OS!O162` | `CE : Entry - 60.00%` | `ENTRY - 60%` | High | `CE : Entry` should normalize to `ENTRY` for this branch. |
| `stoploss_formula` | `AB6 OS!M163` | `Min ( CE : Entry + 60.00% & OPT : PRV : 2DHH + 7.00% )` | `MIN(ENTRY + 60%, OPT_PRV_2DHH + 7%)` or partially unresolved | High | `ENTRY` is clear; `OPT : PRV : 2DHH` still needs a canonical normalized name. |
| `minimum_oi` | `AB6 OS!I162` | `500 Lots` | `500` | High | Numeric normalization should strip the `Lots` suffix. |
| `carry_forward_allowed` | `AB6 OS!H160` and `AB6 OS!T160` | `Yes` | `true` or unresolved | Medium | Appears in operational continuation rows, not in the main branch rows. Keep reviewable. |

## Recommended Interpretation For S23

If the importer remains aligned with the current manual YAML, the base branch should be:

- monthly status family: `Bull / Bull CF`
- option type: `Call`
- source rows: `162-163`

Recommended base-cell mapping for that branch:

- `D162` -> monthly-status family
- `F162` -> option type
- `G162` -> start strike
- `G163` -> end strike
- `H162` -> ideal premium
- `H163` -> minimum premium
- `I162` -> minimum OI
- `M162` -> entry formula
- `O162` -> target formula
- `M163` -> stoploss formula

Timing support cells:

- `L175` -> entry time
- `C176` -> recalculation time

## Explicit Open Questions

1. Should `carry_forward_allowed` be sourced from `AB6 OS!H160` / `AB6 OS!T160`, or remain a manually configured field until that operational note is confirmed as canonical?
2. Should the four workbook branches become four separate `StrategyRule` configs, or should TFIS support one multi-branch strategy config with monthly-status and option-type routing?
3. Should premium formulas be normalized as multiplication of the reference value by percentage, since the workbook text uses `* 1.20%` and `* 0.90%`?
4. What is the exact normalized naming convention for workbook references like `OPT : PRV : 3DLL` and `OPT : PRV : 2DHH`?

## Current Recommendation

Do not generate replacement YAML from the workbook yet.

Reason:

- identity and branch mapping are now clear
- base rule cells are clear
- premium normalization and `OPT : PRV : ...` naming still need approval
- carry-forward sourcing still needs confirmation
