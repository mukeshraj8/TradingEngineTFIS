# S23 Strategy Implementation

This document describes the **implemented** S23 logic in TFIS as of the current
codebase.

It is intended to answer one question clearly:

**What exact strategy logic does TFIS run today for S23?**

This document covers:

- branch selection
- strike-range computation
- premium thresholds
- entry, target, and stoploss formulas
- ORPT missed-entry recalculation
- current-day `FSL / TRP` handling
- option-chain contract selection
- same-day lifecycle exit rules
- expiry-day handling
- intentionally blocked or unsupported paths

It does **not** describe future ideas or unimplemented workbook hypotheses.

## 1. Scope And Boundaries

Current S23 scope in TFIS:

- `S23` only
- `NIFTY` only
- weekly options only
- same-day paper and historical lifecycle support exists
- next-day continuation is strategy-valid, but the current paper runtime still
  implements same-day-only execution
- expiry handling and next-contract rollover policy are not yet fully
  implemented in runtime
- no multi-position handling inside the S23 paper runtime

Important boundary:

- `carry_forward_allowed: true` exists in config as workbook-derived metadata
- S23 should be treated as a carry-forward strategy family
- TFIS does **not** yet implement next-day carry-forward lifecycle behavior in
  the current paper runtime
- rows `190-191` were audited and do **not** currently provide a trusted
  numeric continuation-stoploss rule in the implemented paper scope

## 2. Branch Matrix

S23 is implemented as four normalized branch configs.

| Branch | Monthly Statuses | Option Type | Workbook Rows | Unique Code |
| --- | --- | --- | --- | --- |
| Bull / Bull CF Call | `BULL`, `BULL_CF` | `CALL` | `162-163` | `NIFTY_OP_SELL_WK_DIFF_2D_3D` |
| Bull / Bull CF Put  | `BULL`, `BULL_CF` | `PUT`  | `165-166` | `NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT` |
| Bear / Bear CF Call | `BEAR`, `BEAR_CF` | `CALL` | `168-169` | `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL` |
| Bear / Bear CF Put  | `BEAR`, `BEAR_CF` | `PUT`  | `171-172` | `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT` |

Branch selection principle:

- monthly status is determined upstream
- once status is known, TFIS routes to the matching branch family
- within that family, the branch config fixes the option side and formulas

## 3. Timing Anchors

Implemented timing anchors:

- `09:15:00`
  - current-day `FSL / TRP` trigger check
- `09:24:59`
  - `ORPT`
  - base entry time
  - current-day not-missed row calculations use the ORPT snapshot
- `09:29:59`
  - recalculation time
  - ORPT missed-entry recalculation uses this snapshot
  - current-day missed `FSL / TRP` rows use this snapshot

## 4. Formula Semantics Used By TFIS

TFIS uses a closed formula language.

Important meanings:

- `ROUND_DOWN(x)` = `floor(x)`
- `ROUND_UP(x)` = `ceil(x)`
- `X + 5%` means `X * 1.05`
- `X - 7.5%` means `X * 0.925`
- `X * 1.20%` means `X * 0.012`
- `ENTRY - 60%` means `ENTRY * 0.40`
- `ENTRY + 60%` means `ENTRY * 1.60`
- `MIN(a, b)` and `MAX(a, b)` are literal numeric minimum/maximum

Market aliases used in S23:

- `PRV_2DHH`
- `PRV_2DLL`
- `PRV_3DHH`
- `PRV_3DLL`

Option reference aliases used in S23:

- `OPT_PRV_2DHH`
- `OPT_PRV_2DLL`
- `OPT_PRV_3DHH`
- `OPT_PRV_3DLL`

Shared S23 parameters:

- `strike_buffer_pct = 1.2`
- `ideal_premium_pct = 1.20`
- `minimum_premium_pct = 0.90`
- `entry_discount_pct = 7.50`
- `target_pct = 60.0`
- `sl_entry_pct = 60.0`
- `sl_reference_pct = 7.0`
- `minimum_oi = 500`

