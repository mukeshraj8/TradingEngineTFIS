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

## Intentionally Deferred Ambiguities

- none currently tracked

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
