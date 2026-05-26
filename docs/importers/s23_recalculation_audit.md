# S23 Recalculation Audit

## Purpose

This audit reviews the `AB6 OS` workbook block around rows `162-191` to check
whether TFIS is still missing any safe, workbook-backed S23 recalculation
behavior beyond the currently implemented opt-in paths.

This is an evidence document only.

- no trading behavior is changed here
- blank workbook cells are not inferred
- unsupported branches remain unsupported until the workbook confirms them
- current-day FSL / TRP mappings from rows `183-188` are not changed by this audit

## Scope Notes

Audited rows:

- `AB6 OS` rows `162-191`
- nearby rows were scanned for S23-style recalculation keywords

Interpretation boundary:

- rows `194+` start a different-looking branch family with `1.60%` premium text
- those later rows were not treated as part of the current S23 recalculation scope

## Key Conclusions

1. No workbook-backed recalculated target formulas were found in rows `162-191`.
   The visible target cells remain the base branch targets in `O162`, `O165`,
   `O168`, and `O171`.
2. No additional numeric recalculated stoploss formulas were found beyond the
   already implemented FSL rules in rows `184`, `185`, `187`, and `188`.
3. Rows `190-191` do introduce additional same-day / next-day position-open
   handling text, but they do not provide numeric strike / premium / entry /
   continuation-stoploss formulas in this block.
4. The unsupported current-day FSL / TRP paths remain unsupported:
   - Bull / Bull CF Put not missed
   - Bear / Bear CF Call not missed
5. `Z183:Z186` are formula-generated rule-description cells, not numeric
   workbook outputs, but they sit under the current-day `Option Entry` header
   and mirror the already-used revised-entry column in the ORPT missed-entry
   block.
6. TFIS now safely maps `Z183:Z186` to the opt-in current-day FSL / TRP
   `TradePlan.entry_price` override for supported rows `183-186`.

## Row-By-Row Evidence Table

