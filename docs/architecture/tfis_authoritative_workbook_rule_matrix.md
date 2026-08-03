# TFIS Authoritative Workbook Rule Matrix

This document is the source index for future TFIS business-rule work. The
machine-readable matrix is
`reports/phase3d/milestone13a_authoritative_rule_matrix.json`.

M13B source closure trace:
`reports/phase3d/milestone13b_cell_trace.json`.

Phase 5B Put closure trace:
`reports/phase5b/phase5b_put_cell_trace.json`.

S21 source closure trace:
`reports/s21_source_closure/s21_rule_matrix.json`.

S22 source and universe closure trace:
`reports/s22_source_closure/s22_rule_matrix.json`.

Current S21 source-closure verdict:
`S21_SOURCE_CLOSURE_ACCEPT`. No financially material S21 source questions
remain open after the 2026-08-02 source-closure directive and APS
clarification. S21 implementation has not started and no broker, paper, live,
order, or position mutation authority is granted by this closure.

Current S22 source/universe verdict:
`S22_SOURCE_AND_UNIVERSE_CONDITIONAL`. Workbook rules are traced for identity,
four branches, contract selection, Entry/ORPT/RC, Target, SL/MSL/FSL/TRP,
EOD/carry and quantity semantics. Universe and instrument-metadata governance
is now user-clarified: AB8/AB10 are historical strategy-supported-universe
evidence; current exchange eligibility and per-stock metadata must come from a
dated versioned instrument-master snapshot; no stock is runnable without an
explicit operator-enabled subset. `S22-Q002` is closed by user selection of
`RELIANCE` as the only Stage 1 S22 internal-paper stock, subject to dated
instrument-master and metadata validation. No S22 implementation, runtime
configuration, broker, paper, live, order, or position mutation authority is
granted by this closure.

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
- S21 source closure reports under `reports/s21_source_closure/`
- S22 source and universe closure reports under
  `reports/s22_source_closure/` and `reports/s22_universe/`

Workbook hash:

- `TFISRulesAndSpec/All in One - TFIS 26-12-2023.xlsx`
- SHA256 `1D2DB2C2834C2081AE21E460471CD1546D988DCF8125B312AD453BA8027BD301`
- `TFISRulesAndSpec/All_in_One_TFIS_26-12-2023_Unprotected_Copy.xlsx`
- SHA256 `603ea7bc09ebb0c7df2ad0202d492c9ca49e890cfefdb3f0eddb1edcbe8fbddd`
- `TFISRulesAndSpec/AB6 OS.xlsx`
- SHA256 `a53249475ee6653545c9a4e984667ae405142abee657acabe17348379cadb836`

## S23 Carried-Position Rules

## Global Option-Selling EOD Rules

