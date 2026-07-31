# Phase 3D Milestone 13A/M13B Source Closure

Verdict: `M13B_SOURCE_CLOSURE_ACCEPT`

Source authority used:

- `TFISRulesAndSpec/All in One - TFIS 26-12-2023.xlsx`
- `TFISRulesAndSpec/AB7 OS.xlsx`
- Cell trace: `reports/phase3d/milestone13b_cell_trace.json`

## Closed Questions

Question ID: `M13A-Q001`
Status: `CLOSED_BY_WORKBOOK_CELL_TRACE`

Workbook cells `AB6 OS!F190:J190` and `AB6 OS!Q190:U190` say that when the 15:00 close is greater than the original SL, the position must be squared off at CMP at 15:00.

Workbook cells `AB6 OS!F191:J191` and `AB6 OS!Q191:U191` say that when the 15:00 close is less than the original SL, the position continues for the next day and stop loss is calculated as per the rules.

The next-day carried-position rules are `AB6 OS!E183:H183` for not-missed original SL and `AB6 OS!M184:O185` for Call revised FSL after a missed original SL. Put-side formulas are recorded in `AB6 OS!M187:O188` but remain outside the current Call vertical slice.

The equality case, `close == original SL`, is not specified by the workbook operators and is closed by user clarification as carry-forward.

Question ID: `M13A-Q002`
Status: `CLOSED_BY_WORKBOOK_FORMULA_DOMAIN`

The S23 option-selling formulas reviewed in `AB16!K104`, `AB16!P104:P105`, `AB16!AI107`, `AB16!K111`, `AB16!P111:P112`, and `AB16!AI114` keep target, SL, and MSL values positive when required option premium inputs are valid and positive.

The explicit negative-result guard found in AB16 belongs to S27 option-buying formula branches, not S23 option selling. No S23 option-selling rule authorizes placement of a zero or negative risk order.

M13B behavior: valid positive inputs may produce workbook-backed S23 option-selling risk outputs; invalid zero/negative market inputs fail closed as `RULE_AUTHORITY_UNRESOLVED_FOR_INVALID_MARKET_INPUT`.

Question ID: `M13A-Q003`
Status: `CLOSED_BY_USER_CLARIFICATION`

Latest authoritative user clarification says that if the carried-contract opening market has crossed the applicable target, the authoritative business outcome is to book profit and exit the position.

M13B behavior: if target and protection are both observed as crossed in the same offline packet, target profit-booking priority wins and the lifecycle output is `EXIT_REQUIRED`.

## Remaining Boundaries

- Do not genericize Put-side carried-position formulas into the current S23 Call vertical slice.
- Do not use S27 option-buying non-positive guards as S23 option-selling rules.
- Do not place broker or paper orders from lifecycle coordination; the lifecycle output remains an offline authoritative requirement only.
