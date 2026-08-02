# S21 Platform Reuse Gate

Verdict: `S21_REUSE_GATE_ACCEPT`

Purpose: confirm the implementation surface before S21 onboarding begins. This
gate keeps S21 focused on strategy policy/configuration and protects the
generic platform from S21-specific branching.

Scope: report only. No S21 implementation, runtime configuration, broker path,
paper path, live path, order mutation, or position mutation is introduced here.

| Capability | Reuse? | Change Required? |
| --- | --- | --- |
| Monthly Status | ✅ | No |
| Market Structure | ✅ | No |
| Contract Selection | ✅ | S21 policy only |
| Gap/Missed Entry | ✅ | S21 policy only |
| Entry Engine | ✅ | No |
| Runtime | ✅ | No |
| Persistence | ✅ | No |
| Reconciliation | ✅ | No |
| ExecutionIntent | ✅ | No |
| AccountCoordinator | ✅ | No |
| Order Simulation | ✅ | No |
| PositionCycle | ✅ | No |
| Accounting | ✅ | No |
| TradeFact | ✅ | No |
| PnLFact | ✅ | No |

## Gate Notes

- S21 must consume the generic Monthly Status engine; no Monthly Status logic
  belongs inside an S21 adapter.
- Contract Selection changes are limited to S21 verified policy inputs:
  independent Near-first/Next fallback, strike traversal, premium phases and
  OI threshold.
- Gap/Missed Entry changes are limited to S21 verified policy inputs:
  workbook ORPT missed-entry checks and RC recalculation. No separate S21
  GAP_UP/GAP_DOWN branch logic is authorized.
- APS is not applicable to S21 one-lot Option Selling and must not be
  implemented in generic PositionCycle or lifecycle logic for S21.
- Any generic code change during S21 onboarding must be justified as reusable
  platform capability and regression-tested against existing S23 behavior.

## Implementation Boundary

S21 onboarding may proceed only by composing existing generic capabilities with
source-closed S21 policy/configuration. Do not add broker, external paper, live,
or position/order mutation authority.
