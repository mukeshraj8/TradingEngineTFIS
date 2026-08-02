# S21 Source Completeness Checklist

Verdict: `S21_SOURCE_CLOSURE_ACCEPT`

This checklist uses only final allowed statuses:

- `WORKBOOK_VERIFIED`
- `USER_CLARIFIED`
- `CONFIG_CROSSCHECKED`
- `NOT_APPLICABLE`

Primary workbook:

- `TFISRulesAndSpec/All_in_One_TFIS_26-12-2023_Unprotected_Copy.xlsx`
- SHA-256:
  `603ea7bc09ebb0c7df2ad0202d492c9ca49e890cfefdb3f0eddb1edcbe8fbddd`

Authoritative user clarifications:

- `OPTION_SELLING-EOD-CARRY-ORIGINAL-SL-GLOBAL-USER-2026-08-01`: at EOD,
  Option Selling exits only when close is greater than Original SL; equality
  carries forward.
- `OPTION_SELLING-APS-APPLICABILITY-GLOBAL-USER-2026-08-02`: APS is not
  applicable to one-lot Option Selling strategies such as S21, S22 and S23.

| Business stage | Status | Source / note |
| --- | --- | --- |
| Strategy identity | `WORKBOOK_VERIFIED` | `AB2!A26:AD26`, `AB10!A11:H11`: `S21`, BankNifty, monthly option selling, unique code `BANKNIFTY_OP_SELL_MT_DIFF_2D_3D`. |
| Monthly Status | `WORKBOOK_VERIFIED` | `TFIS_Monthly_Status_Reference_and_Implementation_Specification_v1.0.docx` defines the shared Monthly Status state machine; `AB11!D11` supplies the cached S21 status consumed by S21. |
| Branch resolution | `WORKBOOK_VERIFIED` | `AB6 OS!D100:D110`, `AB6 OS!F100:F110`, `AB6 OS!J100:K110`: Bull/Bull CF and Bear/Bear CF branch families map to Call/Put rows. |
| Underlying references | `WORKBOOK_VERIFIED` | `AB6 OS!G100:H110`, `AB6 OS!M100:M110`, `AB4!A126:AS130`, `AB12!A11:E11`: prior spot/option references include `3DLL`, `2DHH`, `2DLL`, and `3DHH`. |
| Contract selection | `USER_CLARIFIED` | `AB6 OS!I101/I104/I107/I110`, `AB15!J11:P11`, and 2026-08-02 source-closure directive: search Near monthly expiry first independently for each Call/Put leg, then Next if qualification fails; no same-expiry requirement. |
| Expiry selection | `USER_CLARIFIED` | `AB2!V26:AA26`, `AB1!D28:K28`, `AB11!E11:P11`, `AB15!J11:P11`, and 2026-08-02 source-closure directive close independent Near-first/Next fallback for each leg. |
| Strike range | `WORKBOOK_VERIFIED` | `AB6 OS!G100:G110`, `AB16!AK74:AP86`: start/end strike rules and round down/up direction are source-visible. |
| Premium filter | `WORKBOOK_VERIFIED` | `AB6 OS!H100:H110`: ideal premium `2.00%`, minimum premium `1.50%`; cached values in `AB16!AK77:AL78`, `AB16!AK84:AL85`. |
| OI filter | `WORKBOOK_VERIFIED` | `AB6 OS!I100:I110`: `500 Lots`; `AB16!AK79:AL79`, `AB16!AK86:AL86` cache `7500`, matching `500 * lot size 15`. |
| Base Entry | `WORKBOOK_VERIFIED` | `AB6 OS!M100:M110`: option previous reference minus `7.50%`; cached outputs in `AB16!J77:K77`, `AB16!J84:K84`. |
| Gap-up handling | `USER_CLARIFIED` | `AB6 OS!D112:E118` labels `Gap Check`, but S21 V1 has no separate GAP_UP branch behavior. Generic OpeningMarketContext may record gap evidence; S21 consumes workbook ORPT/RC only. |
| Gap-down handling | `USER_CLARIFIED` | Same source and clarification as gap-up. No separate S21 GAP_DOWN/no-gap business action is authorized for V1. |
| ORPT | `WORKBOOK_VERIFIED` | `AB6 OS!B113:C118`, `AB6 OS!L113:L118`, `AB16!W75:Z75`, `AB16!W82:Z82`: ORPT around `09:24:59`. |
| RC | `WORKBOOK_VERIFIED` | `AB6 OS!C114:C118`, `AB6 OS!L114:L118`, `AB16!AD78:AF78`, `AB16!AD85:AF85`: RC around `09:29:59`. |
| Missed Entry | `WORKBOOK_VERIFIED` | `AB6 OS!E113:E118`: strict `09:24:59 AM LL < Call/Put Sell Entry`. |
| Effective Entry | `WORKBOOK_VERIFIED` | `AB6 OS!I114:X118`: recalculated Call/Put entry formulas by Bull/Bear branch. |
| Target | `WORKBOOK_VERIFIED` | `AB6 OS!O100:O110`: `CE/PE Entry - 60.00%`; `AB18!A37:U37`, `AB18!A40:U40` output target rows. |
| Original SL/MSL | `WORKBOOK_VERIFIED` | `AB6 OS!M101:M110`: `Min(Entry + 60%, referenced OPT + 7%/10%)`; `AB16!M77:N77`, `AB16!M84:N84` cached outputs. |
| FSL/TRP | `WORKBOOK_VERIFIED` | `AB6 OS!A121:Z126`: carried/open-position FSL/TRP rows for Call and Put; strict missed condition uses current-day high greater than SL. |
| APS / Partial exits | `USER_CLARIFIED` | `AB2!K26`, `AB6 OS!C107`, `AB15!S11`, `AB16!E79` show `APS`; 2026-08-02 APS clarification closes S21-Q003 as `APS_NOT_APPLICABLE` because S21 is one-lot Option Selling. No APS, no partial target allocation, no quantity splitting, no partial PositionCycle, no APS-specific protection adjustment. |
| EOD exit | `USER_CLARIFIED` | Workbook strict `>` exit in `AB6 OS!F96:J96`, `AB6 OS!Q96:U96`; global Option Selling user rule closes equality. |
| Carry-forward | `USER_CLARIFIED` | Workbook strict `<` carry in `AB6 OS!F97:J97`, `AB6 OS!Q97:U97`; global user clarification makes `<=` carry forward. |
| Equality | `USER_CLARIFIED` | `OPTION_SELLING-EOD-CARRY-ORIGINAL-SL-GLOBAL-USER-2026-08-01`: equality carries forward for Option Selling unless future source overrides. |
| Next-day carried lifecycle | `USER_CLARIFIED` | User carried-position protection clarification supplies platform lifecycle semantics; S21 workbook supplies FSL/TRP formulas in `AB6 OS!A121:Z126` and EOD carry text in `AB6 OS!J97/U97`. |
| Position protection | `USER_CLARIFIED` | User carried-position protection clarification supplies target-first and no-blind-prior-SL requirements; `AB18!A37:U38`, `AB18!A40:U41` provide S21 target/SL output rows. Broker mechanics remain platform behavior, not strategy source. |
| Accounting/P&L unit | `USER_CLARIFIED` | `AB11!H11/K11`, `AB16!K75/K82`, `AB16!I77/I84`, `AB18!O38/O41`, plus 2026-08-02 clarification: configured quantity is one lot; BANKNIFTY lot size is 15; exchange quantity is 15; P&L uses confirmed exchange quantity; `AB15!U11=2` is not execution/P&L quantity. |
| Quantity/Lot handling | `USER_CLARIFIED` | One-lot Option Selling clarification closes S21-Q004 for V1. `500 Lots` remains OI threshold, not order quantity. |
| Rollover/expiry | `USER_CLARIFIED` | `AB2!X26:AA26`, `AB11!M11:P11`, `AB1!D28:K28`, `AB6 OS!J97/U97`, and 2026-08-02 source-closure directive: no automatic rollover for open S21 positions in V1; unsupported expiry continuation fails closed for operator/user decision. |

## Closed Questions

- `S21-Q001`: Near-first/Next fallback per Call/Put leg.
- `S21-Q002`: no separate S21 GAP_UP/GAP_DOWN branch logic for V1.
- `S21-Q003`: `APS_NOT_APPLICABLE` for one-lot S21 Option Selling.
- `S21-Q004`: one lot, lot size 15, exchange quantity 15, P&L by confirmed
  exchange quantity.
- `S21-Q005`: no automatic open-position rollover in S21 V1.

## Bottom Line

S21 source closure is accepted. No financially material source questions remain
open for S21 implementation planning. This acceptance does not implement S21,
does not add APS logic, and does not grant broker, paper, live, order, or
position mutation authority.
