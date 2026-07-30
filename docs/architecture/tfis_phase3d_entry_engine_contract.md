# TFIS Phase 3D Entry Engine Contract

Status: Phase 3D Milestone 2 accepted contract design, offline only.

Date: Thursday, July 30, 2026

## Purpose

The Generic Entry Engine defines product-neutral contracts for:

- Base Entry Candidate
- Effective Entry Trigger
- Entry Qualification
- Entry evidence, validation, metrics, and fail-closed status

It is the final standalone Entry architecture milestone. The next approved
work should be the offline S23 vertical slice that composes Strategy
Resolution, Contract Selection compatibility, Base Entry, Gap/Missed-Entry,
Effective Entry, Target/MSL compatibility, `TFISDecision`, and
`TFISDecisionEvidencePacket`.

## Boundary

Entry owns:

- base entry validation and evidence normalization
- effective entry finalization after supplied Gap/Missed-Entry evidence
- explicit trigger condition, order side, position intent, and reference
  identity evidence
- fail-closed handling for missing policy, instrument, references, formulas,
  unresolved semantics, and incompatible recalculation evidence

Entry does not own:

- strategy branch inference
- option-chain scanning
- strike range, OI, premium, expiry, or near/next contract selection
- ORPT/RC missed-entry detection
- target, stop loss, MSL, FSL, TSL, APS, or TRP
- lifecycle state, order creation, paper/live runtime, broker adapters, or
  filesystem persistence

## Product-Aware Dependency Model

Option strategies:

```text
Branch Resolution
  -> Underlying References
    -> Contract Selection
      -> Selected Contract References
        -> Base Entry
          -> Gap/Missed-Entry, when applicable
            -> Effective Entry
              -> Risk
```

Futures:

```text
Branch Resolution
  -> Resolved Futures Instrument
    -> Futures References
      -> Base Entry
        -> Gap/Missed-Entry
          -> Effective Entry
            -> Risk
```

Equity remains generic only. No equity business rules are implemented.

The catalog avoids a hard universal `Entry -> Contract Selection` or
`Gap -> Entry` dependency. The Entry input contract requires a resolved
tradable instrument or selected option contract, and product-specific
composition decides where that came from.

## Base Entry

`EntryBaseCandidate` is the initial threshold produced by the resolved Entry
policy before Gap/Missed-Entry effects.

Required inputs include:

- `StrategyEvaluationIdentity`
- `PositionCycleIdentity`
- resolved configuration hash
- product
- resolved branch
- resolved tradable instrument or selected option contract
- entry policy key
- formula descriptor
- explicit entry references
- evaluation timestamp

For options, the selected option contract must already be supplied. For
futures, the resolved futures instrument and futures references must be
supplied.

## Effective Entry

`EntryEffectiveTrigger` is the downstream trigger after supplied
Gap/Missed-Entry output is considered.

Generic outcomes include:

- `EFFECTIVE_ENTRY_EQUALS_BASE`
- `EFFECTIVE_ENTRY_RECALCULATED`
- `ENTRY_NOT_MISSED`
- `ENTRY_MISSED`
- `RECALCULATION_REQUIRED`
- `DEFERRED_UNTIL_RECALCULATION`
- `BLOCKED`
- `REJECTED`
- `UNAVAILABLE`
- `INVALID`
- `NOT_APPLICABLE`

The generic engine does not calculate S21/S23 RC formulas. It validates the
supplied Phase 3C result and delegates effective-entry finalization to the
resolved Entry policy.

## Reference Identity

`EntryReference` explicitly distinguishes:

- `UNDERLYING_SPOT`
- `UNDERLYING_FUTURE`
- `SELECTED_OPTION_CONTRACT`
- `EQUITY_INSTRUMENT`
- `FINAL_STRIKE_VALUE`
- `ENTRY_VALUE`
- `CURRENT_DAY_OBSERVATION`
- `OTHER_EXPLICIT_REFERENCE`

Each reference carries instrument id, segment, product, reference type,
lookback, value, value type, event timestamp, effective date, provenance,
quality, and required/optional status.

## Formula Component Model

`EntryFormulaDescriptor` contains bounded `EntryFormulaComponent` rows. The
model preserves formula structure without evaluating arbitrary expressions.

Supported representation includes:

- reference plus/minus percent of the same reference
- selected-contract reference plus/minus percent of final strike
- entry plus/minus percent of entry
- entry plus/minus percent of final strike
- max/min of base entry and recalculated threshold

Every percentage component identifies its percentage base.

## Phase 3C Integration

Phase 3C remains independent and certified. Entry consumes
`GapMissedEntryEngineResult` as an optional typed input.

Entry validates:

- whether Gap/Missed-Entry was required but missing
- whether Phase 3C blocked
- whether recalculation was required but not supplied
- whether recalculation output is compatible with the resolved Entry policy

No Phase 3C behavior, S23 PUT ambiguity, or S21 ORPT/RC applicability was
changed.

## Evidence

`EntryEvidence` preserves:

- strategy identity
- policy key
- product and branch
- resolved instrument
- formula descriptor
- input references
- base entry
- Gap/Missed-Entry dependency summary
- effective entry
- validation, warnings, failures, quality, provenance
- deterministic evidence hash

`TFISDecisionEvidencePacket` now has an optional
`EntryBusinessEngineFragment`. Existing packet JSON remains backward
compatible when the field is absent.

## Validation And Failures

The contract defines fail-closed failures for missing identity, position cycle,
configuration hash, policy, resolved instrument, selected option contract,
reference, formula descriptor, trigger direction, order side, Gap/Missed-Entry
dependency, recalculation output, unsupported product, timestamp chronology,
stale evidence, unresolved semantics, and nondeterministic output.

Validation distinguishes:

- validation failure
- business rejection
- unavailable evidence
- unresolved authority
- not applicable
- deferred
- successful downstream permission

## Business Engine Integration

The catalog Entry engine provides:

- `ENTRY`
- `BASE_ENTRY`
- `EFFECTIVE_ENTRY`
- `ENTRY_QUALIFICATION`
- `RECALCULATED_ENTRY`

Contract Selection now provides `TRADABLE_INSTRUMENT_RESOLVED`. Entry validates
that such a resolved instrument or selected contract is present rather than
hardcoding product-specific dependencies in the generic catalog.

## Performance Expectations

The engine performs no filesystem access, config reloads, broker calls, order
creation, or unbounded expression evaluation. Metrics record validation,
policy resolution, formula/policy evaluation, result construction, evidence
serialization, hash duration, serialized size, reference count, and missing
reference count.

## Unsupported Behavior

Milestone 2 does not implement:

- S21/S23 compatibility policies
- option-buy formulas
- option-sell formulas
- futures formulas
- equity formulas
- parity reports
- runtime shadow
- paper authority
- live authority

## Readiness Matrix

| Readiness area | Status |
| --- | --- |
| Architecture contract | Ready for offline vertical slice |
| Domain contracts | Ready |
| Generic orchestration shell | Ready |
| Business Engine catalog metadata | Ready |
| Decision evidence optional fragment | Ready |
| Strategy compatibility policies | Not implemented |
| S23 vertical slice | Next approved phase |
| Runtime shadow | Not ready |
| Paper authority | Not ready |
| Live money | Not ready |
