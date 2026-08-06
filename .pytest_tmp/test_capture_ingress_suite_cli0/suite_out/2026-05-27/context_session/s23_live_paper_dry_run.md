# S23 Normalized Live-Paper Ingress Dry Run

- session id: `context_session`
- session date: `2026-05-27`
- source mode: `tradingengine_capture_plus_tfis_prelude_jsonl`
- source path: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\suite_out\2026-05-27\context_session\combined_ingress.jsonl`
- terminal state: `ORDER_PLANNED`
- readiness status: `READY`
- operational readiness: `PASS`

## Go / No-Go

- GO: normalized S23 live-paper ingress satisfied the dry-run thresholds and reached ORDER_PLANNED without fill or lifecycle execution.

## Selected Contract Audit

- symbol: `NIFTY_20260602_23200_PE`
- present in option chain: `True`
- quote present: `True`
- quote fresh at finalize: `True`

## Ingress Health Metrics

- total events: `11`
- processed events: `11`
- stale events: `0`
- late events: `0`
- missing option-chain count: `0`
- missing selected-contract count: `0`
- timezone mismatch count: `0`
- selected-contract availability ratio: `1.00`
- no-trade rate: `0.00`

## Timing Audit

- `0915` effective drift `0.0s`, arrival lag `0.0s`, within threshold `True`
- `ORPT` effective drift `0.0s`, arrival lag `0.0s`, within threshold `True`
- `RC` effective drift `0.0s`, arrival lag `0.0s`, within threshold `True`

## Reasons

- no-trade reasons: `none`
- abort reasons: `none`

## Thresholds

- max stale events: `0`
- max timing drift seconds: `5.0`
- max missing chains: `0`
- required selected-contract availability ratio: `1.00`
- max no-trade rate: `0.00`

## Review Artifacts

- review json: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\suite_out\2026-05-27\context_session\paper_session_review.json`
- review markdown: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\suite_out\2026-05-27\context_session\paper_session_review.md`
- execution summary: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\suite_out\2026-05-27\context_session\execution_summary.json`

## Safety Note

- Ingress-only dry run: no order was placed, no fill was simulated, and no lifecycle monitoring occurred.
- Same-day only.
- No real order was placed.
- No broker API was used.
