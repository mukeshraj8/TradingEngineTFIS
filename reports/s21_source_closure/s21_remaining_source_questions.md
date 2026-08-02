# S21 Remaining Source Questions

Status: `S21_SOURCE_CLOSURE_ACCEPT`

Decision pack: `reports/s21_source_closure/s21_user_decision_pack.md`

Decision pack verdict: `S21_USER_DECISION_PACK_CLOSED`

Primary workbook:

- `TFISRulesAndSpec/All_in_One_TFIS_26-12-2023_Unprotected_Copy.xlsx`
- SHA-256:
  `603ea7bc09ebb0c7df2ad0202d492c9ca49e890cfefdb3f0eddb1edcbe8fbddd`

## No Open Financially Material Questions

All S21 source questions are now closed for implementation planning. This file
is retained as the closure register and source-trace pointer.

## Closed Questions

### S21-Q001 Contract Selection / Expiry Fallback

Classification: `USER_CLARIFIED`

Result: search Near monthly expiry first independently for each Call/Put leg.
If no qualifying contract is found due to strike, OI, ideal premium, or minimum
premium failure, search Next monthly expiry. If Next also fails, do not trade
that leg. Call and Put do not need the same expiry. Tie-break traversal is from
Start Strike to End Strike, choosing the first qualifying strike.

Source inspected: `AB2!V26:AA26`, `AB1!D28:K28`, `AB6 OS!G100:I110`,
`AB11!E11:P11`, `AB15!J11:P11`.

### S21-Q002 Gap Classification Versus ORPT Missed Entry

Classification: `USER_CLARIFIED`

Result: S21 has no separate GAP_UP/GAP_DOWN/no-gap branch logic for V1. Generic
OpeningMarketContext may record opening gap evidence, but S21 trade behavior
uses only workbook ORPT missed-entry checks and RC recalculation rules.

Source inspected: `AB6 OS!D112:E118`, `AB6 OS!I114:X118`.

### S21-Q003 APS / Partial Exits

Classification: `USER_CLARIFIED`

Result: `APS_NOT_APPLICABLE`.

Authoritative clarification: APS is not applicable to Option Selling strategies
such as S21, S22, S23, and other Option Selling strategies using the same
one-lot trading model. One lot implies one complete position with one Target
and one protection sequence.

Therefore S21 has no APS, no partial Target allocation, no quantity splitting,
no partial PositionCycle, and no APS-specific protection adjustment.

Source inspected: `AB2!K26`, `AB6 OS!C107`, `AB15!S11`, `AB16!E79`.

### S21-Q004 Quantity And P&L Unit

Classification: `USER_CLARIFIED`

Result: S21 configured trading quantity is one lot. BANKNIFTY lot size is 15
per workbook source, so exchange quantity is 15. P&L must multiply by confirmed
exchange quantity, not by lot size again. `500 Lots` is the minimum OI
threshold, not order quantity. `AB15!U11=2` is not execution/P&L quantity for
S21 V1.

Source inspected: `AB11!H11/K11`, `AB16!K75/K82`, `AB16!I77/I84`,
`AB18!O38/O41`, `AB15!U11`.

### S21-Q005 Rollover / Expiry Action

Classification: `USER_CLARIFIED`

Result: S21 has no automatic rollover for open positions in V1. Fresh entries
follow approved contract-selection rules. Open positions follow verified
EOD/carry and carried-position lifecycle rules. If a position would continue
into an unsupported expiry state, fail closed and require operator/user
decision; do not close old and open new automatically.

Source inspected: `AB2!X26:AA26`, `AB11!M11:P11`, `AB1!D28:K28`,
`AB6 OS!J97/U97`, `AB6 OS!A121:Z126`.

## Runtime Boundary

This closure does not implement S21, APS, broker submission, paper submission,
live routing, order mutation, or position mutation.
