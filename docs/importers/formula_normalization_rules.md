# Formula Normalization Rules

## Purpose

This document defines how workbook rule text should be converted into normalized TFIS formula strings.

These rules are for importer design and review. They are not yet automatic importer behavior.

## Reference Token Mapping

Workbook reference forms and proposed normalized forms:

| Workbook text | Proposed normalized form | Status | Notes |
| --- | --- | --- | --- |
| `SPT : PRV : 3DLL` | `PRV_3DLL` | Approved candidate | Aligns with the current formula engine alias style. |
| `SPT : PRV : 3DHH` | `PRV_3DHH` | Approved candidate | Same alias family. |
| `SPT : PRV : 2DLL` | `PRV_2DLL` | Approved candidate | Same alias family. |
| `SPT : PRV : 2DHH` | `PRV_2DHH` | Approved candidate | Same alias family. |
| `SPT : CDLL` | `CDLL` | Approved candidate | Aligns with current-day low alias. |
| `SPT : CDHH` | `CDHH` | Approved candidate | Aligns with current-day high alias. |
| `OPT : PRV : 3DLL` | `OPT_PRV_3DLL` | Unresolved | Formula engine does not yet support option-premium reference aliases. |
| `OPT : PRV : 2DHH` | `OPT_PRV_2DHH` | Unresolved | Same issue. |
| `OPT : PRV : 3DHH` | `OPT_PRV_3DHH` | Unresolved | Same issue. |
| `OPT : PRV : 2DLL` | `OPT_PRV_2DLL` | Unresolved | Same issue. |
| `CE : Entry` | `ENTRY` | Approved candidate | For call-branch target/SL formulas. |
| `PE : Entry` | `ENTRY` | Approved candidate | For put-branch target/SL formulas. |

## Function Conversion

Use these structural conversions:

| Workbook text | Normalized form |
| --- | --- |
| `Min ( A & B )` | `MIN(A, B)` |
| `Max of ( A & B )` | `MAX(A, B)` |
| `Round Down` | `ROUND_DOWN(...)` |
| `Round Up` | `ROUND_UP(...)` |

Examples:

- `( SPT : PRV : 3DLL + 5.00% ) & Round Down`
  -> `ROUND_DOWN(PRV_3DLL + 5%)`
- `( SPT : PRV : 3DLL ) & Round Down - 1`
  -> `ROUND_DOWN(PRV_3DLL) - 1`
- `Min ( CE : Entry + 60.00% & OPT : PRV : 2DHH + 7.00% )`
  -> `MIN(ENTRY + 60%, OPT_PRV_2DHH + 7%)`

## Percentage Normalization

Normalize percent literals by preserving magnitude and simplifying trailing zeros:

| Workbook text | Normalized form |
| --- | --- |
| `5.00%` | `5%` |
| `7.50%` | `7.5%` |
| `60.00%` | `60%` |
| `1.20%` | `1.20%` |
| `0.90%` | `0.90%` |

Important note:

- Workbook premium text currently uses multiplication form such as `* 1.20%`.
- This should remain multiplication in the normalization plan until explicitly approved otherwise.

## Quantity And OI Normalization

Examples:

- `500 Lots` -> `500`
- `1 Exp` -> keep as workbook-only operational text unless a YAML field is introduced for it

## Time Normalization

Examples:

- `09:24:59.400000` -> `09:24:59`
- `09:29:59.400000` -> `09:29:59`

Normalization rule:

- preserve `HH:MM:SS`
- discard workbook microseconds

## Branch-Specific ENTRY Normalization

For branch-local formulas:

- `CE : Entry` -> `ENTRY`
- `PE : Entry` -> `ENTRY`

Reason:

- the normalized `StrategyRule` already selects one branch
- once a branch is chosen, the branch-local entry reference can be expressed as the generic runtime `ENTRY`

## Current Limits

Not yet fully supported by the current formula engine:

- `OPT_PRV_...` aliases
- explicit multiplication parsing for all workbook premium expressions if those need runtime evaluation
- workbook constructs that mix current-day spot levels with option-premium references in one expression unless aliases are added first

## Recommendation Before Importer Implementation

Approve these first:

1. `OPT : PRV : ...` naming convention
2. premium formulas staying as multiplication
3. whether multi-branch workbook families become one config or multiple configs
