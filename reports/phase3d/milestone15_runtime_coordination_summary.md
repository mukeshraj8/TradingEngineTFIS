# Phase 3D Milestone 15 Runtime Coordination Summary

## Verdict

PHASE3D_M15_ACCEPT

## Scope

Milestone 15 adds a deterministic, in-memory, non-authoritative runtime coordination layer over the accepted S23 offline fresh-entry and carried-position flows. It does not connect to broker feeds, place orders, mutate positions, persist runtime state, or add paper/live authority.

## Runtime Event Contract

`NormalizedRuntimeEvent` is immutable and deterministic. It records event id, event type, trading date, exchange/session, effective/source/dispatch timestamps, sequence identity, instrument identity, optional contract identity, optional strategy-instance target, optional position-cycle target, provenance, freshness classification, payload, and payload hash.

Implemented event families include market observations, clock events, and operational events. Clock events are explicit inputs; runtime business evaluation does not infer ORPT, RC, EOD, or session-end from `datetime.now()`.

## Delivery Classes

`CONFLATABLE_STATE_UPDATE` covers ordinary underlying quotes, option contract quotes, and OI updates. The runtime keeps only the latest pending coherent update for repeated ordinary ticks.

`NON_CONFLATABLE_CRITICAL_EVENT` covers market open, ORPT, RC, EOD, configuration, strategy enable/disable, reconciliation, cancel, resume, and session-end events. Critical events are processed individually and are reported by event id.

## Instrument Snapshot Ownership

`InstrumentStateOwner` is the single in-memory writer for one instrument or contract. It publishes immutable `InstrumentMarketSnapshot` or `ContractMarketSnapshot` values and handles identical duplicates idempotently, conflicting duplicates fail-closed, stale events as ignored/classified, wrong-instrument/wrong-contract events as rejected, and mixed trading dates as rejected.

## Subscription Routing

`RuntimeSubscriptionIndex` maps underlying instruments and option contracts to interested strategy instances and carried-position cycles. Targeted operational events route only to their explicit target. Untargeted shared market observations route through immutable subscription snapshots.

## Fresh-Entry Runtime Streams

`FreshEntryRuntimeCoordinator` drives existing `OfflineTradingDayCoordinator` using normalized runtime events converted to the M12 offline event contract. M15 proves Bull normal, Bull gap, Bear normal, and Bear gap streams. Normal streams do not consume RC. Gap streams preserve ORPT and RC as critical events and reuse the existing Gap/Missed-Entry business path.

## Carried-Position Runtime Streams

`PositionCycleRuntimeCoordinator` drives existing M14 carried-position logic from position reconciliation, opening, ORPT, RC, and EOD runtime events. Covered streams include target exit, normal SL, revised FSL/TRP, EOD square-off, EOD carry-forward, equality carry-forward, and missing RC fail-closed.

## Multiple Streams

The runtime simulation proves two S23 strategy instances can share one NIFTY observation while producing independent plans, handoffs, hashes, and checkpoints. It also proves two carried-position cycles remain isolated when one exits from open and another continues to EOD.

## Multiple Instruments

NIFTY and unrelated BANKNIFTY observations are held by separate state owners and route only through matching subscriptions. No BANKNIFTY strategy is implemented.

## Backpressure And Conflation

The in-memory simulation accepts ordinary quote bursts without unbounded business evaluation. Latest ordinary quote state is retained and critical ORPT/RC events are preserved. This is a deterministic test policy only and does not claim production throughput.

## Replay And Resume

Runtime checkpoints capture stream identity, current state, consumed event ids, latest snapshot hashes, artifact hashes, configuration hash, rule-matrix version, and checkpoint hash. Full replay produces identical business result hashes. Checkpoint mismatch, configuration mismatch, and rule-matrix mismatch fail closed.

## Performance Measurements

Backpressure fixture metrics:

- event count: 52
- quote burst size: 50
- maximum pending conflatable updates: 1
- critical-event processing count: 2
- total processing seconds: 0.010232500004349276

These measurements are offline/shadow simulation measurements only.

## Authority Proof

All runtime outputs are `SHADOW_ONLY` or existing `OFFLINE_ONLY` handoffs. Broker submission, paper submission, live submission, order modification, order cancellation, position mutation, square-off execution, and carry persistence are explicitly false.

## Remaining Gaps Before Real Shadow

- Connect one existing captured/replay market stream to the coordinator in shadow-only mode.
- Add a read-only broker reconciliation boundary before comparing carried positions against live broker state.
- Add production scheduler/persistence only after captured/replay shadow behavior is reviewed.
- Expand beyond S23 Call-side fixtures only after source-backed business rules are available.
