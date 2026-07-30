# Phase 3D Milestone 5 S23 Call Captured Evidence Summary

## Verdict

PHASE3D_M5_ACCEPT

## Objective

Strengthen the accepted S23 Bull Call and Bear Call vertical cases with checked-in workbook-derived legacy fixture provenance while preserving the accepted synthetic golden regressions.

No complete real historical Call-side evaluation packet was found. The strongest available checked-in Call-side evidence is the workbook-normalized strategy configuration plus `excel_crosscheck.yaml` samples for Bull Call and Bear Call. Both M5 fixture cases therefore improve from `SYNTHETIC_GOLDEN` to `LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT`, with all remaining synthetic supplements disclosed.

## Evidence Artifacts Searched

- Refactored repository reports, fixtures, strategy configs, reference packets, runtime fixtures, docs, and `S23Calculation/2026_06_02.txt`.
- Read-only reference repository `D:/TradingEngineTFIS` reports, fixtures, strategy configs, reference packets, runtime fixtures, docs, and `S23Calculation/2026_06_02.txt`.
- Existing Phase 2D captured shadow parity artifacts.
- Existing M3/M4 synthetic golden vertical outputs.

## Evidence Source Table

| Artifact | Date/session | Bull/Bear applicability | Captured fields | Missing fields | Trust classification | Usable without supplementation | Provenance |
| --- | --- | --- | --- | --- | --- | --- | --- |
| config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D/strategy.yaml | undated workbook-normalized config | Bull Call | strategy_code, strategy_instance_identity, monthly_status_allowed_values, option_side, entry_time, recalculation_time, minimum_oi, policy configuration identity | real trading date, captured option-chain snapshot, captured selected-contract quote, captured ORPT/RC option observations, legacy runtime decision packet | LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT | false | checked-in workbook-normalized strategy configuration |
| config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D/excel_crosscheck.yaml | undated workbook-derived sample | Bull Call | source sheet, source cells, spot references, selected-contract historical references, expected ideal premium, expected minimum premium, expected entry, expected target, expected stoploss | real trading date, captured expiry candidate list, captured strike traversal result, captured OI, captured premium, captured final decision packet | LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT | false | checked-in workbook-derived cross-check values |
| config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL/strategy.yaml | undated workbook-normalized config | Bear Call | strategy_code, strategy_instance_identity, monthly_status_allowed_values, option_side, entry_time, recalculation_time, minimum_oi, policy configuration identity | real trading date, captured option-chain snapshot, captured selected-contract quote, captured ORPT/RC option observations, legacy runtime decision packet | LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT | false | checked-in workbook-normalized strategy configuration |
| config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL/excel_crosscheck.yaml | undated workbook-derived sample | Bear Call | source sheet, source cells, spot references, selected-contract historical references, expected ideal premium, expected minimum premium, expected entry, expected target, expected stoploss | real trading date, captured expiry candidate list, captured strike traversal result, captured OI, captured premium, captured final decision packet | LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT | false | checked-in workbook-derived cross-check values |
| tests/fixtures/paper/s23_archive_ingress_dry_run.jsonl | 2026-05-08 | Bear Put only | Monthly status, ORPT/RC underlying snapshots, option chain, selected quote, trade plan | Call-side branch evidence, market structure references, option reference values | captured partial, not Call-side | false | checked-in Phase 2D captured shadow fixture |
| tests/fixtures/paper/s23_fyers_prelude.jsonl | 2026-05-08 | Bear Put only | Monthly status, ORPT/RC underlying snapshots, trade plan | Call-side branch evidence, option chain, selected quote, market structure references, option reference values | captured partial, not Call-side | false | checked-in Phase 2D prelude fixture |
| tests/fixtures/paper/tradingengine_capture_adapter/NIFTY50_option_quotes_20260527.csv | 2026-05-27 | Call quotes only, no Bull/Bear decision | CE quote rows and OI | strategy identity, Monthly Status, branch, historical references, Entry, Gap/Missed-Entry, Target, MSL, decision | captured quote fragment | false | checked-in TradingEngine capture adapter fixture |
| S23Calculation/2026_06_02.txt | 2026-06-02 | no accepted Call decision | 09:16 and 09:25 underlying/option-chain readiness notes | Monthly Status resolved branch, 09:30 decision, selected contract, Entry, Target, MSL | operational note, incomplete | false | checked-in calculation note |

## Classification

- Bull Call before: `SYNTHETIC_GOLDEN`; after: `LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT`.
- Bear Call before: `SYNTHETIC_GOLDEN`; after: `LEGACY_FIXTURE_WITH_SYNTHETIC_SUPPLEMENT`.
- Fully captured cases: 0.
- Captured with derived fields: 0.
- Captured with synthetic supplement: 0.
- Legacy fixture cases: 2.
- Synthetic-only cases: 0 in M5 fixture set; M3/M4 synthetic golden cases remain preserved as regressions.

## Bull Call Result

- Case: `s23_bull_call_workbook_fixture`.
- Deterministic hash: `4e327a977aeaad6841891b2a044155ca8a1f644c1b11a261e255252506deaa1c`.
- Selected contract: `NIFTY_20260806_22250_CALL`.
- Trade result: `TRADE`.
- Parity result: `PASSED`.

## Bear Call Result

- Case: `s23_bear_call_workbook_fixture`.
- Deterministic hash: `3a8dbc6b507ac7603f2c0a4b289f3ecf9855f17206b3d96744b3291af8f20d41`.
- Selected contract: `NIFTY_20260806_22150_CALL`.
- Trade result: `TRADE`.
- Parity result: `PASSED`.

## Field Provenance

Every required M5 field is classified in `milestone5_s23_evidence_gap_matrix.json` as one of the approved provenance values. Material captured-production gaps remain classified as `SYNTHETIC_SUPPLEMENT` or `MISSING`; no field is silently inferred.

## Synthetic Supplements

- stable evaluation timestamp
- single qualifying option-chain candidate
- selected expiry
- selected contract symbol
- selected contract OI
- selected contract premium quote
- ORPT option observation
- RC option observation

## Missing Evidence Fields

- real trading date
- captured option-chain snapshot
- captured selected-contract quote
- captured ORPT option observation
- captured RC option observation
- captured legacy runtime decision packet

## Parity

Both workbook-backed fixture cases reproduce the existing vertical output with `MATCH` classifications for compared fields. No `IMPLEMENTATION_MISMATCH` is present.

## Runtime Impact

NONE. No runtime runner, broker adapter, paper authority, live authority, capture hook, or operational timing path was modified.

## Remaining Blocker

The project still lacks a complete real historical Call-side evaluation packet for Bull Call or Bear Call. Captured parity cannot be upgraded to `FULLY_CAPTURED`, `CAPTURED_WITH_DERIVED_FIELDS`, or `CAPTURED_WITH_SYNTHETIC_SUPPLEMENT` until such evidence exists.

## Next Recommendation

Design a disabled capture hook only if existing operational archives cannot provide the missing Call-side evidence fields.
