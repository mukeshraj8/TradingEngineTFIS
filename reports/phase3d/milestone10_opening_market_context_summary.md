# Phase 3D Milestone 10 Opening Market Context Summary

## Verdict

PHASE3D_M10_ACCEPT

## Scope

Implemented an immutable offline `OpeningMarketContext` contract and generic
builder, plus the smallest S23 Call-side composition for:

- S23 Bull Call complete fixture context
- S23 Bear Call complete fixture context
- S23 Bull Call partial real context from M7 evidence

No `EffectiveExecutionPlan`, execution authority, broker call, scheduler, event
bus, paper/live authority, lifecycle action, Target/MSL recalculation, or
Gap/Missed-Entry business outcome was implemented.

## Contract And Builder

The strategy-neutral contract lives in
`src/tfis/domain/opening_market_context.py`.

The strategy-neutral builder lives in `src/tfis/opening/context_builder.py` and
owns only observation normalization, timestamp classification, quote freshness,
gap evidence classification, ORPT/RC association, quality/readiness
classification, deterministic construction, and hashing.

## Official/Open Distinctions

The model explicitly distinguishes:

- scheduled exchange open time
- official exchange opening timestamp
- first local quote timestamp
- derived opening-bar timestamp
- ORPT observation
- RC observation

When official exchange open is unavailable, the context preserves local or
derived evidence without labeling it official.

## Fixture Results

| Case | Status | Gap | ORPT | RC | Context hash |
| --- | --- | --- | --- | --- | --- |
| S23 Bull Call | `COMPLETE` | `GAP_UP` | `AVAILABLE` | `AVAILABLE` | `cd49e501b4470dc278724c0abf8dc54b32f2ea0befb3d3c3576cf2a0e91bd38a` |
| S23 Bear Call | `COMPLETE` | `GAP_DOWN` | `AVAILABLE` | `AVAILABLE` | `7590f983c4fb7ee5087a7e8909d81a7feb9713c9903fdd778f556ece9f34875e` |

## Partial Real Result

The M7-derived context is `PARTIAL`, evidence classification `PARTIAL_CAPTURE`.
It preserves real underlying opening, ORPT underlying, RC underlying, and RC
selected-contract evidence. It remains partial because selected-contract
opening/OI and ORPT selected-contract evidence are missing, and the gap
comparison reference is unavailable.

Context hash:
`d2863ef30e58c0dc88156436038f51289883dc08dfd2f347af174de1180d4b23`

## Gap Classification

Opening gap classification is evidence only. It may classify `NO_GAP`,
`GAP_UP`, `GAP_DOWN`, `ABNORMAL_OPENING`, `INSUFFICIENT_EVIDENCE`, or
`NOT_APPLICABLE`. It does not produce a final Gap/Missed-Entry business result.

## ORPT/RC Evidence

ORPT and RC remain timed observations with configured timestamp, source
timestamp, underlying observation, selected-contract observation where present,
freshness, provenance, and policy applicability.

## Reuse And Isolation

Tests prove one immutable underlying observation may be shared by multiple S23
strategy-instance contexts while context identities and source plan references
remain independent. Tests also prove NIFTY observations cannot satisfy
BANKNIFTY or mismatched selected-contract contexts.

## Performance And Communication Invariants

M10 records these as contract/test invariants only:

- normalize shared instrument observations once
- route only to subscribed future consumers
- consume immutable coherent snapshots
- preserve future single-writer live-state ownership
- keep broker-order paths out of market-data context construction
- keep official open, ORPT, RC, order acknowledgements, fills, and lifecycle
  transitions non-conflatable
- produce deterministic results for equivalent snapshots and policies
- bound work to the observations required by the specific context

No event bus, scheduler, concurrency, thread pool, or broker queue was built.

## Runtime Impact

Runtime execution authority: `NONE`.

Broker/paper/live impact: `NONE`.

## Remaining Gaps Before EffectiveExecutionPlan

- `EffectiveExecutionPlan` composition is not implemented.
- Real complete OpeningMarketContext packets: `0`.
- Partial real OpeningMarketContext packets: `1`.
- Live feed routing/subscriptions are not implemented.
- Gap/Missed-Entry final retain/recalculate/block outcome remains later work.

