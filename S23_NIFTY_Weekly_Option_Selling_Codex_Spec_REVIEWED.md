# S23 — NIFTY Weekly Option Selling Strategy
## Reviewed Codex Specification with Logical Consistency Flags

Source workbook: `All in One - TFIS 26-12-2023.xlsx`

Reviewed sheets / areas:
- `AB6 OS` rows `162–191`: S23 primary rule block.
- `AB6 OS` rows `68–126` and `194–220`: comparable option-selling strategies S20/S21/S24 used to detect whether a questionable row is isolated or repeated pattern.
- `AB2`, `AB4`, `AB5`: strategy identity and common label text.
- `AB10–AB16`, `AB18`: downstream S23 references checked for strategy identity; they do not override the core S23 formulas in `AB6 OS`.

This reviewed document does **not** treat the Excel workbook as blindly correct. It marks each rule as:
- **CONFIRMED**: present in S23 and consistent with comparable option-selling strategies.
- **WORKBOOK-CONSISTENT BUT NEEDS OWNER SIGNOFF**: repeated in the workbook but logically easy to misread or potentially copied forward.
- **NOT SPECIFIED**: do not guess in implementation.

---

# 1. Review Verdict

The previously generated Codex document is **mostly correct for the base S23 formulas**, but one important area needed correction:

## Important correction

The FSL/TRP section must separate:

1. **Trigger side** — which position's FSL/TRP was missed.
2. **Recalculated/replacement side** — which option side the workbook recalculates after that event.

The earlier document described rows such as `AB6 OS!184` as if the same option type was being recalculated. That is too ambiguous for Codex.

Example:

`AB6 OS!184` says:
- Process: `Recalculate: Call Sell FSL/TRP: Bull / Bull CF`
- But option type field `Q184` = `Put`
- And the formulas use Put-side references:
  - `SPT:PRV:2DHH`
  - `SPT:CDHH`
  - `OPT:PRV:2DLL`
  - `OPT:CDLL`

So Codex must model this as:

```python
trigger_option_type = "CE"       # Call Sell FSL/TRP was missed
recalc_option_type = "PE"        # Workbook recalculates Put-side candidate fields
monthly_status_group = "BULLISH"
```

Do **not** model row 184 as "recalculate CE strike using Put formulas".

This pattern is not isolated to S23. It appears consistently in comparable `2D_3D` option-selling strategies S20, S21, and S24.

---

# 2. Strategy Identity — CONFIRMED

Workbook source: `AB6 OS!C162:C169`.

```yaml
strategy_code: S23
unique_code: NIFTY_OP_SELL_WK_DIFF_2D_3D
segment: OPTIONS_SELL
symbol: NIFTY
expiry_type: WEEKLY
target_type: APS
carry_forward: true
```

Current implementation override:

```yaml
lot_size: 65
```

The workbook is old, so current NIFTY lot size must come from runtime/exchange config, not the workbook. As of current NSE lot-size revisions reported for 2026 contracts, NIFTY derivatives lot size is 65.

---

# 3. Minimum OI Rule — CONFIRMED WITH UNIT WARNING

Workbook cells:
- `AB6 OS!I162`, `I165`, `I168`, `I171` = `500 Lots`

Rule:

```python
minimum_oi_lots = 500
```

Runtime conversion:

```python
if broker_oi_unit == "lots":
    required_oi = 500
elif broker_oi_unit == "contracts":
    required_oi = 500 * lot_size   # 500 * 65 = 32500
else:
    reject_trade("unknown_oi_unit")
```

Do not hardcode `32500` unless the broker OI field is known to be contract quantity.

---

# 4. Monthly Status Handling — CONFIRMED

S23 consumes monthly status as an input. `AB6 OS` does not calculate monthly status.

Supported status groups:

```python
BULLISH_GROUP = {"BULL", "BULL_CF"}
BEARISH_GROUP = {"BEAR", "BEAR_CF"}
```

Implementation:

