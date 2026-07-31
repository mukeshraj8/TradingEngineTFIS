# Phase 3E Milestone 2 Domain Ownership Summary

Date: Friday, July 31, 2026

Verdict: `MILESTONE_ACCEPT`

Milestone 2 defines the minimum production-grade ownership model for TFIS V1.
It is architecture/specification work only. No production runtime code,
broker adapter behavior, paper authority, live authority, order mutation, or
position mutation was added.

## Objective

The objective was to define how TFIS will safely own and trace multiple
strategy instances, instruments, accounts, working orders, partial fills, open
positions, position cycles, fresh-entry lifecycle, and carried-position
lifecycle before implementing persistence/recovery or paper authority.

## Current Ownership Audit

The current branch already has strong identity and offline-decision foundations:

- strategy family/definition/version/instance/evaluation/position-cycle
  identities exist
- S23 Call-side fresh-entry and carried-position offline paths are accepted
- deterministic M15 runtime coordination exists in-memory and non-authoritative
- older paper order/position and reconciliation modules are useful references

The audit also found that production V1 needs stronger ownership boundaries:

- account identity must become first-class
- order state must be owned by one `OrderStateMachine` per client order
- position lifecycle must be owned by `PositionCycleCoordinator`
- cross-account controls must sit in a portfolio supervisor, not strategy logic
- strategy code and symbol are insufficient keys for any order/fill/position

## Files Produced

- `docs/architecture/tfis_minimum_production_architecture_v1.md`
- `reports/phase3e/domain_ownership_catalog.json`
- `reports/phase3e/order_position_invariants.json`
- `reports/phase3e/milestone2_domain_ownership_summary.md`

## Core Design

TFIS V1 should use separate, narrow owners:

- `AccountCoordinator` owns account-session acceptance, idempotency, routing,
  reconciliation gating, and account isolation.
- `OrderStateMachine` owns exactly one `ClientOrderIdentity`.
- `PositionCycleCoordinator` owns exactly one position cycle and its quantity,
  protection, lifecycle, and carry-forward projections.
- `PortfolioRiskAndControlSupervisor` owns cross-account, cross-strategy,
  kill-switch, authority-mode, and portfolio exposure decisions.
- `ExecutionIntent` is the immutable broker-neutral bridge from business
  requirement to account validation.
- `LifecycleRequirement` is the immutable bridge from open/carry lifecycle
  observation to exit/protection intent.

## Identity Chain

Minimum traceability:

```text
BrokerAccountIdentity
-> AccountSession
-> TradingSession
-> StrategyInstance
-> StrategyDefinitionVersion
-> StrategyEvaluationIdentity
-> PositionCycleIdentity
-> EffectiveExecutionPlan
-> LifecycleRequirement or fresh-entry requirement
-> ExecutionIntent
-> ClientOrderIdentity
-> BrokerOrderIdentity
-> OrderEvent
-> Fill
-> PositionCycle
-> TradeFact
-> PnLFact
```

## Quantity Decision

V1 should use aggregate confirmed/remaining quantity plus ordered fill facts
and protection generations. Explicit per-lot `PositionQuantitySlice` ownership
is deferred until a source-verified first-10 strategy requires independent
lot-level lifecycle policy.

This keeps the first paper-authorized architecture focused on preventing
over-exit, under-protection, duplicate mutation, and cross-account leakage.

## Key Invariants

The detailed invariant catalog is in
`reports/phase3e/order_position_invariants.json`.

Minimum must-hold rules:

- no exit or protection quantity may exceed confirmed remaining quantity
- no protection may be placed for unfilled quantity
- one owner writes one order
- one owner writes one position cycle
- broker/paper truth must be reconciled before local action
- stale replacement events cannot overwrite newer protection generations
- analytics cannot mutate trading authority
- failures isolate to the smallest safe owner unless explicitly escalated

## Open User Decisions

These are not blockers for accepting Milestone 2, but should be closed before
paper authority:

1. Should V1 permit multiple active fresh-entry cycles for the same strategy
   instance/product/underlying, or default to one active cycle unless config
   explicitly allows more?
2. Is aggregate quantity plus ordered fill facts acceptable for first paper
   authority, with explicit per-lot slices deferred?
3. When broker OCO semantics are available, should TFIS prefer broker-hosted
   OCO or application-managed target/SL quantity caps?
4. Should re-entry always create a new position cycle unless workbook evidence
   explicitly says to extend the existing cycle?

## Runtime Impact

`NONE`.

## Broker, Paper, And Live Authority

Broker authority: `NONE`.

Paper authority: `NONE`.

Live authority: `NONE`.

Order mutation authority: `NONE`.

Position mutation authority: `NONE`.

## M3 Readiness

Milestone 3 is ready to begin after user approval. The next milestone should
cover persistence/recovery, risk/control refinement, market-data performance,
and failure-isolation implementation planning. It should not skip directly to
paper or live authority.
