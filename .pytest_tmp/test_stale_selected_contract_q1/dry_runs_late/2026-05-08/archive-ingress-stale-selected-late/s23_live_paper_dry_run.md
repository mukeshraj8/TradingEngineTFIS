# S23 Normalized Live-Paper Ingress Dry Run

- session id: `archive-ingress-stale-selected-late`
- session date: `2026-05-08`
- source mode: `normalized_archive_export_jsonl`
- source path: `D:\TradingEngineTFISRefactored\tests\fixtures\paper\s23_archive_ingress_dry_run.jsonl`
- terminal state: `NO_TRADE`
- readiness status: `NO_TRADE`
- operational readiness: `FAIL`

## Go / No-Go

- NO_GO: the normalized ingress dry run ended in NO_TRADE due to `stale_underlying_quote` before an intent-only handoff could be accepted.

## Selected Contract Audit

- symbol: `NIFTY_20260512_25000_PE`
- present in option chain: `True`
- quote present: `True`
- quote fresh at finalize: `False`

## Ingress Health Metrics

- total events: `11`
- processed events: `11`
- stale events: `2`
- late events: `0`
- missing option-chain count: `0`
- missing selected-contract count: `0`
- timezone mismatch count: `0`
- selected-contract availability ratio: `1.00`
- no-trade rate: `1.00`

## Timing Audit

- `0915` effective drift `0.0s`, arrival lag `1.0s`, within threshold `True`
- `ORPT` effective drift `0.0s`, arrival lag `2.0s`, within threshold `True`
- `RC` effective drift `0.0s`, arrival lag `2.0s`, within threshold `True`

## Reasons

- no-trade reasons: `stale_underlying_quote, stale_selected_contract_quote`
- abort reasons: `none`

## Thresholds

- max stale events: `0`
- max timing drift seconds: `5.0`
- max missing chains: `0`
- required selected-contract availability ratio: `1.00`
- max no-trade rate: `0.00`

## Review Artifacts

- review json: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_stale_selected_contract_q1\dry_runs_late\2026-05-08\archive-ingress-stale-selected-late\paper_session_review.json`
- review markdown: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_stale_selected_contract_q1\dry_runs_late\2026-05-08\archive-ingress-stale-selected-late\paper_session_review.md`
- execution summary: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_stale_selected_contract_q1\dry_runs_late\2026-05-08\archive-ingress-stale-selected-late\execution_summary.json`

## Safety Note

- Ingress-only dry run: no order was placed, no fill was simulated, and no lifecycle monitoring occurred.
- Same-day only.
- No real order was placed.
- No broker API was used.
