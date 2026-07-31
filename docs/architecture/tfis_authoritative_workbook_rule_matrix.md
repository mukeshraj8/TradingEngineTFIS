# TFIS Authoritative Workbook Rule Matrix

This document is the source index for future TFIS business-rule work. The
machine-readable matrix is
`reports/phase3d/milestone13a_authoritative_rule_matrix.json`.

M13B source closure trace:
`reports/phase3d/milestone13b_cell_trace.json`.

## Authority Vocabulary

- `WORKBOOK_CELL_VERIFIED`: exact workbook row/cell is available and directly
  reviewed.
- `WORKBOOK_FORMULA_DOMAIN_VERIFIED`: workbook formulas close the valid-input
  formula domain, while invalid-input behavior remains fail-closed if not
  separately authorized.
- `USER_CLARIFIED_AND_RECORDED`: latest user clarification is the authority.
- `WORKBOOK_AND_CODE_MATCH`: verified source and current code agree.
- `MISSING_IMPLEMENTATION`: source rule exists but this architecture slice does
  not implement it yet.
- `SOURCE_CELL_NOT_FOUND`: reviewed source set did not contain the needed cell.
- `OPERATIONAL_IMPLEMENTATION_CHOICE`: implementation mechanism, not business
  rule authority.

## Reviewed Source Set

- `TFISRulesAndSpec/All in One - TFIS 26-12-2023.xlsx`
- `TFISRulesAndSpec/AB7 OS.xlsx`
- `reports/phase3d/milestone13b_cell_trace.json`
- `docs/importers/s23_recalculation_audit.md`
- `docs/importers/excel_ambiguity_audit.md`
- `docs/importers/S23_excel_mapping.md`
- `docs/architecture/s23_weekly_option_selling_engine_contract.md`
- `docs/strategy/s23_gap_recalculation_design.md`
- `config/importer_open_questions.yaml`
- S23 `excel_crosscheck.yaml` files
- current S23 strategy/recalculation/lifecycle code

Workbook hash:

- `TFISRulesAndSpec/All in One - TFIS 26-12-2023.xlsx`
- SHA256 `1D2DB2C2834C2081AE21E460471CD1546D988DCF8125B312AD453BA8027BD301`

## S23 Carried-Position Rules

| Rule ID | Source | Business Rule | Code Status |
| --- | --- | --- | --- |
| `S23-CARRIED-TARGET-USER-2026-07-31` | latest user clarification | Target protection is active from market open; target crossed means `EXIT_REQUIRED`. If target and protection both cross, target-first priority wins. | Implemented offline in M13B |
| `S23-CARRIED-CALL-NOT-MISSED-AB6OS-183` | `AB6 OS!E183:H183` | If 09:15 option high is not above original SL, require normal SL placement at ORPT. | Implemented offline in M13 |
| `S23-CARRIED-CALL-MISSED-BULL-AB6OS-184` | `AB6 OS!M184:O184` | Bull/Bull CF Call missed original SL waits for RC and requires revised FSL using `09:29:59 AM HH + 7.00%`. | Implemented as offline requirement/evidence helper |
| `S23-CARRIED-CALL-MISSED-BEAR-AB6OS-185` | `AB6 OS!M185:O185` | Bear/Bear CF Call missed original SL waits for RC and requires revised FSL using `09:29:59 AM HH + 10.00%`. | Implemented as offline requirement/evidence helper |
| `S23-CARRIED-PUT-MISSED-BULL-AB6OS-187` | `AB6 OS!M187:O187` | Bull/Bull CF Put missed original SL uses `09:29:59 AM HH + 10.00%`. | Policy recorded; not activated in S23 Call vertical |
| `S23-CARRIED-PUT-MISSED-BEAR-AB6OS-188` | `AB6 OS!M188:O188` | Bear/Bear CF Put missed original SL uses `09:29:59 AM HH + 7.00%`. | Policy recorded; not activated in S23 Call vertical |
| `S23-EOD-CARRY-AB6OS-190-191` | `AB6 OS!F190:J191`, `AB6 OS!Q190:U191`; user clarification for equality | Workbook source: 15:00 close above original SL squares off at CMP; 15:00 close below original SL carries forward and calculates next-day SL as per rules. Effective rule after user clarification: close equal to original SL also carries forward. | Implemented as offline evidence helper |
| `S23-NONPOSITIVE-RISK` | `AB16!K104`, `AB16!P104:P105`, `AB16!AI107`, `AB16!K111`, `AB16!P111:P112`, `AB16!AI114` | S23 option-selling formulas remain positive for valid positive premium inputs. Zero/negative invalid market inputs fail closed. | Implemented as offline evidence/helper guard |

## Fresh-Entry Rules

Fresh-entry Gap/Missed-Entry remains separate from carried-position FSL/TRP
recalculation. Verified fresh-entry rows include `AB6 OS!175:180` and are
represented in the JSON matrix.

## Remaining Boundaries

- Do not activate Put-side carried-position formulas in the current S23 Call
  vertical slice.
- Do not generalize S27 option-buying negative-price guards into S23 option
  selling.
- Do not convert source gaps into actionable handoffs. Missing authority must
  remain `RULE_AUTHORITY_UNRESOLVED` or fail closed.