```python
if monthly_status in BULLISH_GROUP:
    regime = "BULLISH"
elif monthly_status in BEARISH_GROUP:
    regime = "BEARISH"
else:
    reject_trade("unsupported_or_unresolved_monthly_status")
```

---

# 5. Strategy Logic — CONFIRMED

S23 is an asymmetric option-selling strategy.

In bullish monthly status:
- safer side = PE sell
- riskier side = CE sell
- PE uses more aggressive 2-day option entry reference
- CE uses more defensive 3-day option entry reference

In bearish monthly status:
- safer side = CE sell
- riskier side = PE sell
- CE uses more aggressive 2-day option entry reference
- PE uses more defensive 3-day option entry reference

This logic is consistent across:
- S20: BANKNIFTY weekly `2D_3D`
- S21: BANKNIFTY monthly `2D_3D`
- S23: NIFTY weekly `2D_3D`
- S24: NIFTY monthly `2D_3D`

The premium percentage differs by instrument/expiry, but the 2D/3D branch pattern is consistent.

---

# 6. Base S23 Branch Matrix — CONFIRMED

## 6.1 Bullish CE Sell — Risk Side

Workbook rows: `AB6 OS!162–163`

Applicable when:

```python
monthly_status in {"BULL", "BULL_CF"}
option_type = "CE"
```

Rules:

```python
spot_base = SPT_PRV_3DLL

start_strike = round_down_to_valid_strike(spot_base * 1.05)
end_strike = round_down_to_valid_strike(spot_base) - strike_step

ideal_premium = spot_base * 0.012
minimum_premium = spot_base * 0.009

entry_price = OPT_PRV_3DLL * (1 - 0.075)

target_price = entry_price * (1 - 0.60)

stoploss_price = min(
    entry_price * (1 + 0.60),
    OPT_PRV_2DHH * (1 + 0.07)
)

minimum_oi_lots = 500
```

---

## 6.2 Bullish PE Sell — Safe Side

Workbook rows: `AB6 OS!165–166`

Applicable when:

```python
monthly_status in {"BULL", "BULL_CF"}
option_type = "PE"
```

Rules:

```python
spot_base = SPT_PRV_2DHH

start_strike = round_up_to_valid_strike(spot_base * 0.95)
end_strike = round_up_to_valid_strike(spot_base) + strike_step

ideal_premium = spot_base * 0.012
minimum_premium = spot_base * 0.009

entry_price = OPT_PRV_2DLL * (1 - 0.075)

target_price = entry_price * (1 - 0.60)

stoploss_price = min(
    entry_price * (1 + 0.60),
    OPT_PRV_3DHH * (1 + 0.10)
)

minimum_oi_lots = 500
```

Logical note:

This is consistent with your explanation:
- PE is safer in bullish status.
- Entry uses 2DLL, which is the aggressive/closer option-entry reference.
- Strike/premium boundary uses 2DHH because PE strike construction is based on upper-side spot reference and rounded upward after subtracting 5%.

---

## 6.3 Bearish CE Sell — Safe Side

Workbook rows: `AB6 OS!168–169`

Applicable when:

```python
monthly_status in {"BEAR", "BEAR_CF"}
option_type = "CE"
```

Rules:

```python
spot_base = SPT_PRV_2DLL

start_strike = round_down_to_valid_strike(spot_base * 1.05)
end_strike = round_down_to_valid_strike(spot_base) - strike_step

ideal_premium = spot_base * 0.012
minimum_premium = spot_base * 0.009

entry_price = OPT_PRV_2DLL * (1 - 0.075)

target_price = entry_price * (1 - 0.60)

stoploss_price = min(
    entry_price * (1 + 0.60),
    OPT_PRV_3DHH * (1 + 0.10)
)

minimum_oi_lots = 500
```

---

## 6.4 Bearish PE Sell — Risk Side

Workbook rows: `AB6 OS!171–172`

Applicable when:

```python
monthly_status in {"BEAR", "BEAR_CF"}
option_type = "PE"
```

Rules:

