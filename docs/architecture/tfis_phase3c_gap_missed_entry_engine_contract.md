# TFIS Phase 3C Gap And Missed-Entry Engine Contract

Status: Milestone 2 contract specification only. Runtime activation and
strategy compatibility policies remain out of scope.

Authoritative Phase 3C certification/specification is consolidated in
`docs/architecture/tfis_phase3c_gap_missed_entry_engine.md`. This contract is
retained for Milestone 2 traceability.

Milestone 3 compatibility policies are documented in
`docs/architecture/tfis_phase3c_gap_missed_entry_compatibility_policies.md`.
They remain isolated under `src/tfis/adapters/legacy_policies/` and do not
change this generic contract boundary.

Milestone 4 parity and typed packet-evidence integration are documented in
`docs/architecture/tfis_phase3c_gap_missed_entry_parity_and_evidence.md`.

## Boundary

`GapMissedEntryEngine` is a generic business engine contract for supplied
timing and observation evidence. It may validate evidence, invoke an explicitly
resolved strategy rule policy, and return three independent outputs:

- gap classification
- missed-entry classification
- recalculation instruction for a later Entry Engine

It must not calculate Monthly Status, calculate Market Structure, collect
ORPT/RC observations, select contracts, calculate final entry unless a
compatibility policy supplies a delegated output, calculate target/FSL/TRP/MSL/
TSL/APS, or place/alter orders.

One combined engine is used because gap, missed-entry timing, and recalculation
instructions share the same timing and observation packet. The contract keeps
their results separate so each stage remains independently auditable.

## Generic Versus Policy Responsibility

The generic engine handles immutable result construction, common validation,
evidence normalization, deterministic serialization, and fail-closed behavior.

The strategy rule policy handles the actual business semantics: reference
selection, thresholds and buffers, comparison source and operator, ORPT/RC
applicability, branch semantics, missed-entry rule identity, and recalculation
key.

## Timing Model

`SessionTimingEvidence` records session timezone, market open, ORPT timestamp,
RC timestamp, evaluation timestamp, source event timestamp, processing
timestamp, ORPT/RC observations, current-day high/low, timing-window state, and
missing/late/stale/chronology warnings.

ORPT and RC are not globally mandatory. Each has an explicit requirement state:
`NOT_APPLICABLE`, `CONFIGURED_BUT_UNUSED`, `OPTIONAL`, `REQUIRED`, or
`UNRESOLVED`.

## Gap Result

`GapClassificationResult` independently carries applicability,
`NORMAL_OR_NO_GAP`, `GAP_UP`, `GAP_DOWN`, `UNAVAILABLE`, `NOT_APPLICABLE`, or
`INVALID`; direction; opening observation; reference price; absolute and
percentage measurement; comparison operator; threshold/buffer; formula and
requirement references; provenance; warnings; and quality.

No universal gap formula is embedded in the contract. The policy supplies the
reference and threshold semantics.

## Missed-Entry Result

`MissedEntryClassificationResult` carries applicability, `NOT_APPLICABLE`,
`NOT_MISSED`, `MISSED`, `UNAVAILABLE`, or `INVALID`; comparison rule identity;
operator; explicit observed source such as `OPTION_HIGH`, `OPTION_LOW`, `LTP`,
`BID`, `ASK`, `UNDERLYING_HIGH`, or `UNDERLYING_LOW`; observed value; entry
reference value; branch; formula and requirement references; provenance;
warnings; and quality.

The observed field is typed, not hidden in free-text evidence.

## Recalculation Instruction

`RecalculationInstruction` is a downstream instruction, not open-ended generic
formula execution. It supports `NOT_REQUIRED`, `REQUIRED`,
`COMPLETED_BY_COMPATIBILITY_POLICY`, `REQUIRED_INPUT_MISSING`, `UNSUPPORTED`,
and `INVALID`; branch/key; required input references; supplied values; policy
key; formula and requirement references; intermediate evidence; optional
compatibility outputs; downstream action; failures; warnings; and provenance.

Risk and lifecycle calculations remain outside this engine.

## Unresolved Semantics

`UnresolvedRuleIssue` records issue code, classification, affected strategy,
version, branch, competing observed behaviors, authoritative source status,
execution permission, and fail-closed reason.

The known S23 PUT missed-entry inconsistency is represented as unresolved
semantics:

- backtest behavior compares `option_low < entry_price`
- paper/live timing-audit behavior compares `option_high < entry_price`

Milestone 2 does not choose between them. The authoritative rule remains
`USER_CLARIFICATION_REQUIRED` and/or `WORKBOOK_VERIFICATION_REQUIRED` until the
workbook or user confirms the intended behavior. Legacy labels may be carried
only in compatibility metadata; the generic enum remains a source/operator
model.

## S21 ORPT/RC Applicability Gap

S21 timing fields must not be inferred to mean ORPT/RC are used in the same way
as S23. The contract supports not applicable, configured but unused, required,
optional, and unresolved timing requirements. Current S21 ORPT/RC applicability
is `USER_CLARIFICATION_REQUIRED` / `INSUFFICIENT_EVIDENCE` before Milestone 3.

## Evidence Integration

`GapMissedEntryEvidence.to_decision_evidence_fragment()` provides the minimum
contract integration point for future `TFISDecisionEvidencePacket` mapping. The
fragment retains raw timing evidence, chronology, gap classification,
missed-entry status, comparison field/operator/reference, recalculation
instruction, policy key, formula and requirement references, provenance,
unresolved metadata, warnings, and failures.

Full packet parity/report integration is reserved for Milestone 4.

## Catalog Integration

`config/business_engines/catalog.yaml` keeps the existing `gap` engine identity
but upgrades its metadata to the combined Gap/Missed-Entry contract. It depends
on Market Structure and Monthly Status where applicable, provides both `GAP`
and `MISSED_ENTRY`, and the downstream Entry engine requires those capabilities.
This is metadata-only and does not activate runtime execution.

## Open Issues Before Milestone 3

- Confirm the authoritative S23 PUT missed-entry comparison.
- Verify S21 ORPT/RC applicability from workbook/user evidence.
- Design strategy-specific compatibility policies without hardcoding formulas
  into the generic engine.
- Map the result into full decision evidence and parity reports in Milestone 4.
- Keep target, FSL, TRP, MSL, TSL, APS, contract selection, and order behavior
  in later engines.
