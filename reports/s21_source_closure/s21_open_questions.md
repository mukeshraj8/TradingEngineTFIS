# S21 Open Questions

Status: `CLOSED_BY_USER_CLARIFICATION`

## Q001 - 15:00 Equality Against Original SL

Workbook cells inspected:

- `All in One - TFIS 26-12-2023.xlsx!AB6 OS!F96:J97`
- `All in One - TFIS 26-12-2023.xlsx!AB6 OS!Q96:U97`

Original Call text:

- `F96`: `Check If Close at 03:00:00 PM  > Call Original SL`
- `J96`: `Then Square Off The Position At CMP at 03:00:00 PM`
- `F97`: `Check If Close at 03:00:00 PM  < Call Original SL`
- `J97`: `Then Continue the Position for Next Day And Calculate Stop Loss Price as per the Rules`

Original Put text:

- `Q96`: `Check If Close at 03:00:00 PM  > Put Original SL`
- `U96`: `Then Square Off The Position At CMP at 03:00:00 PM`
- `Q97`: `Check If Close at 03:00:00 PM  < Put Original SL`
- `U97`: `Then Continue the Position for Next Day And Calculate Stop Loss Price as per the Rules`

Why insufficient before clarification:

The source defines strict `>` and strict `<` only. It does not define the
business outcome when observed 15:00 close is exactly equal to Original SL.
S23 equality behavior cannot be reused as S21 authority.

Alternative interpretations:

- Equality squares off at CMP at 15:00.
- Equality carries forward and calculates next-day stop loss as per rules.

Financial consequence:

Choosing incorrectly changes whether the system exits the S21 carried position
or holds overnight at the exact risk boundary.

User clarification:

On 2026-08-01, the user clarified a global Option Selling EOD carry rule:

- `Close > Original SL` -> square off / exit.
- `Close == Original SL` -> carry forward.
- `Close < Original SL` -> carry forward.

This applies to S21, S22, S23, and all other Option Selling strategies unless a
future workbook explicitly proves otherwise. It does not apply to Futures,
Option Buying, or Equity without their own verified EOD rules.

Closure:

`OPTION_SELLING-EOD-CARRY-ORIGINAL-SL-GLOBAL-USER-2026-08-01`