```python
spot_base = SPT_PRV_3DHH

start_strike = round_up_to_valid_strike(spot_base * 0.95)
end_strike = round_up_to_valid_strike(spot_base) + strike_step

ideal_premium = spot_base * 0.012
minimum_premium = spot_base * 0.009

entry_price = OPT_PRV_3DLL * (1 - 0.075)

target_price = entry_price * (1 - 0.60)

stoploss_price = min(
    entry_price * (1 + 0.60),
    OPT_PRV_2DHH * (1 + 0.07)
)

minimum_oi_lots = 500
```

Logical note:

The spot side uses `3DHH`, while option entry uses `3DLL`. This is not a typo in S23; the same pattern appears in S20, S21, and S24. It matches the workbook's PE construction pattern:
- strike/premium boundary from high-side spot reference
- option entry from option low reference

---

# 7. Candidate Strike Selection — PARTLY NOT SPECIFIED

Workbook confirms the range and filters:

```python
candidate_strikes = strikes_between(start_strike, end_strike, option_type)

premium_qualified = [
    strike for strike in candidate_strikes
    if minimum_premium <= premium(strike) <= ideal_premium
]

oi_qualified = [
    strike for strike in premium_qualified
    if oi_lots(strike) >= 500
]
```

Workbook does **not** clearly define how to select one final strike if multiple strikes qualify.

Codex requirement:

```python
if not oi_qualified:
    reject_trade("no_s23_contract_passed_premium_and_oi_filters")

selected_strike = apply_explicit_selector_policy(oi_qualified)
```

The selector policy must be explicit and tested. Do not silently pick first/nearest/farthest unless that policy is already present in TFIS and documented.

---

# 8. Entry-Missed Rules — CONFIRMED WITH ONE CAUTION

Workbook rows:
- `AB6 OS!175`: CE entry not missed
- `AB6 OS!176`: CE entry missed, Bull/Bull_CF
- `AB6 OS!177`: CE entry missed, Bear/Bear_CF
- `AB6 OS!178`: PE entry not missed
- `AB6 OS!179`: PE entry missed, Bull/Bull_CF
- `AB6 OS!180`: PE entry missed, Bear/Bear_CF

Timings:
- ORPT = `09:24:59`
- RC = `09:29:59`

## 8.1 Entry Not Missed

For CE or PE:

```python
if entry_not_missed:
    place_order_at("09:24:59")
```

## 8.2 CE Entry Missed — Bull/Bull_CF

Workbook row: `AB6 OS!176`

```python
base = min(SPT_PRV_3DLL, SPT_RC_LL)

start_strike = round_down_to_valid_strike(base * 1.05)
end_strike = round_down_to_valid_strike(base) - strike_step

ideal_premium = base * 0.012
minimum_premium = base * 0.009

entry_price = min(OPT_PRV_3DLL, OPT_RC_LL) * (1 - 0.075)
minimum_oi_lots = 500
```

## 8.3 CE Entry Missed — Bear/Bear_CF

Workbook row: `AB6 OS!177`

```python
base = min(SPT_PRV_2DLL, SPT_RC_LL)

start_strike = round_down_to_valid_strike(base * 1.05)
end_strike = round_down_to_valid_strike(base) - strike_step

ideal_premium = base * 0.012
minimum_premium = base * 0.009

entry_price = min(OPT_PRV_2DLL, OPT_RC_LL) * (1 - 0.075)
minimum_oi_lots = 500
```

## 8.4 PE Entry Missed — Bull/Bull_CF

Workbook row: `AB6 OS!179`

```python
strike_base = max(SPT_PRV_2DHH, SPT_RC_LL)
premium_base = min(SPT_PRV_2DHH, SPT_RC_LL)
entry_base = min(OPT_PRV_2DLL, OPT_RC_LL)

start_strike = round_up_to_valid_strike(strike_base * 0.95)
end_strike = round_up_to_valid_strike(strike_base) + strike_step

ideal_premium = premium_base * 0.012
minimum_premium = premium_base * 0.009

entry_price = entry_base * (1 - 0.075)
minimum_oi_lots = 500
```