| Rule ID | Source | Business Rule | Code Status |
| --- | --- | --- | --- |
| `OPTION-CHAIN-ACTUAL-LISTED-STRIKE-GLOBAL-USER-2026-08-03` | User clarification 2026-08-03 plus approved broker/exchange option-chain evidence. | TFIS shall select option contracts only from actual exchange-listed contracts returned by an approved option-chain or instrument-master source. It shall never invent synthetic strikes from a fixed interval. Uneven strike spacing is valid. Start Strike, End Strike, Last Choice, and traversal direction apply as boundary and ordering semantics over the actual listed strike set for the selected expiry and option type. Rounded/calculated strikes are search references only; if not listed, traversal starts from the first actual listed strike that satisfies the workbook boundary semantics. Missing or incomplete chains fail closed with explicit quality classification. | Global authority recorded. S22 actual-strike traversal now uses real listed contracts; S23 paper selector already consumed actual normalized contracts; S21 implementation remains pending. |
| `OPTION_SELLING-EOD-CARRY-ORIGINAL-SL-GLOBAL-USER-2026-08-01` | Workbook authority for strict operators: S21 `AB6 OS!F96:J97`, `AB6 OS!Q96:U97`; S23 `AB6 OS!F190:J191`, `AB6 OS!Q190:U191`. User clarification on 2026-08-01 supplies equality for all Option Selling strategies unless a future workbook explicitly proves otherwise. | At the configured EOD decision time, normally 15:00: if closing price is greater than Original SL, square off the position. Otherwise, closing price less than or equal to Original SL carries the position forward. Workbook authority: `>` and `<`. User-clarified authority: `==` carries forward. Applies to S21, S22, S23, and all other Option Selling strategies. Does not apply to Futures, Option Buying, or Equity unless those products have their own verified EOD rules. | Global authority recorded. Existing S23 implementation already follows equality carry-forward. S21 implementation not started. |
| `OPTION-SELLING-APS-APPLICABILITY-GLOBAL-USER-2026-08-02` | User clarification 2026-08-02; S21 APS labels in `AB2!K26`, `AB6 OS!C107`, `AB15!S11`, `AB16!E79`. | APS is a generic trading capability, but it is not applicable to one-lot Option Selling strategies such as S21, S22 and S23. One lot uses one Target, one PositionCycle quantity, no staged exits, no quantity splitting, no partial PositionCycle, and no APS-specific protection adjustment. APS may apply to strategies configured for more than one lot only when workbook authority defines quantity allocation, Target allocation, and protection-adjustment rules; otherwise fail closed. | Global authority recorded. Do not implement APS inside generic PositionCycle/lifecycle for S21/S22/S23 one-lot Option Selling. |

## S21 Source-Closure Rules

| Rule ID | Source | Business Rule | Code Status |
| --- | --- | --- | --- |
| `S21-MONTHLY-STATUS-V1` | `TFIS_Monthly_Status_Reference_and_Implementation_Specification_v1.0.docx`; `AB11!D11` | S21 consumes the shared upstream Monthly Status state machine. BANKNIFTY uses the Index Option Selling underlying/spot CMP source and BANKNIFTY parameters. | Source-closed; implementation not started. |
| `S21-BRANCH-RESOLUTION-AB6OS-100-110` | `AB6 OS!D100:D110`, `AB6 OS!F100:F110`, `AB6 OS!J100:K110` | `BULL`/`BULL_CF` select Bull Call and Bull Put rows; `BEAR`/`BEAR_CF` select Bear Call and Bear Put rows. Call and Put rows are independent. | Source-closed; implementation not started. |
| `S21-CONTRACT-SELECTION-Q001-CLOSED` | `AB2!V26:AA26`, `AB1!D28:K28`, `AB6 OS!G100:I110`, `AB15!J11:P11`; source-closure directive 2026-08-02 | Search Near monthly expiry first independently for each Call/Put leg. If no qualifying contract is found due to strike, OI, ideal premium, or minimum premium failure, search Next monthly expiry. If Next also fails, do not trade that leg. Call and Put do not need the same expiry. Traverse from Start Strike to End Strike and choose the first qualifying strike. | Source-closed; implementation not started. |
| `S21-GAP-CLASSIFICATION-Q002-CLOSED` | `AB6 OS!D112:E118`, `AB6 OS!I114:X118`; source-closure directive 2026-08-02 | S21 V1 has no separate GAP_UP/GAP_DOWN/no-gap branch logic. Generic OpeningMarketContext may record opening gap evidence, but S21 trade behavior uses only workbook ORPT missed-entry checks and RC recalculation rules. | Source-closed; implementation not started. |
| `S21-APS-Q003-CLOSED` | `AB2!K26`, `AB6 OS!C107`, `AB15!S11`, `AB16!E79`; global APS clarification 2026-08-02 | `APS_NOT_APPLICABLE` for S21 one-lot Option Selling. No APS, no partial Target allocation, no quantity splitting, no partial PositionCycle, and no APS-specific protection adjustment. | Source-closed; implementation not started. |
| `S21-QUANTITY-PNL-Q004-CLOSED` | `AB11!H11/K11`, `AB16!K75/K82`, `AB16!I77/I84`, `AB18!O38/O41`, `AB15!U11`; global APS/quantity clarification 2026-08-02 | Configured trading quantity is one lot. BANKNIFTY lot size is 15, so exchange quantity is 15. P&L uses confirmed exchange quantity. `500 Lots` is the OI threshold, not order quantity. `AB15!U11=2` is not execution/P&L quantity for S21 V1. | Source-closed; implementation not started. |
| `S21-ROLLOVER-EXPIRY-Q005-CLOSED` | `AB2!X26:AA26`, `AB11!M11:P11`, `AB1!D28:K28`, `AB6 OS!J97/U97`; source-closure directive 2026-08-02 | No automatic rollover for open S21 positions in V1. Fresh entries follow approved contract-selection rules. Open positions follow verified EOD/carry and carried-position lifecycle rules. Unsupported expiry continuation fails closed for operator/user decision. | Source-closed; implementation not started. |

