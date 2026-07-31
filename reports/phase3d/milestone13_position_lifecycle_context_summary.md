# Phase 3D Milestone 13 - Position Lifecycle Context

Verdict: `PHASE3D_M13_ACCEPT`

Milestone 13 adds an immutable offline `PositionLifecycleContext` boundary for
carried-position opening observation. It does not implement lifecycle execution,
broker reconciliation, order modification, square-off, scheduler behavior,
paper authority, live authority, PUT branches, S21, or Futures.

## Implemented

- `ReconciledPositionSnapshot` records an already-carried position after local
  and external quantity reconciliation.
- `LifecycleOpeningEvidence` records the carried contract opening quote
  independently from fresh-entry selection, while allowing the underlying
  opening snapshot to be shared.
- `PositionLifecycleContextBuilder` validates contract, date, strategy
  instance, configuration hash, position cycle, reconciliation, quote
  availability, quote freshness, and protective state.
- Gap direction, amount, percentage, and economic effect are observed from
  carried-contract opening LTP versus the prior reference price without
  invoking Phase 3C Gap/Missed Entry.
- Gap economic effect is evaluated from the open position exposure, including
  side, option type, and carried-contract premium movement. It is not inferred
  from the underlying `GAP_UP` / `GAP_DOWN` label alone.
- Target protection is recorded as available from market open. If the carried
  contract opening price has crossed the applicable target, the offline
  authoritative business requirement is `EXIT_REQUIRED`.
- Prior-day SL is not blindly reused at market open. The workbook-style ORPT
  original-SL comparison drives the SL path: if not missed, the offline
  requirement is `NORMAL_SL_PLACEMENT_REQUIRED`; if missed, RC evidence plus
  revised-SL policy input is required before the offline requirement becomes
  `REVISED_SL_PLACEMENT_REQUIRED`.
- Economic gap effect is diagnostic only and cannot by itself create an
  actionable revised-SL requirement.
- Fresh-entry Gap/Missed-Entry and carried-position SL recalculation remain
  separate processes.
- `OfflineLifecycleHandoff` is immutable and carries no mutation authority:
  broker, paper, live, order modification, order cancellation, square-off, and
  position mutation flags are all false.

## S23 Fixture Results

| Case | Status | Action |
| --- | --- | --- |
| Bull carried normal | `NORMAL_OPENING_CONTINUATION` | `NORMAL_SL_PLACEMENT_REQUIRED` |
| Bull carried adverse gap | `PROTECTIVE_LEVEL_CROSSED_AT_OPEN` | `REVISED_SL_PLACEMENT_REQUIRED` |
| Bull favorable gap | `NORMAL_OPENING_CONTINUATION` | `NORMAL_SL_PLACEMENT_REQUIRED` |
| Bull target crossed at open | `TARGET_CROSSED_AT_OPEN` | `EXIT_REQUIRED` |
| Bull protective level crossed at open | `PROTECTIVE_LEVEL_CROSSED_AT_OPEN` | `REVISED_SL_PLACEMENT_REQUIRED` |
| Bear carried normal | `NORMAL_OPENING_CONTINUATION` | `NORMAL_SL_PLACEMENT_REQUIRED` |
| Bear adverse gap | `PROTECTIVE_LEVEL_CROSSED_AT_OPEN` | `REVISED_SL_PLACEMENT_REQUIRED` |
| Missing carried-contract quote | `OPENING_QUOTE_UNAVAILABLE` | `BLOCKED_INSUFFICIENT_EVIDENCE` |
| Reconciliation mismatch | `BLOCKED_LIFECYCLE_CONTEXT` | `BLOCKED_INSUFFICIENT_EVIDENCE` |

## Future Requirements Recorded, Not Genericized

- near-expiry to next-expiry fallback
- directional strike traversal
- ideal-premium and minimum-premium phases
- configurable OI thresholds
- MIN/MAX bounded Target or MSL formulas
- non-positive calculated risk prices: S23 option-selling is positive by
  construction for valid positive premium inputs; invalid zero/negative market
  inputs remain fail-closed
- additional historical reference lookbacks
- exact carried-position revised SL formulas are now recorded from AB6 OS rows
  184, 185, 187, and 188 as strategy-policy inputs

## Certification Notes

- Architecture boundary: generic lifecycle builder has no S21/S23 branches, no
  broker imports, no paper runtime imports, no order placement, no square-off,
  no scheduler, no event bus, no persistence writes, and no string expression
  evaluation.
- Behavior: covered normal, adverse/favorable economic gap,
  target/protection crossed, missing quote, stale quote, missing revised SL
  formula, and reconciliation mismatch cases.
- Evidence: JSON artifacts created for required S23 cases and lifecycle gap
  matrix.
- Parity: M12 carried-position boundary hash is preserved.
- Runtime readiness: offline construction only.
- Captured readiness: no complete captured carried-position packet yet.
- Live readiness: not implemented and no authority granted.
