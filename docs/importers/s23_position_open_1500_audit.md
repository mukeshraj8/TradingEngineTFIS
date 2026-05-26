# S23 Position-Open 15:00 Audit

## Purpose

This audit checks whether the S23 workbook exposes any safe, numeric
continuation logic outside `AB6 OS` rows `162-191`, especially around the
current TFIS blocker at rows `190-191`.

This is an evidence document only.

- no trading behavior is changed here
- no workbook mapping is broadened here
- blank cells are not inferred
- current-day FSL / TRP logic remains unchanged

## Inspected Sheets and Ranges

Primary inspected ranges:

- `AB6 OS!182:191`
- `AB5!79:88`
- `AB5!113:121`

Repeated template-note ranges checked for the same continuation wording:

- `AB5!35:37`
- `AB5!86:88`
- `AB5!155:157`
- `AB5!201:203`
- `AB5!237:239`

Additional workbook-wide text search terms:

- `3:00 PM`
- `15:00`
- `position is open`
- `position open`
- `Call Original SL`
- `Short Original SL`
- `Put Original SL`
- `FSL / TRP`
- `same day`
- `missed`
- `continuation`
- `carry`
- `exit`
- `SL missed`
- `TRP missed`

## Key Conclusions

1. `AB6 OS!190:191` are process / decision notes, not a numeric formula block.
2. The only live formula link in this mini-block is the `15:00:00` time anchor:
   `AB6 OS!B191 = INDEX('AB4'!CU:CU, MATCH(A179, 'AB4'!B:B, 0))`.
3. The visible decision text in `AB6 OS!190:191` is assembled from shared
   `AB5` template cells. No strike, premium, entry, target, or continuation
   stoploss numbers are defined in these rows.
4. The phrase `Then Continue the Position for Next Day And Calculate Stop Loss
   Price as per the Rules` appears only as repeated template text in `AB5`.
   This audit did not find any nearby numeric rule that tells TFIS how to
   calculate that next-day stoploss.
5. The 15:00 position-open wording is not S23-only. It is shared workbook
   scaffolding that appears in multiple template blocks, including the option-
   selling template block used by `AB6 OS`.
6. Nothing new is safe to implement from this audit. The continuation path
   remains blocked until the workbook exposes explicit numeric logic.

## Cell-Level Evidence

| Sheet | Cell / Range | Exact Formula or Visible Text | Category | Interpretation |
| --- | --- | --- | --- | --- |
| `AB6 OS` | `B191` | Formula: `=IF(C162="", "", INDEX('AB4'!CU:CU, MATCH(A179, 'AB4'!B:B, 0)))` -> visible value `15:00:00` | Numeric time anchor | This supplies the evaluation time for the 15:00 position-open note. It does not define continuation stoploss math. |
| `AB6 OS` | `B189` | Visible value: `For Missed SL (Position = Open)` | Process-only | Heading for the 15:00 position-open decision block. |
| `AB6 OS` | `B190` | Visible value: `Check time` | Process-only | Label only. |
| `AB6 OS` | `F190` | Formula builds: `Check If Close at 03:00:00 PM  > Call Original SL` | Process-only | Decision condition for call-side square-off at 15:00. No numeric formula output. |
| `AB6 OS` | `H190` | Visible value: `Yes` | Process-only | Decision marker only. |
| `AB6 OS` | `J190` | Visible value: `Then Square Off The Position At CMP at 03:00:00 PM` | Process-only | Operational instruction only. |
| `AB6 OS` | `Q190` | Visible value: `Check If Close at 03:00:00 PM  > Put Original SL` | Process-only | Put-side square-off condition. |
| `AB6 OS` | `T190` | Visible value: `Yes` | Process-only | Decision marker only. |
| `AB6 OS` | `U190` | Visible value: `Then Square Off The Position At CMP at 03:00:00 PM` | Process-only | Put-side operational instruction only. |
| `AB6 OS` | `F191` | Formula builds: `Check If Close at 03:00:00 PM  < Call Original SL` | Process-only | Decision condition for call-side next-day continuation. No numeric formula output. |
| `AB6 OS` | `H191` | Visible value: `Yes` | Process-only | Decision marker only. |
| `AB6 OS` | `J191` | Visible value: `Then Continue the Position for Next Day And Calculate Stop Loss Price as per the Rules` | Ambiguous process note | Refers to a later rule set, but this block does not define that rule numerically. |
| `AB6 OS` | `Q191` | Visible value: `Check If Close at 03:00:00 PM  < Put Original SL` | Process-only | Put-side next-day continuation condition. |
| `AB6 OS` | `T191` | Visible value: `Yes` | Process-only | Decision marker only. |
| `AB6 OS` | `U191` | Visible value: `Then Continue the Position for Next Day And Calculate Stop Loss Price as per the Rules` | Ambiguous process note | Same issue as `J191`: instruction text exists, but numeric continuation logic is absent here. |
| `AB5` | `B119:W121` | Template block containing `For Missed SL (Position = Open)`, `> Call Original SL`, `> Put Original SL`, and the `Continue the Position for Next Day...` note | Shared template text | This is the direct source text block used by `AB6 OS!189:191`. |
| `AB5` | `K121` / `W121` | `Then Continue the Position for Next Day And Calculate Stop Loss Price as per the Rules` | Shared template text | The continuation note is text-only here too. No formula for the next-day stoploss is defined in the same block. |
| `AB5` | `K37`, `W37`, `K88`, `W88`, `K157`, `W157`, `K203`, `W203`, `K239`, `W239` | Same continuation wording repeated in other template blocks | Shared template text | Confirms this is workbook scaffolding reused across multiple families, not a unique S23 numeric rule. |
| `AB6 OS` | `182:188` | Current-day FSL / TRP rows with populated `R/S/U/W/Z` and `M` where applicable | Numeric / implemented | These remain the currently supported workbook-backed current-day rows. They do not extend into numeric continuation logic at `190:191`. |