## S22 Source And Universe Closure Rules

| Rule ID | Source | Business Rule | Code Status |
| --- | --- | --- | --- |
| `S22-STRATEGY-IDENTITY-AB2-27` | `AB2!A27:AH27`, `AB6 OS!A131:C138`, `AB10!A12:H12` | S22 is the common stock Option Selling monthly strategy `STOCKS_OP_SELL_MT_DIFF_2D_4D`. Stock symbol is an instrument-instance input; copied strategy definitions per stock are prohibited. | Source-closed; implementation waits only for explicit enabled stock selection. |
| `S22-BRANCH-MATRIX-AB6OS-131-141` | `AB6 OS!D131:M141`, `AB14!A42:BG46` | `BULL`/`BULL_CF` and `BEAR`/`BEAR_CF` map to independent Call and Put sell branches with branch-specific 2D/4D references, strike formulas, ideal/minimum premium filters, OI threshold, Base Entry, Target and SL/MSL formulas. | Source-closed; implementation waits only for explicit enabled stock selection. |
| `S22-CONTRACT-SELECTION-AB6OS-131-149` | `AB6 OS!G131:I141`, `AB6 OS!M145:W149`, `AB11!E12:X12` | Contract selection uses Near monthly expiry evidence, branch-specific Start/End strike traversal, ideal premium, minimum premium, minimum OI of 100 lots, and one expiry in the workbook example. Evaluated values are stock-specific and resolved through the trading-date instrument-master snapshot and market evidence. | Source-closed; instrument-master architecture ready. |
| `S22-ENTRY-ORPT-RC-AB6OS-143-149` | `AB6 OS!B143:AA149` | At ORPT, compare `09:24:59 AM LL < option sell entry`. If not missed, place at ORPT; if missed, wait until RC `09:29:59` and recalculate branch-specific strike, premium and entry. | Source-closed; implementation waits only for explicit enabled stock selection. |
| `S22-TARGET-SL-FSL-TRP-AB6OS-131-157` | `AB6 OS!M131:O141`, `AB6 OS!M153:M157`, `AB14!F42:BG46` | Target is entry minus 60 percent. Original SL/MSL is the workbook `Min(entry + 60%, branch option high reference + 7% or +10%)`. Carried-position missed-SL recalculation uses the branch-specific `09:29:59 AM HH + 7%` or `+10%` FSL/TRP rule. | Source-closed; implementation waits only for explicit enabled stock selection. |
| `S22-EOD-CARRY-AB6OS-159-160` | `AB6 OS!F159:J160`, `AB6 OS!Q159:U160`; global Option Selling EOD rule for equality | At 15:00, close greater than Original SL exits. Close less than or equal to Original SL carries forward. Equality is user-clarified globally for Option Selling. | Source-closed; implementation waits only for explicit enabled stock selection. |
| `S22-QUANTITY-ACCOUNTING-ONE-LOT` | `AB11!H12/K12`, `AB16!I90:W91`; global APS clarification; S22 universe closure directive | S22 Option Selling stores `configured_quantity_lots = 1`. Runtime resolves `quantity_exchange_units = configured_quantity_lots * trading-date-applicable lot_size` from the versioned instrument master. APS is not applicable. P&L must use confirmed exchange units and must not double-multiply lot size. | Source-closed; instrument-master architecture ready. |
| `S22-UNIVERSE-GOVERNANCE` | `AB8`, `AB10`, S22 universe closure directive 2026-08-02 | AB8/AB10 are historical `STRATEGY_SUPPORTED_UNIVERSE` evidence. `EXCHANGE_ELIGIBLE_UNIVERSE` must come from a dated versioned instrument-master snapshot. `OPERATOR_ENABLED_SUBSET` requires explicit user-approved symbols. A stock is runnable only when it belongs to all required layers. | Architecture-ready. Stage 1 user-selected stock is `RELIANCE`. |
| `S22-STAGE1-RELIANCE-OPERATOR-SELECTION` | User clarification 2026-08-02 | Enable `RELIANCE` as the only Stage 1 S22 internal-paper stock, with one instrument-bound S22 strategy instance and one internal-paper account. Before implementation, dated instrument-master metadata must confirm F&O eligibility, lot size/effective date, strike interval/tick size, monthly option expiry availability, broker/data identifiers, and usable option-chain/premium/OI evidence. If incomplete, return `BLOCKED_METADATA` and do not select a substitute automatically. | Operator selection closed; implementation gated by RELIANCE metadata validation. |