## 5. Base Branch Formulas

### 5.1 Bull / Bull CF Call

Status family:

- `BULL`
- `BULL_CF`

Option side:

- `CALL`

Base formulas:

- `start_strike = floor(PRV_3DLL * 1.05)`
- `end_strike = floor(PRV_3DLL) - 1`
- `ideal_premium = PRV_3DLL * 0.012`
- `minimum_premium = PRV_3DLL * 0.009`
- `entry = OPT_PRV_3DLL * 0.925`
- `target = ENTRY * 0.40`
- `stoploss = min(ENTRY * 1.60, OPT_PRV_2DHH * 1.07)`

### 5.2 Bull / Bull CF Put

Status family:

- `BULL`
- `BULL_CF`

Option side:

- `PUT`

Base formulas:

- `start_strike = ceil(PRV_2DHH * 0.95)`
- `end_strike = ceil(PRV_2DHH) + 1`
- `ideal_premium = PRV_2DHH * 0.012`
- `minimum_premium = PRV_2DHH * 0.009`
- `entry = OPT_PRV_2DLL * 0.925`
- `target = ENTRY * 0.40`
- `stoploss = min(ENTRY * 1.60, OPT_PRV_3DHH * 1.07)`

### 5.3 Bear / Bear CF Call

Status family:

- `BEAR`
- `BEAR_CF`

Option side:

- `CALL`

Base formulas:

- `start_strike = floor(PRV_2DLL * 1.05)`
- `end_strike = floor(PRV_2DLL) - 1`
- `ideal_premium = PRV_2DLL * 0.012`
- `minimum_premium = PRV_2DLL * 0.009`
- `entry = OPT_PRV_2DLL * 0.925`
- `target = ENTRY * 0.40`
- `stoploss = min(ENTRY * 1.60, OPT_PRV_3DHH * 1.07)`

### 5.4 Bear / Bear CF Put

Status family:

- `BEAR`
- `BEAR_CF`

Option side:

- `PUT`

Base formulas:

- `start_strike = ceil(PRV_3DHH * 0.95)`
- `end_strike = ceil(PRV_3DHH) + 1`
- `ideal_premium = PRV_3DHH * 0.012`
- `minimum_premium = PRV_3DHH * 0.009`
- `entry = OPT_PRV_3DLL * 0.925`
- `target = ENTRY * 0.40`
- `stoploss = min(ENTRY * 1.60, OPT_PRV_2DHH * 1.07)`

## 6. Normal Scenario Flow

This is the base S23 path when no special overlay changes the plan.

1. Determine monthly status.
2. Select the matching S23 branch.
3. Compute:
   - strike range
   - ideal premium
   - minimum premium
   - entry
   - target
   - stoploss
4. At `09:24:59`, use the branch output as the working trade plan.
5. If option-chain selection is enabled:
   - freeze a concrete contract symbol from the chain
6. Lifecycle then checks:
   - whether entry price is touched
   - whether target or stoploss is hit
   - otherwise square off at EOD if that policy is enabled

## 7. ORPT Missed-Entry Recalculation

This is separate from the base formulas and is opt-in.

Detection rule at `ORPT`:

- `entry_missed = option_low_at_09:24:59 < base_entry_price`

If entry is not missed:

- base trade plan remains in force

If entry is missed:

- TFIS waits for `09:29:59`
- recalculates:
  - `start_strike`
  - `end_strike`
  - `ideal_premium`
  - `minimum_premium`
  - `entry_price`
- TFIS does **not** currently recalculate:
  - `target_price`
  - `stoploss_price`

### 7.1 Recalculation formulas by branch

#### Bull / Bull CF Call recalculation

- `reference = min(PRV_3DLL, recalc_spot_low)`
- `entry_reference = min(OPT_PRV_3DLL, recalc_option_low)`
- `start = floor(reference * 1.05)`
- `end = floor(reference) - 1`
- `ideal = reference * 0.012`
- `minimum = reference * 0.009`
- `entry = entry_reference * 0.925`

