# Phase 3D Milestone 13B Source Closure Summary

Verdict: `M13B_SOURCE_CLOSURE_ACCEPT`

M13B reviewed the authoritative workbook files supplied in
`TFISRulesAndSpec` and closed the three M13A questions before any M14 work.

## Source Authority

- Workbook: `TFISRulesAndSpec/All in One - TFIS 26-12-2023.xlsx`
- SHA256: `1D2DB2C2834C2081AE21E460471CD1546D988DCF8125B312AD453BA8027BD301`
- Supporting individual workbook: `TFISRulesAndSpec/AB7 OS.xlsx`
- Cell trace: `reports/phase3d/milestone13b_cell_trace.json`

## Decisions

`M13A-Q001`: closed.

Rows `AB6 OS!190:191` define the 15:00 EOD decision. Close above original SL
requires square-off at CMP. Close below original SL carries the position and
uses the next-day carried-position rules. The workbook does not define equality
with `>=` or `<=`; user clarification closes equality as carry-forward.

Effective M13B equality behavior:

- Call: `15:00 close > Call Original SL` squares off; `15:00 close <= Call
  Original SL` carries forward.
- Put: `15:00 close > Put Original SL` squares off; `15:00 close <= Put
  Original SL` carries forward.

`M13A-Q002`: closed.

S23 option-selling target, SL, MSL, and revised-FSL formulas are positive by
construction for valid positive premium inputs. The workbook's explicit
negative-result guard is in S27 option-buying branches, not S23 option selling.
Zero/negative S23 market inputs remain fail-closed.

`M13A-Q003`: closed.

Target crossed at opening requires profit booking and exit. If target and
protection cross together in the same observation packet, target-first priority
wins and the offline lifecycle output is `EXIT_REQUIRED`.

## Implementation Scope

Added S23 adapter evidence helpers only:

- `evaluate_s23_eod_carry_decision`
- `calculate_s23_carried_revised_fsl`

These helpers do not call brokers, mutate positions, place paper orders, parse
arbitrary strings, or genericize Contract Selection, Risk, or Market Structure.

## Remaining Boundaries

- Do not activate Put-side lifecycle formulas in the current S23 Call vertical
  slice.
- Do not reuse S27 option-buying negative-price behavior for S23 option selling.
- Do not start M14 until this M13B closure is accepted.
