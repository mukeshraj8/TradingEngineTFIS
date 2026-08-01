# Critical Path To First Paper Trade

Date: Saturday, August 1, 2026

Verdict: `DEFINED`

The first paper-traded vertical slice should be one S23 NIFTY option-selling
Call-side strategy instance. Bull Call and Bear Call are certification cases
inside the same S23 Call-side family path; they should not create duplicate
order, lifecycle, persistence, or accounting implementations.

## Target Slice

```text
Strategy Resolution
-> captured/replay or live market stream
-> PreMarketStrategyPlan
-> OpeningMarketContext
-> normal/gap EffectiveExecutionPlan
-> carried-position LifecycleRequirement when applicable
-> ExecutionIntent
-> RiskDecision
-> AccountCoordinator
-> paper OrderStateMachine
-> Fill
-> PositionCycle
-> Target / Original SL / Revised SL / EOD handling
-> Reconciliation
-> TradeFact
-> PnLFact
-> operator evidence
```

## Phases

| Phase | Objective | Minimum components | Tests | Authority gained | Disabled |
| --- | --- | --- | --- | --- | --- |
| P4A | Connect M15 to one existing captured/replay stream in shadow-only mode. | replay adapter, event watermark, deterministic coordinator hook | captured/replay shadow parity | none | broker/paper/live mutation |
| P4B | Implement broker-neutral read-only account/order/position boundary. | account snapshot DTOs, adapter protocol, reconciliation input | read-only adapter contract tests | read-only broker integration readiness | order placement |
| P4C | Implement transactional persistence foundation. | event/fact tables, idempotency keys, current projections | restart/recovery equivalence tests | durable state readiness | authority-bearing orders |
| P4D | Implement reconciliation engine for read-only truth. | order/position/fill classifiers, mismatch blocks | reconciliation matrix tests | live-data shadow readiness | automatic repair |
| P4E | Implement ExecutionIntent and minimum risk validation. | intent builder, validator, risk/control decisions | intent idempotency and fail-closed tests | risk-gated intent readiness | account submission |
| P4F | Implement AccountCoordinator and paper execution adapter. | account session, paper adapter, order registry | account isolation and simulator tests | internal paper preparation | broker write |
| P4G | Implement OrderStateMachine. | ENTRY, TARGET, ORIGINAL_SL, REVISED_SL, EOD_EXIT purposes | state transition and partial-fill tests | paper order lifecycle readiness | live routing |
| P4H | Integrate PositionCycle lifecycle. | fill-to-position projection, protection generations, carried restart | position invariant and carried lifecycle tests | lifecycle paper readiness | automatic strategy expansion |
| P4I | Project TradeFact and PnLFact. | weighted-average cost, provisional charges, conservative marks | accounting projection tests | measurable paper readiness | analytics-driven trading changes |
| P5A | Enable one approved S23 Call-side instance in paper. | paper approval record, dashboard, rollback controls | paper readiness checklist | one-route internal paper authority | broker write and live money |

## Rollback

Every authority-bearing phase must support strategy disable, account halt,
global halt, rollback to shadow, rollback to a prior configuration version,
evidence preservation, and explicit operator approval. Disabling fresh entries
must not abandon open positions or their protection requirements.

## First Implementation Task

`P4A` is the next narrow implementation task: connect the M15 runtime coordinator
to one existing captured/replay stream in non-authoritative shadow-only mode and
prove deterministic fresh-entry plus carried-position event flow.