#### Bear / Bear CF Call recalculation

- `reference = min(PRV_2DLL, recalc_spot_low)`
- `entry_reference = min(OPT_PRV_2DLL, recalc_option_low)`
- `start = floor(reference * 1.05)`
- `end = floor(reference) - 1`
- `ideal = reference * 0.012`
- `minimum = reference * 0.009`
- `entry = entry_reference * 0.925`

#### Bull / Bull CF Put recalculation

- `strike_reference = max(PRV_2DHH, recalc_spot_high)`
- `premium_reference = min(PRV_2DHH, recalc_spot_low)`
- `entry_reference = min(OPT_PRV_2DLL, recalc_option_low)`
- `start = ceil(strike_reference * 0.95)`
- `end = ceil(strike_reference) + 1`
- `ideal = premium_reference * 0.012`
- `minimum = premium_reference * 0.009`
- `entry = entry_reference * 0.925`

#### Bear / Bear CF Put recalculation

- `strike_reference = max(PRV_3DHH, recalc_spot_high)`
- `premium_reference = min(PRV_3DHH, recalc_spot_low)`
- `entry_reference = min(OPT_PRV_3DLL, recalc_option_low)`
- `start = ceil(strike_reference * 0.95)`
- `end = ceil(strike_reference) + 1`
- `ideal = premium_reference * 0.012`
- `minimum = premium_reference * 0.009`
- `entry = entry_reference * 0.925`

## 8. Current-Day FSL / TRP Handling

This is a separate opt-in layer driven by workbook rows `183-188`.

Trigger rule at `09:15:00`:

- `fsl_trp_missed = current_day_option_high_at_09:15 > base_stoploss_price`

This layer may override:

- strike range
- premium thresholds
- entry price
- stoploss price

It does **not** invent missing formulas when the workbook leaves fields blank.

### 8.1 Row 183: Bull / Bull CF Call not missed

Applied when:

- branch = Bull / Bull CF Call
- `09:15` trigger is **not** missed

Formulas:

- `reference = min(PRV_3DLL, CDLL_at_ORPT)`
- `entry_reference = min(OPT_PRV_3DLL, OPT_CDLL_at_ORPT)`
- `start = floor(reference * 1.05)`
- `end = floor(reference) - 1`
- `ideal = reference * 0.012`
- `minimum = reference * 0.009`
- `entry_override = entry_reference * 0.925`
- `target = inherited from base trade plan`
- `stoploss = inherited from base trade plan`

Lifecycle starts after:

- `09:24:59`

### 8.2 Row 184: Bull / Bull CF Call missed

Applied when:

- branch = Bull / Bull CF Call
- `09:15` trigger **is** missed

Important workbook-resolved detail:

- TFIS implements row `184` exactly as workbook-directed
- although the branch context is Bull / Bull CF Call, the row uses the
  Put-side `Q/R/S/U/W/Z` family and TFIS preserves that implementation

Formulas:

- `strike_reference = max(PRV_2DHH, CDHH_at_recalc)`
- `premium_reference = min(PRV_2DHH, CDLL_at_recalc)`
- `entry_reference = min(OPT_PRV_2DLL, OPT_CDLL_at_recalc)`
- `start = ceil(strike_reference * 0.95)`
- `end = ceil(strike_reference) + 1`
- `ideal = premium_reference * 0.012`
- `minimum = premium_reference * 0.009`
- `entry_override = entry_reference * 0.925`
- `new_fsl = current_day_option_high_at_recalc * 1.07`
- `target = inherited from base trade plan`

Lifecycle starts after:

- `09:29:59`

### 8.3 Row 185: Bear / Bear CF Call missed

Applied when:

- branch = Bear / Bear CF Call
- `09:15` trigger **is** missed

Formulas:

