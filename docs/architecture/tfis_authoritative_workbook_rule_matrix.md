# TFIS Authoritative Workbook Rule Matrix

This document is the source index for future TFIS business-rule work. The
machine-readable matrix is
`reports/phase3d/milestone13a_authoritative_rule_matrix.json`.

M13B source closure trace:
`reports/phase3d/milestone13b_cell_trace.json`.

Phase 5B Put closure trace:
`reports/phase5b/phase5b_put_cell_trace.json`.

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
- Phase 5B S23 Put reports under `reports/phase5b/`

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
| `S23-CARRIED-PUT-MISSED-BULL-AB6OS-187` | `AB6 OS!M187:O187` | Bull/Bull CF Put missed original SL uses `09:29:59 AM HH + 10.00%`. | Activated in Phase 5B internal-paper Put evidence |
| `S23-CARRIED-PUT-MISSED-BEAR-AB6OS-188` | `AB6 OS!M188:O188` | Bear/Bear CF Put missed original SL uses `09:29:59 AM HH + 7.00%`. | Activated in Phase 5B internal-paper Put evidence |
| `S23-EOD-CARRY-AB6OS-190-191` | `AB6 OS!F190:J191`, `AB6 OS!Q190:U191`; user clarification for equality | Workbook source: 15:00 close above original SL squares off at CMP; 15:00 close below original SL carries forward and calculates next-day SL as per rules. Effective rule after user clarification: close equal to original SL also carries forward. | Implemented as offline evidence helper |
| `S23-NONPOSITIVE-RISK` | `AB16!K104`, `AB16!P104:P105`, `AB16!AI107`, `AB16!K111`, `AB16!P111:P112`, `AB16!AI114` | S23 option-selling formulas remain positive for valid positive premium inputs. Zero/negative invalid market inputs fail closed. | Implemented as offline evidence/helper guard |

## Fresh-Entry Rules

Fresh-entry Gap/Missed-Entry remains separate from carried-position FSL/TRP
recalculation. Verified fresh-entry rows include `AB6 OS!175:180` and are
represented in the JSON matrix.

## S23 Put Fresh-Entry And Lifecycle Rules

| Rule ID | Source | Business Rule | Code Status |
| --- | --- | --- | --- |
| `S23-BULL-PUT-AB6OS-165-166` | `AB6 OS!F165:M166` | Bull/Bull CF Put selects Put, start strike from `SPT:PRV:2DHH - 5%` rounded up, end strike from `SPT:PRV:2DHH` rounded up plus one strike, ideal premium `SPT:PRV:2DHH * 1.20%`, minimum premium `SPT:PRV:2DHH * 0.90%`, minimum OI `500 Lots`, base entry `OPT:PRV:2DLL - 7.50%`, target `PE Entry - 60%`, and original SL/MSL as `Min(PE Entry + 60%, OPT:PRV:3DHH + 10%)`. | Activated in Phase 5B internal-paper Put evidence |
| `S23-BEAR-PUT-AB6OS-171-172` | `AB6 OS!F171:M172` | Bear/Bear CF Put selects Put, start strike from `SPT:PRV:3DHH - 5%` rounded up, end strike from `SPT:PRV:3DHH` rounded up plus one strike, ideal premium `SPT:PRV:3DHH * 1.20%`, minimum premium `SPT:PRV:3DHH * 0.90%`, minimum OI `500 Lots`, base entry `OPT:PRV:3DLL - 7.50%`, target `PE Entry - 60%`, and original SL/MSL as `Min(PE Entry + 60%, OPT:PRV:2DHH + 7%)`. | Activated in Phase 5B internal-paper Put evidence |
| `S23-PUT-MISSED-ENTRY-OPTION-LOW` | `AB6 OS!E175`, `AB6 OS!I179:X180`; `docs/strategy/s23_entry_missed_detection.md` | Active Put missed-entry detection uses selected option low: `OPTION_LOW < BASE_ENTRY`. Legacy option-high Put profiles are classified `LEGACY_ONLY_NOT_AUTHORITY`. | Conflict closed as `AUTHORITATIVE_OPTION_LOW` |
| `S23-BULL-PUT-GAP-RC-AB6OS-179` | `AB6 OS!M179:X179` | Bull/Bull CF Put missed-entry recalculation waits for RC and recalculates strike, premium, and entry references from the workbook Put row. | Activated in Phase 5B internal-paper Put evidence |
| `S23-BEAR-PUT-GAP-RC-AB6OS-180` | `AB6 OS!M180:X180` | Bear/Bear CF Put missed-entry recalculation waits for RC and recalculates strike, premium, and entry references from the workbook Put row. | Activated in Phase 5B internal-paper Put evidence |

## Remaining Boundaries

- Phase 5B activates Put-side evidence only inside complete S23 internal-paper
  certification. It does not add broker, paper-order submission, live routing,
  order mutation, or position mutation authority.
- Do not generalize S27 option-buying negative-price guards into S23 option
  selling.
- Do not convert source gaps into actionable handoffs. Missing authority must
  remain `RULE_AUTHORITY_UNRESOLVED` or fail closed.
