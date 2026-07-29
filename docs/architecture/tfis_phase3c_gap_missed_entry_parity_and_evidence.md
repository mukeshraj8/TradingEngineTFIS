# TFIS Phase 3C Gap/Missed-Entry Parity And Evidence

Status: Milestone 4 offline parity and packet-evidence integration. Runtime
activation remains out of scope.

Authoritative Phase 3C certification/specification is consolidated in
`docs/architecture/tfis_phase3c_gap_missed_entry_engine.md`. This parity and
evidence document is retained for Milestone 4 traceability.

## Purpose

Milestone 4 proves that the generic `GapMissedEntryEngine` plus compatibility
profiles can reproduce supported S21/S23 gap and missed-entry behavior in a
deterministic offline path. It also adds a typed decision-evidence packet
fragment so future migration can audit the new business-engine result without
free-text payloads.

## Evidence Sources

The report model classifies cases as:

- `SYNTHETIC_GOLDEN_PARITY`
- `PARTIAL_CAPTURED_PARITY`
- `LEGACY_FIXTURE_PARITY`
- `UNSUPPORTED_FOR_PARITY`

The generated report uses deterministic repository fixtures and direct legacy
function calls. Captured evidence remains partial where the repository does not
contain complete option-chain and timing observations for a full field-by-field
case.

## Evaluators

The legacy observation adapter normalizes the existing supported semantics:

- S21 evidence-only and unresolved timing behavior
- S23 ORPT missed-entry detection
- S23 recalculation outputs from `S23RecalculationEngine`
- S23 PUT backtest-low and paper/live-high profile behavior

The generic evaluator resolves an explicit compatibility profile, constructs
`GapMissedEntryEngineInput`, runs `GapMissedEntryEngine`, and preserves typed
validation, warnings, failures, unresolved issues, and evidence.

## Comparison Fields

The comparator checks identity, timing, gap, missed-entry, recalculation,
evidence, and output-hash fields only where the case supports that field group.
Unsupported or irrelevant fields are not treated as mismatches.

Mismatch classification supports the Milestone 4 taxonomy, including
`TIMING_DIFFERENCE`, `COMPARISON_SOURCE_DIFFERENCE`, `FORMULA_DIFFERENCE`,
`VALUE_DIFFERENCE`, `LEGACY_INCONSISTENCY`,
`WORKBOOK_VERIFICATION_REQUIRED`, `USER_CLARIFICATION_REQUIRED`,
`INSUFFICIENT_EVIDENCE`, and `UNSUPPORTED_CASE`.

## S23 PUT Result

Both PUT profiles are reported independently:

- `legacy.s23.gap_missed_entry.backtest_low_v1`
- `legacy.s23.gap_missed_entry.paper_live_high_v1`

The same candle can produce different missed-entry results. The unresolved
profile fails closed and retains both competing behaviors. No authoritative
TFIS rule is declared.

## S21 Result

S21 has evidence-only parity for ORPT/RC `NOT_APPLICABLE` and a fail-closed
unresolved timing profile. No S21 gap formula is invented.

## Packet Integration

`GapMissedEntryBusinessEngineFragment` is an optional typed field on
`GapMissedEntryEvidence`. It preserves policy/profile, timing applicability,
chronology, gap classification, missed-entry comparison source/operator/value,
reference value, recalculation status/branch/downstream action,
compatibility outputs, unresolved issue codes, warnings, failures, and
provenance.

Existing packet parsing remains backward-compatible because the fragment is
optional.

## Reports

Generated under `reports/phase3c/`:

- `gap_missed_entry_parity.json`
- `gap_missed_entry_parity_fields.csv`
- `gap_missed_entry_parity_summary.md`
- `gap_missed_entry_evidence_packet_sample.json`

Current generated counts:

- total cases: 8
- passed cases: 8
- mismatched cases: 0
- fail-closed cases: 2

## Performance

The parity model records import, legacy evaluation, generic evaluation,
comparison, serialization, report generation, packet size, and repeated
evaluation timing. Report artifacts stabilize variable timing fields so the
files remain deterministic.

## Runtime Migration Blockers

- S23 PUT authoritative comparison remains unresolved.
- S21 ORPT/RC applicability remains unresolved for executable behavior.
- Runtime activation is not part of Milestone 4.
- Full captured parity remains limited by available captured evidence.

## Readiness For Milestone 5

Milestone 4 is ready for review as an offline parity/evidence checkpoint. Any
Milestone 5 runtime migration must remain separately approved and must continue
to preserve the unresolved S23 PUT and S21 timing blockers.