## 8.5 PE Entry Missed — Bear/Bear_CF

Workbook row: `AB6 OS!180`

```python
strike_base = max(SPT_PRV_3DHH, SPT_RC_LL)
premium_base = min(SPT_PRV_3DHH, SPT_RC_LL)
entry_base = min(OPT_PRV_3DLL, OPT_RC_LL)

start_strike = round_up_to_valid_strike(strike_base * 0.95)
end_strike = round_up_to_valid_strike(strike_base) + strike_step

ideal_premium = premium_base * 0.012
minimum_premium = premium_base * 0.009

entry_price = entry_base * (1 - 0.075)
minimum_oi_lots = 500
```

Caution:

The PE missed rows combine:
- `max(..., SPT_RC_LL)` for strike base
- `min(..., SPT_RC_LL)` for premium base

This is workbook-consistent across S20/S21/S23/S24. It is not an isolated S23 copy-paste error. Keep it unless strategy owner explicitly decides the `LL` label should be corrected.

---

# 9. FSL/TRP Rules — REVIEWED AND CORRECTED FOR CODEX

Workbook rows:
- `AB6 OS!183–188`

Important modeling rule:

```python
# Do not model only option_type.
# Model event trigger and recalculation side separately.
class FslTrpRule:
    trigger_option_type: "CE" | "PE"
    trigger_status: "MISSED" | "NOT_MISSED"
    monthly_status_group: "BULLISH" | "BEARISH" | None
    recalculated_option_type: "CE" | "PE" | None
    action: str
```

---

## 9.1 CE FSL/TRP Not Missed — Bull/Bull_CF

Workbook row: `AB6 OS!183`

Trigger:

```python
trigger_option_type = "CE"
monthly_status_group = "BULLISH"
fsl_or_trp_missed = False
```

Action:

```python
place_order_at_orpt()
use_original_ce_rules()
```

Workbook row 183 contains extra recalculated-style fields using current-day low (`CDLL`), but process columns say:
- `FSL / TRP Not Missed`
- `Place the Order at ORPT`
- formula fields `M/N/O` are `N.A.`

Therefore row 183 should not be treated as a missed recalculation event.

---

## 9.2 CE FSL/TRP Missed — Bull/Bull_CF

Workbook row: `AB6 OS!184`

Trigger:

```python
trigger_option_type = "CE"
monthly_status_group = "BULLISH"
fsl_or_trp_missed = True
```

Workbook recalculates replacement side:

```python
recalculated_option_type = "PE"
```

Recalculation:

```python
fsl_reference = OPT_RC_HH * (1 + 0.07)

strike_base = max(SPT_PRV_2DHH, SPT_CDHH)
premium_base = min(SPT_PRV_2DHH, SPT_CDLL)
entry_base = min(OPT_PRV_2DLL, OPT_CDLL)

start_strike = round_up_to_valid_strike(strike_base * 0.95)
end_strike = round_up_to_valid_strike(strike_base) + strike_step

ideal_premium = premium_base * 0.012
minimum_premium = premium_base * 0.009

entry_price = entry_base * (1 - 0.075)
minimum_oi_lots = 500
```

This is logically consistent with the asymmetric framework:
- In bullish status, CE is the risk side.
- If CE FSL/TRP is missed, the workbook moves recalculation to the safer PE side.
- The `+7%` belongs to the missed CE event buffer.

---

## 9.3 CE FSL/TRP Missed — Bear/Bear_CF

Workbook row: `AB6 OS!185`

Trigger:

```python
trigger_option_type = "CE"
monthly_status_group = "BEARISH"
fsl_or_trp_missed = True
```

Workbook recalculates:

```python
recalculated_option_type = "CE"
```

Recalculation:

```python
fsl_reference = OPT_RC_HH * (1 + 0.10)

base = min(SPT_PRV_2DLL, SPT_CDLL)

start_strike = round_down_to_valid_strike(base * 1.05)
end_strike = round_down_to_valid_strike(base) - strike_step

ideal_premium = base * 0.012
minimum_premium = base * 0.009

entry_price = min(OPT_PRV_2DLL, OPT_CDLL) * (1 - 0.075)
minimum_oi_lots = 500
```

This is consistent because in bearish status CE is the safe side.

---

## 9.4 PE FSL/TRP Not Missed

Workbook row: `AB6 OS!186`

Trigger:

```python
trigger_option_type = "PE"
fsl_or_trp_missed = False
```

Action:

```python
place_order_at_orpt()
use_original_pe_rules()
```

Caution:

Row 186 contains formula-like PE fields using `3DHH/3DLL`, which align with Bearish PE risk-side formulas, but the process columns say `Not Missed -> Place the Order at ORPT`. Do not treat row 186 as a missed recalculation row.

---

## 9.5 PE FSL/TRP Missed — Bull/Bull_CF

Workbook row: `AB6 OS!187`

Trigger:

```python
trigger_option_type = "PE"
monthly_status_group = "BULLISH"
fsl_or_trp_missed = True
```

Workbook-confirmed rule:

```python
fsl_reference = OPT_RC_HH * (1 + 0.10)
```

Workbook limitation:

Row 187 does not provide strike/premium/OI/entry recalculation fields.

Implementation:

```python
apply_fsl_only_rule(buffer_pct=0.10)
```

Do not invent a new strike selector from row 187.

---

## 9.6 PE FSL/TRP Missed — Bear/Bear_CF

Workbook row: `AB6 OS!188`

Trigger:

```python
trigger_option_type = "PE"
monthly_status_group = "BEARISH"
fsl_or_trp_missed = True
```

Workbook-confirmed rule:

```python
fsl_reference = OPT_RC_HH * (1 + 0.07)
same_day_only = True
```

Workbook limitation:

Row 188 does not provide strike/premium/OI/entry recalculation fields.

Implementation:

```python
apply_fsl_only_rule(buffer_pct=0.07, same_day_only=True)
```

Do not invent a new strike selector from row 188.

---

# 10. Missed SL at 15:00 — CONFIRMED WITH EQUALITY GAP

Workbook rows: `AB6 OS!189–191`

For open positions:

```python
if time == "15:00:00":
    if option_close > original_sl:
        square_off_at_cmp()
    elif option_close < original_sl:
        continue_position_next_day()
        recalculate_stop_loss_as_per_rules()
    else:
        handle_equality_explicitly()
```

Workbook does not specify equality case:

```python
option_close == original_sl
```

Codex must not leave equality implicit. Recommended conservative implementation:

```python
if option_close >= original_sl:
    square_off_at_cmp()
else:
    continue_position_next_day()
```

But this is a safety recommendation, not an Excel-confirmed rule.

---

# 11. Carry Forward / Expiry Governance — CONFIRMED WITH RUNTIME SAFETY OVERRIDE

Workbook rows `189–191` allow next-day continuation when option close is below original SL at 15:00.

Implementation rule:

```python
if can_continue_by_strategy and not blocked_by_expiry_governance:
    persist_position_for_next_day()
else:
    square_off_or_block_resume()
```

Runtime expiry governance must override workbook carry-forward:

```python
if contract_expiry_passed:
    do_not_resume_position()
if current_date >= configured_expiry_cutoff_date:
    square_off_or_roll_according_to_config()
```

---

# 12. Items That Are Logically Consistent

These parts of the previous Codex doc are consistent and can remain:

