# S21 Source Closure Summary

Status: `S21_SOURCE_CLOSURE_ACCEPT`

Scope: S21 BankNifty monthly option selling source closure only. No S21
implementation code, runtime configuration, strategy policy, broker path,
paper path, or live path was changed.

Primary workbook:

- `TFISRulesAndSpec/All_in_One_TFIS_26-12-2023_Unprotected_Copy.xlsx`
- SHA-256:
  `603ea7bc09ebb0c7df2ad0202d492c9ca49e890cfefdb3f0eddb1edcbe8fbddd`

Additional authoritative source inspected:

- `TFISRulesAndSpec/TFIS_Monthly_Status_Reference_and_Implementation_Specification_v1.0.docx`

Authoritative user clarifications:

- `OPTION_SELLING-EOD-CARRY-ORIGINAL-SL-GLOBAL-USER-2026-08-01`: at EOD,
  close greater than Original SL exits; close less than or equal to Original SL
  carries forward for Option Selling unless a future workbook explicitly proves
  otherwise.
- `OPTION_SELLING-APS-APPLICABILITY-GLOBAL-USER-2026-08-02`: APS is not
  applicable to one-lot Option Selling strategies such as S21, S22 and S23.

## Closed

- Strategy identity: `WORKBOOK_VERIFIED`.
- Monthly Status: `WORKBOOK_VERIFIED` through the shared Monthly Status v1.0
  specification and S21 `AB11!D11` consumption.
- Branch resolution: `WORKBOOK_VERIFIED`.
- Static formula spine: `WORKBOOK_VERIFIED` for strike range, premium, OI,
  base entry, target, original SL/MSL and FSL/TRP.
- ORPT/RC/missed-entry: `WORKBOOK_VERIFIED`.
- EOD exit/carry/equality: `USER_CLARIFIED` through the global Option Selling
  EOD rule.
- Carried-position lifecycle/protection requirements: `USER_CLARIFIED` for
  platform semantics plus S21 workbook FSL/TRP policy cells.
- Contract/expiry fallback: `USER_CLARIFIED`; Near monthly expiry is searched
  first independently by Call/Put leg, then Next if qualification fails.
- Gap classification: `USER_CLARIFIED`; S21 V1 has no separate GAP_UP/GAP_DOWN
  branch action beyond workbook ORPT missed-entry and RC recalculation.
- APS/partial exits: `USER_CLARIFIED`; `APS_NOT_APPLICABLE` for S21 because it
  is one-lot Option Selling.
- Quantity and P&L unit: `USER_CLARIFIED`; S21 configured quantity is one lot,
  BANKNIFTY lot size is 15, exchange quantity is 15, and P&L uses confirmed
  exchange quantity.
- Rollover/expiry action: `USER_CLARIFIED`; no automatic open-position
  rollover in S21 V1.

## Closed Question Register

1. `S21-Q001`: Near/Next monthly contract-selection and expiry fallback.
2. `S21-Q002`: GAP_UP/GAP_DOWN classification versus ORPT missed-entry.
3. `S21-Q003`: APS/partial-exit action, quantity and protection interaction.
4. `S21-Q004`: Quantity/P&L unit normalization.
5. `S21-Q005`: Carried-position rollover/expiry action.

## User Decision Pack

`reports/s21_source_closure/s21_user_decision_pack.md` and
`reports/s21_source_closure/s21_user_decision_pack.json` remain the source
question audit trail. They are superseded by this closure summary where they
describe questions as awaiting user approval.

Decision pack verdict: `S21_USER_DECISION_PACK_CLOSED`.

Monthly Status independence is explicitly confirmed: Monthly Status remains a
generic, strategy-independent engine; S21 only consumes BANKNIFTY Monthly
Status and maps that typed result to branch policy.

## Legacy Audit

Legacy S21 implementation and tests were not inspected as rule authority. The
S21 source matrix is now complete enough to compare legacy behavior later as
non-authoritative discrepancy evidence if implementation planning requires it.

## Verdict

`S21_SOURCE_CLOSURE_ACCEPT`

No financially material S21 source questions remain open. This closure does
not implement S21 and does not add broker, paper, live, order, or position
mutation authority.
