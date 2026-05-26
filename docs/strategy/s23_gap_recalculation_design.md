# S23 Gap And Recalculation Design

## Purpose

This document records the current TFIS foundation for S23 missed-entry and
current-day FSL / TRP handling.

This layer is intentionally:

- diagnostic
- separate from base strategy formulas
- separate from `MonthlyStatusEngine`
- separate from `StrategyBranchSelector`
- separate from default historical backtest behavior

It is not yet a full gap engine.

## Excel Timing Context

The relevant S23 workbook block uses:

- `ORPT`: `09:24:59`
- recalculation time: `09:29:59`

Interpretation for this first foundation:

- the base branch strategy still defines the original entry and strike formulas
- if that base entry is missed by ORPT, a separate recalculation step may be applied
- this recalculation step uses current-day dynamic spot and option references at the recalculation snapshot

## Reference Semantics

Completed daily references remain unchanged:

- `PRV_2DHH`
- `PRV_2DLL`
- `PRV_3DHH`
- `PRV_3DLL`

These are completed prior daily references only.

Current-day dynamic references are separate:

- recalculation spot low / high
- recalculation option low / high

This means:

- `2DLL` / `3DHH` style references still come from completed daily bars
- recalculation combines those completed references with current-day intraday values
- `CDLL` / `CDHH` style thinking belongs to the current day and should not rewrite the meaning of `PRV_*`

## First Implemented High-Confidence Rules

### Bull / Bull CF Call

Implemented:

- `start = ROUND_DOWN(MIN(PRV_3DLL, recalc_spot_low) + strike_buffer_pct%)`
- `end = ROUND_DOWN(MIN(PRV_3DLL, recalc_spot_low)) - 1`
- `ideal = MIN(PRV_3DLL, recalc_spot_low) * ideal_premium_pct%`
- `minimum = MIN(PRV_3DLL, recalc_spot_low) * minimum_premium_pct%`
- `entry = MIN(OPT_PRV_3DLL, recalc_option_low) - entry_discount_pct%`

### Bear / Bear CF Call

Implemented:

- `start = ROUND_DOWN(MIN(PRV_2DLL, recalc_spot_low) + strike_buffer_pct%)`
- `end = ROUND_DOWN(MIN(PRV_2DLL, recalc_spot_low)) - 1`
- `ideal = MIN(PRV_2DLL, recalc_spot_low) * ideal_premium_pct%`
- `minimum = MIN(PRV_2DLL, recalc_spot_low) * minimum_premium_pct%`
- `entry = MIN(OPT_PRV_2DLL, recalc_option_low) - entry_discount_pct%`

### Bull / Bull CF Put

Confirmed from `AB6 OS`:

- `M179 = Max of ( SPT : PRV : 2DHH & 09:29:59 AM LL ) - 5.00% ) & Round Up`
- `O179 = Max of ( SPT : PRV : 2DHH & 09:29:59 AM LL ) & Round Up + 1`
- `T179 = Min of ( SPT : PRV : 2DHH & 09:29:59 AM LL ) * 1.20%`
- `V179 = Min of ( SPT : PRV : 2DHH & 09:29:59 AM LL ) * 0.90%`
- `X179 = Min of ( OPT : PRV : 2DLL & 09:29:59 AM LL ) - 7.50%`

Implemented:

- `start = ROUND_UP(MAX(PRV_2DHH, recalc_spot_high) - strike_buffer_pct%)`
- `end = ROUND_UP(MAX(PRV_2DHH, recalc_spot_high)) + 1`
- `ideal = MIN(PRV_2DHH, recalc_spot_low) * ideal_premium_pct%`
- `minimum = MIN(PRV_2DHH, recalc_spot_low) * minimum_premium_pct%`
- `entry = MIN(OPT_PRV_2DLL, recalc_option_low) - entry_discount_pct%`

Confirmed workbook correction:

- the `09:29:59 AM LL` wording in `M179/O179` is treated as a copy-paste issue
- the confirmed business rule is high-versus-high comparison for the
  recalculated strike range

### Bear / Bear CF Put

Confirmed from `AB6 OS`:

- `M180 = Max of ( SPT : PRV : 3DHH & 09:29:59 AM LL ) - 5.00% ) & Round Up`
- `O180 = Max of ( SPT : PRV : 3DHH & 09:29:59 AM LL ) & Round Up + 1`
- `T180 = Min of ( SPT : PRV : 3DHH & 09:29:59 AM LL ) * 1.20%`
- `V180 = Min of ( SPT : PRV : 3DHH & 09:29:59 AM LL ) * 0.90%`
- `X180 = Min of ( OPT : PRV : 3DLL & 09:29:59 AM LL ) - 7.50%`

Implemented:

- `start = ROUND_UP(MAX(PRV_3DHH, recalc_spot_high) - strike_buffer_pct%)`
- `end = ROUND_UP(MAX(PRV_3DHH, recalc_spot_high)) + 1`
- `ideal = MIN(PRV_3DHH, recalc_spot_low) * ideal_premium_pct%`
- `minimum = MIN(PRV_3DHH, recalc_spot_low) * minimum_premium_pct%`
- `entry = MIN(OPT_PRV_3DLL, recalc_option_low) - entry_discount_pct%`

Confirmed workbook correction:

- the `09:29:59 AM LL` wording in `M180/O180` is treated as a copy-paste issue
- the confirmed business rule is high-versus-high comparison for the
  recalculated strike range

## Current API Shape

The first recalculation foundation introduces:

- `IntradaySnapshot`
- `RecalculationInput`
- `RecalculationResult`
- `S23RecalculationEngine`

Current design decisions:

- `entry_missed` is supplied by the caller
- missed-entry detection is not inferred automatically from intraday bars yet
- unresolved recalculation fields remain `None`
- unresolved formulas are recorded in `audit_notes`

Historical backtest integration:

- historical backtest can now opt into S23 missed-entry detection plus recalculation
- this integration is still opt-in only through `--enable-s23-recalculation`
- the default historical backtest path remains unchanged
- when enabled:
  - ORPT entry-missed detection is evaluated first
  - if missed, the recalculated trade plan becomes the effective lifecycle plan
  - base plan and recalculated plan are both preserved in audit output
- current sourcing behavior:
  - ORPT and recalculation option snapshots come from the intraday option bars
  - if `--spot-intraday-csv` is provided, ORPT and recalculation spot high/low come from that spot/index intraday series
  - otherwise ORPT and recalculation spot high/low fall back to current-day low/high from market levels
  - the audit trail records which spot source was used rather than hiding the fallback

## What This Does Not Do Yet

This first foundation does not yet implement:

- automatic ORPT versus recalculation window scanning
- full gap-up / gap-down behavior
- target / stoploss recalculation
- next-step order management after recalculation
- backtest runtime integration by default

## Current-Day FSL / TRP Rows `183-188`

Workbook rows `183-188` were inspected directly and now back a separate,
opt-in `S23 current-day FSL / TRP missed / not-missed` layer.

Safe evidence-backed rows:

- `183`
  - Bull / Bull CF Call
  - FSL / TRP not missed
  - populated current-day strike and premium formulas
- `185`
  - Bear / Bear CF Call
  - FSL / TRP missed
  - populated current-day strike and premium formulas plus recalculated FSL
- `186`
  - Bear / Bear CF Put
  - FSL / TRP not missed
  - populated current-day strike and premium formulas
- `187`
  - Bull / Bull CF Put
  - FSL / TRP missed
  - only recalculated FSL is confirmed
- `188`
  - Bear / Bear CF Put
  - FSL / TRP missed
  - only recalculated FSL is confirmed

Resolved row:

- `184`
  - Bull / Bull CF Call
  - FSL / TRP missed
  - workbook text says Call-side missed context
  - visible `Q184` plus `R/S/U/W` use the Put-side formula family
  - TFIS implements it exactly as workbook-directed after user confirmation

Current implementation scope:

- rows `183-186`
  - apply populated `R/S/U/W/Z` workbook formulas
  - `Z183:Z186` now map to the current-day option-entry override that updates
    `TradePlan.entry_price`
- rows `184/185/187/188`
  - also apply the workbook-backed recalculated FSL from `M/O`
- rows `187-188`
  - remain `FSL-only`
  - TFIS must not invent strike, premium, or entry recalculation because
    `R/S/U/W/Z` are blank there
- unsupported paths remain unchanged:
  - Bull / Bull CF Put not missed
  - Bear / Bear CF Call not missed

Historical backtest integration:

- this layer is opt-in only through `--enable-s23-current-day-fsl-trp`
- it is separate from the older `--enable-s23-recalculation` ORPT missed-entry
  path
- it requires explicit spot and option intraday CSV data
- it uses aggregated current-day snapshots at:
  - `09:15:00` for the FSL / TRP missed trigger
  - `09:24:59` for not-missed current-day `CDHH / CDLL` formulas
  - `09:29:59` for missed current-day recalculation and FSL
- when a branch path is unsupported by workbook coverage, TFIS keeps the base
  trade plan and records a warning instead of inferring behavior
- rows `183-186` can now also override `entry_price` from the workbook-backed
  `Z183:Z186` option-entry cells, which means this opt-in layer may change
  lifecycle entry timing and realized P&L under apples-to-apples inputs
- when row `184` is applied, audit output preserves the resolved workbook
  clarification rather than hiding the mixed Call / Put evidence

## Open Questions

- No additional target override formulas were found in `AB6 OS` rows `162-191`; any future target override needs new workbook evidence from outside this block.
- Rows `190-191` still only describe position-open process flow and do not provide a numeric continuation-stoploss rule in this block.
- How should same-day recalculation interact with later carry-forward and rollover logic once those modules exist?