| Sheet | Row | Condition | Status | Monthly Status | Option Type | ORPT / RC Time | Target Formula | Stoploss / FSL Formula | Strike / Premium / Entry Formulas | Implementation Status | Reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `AB6 OS` | `162` | Base branch anchor | Base branch | `BULL / BULL CF` | `Call` | `L162 = E & T` | `O162 = CE : Entry  - 60.00%` | `See row 163` | `G162 = ( SPT : PRV : 3DLL + 5.00% ) & Round Down`<br>`H162 = SPT : PRV : 3DLL * 1.20%`<br>`M162 = OPT : PRV : 3DLL - 7.50%` | `implemented` | Base Bull Call branch already feeds the normal strategy path. |
| `AB6 OS` | `163` | Base branch stoploss row | Base branch | `BULL / BULL CF` | `Call` | `L163 = SL / TRP` | `None` | `M163 = Min ( CE : Entry  + 60.00% & OPT : PRV : 2DHH + 7.00% )` | `H163 = SPT : PRV : 3DLL * 0.90%` | `implemented` | Base Bull Call stoploss / TRP anchor already exists and is inherited by recalculation layers unless explicitly overridden. |
| `AB6 OS` | `165` | Base branch anchor | Base branch | `BULL / BULL CF` | `Put` | `L165 = E & T` | `O165 = PE : Entry  - 60.00%` | `See row 166` | `G165 = ( SPT : PRV : 2DHH - 5.00% ) & Round Up`<br>`H165 = SPT : PRV : 2DHH * 1.20%`<br>`M165 = OPT : PRV : 2DLL - 7.50%` | `implemented` | Base Bull Put branch already feeds the normal strategy path. |
| `AB6 OS` | `166` | Base branch stoploss row | Base branch | `BULL / BULL CF` | `Put` | `L166 = SL / TRP` | `None` | `M166 = Min ( PE : Entry  + 60.00% & OPT : PRV : 3DHH + 10.00% )` | `H166 = SPT : PRV : 2DHH * 0.90%` | `implemented` | Base Bull Put stoploss / TRP anchor already exists and is inherited unless explicitly overridden. |
| `AB6 OS` | `168` | Base branch anchor | Base branch | `BEAR / BEAR CF` | `Call` | `L168 = E & T` | `O168 = CE : Entry  - 60.00%` | `See row 169` | `G168 = ( SPT : PRV : 2DLL + 5.00% ) & Round Down`<br>`H168 = SPT : PRV : 2DLL * 1.20%`<br>`M168 = OPT : PRV : 2DLL - 7.50%` | `implemented` | Base Bear Call branch already feeds the normal strategy path. |
| `AB6 OS` | `169` | Base branch stoploss row | Base branch | `BEAR / BEAR CF` | `Call` | `L169 = SL / TRP` | `None` | `M169 = Min ( CE : Entry  + 60.00% & OPT : PRV : 3DHH + 10.00% )` | `H169 = SPT : PRV : 2DLL * 0.90%` | `implemented` | Base Bear Call stoploss / TRP anchor already exists and is inherited unless explicitly overridden. |
| `AB6 OS` | `171` | Base branch anchor | Base branch | `BEAR / BEAR CF` | `Put` | `L171 = E & T` | `O171 = PE : Entry  - 60.00%` | `See row 172` | `G171 = ( SPT : PRV : 3DHH - 5.00% ) & Round Up`<br>`H171 = SPT : PRV : 3DHH * 1.20%`<br>`M171 = OPT : PRV : 3DLL - 7.50%` | `implemented` | Base Bear Put branch already feeds the normal strategy path. |
| `AB6 OS` | `172` | Base branch stoploss row | Base branch | `BEAR / BEAR CF` | `Put` | `L172 = SL / TRP` | `None` | `M172 = Min ( PE : Entry  + 60.00% & OPT : PRV : 2DHH + 7.00% )` | `H172 = SPT : PRV : 3DHH * 0.90%` | `implemented` | Base Bear Put stoploss / TRP anchor already exists and is inherited unless explicitly overridden. |
| `AB6 OS` | `175` | `E175 = Check If 09:24:59 AM LL < Call Sell Entry` | `Entry Not Missed` | `Bull / Bull CF` call context | `Call` | `ORPT @ L175 = 09:24:59.400000` | `None` | `None` | `M175:X175 = N.A.` | `implemented` | This is the no-recalculation ORPT path; TFIS already keeps the base plan. |
| `AB6 OS` | `176` | Call Sell Entry missed | `Entry Missed` | `Bull / Bull CF` | `Call` | `RC @ L176 = 09:29:59.400000` | `None` | `None` | `M176 = Min of ( SPT : PRV : 3DLL & 09:29:59 AM LL ) + 5.00% ) & Round Down`<br>`O176 = Min of ( SPT : PRV : 3DLL & 09:29:59 AM LL ) & Round Down - 1`<br>`T176 = Min of ( SPT : PRV : 3DLL & 09:29:59 AM LL )  * 1.20%`<br>`V176 = Min of ( SPT : PRV : 3DLL & 09:29:59 AM LL )  * 0.90%`<br>`X176 = Min of ( OPT : PRV : 3DLL & 09:29:59 AM LL )  -  7.50%` | `implemented` | Fully workbook-backed and already implemented in the ORPT missed-entry recalculation path. |
| `AB6 OS` | `177` | Call Sell Entry missed | `Entry Missed` | `Bear / Bear CF` | `Call` | `RC @ L177 = 09:29:59.400000` | `None` | `None` | `M177 = Min of ( SPT : PRV : 2DLL & 09:29:59 AM LL ) + 5.00% ) & Round Down`<br>`O177 = Min of ( SPT : PRV : 2DLL & 09:29:59 AM LL ) & Round Down - 1`<br>`T177 = Min of  of ( SPT : PRV : 2DLL & 09:29:59 AM LL )  * 1.20%`<br>`V177 = Min of ( SPT : PRV : 2DLL & 09:29:59 AM LL )  * 0.90%`<br>`X177 = Min of ( OPT : PRV : 2DLL & 09:29:59 AM LL )  -  7.50%` | `implemented` | Fully workbook-backed and already implemented in the ORPT missed-entry recalculation path. |
| `AB6 OS` | `178` | `E178 = Check If 09:24:59 AM LL < Put Sell Entry` | `Entry Not Missed` | `Bull / Bear Put entry context only` | `Put` | `ORPT @ L178 = 09:24:59.400000` | `None` | `None` | `M178:X178 = N.A.` | `implemented` | This is the no-recalculation ORPT path for Put entry; TFIS already keeps the base plan. |
| `AB6 OS` | `179` | Put Sell Entry missed | `Entry Missed` | `Bull / Bull CF` | `Put` | `RC @ L179 = 09:29:59.400000` | `None` | `None` | `M179 = Max of ( SPT : PRV : 2DHH & 09:29:59 AM LL ) - 5.00% ) & Round Up`<br>`O179 = Max of ( SPT : PRV : 2DHH & 09:29:59 AM LL ) & Round Up + 1`<br>`T179 = Min of ( SPT : PRV : 2DHH & 09:29:59 AM LL )  * 1.20%`<br>`V179 = Min of ( SPT : PRV : 2DHH & 09:29:59 AM LL )  * 0.90%`<br>`X179 = Min of ( OPT : PRV : 2DLL & 09:29:59 AM LL )  -  7.50%` | `implemented` | Fully workbook-backed and already implemented, with the strike-side LL wording already resolved as a confirmed workbook copy-paste issue. |
| `AB6 OS` | `180` | Put Sell Entry missed | `Entry Missed` | `Bear / Bear CF` | `Put` | `RC @ L180 = 09:29:59.400000` | `None` | `None` | `M180 = Max of ( SPT : PRV : 3DHH & 09:29:59 AM LL ) - 5.00% ) & Round Up`<br>`O180 = Max of ( SPT : PRV : 3DHH & 09:29:59 AM LL ) & Round Up + 1`<br>`T180 = Min of ( SPT : PRV : 3DHH & 09:29:59 AM LL )  * 1.20%`<br>`V180 = Min of ( SPT : PRV : 3DHH & 09:29:59 AM LL )  * 0.90%`<br>`X180 = Min of ( OPT : PRV : 3DLL & 09:29:59 AM LL )  -  7.50%` | `implemented` | Fully workbook-backed and already implemented, with the strike-side LL wording already resolved as a confirmed workbook copy-paste issue. |
| `AB6 OS` | `183` | `E183 = Check If  09:15:00 AM HH > Call Sell SL` | `FSL / TRP Not Missed` | `BULL / BULL CF` | `Call` | `ORPT @ L183 = 09:24:59.400000` | `None` | `None` | `R183 = Min of ( SPT : PRV : 3DLL & SPT : CDLL ) + 5.00% ) & Round Down`<br>`S183 = Min of ( SPT : PRV : 3DLL & SPT : CDLL ) & Round Down - 1`<br>`U183 = Min of ( SPT : PRV : 3DLL & SPT : CDLL )  * 1.20%`<br>`W183 = Min of ( SPT : PRV : 3DLL & SPT : CDLL )  * 0.90%`<br>`Z183 = Min of ( OPT : PRV : 3DLL & OPT : CDLL )  -  7.50%` | `implemented` | TFIS now consumes `R/S/U/W/Z183`; `Z183` maps to the current-day `entry_price` override from `AB6_OS_Z183`. |
| `AB6 OS` | `184` | Call Sell SL missed | `FSL / TRP Missed` | `Bull / Bull CF` Call context | `Put` workbook family | `RC @ L184 = 09:29:59.400000` | `None` | `M184 = 09:29:59 AM HH + 7.00%` | `R184 = Max of ( SPT : PRV : 2DHH & SPT : CDHH ) - 5.00% ) & Round Up`<br>`S184 = Max of ( SPT : PRV : 2DHH & SPT : CDHH ) & Round Up + 1`<br>`U184 = Min of ( SPT : PRV : 2DHH & SPT : CDLL )  * 1.20%`<br>`W184 = Min of ( SPT : PRV : 2DHH & SPT : CDLL )  * 0.90%`<br>`Z184 = Min of ( OPT : PRV : 2DLL & OPT : CDLL )  -  7.50%` | `implemented` | TFIS now consumes the resolved workbook-directed row-184 mapping, the new FSL, and the `Z184` current-day option-entry override from `AB6_OS_Z184`. |
| `AB6 OS` | `185` | Call Sell SL missed | `FSL / TRP Missed` | `BEAR / BEAR CF` | `Call` | `RC @ L185 = 09:29:59.400000` | `None` | `M185 = 09:29:59 AM HH + 10.00%` | `R185 = Min of ( SPT : PRV : 2DLL & SPT : CDLL ) + 5.00% ) & Round Down`<br>`S185 = Min of ( SPT : PRV : 2DLL & SPT : CDLL ) & Round Down - 1`<br>`U185 = Min of  of ( SPT : PRV : 2DLL & SPT : CDLL )  * 1.20%`<br>`W185 = Min of ( SPT : PRV : 2DLL & SPT : CDLL )  * 0.90%`<br>`Z185 = Min of ( OPT : PRV : 2DLL & OPT : CDLL )  -  7.50%` | `implemented` | TFIS now consumes `R/S/U/W/Z185` plus the new FSL; `Z185` maps to the current-day `entry_price` override from `AB6_OS_Z185`. |
| `AB6 OS` | `186` | `E186 = Check If  09:15:00 AM HH > Short SL` | `FSL / TRP Not Missed` | `Bear / Bear CF` by formula family | `Put` | `ORPT @ L186 = 09:24:59.400000` | `None` | `None` | `R186 = Max of ( SPT : PRV : 3DHH & SPT : CDHH ) - 5.00% ) & Round Up`<br>`S186 = Max of ( SPT : PRV : 3DHH & SPT : CDHH ) & Round Up + 1`<br>`U186 = Min of ( SPT : PRV : 3DHH & SPT : CDLL )  * 1.20%`<br>`W186 = Min of ( SPT : PRV : 3DHH & SPT : CDLL )  * 0.90%`<br>`Z186 = Min of ( OPT : PRV : 3DLL & OPT : CDLL )  -  7.50%` | `implemented` | TFIS now consumes `R/S/U/W/Z186`; `Z186` maps to the current-day `entry_price` override from `AB6_OS_Z186`. |
| `AB6 OS` | `187` | Short FSL / TRP missed | `FSL / TRP Missed` | `Bull / Bull CF` | `Put / Short` | `RC @ L187 = 09:29:59.400000` | `None` | `M187 = 09:29:59 AM HH + 10.00%` | `R/S/U/W/Z blank` | `implemented` | Workbook confirms FSL-only handling here. Blank strike / premium / entry cells must not be inferred. |
| `AB6 OS` | `188` | Short FSL / TRP missed | `FSL / TRP Missed` | `Bear / Bear CF` | `Put / Short` | `RC @ L188 = 09:29:59.400000` | `None` | `M188 = 09:29:59 AM HH + 7.00%` | `R/S/U/W/Z blank` | `implemented` | Workbook confirms FSL-only handling here. Blank strike / premium / entry cells must not be inferred. |
| `AB6 OS` | `190` | `Check If Close at 03:00:00 PM  > Call/Put Original SL` | Position open note | `N/A` | `Call` and `Put` | `15:00:00` | `None` | `Square Off The Position At CMP at 03:00:00 PM` | `None` | `blocked` | This is operational text for a position-open missed-SL case, not a numeric recalculation formula block. |
| `AB6 OS` | `191` | `Check If Close at 03:00:00 PM  < Call/Put Original SL` | Position open note | `N/A` | `Call` and `Put` | `15:00:00` | `None` | `Then Continue the Position for Next Day And Calculate Stop Loss Price as per the Rules` | `None` | `blocked` | The workbook signals later continuation-stoploss logic, but this block does not provide the numeric rule needed to implement it safely. |

