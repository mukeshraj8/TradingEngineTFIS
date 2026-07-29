# TFIS Phase 2D.1 Decision Evidence Packet

Date: 2026-07-29

## Purpose

Phase 2D.1 adds a complete immutable `TFISDecisionEvidencePacket` contract and
offline packet-production framework. The packet is designed to hold enough
correlated evidence to reproduce one decision through both:

1. the existing legacy S21/S23 calculation path
2. `TFISDecisionEngine` with existing legacy policy adapters

No packet capture is activated in paper, live, replay, backtest, broker,
lifecycle, dashboard, persistence, or scheduled runtime paths.

## Schema

The product-neutral contract lives in `src/tfis/domain/decision_evidence.py`.
It contains typed immutable sections:

- `IdentityEvidence`: schema version, packet id, evaluation id, strategy
  identity, configuration version/hash, trading date, event time, evaluation
  time, and processing time
- `SessionEvidence`: exchange, segment, timezone, market window, ORPT time, RC
  time, trigger, and reason
- `InstrumentProductEvidence`: underlying, price source, product type,
  contract identity when applicable, expiry, rollover context, and availability
- `MonthlyStatusEvidence`: previous and resolved status, PMH/PML, PWH/PWL,
  CWH/CWL, CMH/CML, a/b/c parameters, transition condition, reason, and quality
- `MarketStructureEvidence`: PRV 1D/2D/3D/4D HH/LL, included candle dates,
  current-day high/low, source contract, quality, and provenance
- `PriceContextEvidence`: CMP, source, event timestamp, freshness, bid, ask,
  and LTP
- `GapMissedEntryEvidence`: opening/reference price, ORPT and RC observations,
  gap classification, missed-entry classification, recalculation branch,
  formulas, and intermediate values
- `OptionProductReferenceEvidence`: option formula references, expiry
  candidates, strike range, premium range, minimum OI, and expiry-search count
- `OptionChainEvidence`: complete candidate set considered, quote details,
  quality, freshness, and rejected-candidate counts
- `SelectedContractEvidence`: selected identity, selected quote, selection
  reason, and rejected candidate reasons
- `CalculatedDecisionEvidence`: entry, targets, MSL, TSL/APS as explicit
  `NOT_APPLICABLE` when absent, lots, quantity, direction, execution side,
  trade/no-trade result, and final reason
- `AuditEvidence`: policy keys, requirement ids, formula expressions,
  intermediate values, data-quality warnings, evidence classifications, and
  compatibility payload

`ProvenancedValue` preserves decimal values, `null` versus zero, unavailable
versus not applicable, and captured/imported/derived/synthetic provenance.

## Provenance Model

Core provenance values:

- `CAPTURED`: observed in a saved runtime/capture artifact
- `IMPORTED`: read from a deterministic fixture or reference artifact
- `DERIVED`: calculated from packet-local evidence
- `SYNTHETIC`: supplied by a deterministic golden fixture
- `NOT_APPLICABLE`: product/stage field is irrelevant for this packet

Product-specific sections remain optional by availability. For example, option
chain evidence is `NOT_APPLICABLE` for a future/equity packet, `UNAVAILABLE`
for an incomplete option packet, and `AVAILABLE` only when the candidate set is
present.

## Completeness Criteria

`validate_decision_evidence_packet()` classifies packets as:

- `FULL_DECISION_EVIDENCE`: packet can reproduce the complete decision without
  external lookup
- `PARTIAL_DECISION_EVIDENCE`: packet is valid but lacks one or more required
  reproducibility inputs
- `CAPTURED_WITH_SYNTHETIC_SUPPLEMENT`: captured packet includes an explicitly
  labelled synthetic supplement
- `INVALID_DECISION_EVIDENCE`: packet is internally inconsistent or unsafe to
  compare

Validator checks include:

- missing mandatory fields
- segment/product identity mismatch
- missing formula inputs
- missing ORPT/RC evidence
- incomplete option-chain evidence
- selected contract absent from candidate set
- invalid timestamp ordering
- missing final legacy decision
- data-quality warnings carried in audit evidence

A packet is full only when it contains formula inputs, Monthly Status evidence,
ORPT/RC evidence, option/product references, option-chain candidates, selected
contract quote, target/MSL, and final decision output in the same packet.

## Offline Producers

The legacy-specific producers live in
`src/tfis/adapters/legacy_policies/decision_packet.py`.

Current producers:

- `build_s23_synthetic_golden_packet()`: complete deterministic S23 Bear Put
  packet labelled `SYNTHETIC_GOLDEN`
