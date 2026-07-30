# Phase 3D Milestone 11 - EffectiveExecutionPlan Summary

Date: Thursday, July 30, 2026

Verdict: `PHASE3D_M11_ACCEPT`

## Scope

Milestone 11 implements immutable offline `EffectiveExecutionPlan`
composition for the existing supported S23 Call-side cases only:

- S23 Bull Call
- S23 Bear Call

The implemented path consumes a completed immutable `PreMarketStrategyPlan`
plus an immutable `OpeningMarketContext` and produces an offline execution-plan
candidate, blocked plan, or insufficient-evidence plan. It does not place
orders, publish execution intent, mutate positions, schedule work, or grant
paper/live authority.

## Contract And Composer

- Contract: `src/tfis/domain/effective_execution_plan.py`
- Composer: `src/tfis/execution_plan/composer.py`
- S23 adapter: `src/tfis/adapters/legacy_policies/s23_effective_execution_plan.py`

The generic composer owns compatibility validation, ordered stage invocation,
normal/recalculation path selection, fail-closed propagation, evidence
aggregation, and deterministic hash construction. It contains no S23/S21
branching, broker dependency, scheduler, event bus, filesystem write, contract
selection, monthly-status calculation, historical-reference calculation, or
arbitrary expression evaluation.

## Supported Paths

### Normal Retained Path

Normal retained plans use sufficient opening context with `NO_GAP` and skip
Phase 3C Gap/Missed-Entry evaluation. Base Entry, preliminary Target, and
preliminary MSL are retained from the pre-market plan. Authorized timing is
normal ORPT.

### Gap Recalculated Path

Gap paths use the existing Phase 3C Gap/Missed-Entry compatibility engine and
the generic Entry Engine to finalize Effective Entry. Target/MSL are
recalculated only inside the S23 compatibility adapter using the accepted S23
rule authority already represented by existing strategy parameters. The generic
composer does not duplicate those formulas.

### Partial Real Path

The M7-derived M10 partial real opening context is consumed without fabricated
evidence. The result is `INSUFFICIENT_EVIDENCE`, with missing fields preserved
and no downstream execution permission.

## Result Artifacts

| Case | Status | Path | Hash |
| --- | --- | --- | --- |
| Bull normal | `READY_OFFLINE` | `NORMAL_RETAINED` | `c30bd67eeeb2063c90ddce7afd9a175cb38c049c2896ed914a6948382c16ebb1` |
| Bull gap | `READY_OFFLINE` | `GAP_RECALCULATED` | `45a5106bb1027881abf5d937224fd6def4237476941f2c8d8603d2963526df51` |
| Bear normal | `READY_OFFLINE` | `NORMAL_RETAINED` | `3830fd5b913db77e765d2203740ebbd6e16d8549f4cee8a3a5051f26afba8051` |
| Bear gap | `READY_OFFLINE` | `GAP_RECALCULATED` | `f21d868f8e78edd54b5c231848e9b4f820150e2d65d5855b30adde35ea8a505e` |
| Partial real | `INSUFFICIENT_EVIDENCE` | `BLOCKED_OPENING_VALIDATION` | `413cfb509cb5d511b9d08ef013d6ec6c8064aedb5962e251b1ea576673475fbd` |

JSON artifacts:

- `reports/phase3d/milestone11_s23_bull_normal_execution_plan.json`
- `reports/phase3d/milestone11_s23_bull_gap_execution_plan.json`
- `reports/phase3d/milestone11_s23_bear_normal_execution_plan.json`
- `reports/phase3d/milestone11_s23_bear_gap_execution_plan.json`
- `reports/phase3d/milestone11_partial_real_execution_plan.json`
- `reports/phase3d/milestone11_execution_plan_gap_matrix.json`

## Target/MSL Ownership

Target and MSL statuses are explicit:

- normal retained paths: `RETAINED_FROM_PREMARKET`
- supported gap recalculated paths: `RECALCULATED`
- blocked paths: `BLOCKED`

Unresolved future risk handling must be represented as
`RULE_AUTHORITY_UNRESOLVED` or fail-closed rather than inferred.

## Timing Authorization

The execution plan calculates only an offline authorized time:

- retained path: normal ORPT `09:19:59`
- recalculated path: RC time `09:29:59`

No scheduler or clock wait was implemented.

## Evidence And Fail-Closed Cases

The composer blocks on missing plan/context, plan-context hash mismatch,
trading-date mismatch, underlying mismatch, selected-contract mismatch, missing
ORPT, missing policy identities, blocked opening context, Phase 3C failure,
Entry finalization failure, Target policy failure, MSL policy failure,
unresolved recalculation authority, and invalid authorized time.

Every blocked/insufficient result has:

- `offline_execution_candidate = false`
- `downstream_execution_permission = "NONE"`
- typed block code/reason
- accumulated stage evidence where available

## Multiple-Instance Proof

Unit coverage proves two strategy instances can share normalized market
evidence while producing independent `EffectiveExecutionPlan` identities and
hashes. A blocked plan/context mismatch for one instance does not contaminate
the other instance.

## Performance

Composition records diagnostic `composition_seconds`, but performance is
excluded from `execution_plan_hash`. No file path, live capture setting, or
diagnostic timing enters the deterministic business hash.

## Runtime Impact

Runtime impact: `NONE`.

Broker/paper/live authority: `NONE`.

The milestone adds offline composition artifacts only. It does not activate
runtime shadow, paper authority, live authority, broker calls, order routing,
execution intent publication, position lifecycle, or shared trading-day
coordination.

## Remaining Gaps Before Live Coordination

- `PositionLifecycleContext` remains `NOT_IMPLEMENTED`.
- Full trading-day coordination remains `NOT_IMPLEMENTED`.
- Shared live routing remains `NOT_IMPLEMENTED`.
- Runtime execution authority remains `NONE`.
- Complete real S23 Call-side parity evidence remains unavailable.
