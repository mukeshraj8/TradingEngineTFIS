# Premium Formula Semantics

## Context

There was an interpretation gap between:

- the original manual S23 YAML behavior
- the workbook-discovered premium formulas
- the folder-based S23 parameters

This note records the current decision and the remaining migration question.

For folder-based S23, Excel is now treated as the source of truth.

## Old Manual YAML Behavior

Legacy S23 YAML uses:

- `ideal_premium_formula: "PRV_3DLL + 1.20%"`
- `minimum_premium_formula: "PRV_3DLL + 0.90%"`

That means the manual config behaves like:

- add `1.20%` of `PRV_3DLL`
- add `0.90%` of `PRV_3DLL`

For `PRV_3DLL = 22000`, this gives:

- ideal premium = `22264`
- minimum premium = `22198`

## Excel-Discovered Formula

Workbook discovery for the Bull / Bull CF Call branch found:

- `AB6 OS!H162 = "SPT : PRV : 3DLL * 1.20%"`
- `AB6 OS!H163 = "SPT : PRV : 3DLL * 0.90%"`

This reads more naturally as multiplication rather than additive adjustment.

If interpreted literally:

- `22000 * 1.20% = 264`
- `22000 * 0.90% = 198`

That does not match the current S23 evaluated outputs.

## Current Folder-Based S23 Decision

The folder-based S23 config currently uses:

- `ideal_premium_formula: "PRV_3DLL * PARAM(ideal_premium_pct)%"`
- `minimum_premium_formula: "PRV_3DLL * PARAM(minimum_premium_pct)%"`

with parameters:

- `ideal_premium_pct: 1.20`
- `minimum_premium_pct: 0.90`

This now follows the Excel-discovered semantics:

- `22000 * 1.20% = 264`
- `22000 * 0.90% = 198`

So the folder-based S23 strategy is now semantically aligned with the workbook.

## Legacy Compatibility

The legacy single-file YAML remains unchanged.

That means TFIS currently supports two explicit behaviors:

- legacy YAML behavior:
  - `PRV_3DLL + 1.20%`
  - `PRV_3DLL + 0.90%`
- folder-based S23 behavior:
  - `PRV_3DLL * 1.20%`
  - `PRV_3DLL * 0.90%`

This difference is intentional and covered by tests.

## Recommendation Going Forward

- treat the folder-based strategy layout as the preferred and semantically corrected source
- keep the legacy YAML unchanged until a broader migration is intentionally approved
- make the legacy-vs-folder premium difference explicit in importer and migration docs

## Remaining Open Question

The remaining question is not about S23 folder behavior anymore. It is about migration policy:

- should other legacy strategies be corrected to workbook semantics during folder migration, or should they preserve old runtime behavior until individually reviewed?
