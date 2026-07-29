# TFIS Phase 3C Gap/Missed-Entry Engine

Status: authoritative Phase 3C engineering specification. Phase 3C is complete
for offline architecture and supported legacy parity. Runtime activation remains
deferred.

This document consolidates the approved Phase 3C inventory, generic contract,
compatibility-policy, parity, and evidence artifacts without resolving open
business rules silently.

## A. Purpose

The Generic Gap/Missed-Entry Business Engine provides a broker-agnostic,
strategy-neutral, deterministic business capability for supplied timing,
market-level, option-observation, and entry-reference evidence. It turns those
inputs into independent gap, missed-entry, and recalculation-instruction
outputs that can later be consumed by an Entry Engine.

## B. Business Responsibility

The engine validates supplied observations, invokes an explicitly resolved
policy, produces immutable results, preserves provenance, records unresolved
rules, and fails closed when required evidence or policy authority is missing.

## C. Explicit Non-Responsibilities

The engine does not calculate Monthly Status, calculate Market Structure,
collect ORPT/RC, fetch broker data, parse YAML per evaluation, select
contracts, calculate target/stop/FSL/TRP/MSL/TSL/APS, manage lifecycle state,
place orders, or authorize paper/live execution.

## D. Dependency Position

The generic engine lives in `src/tfis/domain/gap_missed_entry.py`. It may depend
on TFIS domain/business-engine contracts only. S21/S23 compatibility behavior
lives in `src/tfis/adapters/legacy_policies/` and may delegate to existing
legacy calculators for offline parity.

## E. Generic Engine Boundary

The generic boundary owns immutable input/result/evidence construction,
common validation, fail-closed status selection, deterministic JSON
serialization, and typed evidence fragments. It does not contain S21/S23 branch
formulas or broker/runtime dependencies.

## F. Input Contract

`GapMissedEntryEngineInput` carries strategy family, definition, version,
instance, product type, resolved configuration hash, policy key, timing
evidence, optional monthly status, supplied market-structure references,
entry reference value, policy configuration, unresolved issues, and provenance.

## G. Gap Output

`GapClassificationResult` carries applicability, classification, direction,
opening observation, reference, absolute/percentage measurement, comparison
operator, threshold buffer, formula reference, requirement reference, quality,
warnings, and provenance.

## H. Missed-Entry Output

`MissedEntryClassificationResult` carries applicability, status, comparison
rule, observed value, entry reference value, branch, direction, quality,
warnings, and provenance. Comparison source and operator are explicit typed
fields, not free text.

## I. Recalculation Instruction

`RecalculationInstruction` carries whether recalculation is applicable, status,
branch, required input references, supplied values, policy key, formula
reference, requirement reference, intermediate evidence, compatibility outputs,
downstream action, failures, warnings, and provenance. It is an instruction to
the future Entry Engine, not final entry authority.

## J. Timing And Chronology

`SessionTimingEvidence` records timezone, market open, evaluation, source
event, processing, ORPT, RC, current-day high/low, missing/late/stale evidence,
and chronology warnings. Invalid chronology, stale evidence, and missing
required timing evidence fail closed.

## K. ORPT/RC Applicability

ORPT and RC are explicitly modeled as `NOT_APPLICABLE`,
`CONFIGURED_BUT_UNUSED`, `OPTIONAL`, `REQUIRED`, or `UNRESOLVED`. S21 is not
allowed to inherit S23 ORPT/RC semantics by inference.

## L. Validation And Fail-Closed Rules

The engine fails closed for unsupported product, unsupported strategy family,
missing policy/configuration identity, missing required market-structure refs,
unsupported monthly-status branch, missing required ORPT/RC observations, stale
observations, invalid timing chronology, missing entry/option observations, and
unresolved executable policy authority.

## M. Evidence Model

`GapMissedEntryEvidence` preserves timing, gap, missed-entry, recalculation,
formula references, requirement references, unresolved issues, warnings,
failures, and provenance. The optional
`GapMissedEntryBusinessEngineFragment` maps this into
`TFISDecisionEvidencePacket` with typed values and deterministic JSON.

## N. Policy Boundary

Policies provide business semantics: reference selection, threshold/buffer,
branch mapping, comparison source/operator, ORPT/RC applicability, and
compatibility recalculation. Policy resolution uses strategy definition plus
version and does not infer a default profile.

## O. S21 Compatibility

S21 supports evidence-only `NOT_APPLICABLE` behavior and an unresolved timing
profile that fails closed. Phase 3C does not declare a confirmed S21 gap formula
or executable ORPT/RC missed-entry rule.

## P. S23 Branch Compatibility

S23 compatibility covers Bull Call, Bear Call, Bull Put, and Bear Put branches
with required ORPT/RC timing, supplied current-day references, explicit missed-
entry comparison, and delegated recalculation compatibility outputs when
missed entry is detected.

