# Phase 3E Milestone 3 Persistence, Recovery, Risk, And Performance Summary

Date: Friday, July 31, 2026

Verdict: `MILESTONE_ACCEPT`

Milestone 3 defines the minimum Version 1 architecture for reliable
persistence, deterministic restart/recovery, broker reconciliation,
risk/control, market-data performance, failure isolation, degraded modes, and
operational observability before paper authority.

This is architecture and implementation planning only. No production
persistence, broker access, order placement, paper authority, live authority,
order mutation, or position mutation was added.

## Audit Result

The refactored and read-only reference repositories contain useful file-backed
paper state, JSONL event/ledger artifacts, atomic write helpers, broker order
state, broker order idempotency, live-state mirrors, dashboard read models, and
read-first reconciliation helpers.

Those pieces are valuable references, but they are not yet the V1 authority
model because V1 needs account/session/position-cycle identity, transactional
boundaries, unified idempotency, broker reconciliation before resumed
authority, projection recovery, and explicit degraded-mode behavior.

## Persistence Model

Recommended V1 shape:

```text
transactional operational database
+ append-only domain events and immutable facts
+ current-state projections
+ read-first broker reconciliation
```

Distributed infrastructure is not required for V1.

## Catalogs

Created:

- `reports/phase3e/persistence_entity_catalog.json`
- `reports/phase3e/risk_control_catalog.json`
- `reports/phase3e/failure_isolation_matrix.json`
- `reports/phase3e/performance_budget_catalog.json`

## Critical Transactions

Defined atomic boundaries for:

- ExecutionIntent acceptance
- broker submission acknowledgement
- fill processing
- protection replacement
- position closure
- EOD carry-forward

Every retry must be idempotent. No retry may produce a second financial action.

## Reconciliation

Broker reconciliation gates resumed authority at startup, restart, periodic
intraday checks, broker reconnect, order timeout, partial fill, cancel/replace,
before new entry, before EOD closure, and next-day carried-position startup.

Automatic projection repair is allowed only for complete, unambiguous,
broker-confirmed cases. Unknown broker orders, duplicate protection,
local-closed/broker-open conflicts, missing broker state, and exposure-hiding
repairs require manual review.

## Risk And Degraded Modes

Risk hierarchy:

```text
global/portfolio
-> account
-> strategy instance
-> execution intent
-> order
-> position cycle
```

Kill-switch actions are distinct: block entries, cancel pending entries,
preserve protection, replace unsafe protection, reduce risk, emergency exit,
account halt, global halt, and read-only recovery.

Degraded modes distinguish fresh entry from protection. Analytics degradation
does not automatically stop trading, but persistence degradation downgrades
authority because financial state cannot be durably recorded.

## Market Data

Production-intended flow:

```text
provider feed
-> provider adapter
-> normalized event
-> instrument state owner
-> immutable snapshot
-> subscription index
-> affected strategy and position streams
```

Ordinary quote/OI updates are conflatable. Market open, ORPT, RC, EOD,
operator/risk actions, broker acknowledgements, fills, cancel/replace results,
reconciliation results, and position transitions are non-conflatable.

## PnL Reliability

P&L projections must be rebuildable from broker-confirmed fills, confirmed
quantities, charges, reconciliation corrections, contract metadata, and market
marks. Corrections produce correction facts rather than mutating source facts.

## Phase 4 Order

Recommended implementation order:

1. captured/replay shadow connection
2. broker read-only boundary
3. persistence foundation
4. reconciliation engine
5. ExecutionIntent and risk validation
6. AccountCoordinator
7. OrderStateMachine
8. PositionCycle execution integration
9. operational facts
10. essential P&L projections

## Later User Decisions

Not blockers for this milestone:

1. preferred transactional database, with SQLite recommended for local V1
2. broker read-only API availability for orders/fills/positions/margin
3. paper source of truth, with internal simulator recommended initially
4. persistence-degraded protection behavior
5. automatic projection-repair scope
6. provisional loss/order/position limits as configuration placeholders

## Authority

Broker authority: `NONE`

Paper authority: `NONE`

Live authority: `NONE`

Order mutation authority: `NONE`

Position mutation authority: `NONE`

## Next Milestone

Milestone 4 should cover essential analytics/P&L facts, the first-10 candidate
strategy matrix, and the strategy-onboarding process.
