# Excel Ambiguity Audit

This document tracks workbook ambiguities that affect TFIS normalization or
diagnostic implementations.

Purpose:

- keep workbook uncertainties visible
- separate resolved interpretations from deferred ones
- prevent later normalization from silently overwriting an unresolved choice
- link each ambiguity to concrete workbook rows and cells

## Resolved Ambiguities

### S23 put-branch missed-entry recalculated premium formulas

Workbook references:

- `AB6 OS!T179`
- `AB6 OS!V179`
- `AB6 OS!T180`
- `AB6 OS!V180`

Resolved reading:

- Bull / Bull CF Put recalculated ideal premium uses:
  - `MIN(SPT : PRV : 2DHH, 09:29:59 AM LL) * 1.20%`
- Bull / Bull CF Put recalculated minimum premium uses:
  - `MIN(SPT : PRV : 2DHH, 09:29:59 AM LL) * 0.90%`
- Bear / Bear CF Put recalculated ideal premium uses:
  - `MIN(SPT : PRV : 3DHH, 09:29:59 AM LL) * 1.20%`
- Bear / Bear CF Put recalculated minimum premium uses:
  - `MIN(SPT : PRV : 3DHH, 09:29:59 AM LL) * 0.90%`

Why this is resolved:

- the workbook cell wording is explicit
- the premium cells consistently use `Min of (...)` and `09:29:59 AM LL`
- this reading matches the existing S23 call-side recalculation pattern of
  using the lower reference for recalculated premium and entry

### S23 put-branch missed-entry recalculated strike wording

Workbook references:

- `AB6 OS!M179`
- `AB6 OS!O179`
- `AB6 OS!M180`
- `AB6 OS!O180`

Workbook wording:

- `Max of ( SPT : PRV : 2DHH & 09:29:59 AM LL ) - 5.00% ) & Round Up`
- `Max of ( SPT : PRV : 2DHH & 09:29:59 AM LL ) & Round Up + 1`
- `Max of ( SPT : PRV : 3DHH & 09:29:59 AM LL ) - 5.00% ) & Round Up`
- `Max of ( SPT : PRV : 3DHH & 09:29:59 AM LL ) & Round Up + 1`

Confirmed correction:

- Bull / Bull CF Put recalculated strike uses:
  - `MAX(PRV_2DHH, recalc_spot_high)`
- Bear / Bear CF Put recalculated strike uses:
  - `MAX(PRV_3DHH, recalc_spot_high)`

Why this is resolved:

- user confirmation established that the `LL` wording in these cells is a
  workbook copy-paste issue
- the intended business rule is high-versus-high comparison for the put-side
  strike recalculation
- TFIS now treats this as a confirmed workbook correction, not as a silent
  normalization

Audit consequence:

- recalculation audit should no longer surface this item as an unresolved open
  question
- the correction should remain visible as a resolved workbook correction in the
  audit trail where relevant

### S23 current-day FSL / TRP row 184 mixed mapping

Workbook references:

- `AB6 OS!I184`
- `AB6 OS!Q184`
- `AB6 OS!R184`
- `AB6 OS!S184`
- `AB6 OS!U184`
- `AB6 OS!W184`

Workbook wording:

- `I184 = Recalcuate : Call Sell FSL / TRP : Bull / Bull CF`
- `Q184 = Put`
- `R184/S184/U184/W184` structurally reference the Bull Put anchor `A165`

Confirmed reading:

- row `184` is implemented exactly as workbook-directed for the
  Bull / Bull CF Call `FSL / TRP missed` branch
- the Put-side `Q/R/S/U/W` family is treated as intentional for this one
  missed-Call context
- TFIS does not generalize that into a broader rule outside the confirmed row

Why this is resolved:

- user confirmation explicitly removed row `184` as a blocker
- TFIS preserves the mixed workbook evidence in audit notes instead of
  silently normalizing it away
- the implementation stays row-specific, not branch-generalized

Audit consequence:

- `s23_fsl_trp_row_184_mixed_mapping` is now a resolved workbook clarification
- when row `184` is applied, historical audit output should show the resolved
  clarification entry rather than treating it as an open blocker

## Intentionally Deferred Ambiguities

### S23 current-day FSL / TRP rows `183-188`

Workbook references:

