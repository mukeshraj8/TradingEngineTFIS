# TFIS Phase 2D Captured Shadow Parity

Date: 2026-07-29

## Purpose

Phase 2D adds an offline captured-data shadow comparison pipeline for the
existing S21/S23 legacy-policy adapter boundary. It evaluates repository saved
evidence through:

1. a read-only legacy observation path, preserving captured trade-plan output
   and using the current legacy option-chain selector when captured chain data
   is present
2. `TFISRuntimeInput -> TFISDecisionEngine -> legacy S21/S23 policy adapters`

No paper, live, replay, backtest, broker, lifecycle, persistence, dashboard, or
scheduled runtime caller is activated through the generic engine.

## Implementation

The Phase 2D code lives in
`src/tfis/adapters/legacy_policies/captured_shadow.py`.

It provides:

- immutable `CapturedDecisionCase`
- captured evidence inventory rows
- deterministic JSONL importer for the fixture formats present in the repo
- offline-only `LegacyDecisionObservation`
- generic evaluation through existing policy composition and adapters
- field-level comparator with mismatch taxonomy
- deterministic JSON, CSV, and Markdown report generation

The report runner is
`scripts/run_phase2d_captured_shadow_parity.py`.

## Evidence Inventory

Repository evidence reviewed by the pipeline includes:

| Path | Format | Classification | Strategy/Branch | Completeness |
| --- | --- | --- | --- | --- |
| `tests/fixtures/paper/s23_archive_ingress_dry_run.jsonl` | JSONL | captured | S23 / `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT` | partial |
| `tests/fixtures/paper/s23_fyers_prelude.jsonl` | JSONL | captured | S23 / `NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT` | partial |
| `config/reference_packets/s23_bear_put_live_decision_reference.json` | JSON | reference packet | S23 / Bear Put | not a captured event stream |
| `config/reference_packets/s21_banknifty_monthly_live_decision_reference.json` | JSON | reference packet | S21 | not a captured event stream |
| `config/runtime_fixtures/s23_bear_put_live_smoke_fixture.json` | JSON | runtime fixture | S23 | not a captured event stream |

The inventory function also records other repo JSON/JSONL fixture artifacts, but
only the two S23 paper JSONL streams currently contain the captured prelude
schema needed by Phase 2D.

## Capture Quality

Capture categories:

- `FULL_CAPTURED_PARITY`: all required evidence is captured, including raw
  market-structure references and option reference values used by formulas
- `PARTIAL_CAPTURED_PARITY`: captured evidence exists but cannot reproduce the
  complete decision without missing inputs
- `CAPTURED_WITH_SYNTHETIC_SUPPLEMENT`: captured evidence plus explicitly
  labelled synthetic supplement
- `SYNTHETIC_PARITY`: synthetic branch parity, used by Phase 2B/2C but not by
  this captured report
- `UNSUPPORTED`: evidence cannot be parsed safely

Current Phase 2D report counts:

- total cases: 2
- full captured cases: 0
- partial captured cases: 2
- synthetic cases: 0
- passed cases: 0
- mismatched cases: 2
- unsupported cases: 0

## Importer Schema

The JSONL importer requires each row to preserve:

- `event_type`
- `session_date`
- `effective_timestamp`
- `captured_at`
- `timezone`
- `source_type`
- `source_id`
- `synthetic_fixture`
- `normalized_by`
- object `payload`

Mandatory case events are:

- `MONTHLY_STATUS_INPUT`
- `TRADE_PLAN_INPUT`

Optional but completeness-relevant events are:

- `UNDERLYING_SNAPSHOT` with `ORPT` and `RC`
- `OPTION_CHAIN_SNAPSHOT`
- `SELECTED_CONTRACT_QUOTE`
- raw `market_structure_references`
- raw `option_reference_values`

The importer preserves `null` separately from `0`, preserves timestamps and
source identifiers, orders deterministically by source sequence, and raises
`ValueError` on malformed mandatory schema.

## Evaluation Flow

```text
Captured JSONL
  -> CapturedDecisionCase
  -> LegacyDecisionObservation
  -> TFISRuntimeInput
  -> TFISDecisionEngine + external S23 policy composition
  -> TFISDecision
  -> Captured field comparator
  -> JSON / CSV / Markdown reports
```

For `s23_archive_ingress_dry_run.jsonl`, the legacy observation can run current
contract-selection logic against the captured option-chain snapshot. It still
cannot reproduce formulas because the capture does not include raw
market-structure and option reference values.

For `s23_fyers_prelude.jsonl`, the case lacks option-chain snapshot and
selected-contract quote evidence, so contract-selection parity is also partial.

## Parity Fields

The comparator records:

- case id
- evaluation timestamp
- strategy instance and branch
- monthly status
- trade/no-trade result
- product type
- direction
- BUY/SELL side
- entry
- gap state
- missed-entry/recalculation result
- expiry
- strike
- premium/LTP
- OI
- target sequence
- MSL
- lots
- quantity
- final decision reason
- formula references
- requirement references
- selected policy keys
- evidence completeness

## Mismatch Taxonomy

Supported mismatch classifications are:

- `IMPORTER_GAP`
- `LEGACY_REPRODUCTION_GAP`
- `ADAPTER_DEFECT`
- `GENERIC_MODEL_GAP`
- `FORMULA_DIFFERENCE`
- `TIMING_DIFFERENCE`
- `DATA_QUALITY_DIFFERENCE`
- `WORKBOOK_VERIFICATION_REQUIRED`
- `INSUFFICIENT_CAPTURED_EVIDENCE`

Current generated reports classify mismatches primarily as
`LEGACY_REPRODUCTION_GAP`, `TIMING_DIFFERENCE`, `GENERIC_MODEL_GAP`, and
`INSUFFICIENT_CAPTURED_EVIDENCE`.

## Reports

Generated reports:

- `reports/phase2d/captured_shadow_parity.json`
- `reports/phase2d/captured_shadow_parity_fields.csv`
- `reports/phase2d/captured_shadow_parity_summary.md`

Reports are deterministic when generated with the fixed Phase 2D timestamp used
by the runner.

## Limitations

- No current captured fixture contains raw `market_structure_references` and
  `option_reference_values`; the generic entry adapter therefore fails closed at
  formula evaluation with missing `PRV_3DHH` evidence.
- `s23_fyers_prelude.jsonl` lacks option-chain and selected-contract quote
  evidence.
- `s23_archive_ingress_dry_run.jsonl` includes option-chain evidence, but the
  captured selected quote has OI below the configured current minimum OI, so it
  should be treated as captured output evidence rather than proof of full
  selector parity.
- S21 has no captured end-to-end decision JSONL fixture in this repo.
- No synthetic supplement was added in Phase 2D.

## Runtime Shadow Readiness

Verdict: `PHASE_2D_CONDITIONAL`.

The offline pipeline is implemented and deterministic, but Phase 2E runtime
shadow mode is not ready. Before runtime shadow mode, TFIS needs captured
decision evidence that includes raw formula inputs, option reference values,
ORPT/RC timing outcome, option-chain snapshot, selected-contract quote, target,
MSL, and final legacy decision for at least the operational S23 branch under
review. S21 needs its own captured decision evidence before any S21 runtime
shadow readiness claim.
