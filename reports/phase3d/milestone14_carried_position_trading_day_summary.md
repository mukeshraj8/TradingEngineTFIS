# Phase 3D Milestone 14 - Offline Carried-Position Trading-Day Coordination

Verdict: `PHASE3D_M14_ACCEPT`

Milestone 14 implements the complete offline carried-position trading-day
coordination slice. It composes the M13 `PositionLifecycleContext` with the
M13B verified 15:00 EOD rule and produces an immutable offline lifecycle
handoff.

## Implemented Sequence

1. Position reconciliation.
2. Target protection from market open.
3. Target-first opening assessment.
4. ORPT original-SL evaluation.
5. Normal SL requirement or RC revised FSL/TRP requirement.
6. Intraday lifecycle state.
7. 15:00 square-off/carry decision.
8. Offline lifecycle handoff.

## Verified S23 Fixtures

| Fixture | Intraday State | 15:00 Outcome | Terminal |
| --- | --- | --- | --- |
| `bull_carried_normal_day_carry` | `NORMAL_SL_REQUIRED` | `CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL` | `COMPLETED_OFFLINE` |
| `bull_carried_normal_day_equal_carry` | `NORMAL_SL_REQUIRED` | `CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL` | `COMPLETED_OFFLINE` |
| `bull_carried_normal_day_square_off` | `NORMAL_SL_REQUIRED` | `SQUARE_OFF_AT_CMP_REQUIRED` | `COMPLETED_OFFLINE` |
| `bull_carried_adverse_day_revised_fsl_carry` | `REVISED_FSL_REQUIRED` | `CARRY_FORWARD_AND_CALCULATE_NEXT_DAY_SL` | `COMPLETED_OFFLINE` |
| `bull_carried_target_exit_day` | `EXIT_REQUIRED_FROM_OPEN` | not applicable | `COMPLETED_OFFLINE` |

## Boundary

This milestone does not add broker, paper, live, scheduler, order modification,
order cancellation, square-off, or position mutation authority. All mutation
flags remain false and all authority properties report `NONE`.

## Source Rules

- Target-first opening exit: user clarification.
- ORPT/RC carried-position rules: `AB6 OS!183:188`.
- 15:00 Call EOD rules: `AB6 OS!F190:J191`.
- 15:00 Put EOD rules: `AB6 OS!Q190:U191`.
- Equality at 15:00 close equal to Original SL: user clarified carry-forward.

## Reports

- `reports/phase3d/milestone14_s23_bull_carried_normal_day_carry.json`
- `reports/phase3d/milestone14_s23_bull_carried_normal_day_equal_carry.json`
- `reports/phase3d/milestone14_s23_bull_carried_normal_day_square_off.json`
- `reports/phase3d/milestone14_s23_bull_carried_adverse_day_revised_fsl_carry.json`
- `reports/phase3d/milestone14_s23_bull_carried_target_exit_day.json`
- `reports/phase3d/milestone14_carried_position_gap_matrix.json`
