# Phase 3D Milestone 9 S23 Pre-Market Plan Summary

## Verdict

PHASE3D_M9_ACCEPT

## Scope

Implemented one immutable offline `PreMarketStrategyPlan` builder path for the
existing supported S23 Call-side cases:

- S23 Bull Call
- S23 Bear Call

This milestone does not implement `OpeningMarketContext`,
`EffectiveExecutionPlan`, `PositionLifecycleContext`, market-open scheduling,
ORPT/RC waiting, current-session gap analysis, broker reconciliation,
execution, paper authority, or live authority.

## Builder Architecture

The generic `PreMarketStrategyPlanBuilder` runs explicitly supplied pre-market
stages in fixed order:

1. strategy resolution
2. Monthly Status and branch validation
3. completed underlying references
4. contract selection
5. Base Entry
6. preliminary Target
7. preliminary MSL
8. ORPT/RC timing

The builder owns ordering, validation, fail-closed propagation, evidence
aggregation, and deterministic hashing. It does not own strategy formulas,
contract-selection rules, Entry formulas, Target/MSL formulas, broker logic,
Gap/Missed-Entry evaluation, execution, or lifecycle behavior.

## Implementation Source Map

| Plan field | Existing source component | Input contract | Output contract | Evidence source | Missing authority | Failure behavior |
| --- | --- | --- | --- | --- | --- | --- |
| Strategy identity | `TFISRuntimeInput` fixture | Runtime input | Plan identity | M3/M4 vertical fixtures | Real captured pre-market packet | Block if identity missing |
| Resolved configuration | S23 vertical branch spec | Mapping payload | `resolved_configuration_hash` | M3/M4/M5 fixture hashes | Full runtime config resolver composition | Block if missing or mismatched |
| Monthly Status | S23 fixture runtime input | `ProductPolicyInput` | Product/branch result | Legacy fixture | Real daily Monthly Status capture | Block on missing/unknown branch |
| Underlying references | `S23EntryPolicyAdapter` | `EntryPolicyInput` | trade-plan references | workbook-normalized formulas | Real completed reference packet | Block on missing references |
| Contract selection | `S23ContractSelectionPolicyAdapter` | `ContractSelectionPolicyInput` | selected Call contract | legacy fixture/supplemented option chain | Real option-chain packet | Block on no qualifying contract |
| Base Entry | `EntryEngine` + S23 vertical entry policy | `EntryEngineInput` | Base Entry result | Entry evidence fragment | none for fixture path | Block on Entry failure |
| Preliminary Target | `S23TargetPolicyAdapter` | `TargetPolicyInput` | Target result | workbook-normalized trade plan | real captured risk packet | Block on Target failure |
| Preliminary MSL | `S23MSLPolicyAdapter` | `MSLPolicyInput` | MSL result | workbook-normalized trade plan | real captured risk packet | Block on MSL failure |
| ORPT/RC | M9 fixture timing policy | timing stage | plan timing values | synthetic supplement | authoritative timing config contract | Block if missing |

## Plans

| Case | Status | Selected contract | Base Entry | Target | MSL | Plan hash |
| --- | --- | --- | --- | --- | --- | --- |
| S23 Bull Call | `PREPARED` | `NIFTY_20260806_22250_CALL` | `203.5` | `81.4` | `321.0` | `873a7662f321b70af350a5d3b2e0b9fccf72852ae0bfc88e4471faca4cd91f22` |
| S23 Bear Call | `PREPARED` | `NIFTY_20260806_22150_CALL` | `194.25` | `77.7` | `310.8` | `cfb09a5b41ee667a045e89d36cf4167dfe3acb46630bf76dd03e16f51e3e576b` |

## Pre-Market Parity

Both plans match the accepted vertical fixture fields for selected Call
contract, selected expiry, selected strike, premium, OI, Base Entry,
preliminary Target, and preliminary MSL. Current-session Gap/Missed-Entry and
Effective Entry are intentionally not compared because they are not pre-market
plan fields.

## Evidence Classification

M9 plan evidence is classified as
`LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT`.

Material field provenance is recorded in each plan JSON using only:

- `LEGACY_CONFIG`
- `WORKBOOK_NORMALIZED`
- `LEGACY_FIXTURE`
- `SYNTHETIC_SUPPLEMENT`
- `DERIVED`
- `MISSING`
- `NOT_APPLICABLE`

## Fail-Closed Scenarios

Covered by tests:

- missing strategy identity
- missing resolved configuration
- disabled strategy instance
- trading-day ineligible
- missing Monthly Status
- unknown branch
- missing completed underlying reference
- missing option-chain input/no qualifying contract
- missing selected-contract historical reference
- Base Entry failure
- preliminary Target failure
- preliminary MSL failure
- missing ORPT
- missing required RC time
- invalid quantity/lots
- carried position detected
- configuration hash mismatch
- evidence validation failure through missing required plan fields

## Carried-Position Boundary

If a carried position is detected, the builder returns `NO_ACTION_TODAY` with
`MANAGING_CARRIED_POSITION` and does not invoke fresh-entry Contract Selection,
Entry, Target, or MSL.

## Plan-To-Opening Compatibility

The plan contains the upstream data needed by the future opening path:

`PreMarketStrategyPlan -> OpeningMarketContext -> Gap/Missed-Entry -> Effective Entry -> TFISDecision`

M9 proves data compatibility only. It does not implement
`OpeningMarketContext` processing.

## Source/Runtime Impact

Runtime authority: `NONE`.

Broker/paper/live impact: `NONE`.

No runtime profile, broker route, scheduler, execution configuration, paper
authority, or live authority was enabled.

## Remaining Gaps

- `OpeningMarketContext` contract and offline S23 Call-side builder remain not
  implemented.
- Real captured S23 pre-market packets remain `0`.
- S23 PUT, S21, futures, execution, lifecycle, broker reconciliation, and
  carried-position opening-gap behavior remain out of scope.