1. S23 is NIFTY weekly option selling.
2. Monthly status drives the regime.
3. BULL and BULL_CF behave the same.
4. BEAR and BEAR_CF behave the same.
5. Bullish CE uses `3DLL`.
6. Bullish PE uses `2DHH` for strike/premium and `2DLL` for entry.
7. Bearish CE uses `2DLL`.
8. Bearish PE uses `3DHH` for strike/premium and `3DLL` for entry.
9. Premium band is `1.20%` ideal and `0.90%` minimum.
10. Entry discount is `7.50%`.
11. Target is `entry - 60%`.
12. Base SL is `min(entry + 60%, structure reference + branch buffer)`.
13. Branch SL buffers are `7%` or `10%` as documented.
14. Minimum OI is `500 lots`, converted to contracts only if needed.
15. Entry-missed recalculation happens at RC `09:29:59`.
16. Not-missed order placement uses ORPT `09:24:59`.
17. Position-open missed SL check uses 15:00 close vs original SL.

---

# 13. Items That Needed Correction / Rewording

## Correction 1 — FSL/TRP trigger side vs recalculation side

Old wording risk:
```python
option_type = "CE"
row_184_formulas = PE formulas
```

Correct wording:
```python
trigger_option_type = "CE"
recalculated_option_type = "PE"
```

## Correction 2 — Row 184 should not be implemented as CE formula output

Row 184 is a Call Sell FSL/TRP missed event in Bull/Bull_CF, but its recalculated candidate is Put-side.

## Correction 3 — Row 186 should not be treated as missed recalculation

Row 186 has formula-looking fields, but process says `FSL / TRP Not Missed -> Place the Order at ORPT`.

## Correction 4 — Entry and FSL recalculation should use current-day labels carefully

Use:
- `RC_LL` for row 176–180 entry-missed rules.
- `CDLL/CDHH` for row 183–186 FSL/TRP current-day recalculation fields.
- Do not collapse them into one generic "current low/high" without preserving timing.

---

# 14. Remaining Open Items

These must be clarified or taken from already validated TFIS implementation:

1. Final strike selector when multiple contracts pass premium + OI.
2. Quantity allocation ratio between safe side and risk side.
3. Equality case at 15:00 close vs original SL.
4. Broker OI unit: lots or contracts.
5. Monthly status calculation.
6. Expiry cut-off / roll policy.
7. Whether row 187 phrase `When You Call And Put Position is Exited` means no further replacement trade, or only FSL-only management.

---

# 15. Codex Implementation Summary

Codex should implement S23 as:

```python
class S23Strategy:
    def calculate_base_branches(monthly_status, market_refs, option_refs):
        # returns CE and PE candidate rules from rows 162–172

    def handle_entry_missed(option_type, monthly_status, rc_refs):
        # rows 176–180

    def handle_fsl_trp_event(trigger_option_type, monthly_status, missed, current_day_refs):
        # rows 183–188
        # IMPORTANT: trigger_option_type and recalculated_option_type may differ

    def handle_1500_missed_sl(position, option_close):
        # rows 189–191

    def apply_expiry_governance(position):
        # runtime safety override
```

Minimum test cases:

1. `BULL + CE` base uses `3DLL`.
2. `BULL + PE` base uses `2DHH` strike/premium and `2DLL` entry.
3. `BEAR + CE` base uses `2DLL`.
4. `BEAR + PE` base uses `3DHH` strike/premium and `3DLL` entry.
5. `BULL + CE FSL missed` triggers CE event but recalculates PE candidate.
6. `BEAR + CE FSL missed` triggers CE event and recalculates CE candidate.
7. `BULL + PE FSL missed` is FSL-only with `+10%`.
8. `BEAR + PE FSL missed` is FSL-only with `+7%` and same-day-only.
9. Row 186 not-missed PE branch does not cause missed recalculation.
10. `500 lots` OI converts to `32500 contracts` only when broker OI is contract-based and lot size is `65`.

---

# 16. Final Reviewed Verdict

The base S23 branch formulas in the earlier generated document are logically consistent and workbook-confirmed.

The FSL/TRP section needed rewording to avoid a dangerous implementation mistake:
- The event side and recalculated side are not always the same.
- Row 184 is the most important example.

With the corrections in this reviewed document, the S23 rules are suitable for Codex implementation and documentation updates, provided the open items are either configured or explicitly tested.
