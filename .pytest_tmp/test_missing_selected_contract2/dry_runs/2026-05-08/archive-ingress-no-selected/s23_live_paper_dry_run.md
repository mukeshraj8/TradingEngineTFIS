# S23 Normalized Live-Paper Ingress Dry Run

- session id: `archive-ingress-no-selected`
- session date: `2026-05-08`
- source mode: `normalized_archive_export_jsonl`
- source path: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_missing_selected_contract2\events.jsonl`
- terminal state: `NO_TRADE`
- readiness status: `NO_TRADE`
- operational readiness: `FAIL`

## Go / No-Go

- NO_GO: the normalized ingress dry run ended in NO_TRADE due to `missing_selected_contract_quote` before an intent-only handoff could be accepted.

## Selected Contract Audit

- symbol: `None`
- present in option chain: `False`
- quote present: `False`
- quote fresh at finalize: `None`

## Ingress Health Metrics

- total events: `10`
- processed events: `10`
- stale events: `0`
- late events: `0`
- missing option-chain count: `0`
- missing selected-contract count: `1`
- timezone mismatch count: `0`
- selected-contract availability ratio: `0.00`
- no-trade rate: `1.00`

## Timing Audit

- `0915` effective drift `0.0s`, arrival lag `1.0s`, within threshold `True`
- `ORPT` effective drift `0.0s`, arrival lag `2.0s`, within threshold `True`
- `RC` effective drift `0.0s`, arrival lag `2.0s`, within threshold `True`

## Reasons

- no-trade reasons: `missing_selected_contract_quote`
- abort reasons: `none`

## Thresholds

- max stale events: `0`
- max timing drift seconds: `5.0`
- max missing chains: `0`
- required selected-contract availability ratio: `1.00`
- max no-trade rate: `0.00`

## Review Artifacts

- review json: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_missing_selected_contract2\dry_runs\2026-05-08\archive-ingress-no-selected\paper_session_review.json`
- review markdown: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_missing_selected_contract2\dry_runs\2026-05-08\archive-ingress-no-selected\paper_session_review.md`
- execution summary: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_missing_selected_contract2\dry_runs\2026-05-08\archive-ingress-no-selected\execution_summary.json`

## Safety Note

- Ingress-only dry run: no order was placed, no fill was simulated, and no lifecycle monitoring occurred.
- Same-day only.
- No real order was placed.
- No broker API was used.