- `reference = min(PRV_2DLL, CDLL_at_recalc)`
- `entry_reference = min(OPT_PRV_2DLL, OPT_CDLL_at_recalc)`
- `start = floor(reference * 1.05)`
- `end = floor(reference) - 1`
- `ideal = reference * 0.012`
- `minimum = reference * 0.009`
- `entry_override = entry_reference * 0.925`
- `new_fsl = current_day_option_high_at_recalc * 1.10`
- `target = inherited from base trade plan`

Lifecycle starts after:

- `09:29:59`

### 8.4 Row 186: Bear / Bear CF Put not missed

Applied when:

- branch = Bear / Bear CF Put
- `09:15` trigger is **not** missed

Formulas:

- `strike_reference = max(PRV_3DHH, CDHH_at_ORPT)`
- `premium_reference = min(PRV_3DHH, CDLL_at_ORPT)`
- `entry_reference = min(OPT_PRV_3DLL, OPT_CDLL_at_ORPT)`
- `start = ceil(strike_reference * 0.95)`
- `end = ceil(strike_reference) + 1`
- `ideal = premium_reference * 0.012`
- `minimum = premium_reference * 0.009`
- `entry_override = entry_reference * 0.925`
- `target = inherited from base trade plan`
- `stoploss = inherited from base trade plan`

Lifecycle starts after:

- `09:24:59`

### 8.5 Row 187: Bull / Bull CF Put missed

Applied when:

- branch = Bull / Bull CF Put
- `09:15` trigger **is** missed

Implemented scope:

- `FSL-only`

Formula:

- `new_fsl = current_day_option_high_at_recalc * 1.10`

Not recalculated because workbook fields are blank:

- `start_strike`
- `end_strike`
- `ideal_premium`
- `minimum_premium`
- `entry_price`
- `target_price`

Lifecycle starts after:

- `09:29:59`

### 8.6 Row 188: Bear / Bear CF Put missed

Applied when:

- branch = Bear / Bear CF Put
- `09:15` trigger **is** missed

Implemented scope:

- `FSL-only`

Formula:

- `new_fsl = current_day_option_high_at_recalc * 1.07`

Not recalculated because workbook fields are blank:

- `start_strike`
- `end_strike`
- `ideal_premium`
- `minimum_premium`
- `entry_price`
- `target_price`

Lifecycle starts after:

- `09:29:59`

### 8.7 Unsupported current-day paths

These are intentionally **not** inferred:

- Bull / Bull CF Put not missed
- Bear / Bear CF Call not missed

When those paths are encountered:

- TFIS keeps the base trade plan
- TFIS records a warning instead of guessing logic

## 9. CE / PE Strike And Contract Selection

There are two levels of selection.

### 9.1 Formula-level strike window

Each branch first produces:

- option type
- start strike
- end strike
- ideal premium
- minimum premium
- minimum OI

This is the **rule-level** strike window.

### 9.2 Actual contract selection from option chain

If option-chain selection is enabled, TFIS freezes a concrete selected contract.

Required option-chain fields:

- `timestamp`
- `symbol`
- `option_type`
- `strike`
- `expiry`
- `bid`
- `ask`
- `ltp`
- `oi`
- `volume`

Selection logic:

1. Keep only rows at the request timestamp.
2. Keep only rows matching the intended underlying and expiry.
3. Keep only rows matching branch option type.
4. Keep only strikes within the computed strike range.
5. Keep only contracts with:
   - `oi >= minimum_oi`
6. Keep only contracts with:
   - `ltp >= minimum_premium`
7. Among remaining contracts, choose the minimum by this tuple:
   - `abs(ltp - ideal_premium)`
   - `-oi`
   - `strike`
   - `symbol`

Interpretation:

- first preference is premium closeness to the ideal premium
- higher OI wins ties
- deterministic strike and symbol ordering break any remaining ties

Operational note:

- static `selected_contract_symbol` config may still exist for smoke or replay overrides
- operational paper selection should use normalized option-chain records with OI
- if OI is missing for otherwise-eligible candidates, selection must fail safely

If no candidate survives any step:

- TFIS does not invent a contract
- the trade is rejected with an explicit reason

