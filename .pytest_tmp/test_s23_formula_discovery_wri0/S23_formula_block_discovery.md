# S23 Formula Block Discovery

Workbook: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_s23_formula_discovery_wri0\s23_discovery.xlsx`

## Field Candidates
### `allowed_monthly_statuses`
- Confidence: `high`
- Recommended extraction mapping: Use `AB6 OS!D162` for Bull/Bull CF and `AB6 OS!D168` for Bear/Bear CF rule families.
- Likely candidate cells:
  - `AB6 OS!D162` value=`BULL / BULL CF` formula=`BULL / BULL CF`

### `option_type`
- Confidence: `high`
- Recommended extraction mapping: Use the option-type cell on the same AB6 OS rule row as the selected monthly-status branch.
- Likely candidate cells:
  - `AB6 OS!F162` value=`Call` formula=`Call`

### `entry_time`
- Confidence: `medium`
- Recommended extraction mapping: Prefer `AB6 OS!L175` for call-sell ORPT entry time; confirm whether the row-176 mirrored `09:24:59` cell is the canonical source.
- Open question: The workbook shows both ORPT rows and mirrored timing rows. The canonical entry-time source should be confirmed before YAML generation.
- Likely candidate cells:
  - `AB6 OS!L175` value=`09:24:59` formula=`09:24:59`

### `recalculation_time`
- Confidence: `high`
- Recommended extraction mapping: Use the AB6 OS recalculation rows (`176-180`) with `09:29:59` as the primary source for recalculation time.
- Likely candidate cells:
  - `AB6 OS!C176` value=`09:29:59` formula=`09:29:59`

### `start_strike_formula`
- Confidence: `high`
- Recommended extraction mapping: Use `AB6 OS!G162` for the base Bull/Call start-strike rule. Treat `AB6 OS!M176` and the `R183`-style gap rows as recalculation or position-open variants.
- Likely candidate cells:
  - `AB6 OS!G162` value=`( SPT : PRV : 3DLL + 5.00% ) & Round Down` formula=`( SPT : PRV : 3DLL + 5.00% ) & Round Down`

### `end_strike_formula`
- Confidence: `high`
- Recommended extraction mapping: Use `AB6 OS!G163` for the base Bull/Call end-strike rule; the later timing rows look like recalculation variants.
- Likely candidate cells:
  - `AB6 OS!G163` value=`( SPT : PRV : 3DLL ) & Round Down - 1` formula=`( SPT : PRV : 3DLL ) & Round Down - 1`

### `ideal_premium_formula`
- Confidence: `high`
- Recommended extraction mapping: Use `AB6 OS!H162` for the base ideal premium and keep the timing rows as recalculation variants.
- Likely candidate cells:
  - `AB6 OS!H162` value=`SPT : PRV : 3DLL * 1.20%` formula=`SPT : PRV : 3DLL * 1.20%`

### `minimum_premium_formula`
- Confidence: `high`
- Recommended extraction mapping: Use `AB6 OS!H163` for the base minimum premium and treat the later rows as timing-gap variants.
- Likely candidate cells:
  - `AB6 OS!H163` value=`SPT : PRV : 3DLL * 0.90%` formula=`SPT : PRV : 3DLL * 0.90%`

### `entry_formula`
- Confidence: `high`
- Recommended extraction mapping: Use `AB6 OS!M162` as the Bull/Call entry formula; `AB6 OS!O162` is the first target expression tied to that entry.
- Likely candidate cells:
  - `AB6 OS!M162` value=`OPT : PRV : 3DLL - 7.50%` formula=`OPT : PRV : 3DLL - 7.50%`
  - `AB6 OS!O162` value=`CE : Entry  - 60.00%` formula=`CE : Entry  - 60.00%`

### `target_formula`
- Confidence: `high`
- Recommended extraction mapping: Use the target column on AB6 OS (`O`) for each rule row; `AB6 OS!O162` is the Bull/Call target formula.
- Likely candidate cells:
  - `AB6 OS!O162` value=`CE : Entry  - 60.00%` formula=`CE : Entry  - 60.00%`

### `stoploss_formula`
- Confidence: `high`
- Recommended extraction mapping: Use the AB6 OS row immediately below each entry row for the paired SL/TRP formula; `AB6 OS!M163` is the Bull/Call stoploss formula.
- Likely candidate cells:
  - `AB6 OS!M163` value=`Min ( CE : Entry  + 60.00% & OPT : PRV : 2DHH + 7.00% )` formula=`Min ( CE : Entry  + 60.00% & OPT : PRV : 2DHH + 7.00% )`

### `minimum_oi`
- Confidence: `high`
- Recommended extraction mapping: Use the AB6 OS OI column (`I`) on the selected rule row. The current workbook text is `500 Lots`, so numeric normalization will still be needed later.
- Open question: The workbook stores OI as `500 Lots`, so a later normalization rule is needed to strip the unit text safely.
- Likely candidate cells:
  - `AB6 OS!I162` value=`500 Lots` formula=`500 Lots`

### `carry_forward_allowed`
- Confidence: `medium`
- Recommended extraction mapping: Tentatively map carry-forward permission from the `Yes` cells on the AB6 OS close-at-03:00 continuation rules.
- Open question: Carry-forward appears in operational note rows rather than the main rule table, so the canonical source should be confirmed.
- Likely candidate cells:
  - `AB6 OS!H160` value=`Yes` formula=`Yes`

## Sheet Anchors

### `AB6 OS`
- Anchor `C163` = `S23`
- Anchor `C164` = `NIFTY_OP_SELL_WK_DIFF_2D_3D`
- Nearby non-empty cells captured: `15`

### `AB14`
- Anchor `E48` = `S23`
- Anchor `E49` = `NIFTY_OP_SELL_WK_DIFF_2D_3D`
- Nearby non-empty cells captured: `2`

### `AB15`
- Anchor `C13` = `S23`
- Anchor `G13` = `NIFTY_OP_SELL_WK_DIFF_2D_3D`
- Nearby non-empty cells captured: `2`

### `AB16`
- Anchor `E102` = `S23`
- Anchor `E105` = `NIFTY_OP_SELL_WK_DIFF_2D_3D`
- Nearby non-empty cells captured: `2`

## Open Questions
- entry_time: The workbook shows both ORPT rows and mirrored timing rows. The canonical entry-time source should be confirmed before YAML generation.
- minimum_oi: The workbook stores OI as `500 Lots`, so a later normalization rule is needed to strip the unit text safely.
- carry_forward_allowed: Carry-forward appears in operational note rows rather than the main rule table, so the canonical source should be confirmed.