## Q. S23 PUT Dual-Profile Inconsistency

S23 PUT has two reproducible compatibility profiles:

- `legacy.s23.gap_missed_entry.backtest_low_v1`: `OPTION_LOW < entry`
- `legacy.s23.gap_missed_entry.paper_live_high_v1`: `OPTION_HIGH < entry`

Neither profile is declared authoritative. The unresolved PUT profile records
both behaviors and fails closed.

## R. Strategy Composition

Strategy composition is external to the generic engine. The current
compatibility composition is definition-and-version keyed. A strategy instance
must supply or resolve a policy key explicitly before evaluation.

## S. State And Concurrency Model

The engine is stateless after construction. Inputs and results are frozen
dataclasses with frozen mapping fields. There is no shared mutable engine state,
module-level strategy state, global lock, or external persistence dependency
inside evaluation.

## T. Determinism Requirements

For identical inputs and policy, engine JSON output must be byte-stable with
sorted keys, ASCII JSON, stable enum values, stable provenance, and null-versus-
zero preservation. Report artifacts stabilize variable wall-clock timing fields
so certification files are deterministic.

## U. Performance Expectations

Offline validation shows in-process evaluation suitable for later
multi-strategy shadow design: no YAML parsing per evaluation, no registry scan
per evaluation, no external storage lookup, no broker call, no shared global
lock, and no mutable module-level strategy state. Phase 3C makes no live-money
throughput claim.

## V. Parity Results

Milestone 4/5 parity counts:

- total cases: 8
- passed cases: 8
- mismatches: 0
- fail-closed cases: 2
- full captured parity: 0
- partial captured parity: 1
- synthetic golden parity: 1
- legacy fixture parity: 5
- unsupported parity: 1

## W. Captured-Evidence Limitations

Full captured parity is unavailable. This is an evidence/capture gap, not a
formula-rule defect. Supported offline parity is certified only according to
each case's evidence classification.

## X. Runtime Migration Constraints

No active paper/live/backtest/runtime module may import or invoke
`GapMissedEntryEngine` until a separately approved runtime-shadow milestone.
Disabled shadow adoption remains blocked by S23 PUT authority, S21 ORPT/RC
applicability, and full captured-evidence limitations.

## Y. Open Business-Rule Questions

The open-rule register is maintained in
`docs/architecture/tfis_phase3c_open_rule_register.md` and includes:

- `TFIS-GME-OPEN-001`: S23 PUT missed-entry authoritative comparison
- `TFIS-GME-OPEN-002`: S21 ORPT/RC applicability
- `TFIS-GME-OPEN-003`: full captured parity availability

## Z. Requirements And Acceptance Criteria

| Requirement | Acceptance criterion | Primary proof |
| --- | --- | --- |
| TFIS-GME-001 | Generic engine neutrality | `tests/architecture/test_business_engine_boundary.py` |
| TFIS-GME-002 | Immutable inputs/results | `tests/unit/test_phase3c_gap_missed_entry_contracts.py` |
| TFIS-GME-003 | Supplied upstream observations only | architecture tests and no broker/storage imports |
| TFIS-GME-004 | No engine-owned timing state | chronology validation tests |
| TFIS-GME-005 | Independent gap and missed-entry outputs | contract tests |
| TFIS-GME-006 | Explicit ORPT/RC applicability | contract and compatibility tests |
| TFIS-GME-007 | Explicit comparison source | contract tests |
| TFIS-GME-008 | Explicit comparison operator | contract tests |
| TFIS-GME-009 | Explicit observed/reference values | serialization tests |
| TFIS-GME-010 | Recalculation is downstream instruction | contract tests |
| TFIS-GME-011 | Missing evidence fails closed | compatibility tests |
| TFIS-GME-012 | Unresolved policy fails closed | compatibility tests |
| TFIS-GME-013 | Definition-plus-version policy resolution | compatibility tests |
| TFIS-GME-014 | Evidence determinism | parity/evidence tests |
| TFIS-GME-015 | Provenance preservation | packet round-trip tests |
| TFIS-GME-016 | Null-versus-zero preservation | serialization tests |
| TFIS-GME-017 | Strategy-instance isolation | adapter mapping tests |
| TFIS-GME-018 | S23 PUT profile non-selection | contract and parity tests |
| TFIS-GME-019 | No target/stop/contract responsibility | contract and evidence tests |
| TFIS-GME-020 | No active runtime dependency | architecture tests |

Phase 3C accepts only if architecture is complete, supported legacy behavior has
zero unexplained mismatches, evidence integration is deterministic, unresolved
behavior fails closed, and runtime remains explicitly deferred. The final
certification verdict is `PHASE_3C_ACCEPT`.