| Rule ID | Source | Business Rule | Code Status |
| --- | --- | --- | --- |
| `S23-CARRIED-TARGET-USER-2026-07-31` | latest user clarification | Target protection is active from market open; target crossed means `EXIT_REQUIRED`. If target and protection both cross, target-first priority wins. | Implemented offline in M13B |
| `S23-CARRIED-CALL-NOT-MISSED-AB6OS-183` | `AB6 OS!E183:H183` | If 09:15 option high is not above original SL, require normal SL placement at ORPT. | Implemented offline in M13 |
| `S23-CARRIED-CALL-MISSED-BULL-AB6OS-184` | `AB6 OS!M184:O184` | Bull/Bull CF Call missed original SL waits for RC and requires revised FSL using `09:29:59 AM HH + 7.00%`. | Implemented as offline requirement/evidence helper |
| `S23-CARRIED-CALL-MISSED-BEAR-AB6OS-185` | `AB6 OS!M185:O185` | Bear/Bear CF Call missed original SL waits for RC and requires revised FSL using `09:29:59 AM HH + 10.00%`. | Implemented as offline requirement/evidence helper |
| `S23-CARRIED-PUT-MISSED-BULL-AB6OS-187` | `AB6 OS!M187:O187` | Bull/Bull CF Put missed original SL uses `09:29:59 AM HH + 10.00%`. | Activated in Phase 5B internal-paper Put evidence |
| `S23-CARRIED-PUT-MISSED-BEAR-AB6OS-188` | `AB6 OS!M188:O188` | Bear/Bear CF Put missed original SL uses `09:29:59 AM HH + 7.00%`. | Activated in Phase 5B internal-paper Put evidence |
| `S23-EOD-CARRY-AB6OS-190-191` | `AB6 OS!F190:J191`, `AB6 OS!Q190:U191`; references global rule `OPTION_SELLING-EOD-CARRY-ORIGINAL-SL-GLOBAL-USER-2026-08-01` for equality | Workbook source: 15:00 close above original SL squares off at CMP; 15:00 close below original SL carries forward and calculates next-day SL as per rules. Effective Option Selling rule: close equal to original SL also carries forward. | Implemented as offline evidence helper |
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