- `packet_from_captured_case()`: converts a Phase 2D captured case to a partial
  packet while preserving missing fields as unavailable
- `captured_cases_to_packets()`: imports the existing captured S23 JSONL
  fixtures into packets

The producer records whether each value was captured or synthetic. It does not
fabricate missing captured fields or label synthetic evidence as captured.

## Reproduction Flow

```text
TFISDecisionEvidencePacket
  -> validator
  -> legacy StrategyEvaluator + current selector
  -> TFISRuntimeInput
  -> TFISDecisionEngine + existing S21/S23 policy adapters
  -> field-level parity result
```

For full packets, both legacy and generic paths are evaluated. For partial
packets, the harness reports the exact missing dependencies and avoids claiming
complete decision parity.

## Synthetic Golden Result

`reports/phase2d1/s23_synthetic_golden_packet.json` is a complete S23 Bear Put
golden packet.

Generated result:

- completeness: `FULL_DECISION_EVIDENCE`
- parity passed: yes
- mismatches: 0
- selected strike: `22350`
- entry: `203.5`
- target: `81.4`
- MSL: `321.0`

The golden packet demonstrates that the contract can represent enough evidence
to reproduce both legacy and generic decisions without external lookup.

## Captured Packet Results

Existing captured fixtures remain partial:

| Packet | Classification | Missing dependencies |
| --- | --- | --- |
| `s23_archive_ingress_dry_run` | `PARTIAL_DECISION_EVIDENCE` | raw market-structure formula inputs and option reference values |
| `s23_fyers_prelude` | `PARTIAL_DECISION_EVIDENCE` | raw formula inputs, option-chain evidence, selected-contract quote |

## Performance Measurements

Measured by `scripts/run_phase2d1_decision_evidence_packet_report.py` on
2026-07-29:

| Packet | Size bytes | Serialize s | Deserialize s | Validate s | Parity s | Candidates | Scale risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| archive partial | 9276 | 0.0018397 | 0.0007100 | 0.0002610 | 0.0002307 | 1 | LOW |
| prelude partial | 7154 | 0.0011253 | 0.0004302 | 0.0000298 | 0.0000274 | 0 | LOW |
| S23 synthetic golden | 11020 | 0.0020307 | 0.0010266 | 0.0003054 | 0.0276947 | 1 | LOW |

Obvious scale risk: large option-chain candidate sets will dominate packet
size. The current scale-risk marker becomes moderate above 100 candidates and
high above 500 candidates.

## Security and Data Retention

Decision packets should not include broker tokens, account secrets, OAuth
tokens, or operator credentials. Packet retention should follow the same
strategy/date partitioning as paper evidence and should avoid sibling project
paths. If packets are captured later from a reference implementation, store
only normalized market/decision evidence needed for replay and audit.

## Proposed Reference Capture Points

Do not modify `D:\TradingEngineTFIS` until reviewed. Minimal additive
post-market capture points in that reference implementation would be:

1. immediately after Monthly Status resolution, emit status, thresholds,
   transition reason, and quality
2. immediately after market-structure preparation, emit PRV 1D/2D/3D/4D HH/LL,
   included candle dates, current-day high/low, and source identity
3. immediately after ORPT and RC snapshots are finalized, emit timing evidence,
   gap/missed-entry classification, and recalculation branch
4. immediately before option-chain selection, emit option formula references,
   expiry candidates, strike range, premium range, and minimum OI
5. immediately after option-chain selection, emit complete candidate set,
   rejected reasons, selected identity, selected quote, and selection reason
6. immediately after final legacy decision, emit entry, target, MSL, lots,
   quantity, direction, side, trade/no-trade, final reason, formula references,
   and requirement ids

These should be post-market or dry-run reviewed first and remain disabled for
live runtime until packet reports show full captured parity.

## Rollout and Rollback

Rollout plan:

1. generate packets offline from existing fixtures
2. add a disabled capture flag in the reference implementation only after
   review
3. run post-market packet capture for one S23 decision
4. validate packet classification and parity offline in TFISRefactored
5. expand to more dates/branches only after full packet quality is stable

Rollback plan:

- disable the capture flag
- delete only newly generated packet artifacts for the affected run
- keep existing runtime decision flow unchanged
- continue using the Phase 2D.1 offline golden packet for contract regression

## Phase 2E Readiness

Verdict: `PHASE_2D1_ACCEPT` for the offline packet contract and synthetic
golden proof.

Phase 2E runtime shadow mode remains deferred until real captured packets reach
`FULL_DECISION_EVIDENCE` and pass complete parity for the operational S23 path.