## Answers

### 1. Are rows `190-191` purely process / decision notes, or do they link to numeric formulas elsewhere?

They are process / decision notes in this block.

- `B191` links to a numeric time anchor (`15:00:00`), but not to a continuation
  price formula.
- The rest of `190:191` assembles human-readable decision text from `AB5`
  template cells.
- This audit did not find a linked numeric continuation-stoploss formula tied to
  these rows.

### 2. Is there any workbook-backed rule for what TFIS should do when the position remains open at 15:00?

Yes, but only at the decision-text level:

- if `Close at 03:00:00 PM > Call/Put Original SL`, square off at CMP at
  `03:00:00 PM`
- if `Close at 03:00:00 PM < Call/Put Original SL`, continue the position for
  next day and calculate stoploss as per the rules

The workbook-backed existence of this decision text is clear. The missing part is
the numeric rule for the next-day stoploss.

### 3. Is there any numeric continuation stoploss / FSL / target formula associated with rows `190-191`?

No numeric continuation formula was found in the inspected areas.

- no strike or premium override cells are populated in `190:191`
- no target override cells are populated in `190:191`
- no continuation-stoploss numeric formula appears in `190:191`
- the same continuation phrase appears only as repeated template text elsewhere

### 4. Does this logic apply to S23 only, or is it shared across option-selling strategies?

It is not S23-only.

- `AB6 OS!189:191` is driven by shared `AB5` template text
- the same `position open / continue next day` phrase appears in several other
  `AB5` template blocks
- this suggests shared workbook scaffolding across multiple families, including
  option-selling blocks, rather than a unique S23-only continuation formula

This audit does **not** prove that every repeated template block should be
implemented the same way. It only proves the continuation note itself is shared.

### 5. Is anything safe to implement now, or should it remain blocked?

It should remain blocked.

Safe current recommendation:

- keep `AB6 OS!190:191` documented as process-only
- do not implement next-day continuation-stoploss logic from this block
- do not infer continuation target, stoploss, or entry formulas from the note
- only revisit implementation if another workbook area exposes explicit numeric
  continuation formulas

## Implementation Recommendation

- No behavior change should be made from this audit.
- `AB6 OS!190:191` should remain blocked for implementation.
- The next safe S23 step is not continuation logic from these rows; it is either:
  - locating another workbook area with explicit next-day numeric rules, or
  - staying within already confirmed option-selling realism / reporting tasks.