- `AB6 OS!D183:W188`
- especially:
  - `AB6 OS!I183:I188`
  - `AB6 OS!Q183:Q186`
  - `AB6 OS!R183:W186`

Purpose of this audit:

- keep the current-day FSL / TRP rows visible and reviewable
- prevent TFIS from generalizing partial row coverage into behavior
- show exactly which rows are implemented and which remain deliberately
  unsupported

Evidence-backed row summary:

| Row | Workbook labels | M:X populated cells | Proposed branch mapping | Confidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `183` | `For Call Sell SL`, `FSL / TRP Not Missed`, `P183 = BULL / BULL CF`, `Q183 = Call` | `R183/S183/U183/W183` | Bull / Bull CF Call, not missed | High | `R/S/U/W` formulas point to `A162`, the Bull Call base branch. |
| `184` | `FSL / TRP Missed`, `I184 = Recalcuate : Call Sell FSL / TRP : Bull / Bull CF`, `Q184 = Put` | `M184/O184` and `R184/S184/U184/W184` | Bull / Bull CF Call missed, workbook-directed Put-side formula family | High | Implement exactly as confirmed; do not generalize beyond this row. |
| `185` | `I185 = Recalcuate : Call Sell FSL / TRP : Bear / Bear CF`, `P185 = BEAR / BEAR CF`, `Q185 = Call` | `M185/O185` and `R185/S185/U185/W185` | Bear / Bear CF Call, missed | High | `R/S/U/W` formulas point to `A168`, the Bear Call base branch. |
| `186` | `For Put Sell SL`, `Check If 09:15:00 AM HH > Short SL`, `FSL / TRP Not Missed`, `Q186 = Put` | `R186/S186/U186/W186` | Bear / Bear CF Put, not missed | Medium-High | No explicit `P186`, but `R/S/U/W` formulas point to `A171`, the Bear Put base branch. |
| `187` | `I187 = Recalcuate : Short FSL / TRP : Bull / Bull CF` | `M187/O187` only | Bull / Bull CF Put, missed, FSL-only | High | `R/S/U/W` are blank; no strike/premium recalculation should be inferred. |
| `188` | `I188 = Recalcuate : Short FSL / TRP : Bear / Bear CF` | `M188/O188` only | Bear / Bear CF Put, missed, FSL-only | High | `R/S/U/W` are blank; no strike/premium recalculation should be inferred. |

Current implementation boundary:

- rows `183-186` are now implemented exactly where the workbook populates
  current-day `R/S/U/W` fields
- rows `187-188` are now implemented as `FSL-only`
- TFIS still must not treat partial workbook coverage as permission to
  generalize current-day FSL / TRP behavior across all four branches
- rows `187-188` remain especially constrained:
  - use them only as evidence for the recalculated FSL buffer
  - do not infer start strike, end strike, ideal premium, or minimum premium

## Rejected Interpretations

### Rejected: put-branch recalculated premiums use high-side references

Rejected interpretation:

- Bull / Bear Put recalculated ideal and minimum premiums should use
  `MAX(...)` or a `09:29:59 AM HH` style reference

Why rejected:

- `AB6 OS!T179`, `AB6 OS!V179`, `AB6 OS!T180`, and `AB6 OS!V180` explicitly use
  `Min of (...)`
- those same cells explicitly refer to `09:29:59 AM LL`

### Rejected: leave put-branch recalculated premiums unresolved

Rejected interpretation:

- keep Bull Put and Bear Put recalculated ideal and minimum premiums as
  unresolved placeholders

Why rejected:

- the workbook wording is explicit enough to implement these fields with high
  confidence

### Rejected: apply the put-side strike cells literally with `recalc_spot_low`

Rejected interpretation:

- follow the `09:29:59 AM LL` text literally inside `AB6 OS!M179/O179/M180/O180`
  and compute the put-side strike range using current-day low

Why rejected:

- user clarification confirmed the `LL` text is a workbook copy-paste issue
- the intended business rule is high-versus-high comparison for these put-side
  strike recalculation rows

## Audit References

- S23 branch mapping: [S23_branch_mapping.md](S23_branch_mapping.md)
- S23 recalculation design: [s23_gap_recalculation_design.md](../strategy/s23_gap_recalculation_design.md)
- Machine-readable open questions: [importer_open_questions.yaml](../../config/importer_open_questions.yaml)