## 10. Entry And Exit Logic After A Plan Exists

### 10.1 Entry

For historical and same-day paper lifecycle simulation, entry is considered
filled only if the option bar touches the planned entry price:

- `bar.low <= entry_price <= bar.high`

If no bar ever touches entry:

- result is `NO_ENTRY`

### 10.2 Exit rules for a SELL option position

After entry:

- `target_hit` if `bar.low <= target_price`
- `stoploss_hit` if `bar.high >= stoploss_price`

If both target and stoploss appear in the same bar:

- TFIS uses the conservative rule
- result = `STOPLOSS_HIT`

This same conservative same-bar rule is used in both:

- historical lifecycle simulation
- paper same-day lifecycle simulation

### 10.3 EOD square-off

If the position is open and neither target nor stoploss is hit by the last
available bar:

- with `square_off_at_close`, TFIS exits at the last available close
- exit reason = `EOD_SQUARE_OFF`

### 10.4 P&L sign convention

For a SELL option trade:

- points P&L = `entry_price - exit_price`

In paper same-day lifecycle:

- gross P&L = `(entry_price - exit_price) * quantity`
- net P&L applies configured costs if the shell includes them

## 11. Expiry Handling

Expiry handling is explicit, but currently incomplete in runtime.

If a selected contract exists and its expiry date equals the evaluation date:

- S23 requires full exit on that day
- the position must not be carried past expiry
- any move into the next expiry contract must happen through strategy-specific
  expiry handling rather than by carrying the expired contract

Expiry-day compliance is satisfied if exit reason is one of:

- `NO_ENTRY`
- `TARGET_HIT`
- `STOPLOSS_HIT`
- `EOD_SQUARE_OFF`

If an expiry-day contract would remain open:

- TFIS raises an expiry-day audit warning
- it does **not** yet convert that into the required expiry-handling or
  next-expiry rollover behavior

## 12. Contract-Specific Lifecycle Source

When contract-specific lifecycle mode is enabled:

- TFIS tries to use the exact selected-contract intraday series

If symbol-specific bars are missing:

- TFIS can fall back to the generic option intraday series
- that fallback is explicitly audited

In the current normalized fixture-backed S23 comparison:

- selected-contract lifecycle coverage is `100%`
- generic fallback is `0%`

This is a data-realism policy, not a change to the S23 formulas themselves.

## 13. What TFIS Intentionally Does Not Implement For S23

The following are intentionally blocked or unresolved:

- the exact runtime implementation for next-day carry-forward monitoring
- the exact runtime implementation for strategy-specific T-1 / T-2 expiry
  handling into the next contract
- any invented current-day branch formulas where workbook cells are blank
- automatic target recalculation for ORPT missed-entry handling
- automatic target override for current-day rows `183-188`
- automatic stoploss override unless workbook-backed for that row
- broad live paper or broker order placement

## 14. Practical Reading Order

If you want to verify this document against code and workbook mappings, read in
this order:

1. `config/strategies/options_sell/nifty/S23_*`
2. `docs/importers/S23_branch_mapping.md`
3. `docs/importers/S23_excel_mapping.md`
4. `docs/strategy/s23_gap_recalculation_design.md`
5. `src/tfis/backtest/recalculation.py`
6. `src/tfis/backtest/s23_current_day_fsl_trp.py`
7. `src/tfis/backtest/option_chain.py`
8. `src/tfis/backtest/trade_lifecycle.py`
9. `src/tfis/backtest/expiry_day.py`

## 15. Bottom Line

The implemented S23 logic in TFIS is:

- workbook-backed for the supported branch formulas
- explicit for ORPT missed-entry recalculation
- explicit for the supported current-day `FSL / TRP` rows
- explicit for CE/PE contract selection from option chains
- explicit for same-day lifecycle exits
- explicit that carry-forward is strategy-valid but not yet implemented in the
  current paper runtime
- explicit about what remains blocked instead of silently guessing

That is the exact behavior you should review when checking whether the S23
implementation is correct.