## Audit Answers

### 1. Are there workbook-backed cases where recalculated target should differ from base target?

No within `AB6 OS` rows `162-191`.

- base target cells are visible in `O162`, `O165`, `O168`, and `O171`
- no recalculation row in `175-191` shows a replacement target cell
- rows `190-191` describe square-off / continue decisions, not new numeric target formulas

### 2. Are there workbook-backed cases where recalculated stoploss should differ beyond already implemented paths?

Not numerically within this block.

Workbook-backed and already implemented stoploss / FSL recalculation exists only for:

- `184` -> `09:29:59 AM HH + 7.00%`
- `185` -> `09:29:59 AM HH + 10.00%`
- `187` -> `09:29:59 AM HH + 10.00%`
- `188` -> `09:29:59 AM HH + 7.00%`

Rows `190-191` mention later position-open stoploss handling, but the numeric
continuation rule is not present in this block.

### 3. Are there additional same-day recalculation rows beyond currently implemented rows 183-188?

Two categories exist:

- already implemented ORPT missed-entry rows `176-180`
- later same-day / next-day position-open notes in rows `190-191`

Rows `190-191` are not safe to implement yet because they contain process text
only and no numeric recalculation cells.

### 4. Are there any rows that confirm unsupported paths?

No.

This audit still found no current-day FSL / TRP row that safely confirms:

- Bull / Bull CF Put not missed
- Bear / Bear CF Call not missed

Those paths should remain unchanged / unsupported.

### 5. Are there any formula cells that were previously skipped but actually contain valid logic?

Yes.

The strongest prior gap was the populated current-day option-entry cells:

- `Z183 = Min of ( OPT : PRV : 3DLL & OPT : CDLL )  -  7.50%`
- `Z184 = Min of ( OPT : PRV : 2DLL & OPT : CDLL )  -  7.50%`
- `Z185 = Min of ( OPT : PRV : 2DLL & OPT : CDLL )  -  7.50%`
- `Z186 = Min of ( OPT : PRV : 3DLL & OPT : CDLL )  -  7.50%`

These cells are formula-generated rule-description text, not direct numeric
outputs, but they sit under the `Option Entry` header in row `182` and mirror
the already-consumed revised-entry column in the ORPT missed-entry block. That
made them safe to map to the current-day `entry_price` override for supported
rows `183-186`.

### 6. Which recalculation rules are fully implementable, partially implementable, or blocked?

Fully implementable and already implemented:

- ORPT missed-entry rows `176-180`
- current-day FSL / TRP rows `183-186`, including their workbook-backed
  `entry_price` overrides from `Z183:Z186`
- current-day FSL / TRP FSL-only rows `187-188`
- current-day FSL / TRP stoploss overrides in `184-185`

Blocked:

- any recalculated target override in this block
- position-open continuation logic from `190-191`
- unsupported current-day not-missed paths that still have no confirming row

## Recommended Next Step From This Audit

No further safe target or continuation-stoploss expansion is supported by
`AB6 OS` rows `162-191` at this time.

The next S23 priority should move away from workbook inference and toward the
remaining realism and coverage layers unless new workbook evidence appears.
