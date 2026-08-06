# S23 Normalized Live-Paper Ingress Dry Run

- session id: `stale-selected-quote`
- session date: `2026-05-08`
- source mode: `broker_fyers_live_paper_ingress`
- source path: `D:\TradingEngineTFISRefactored\tests\fixtures\paper\s23_fyers_prelude.jsonl`
- terminal state: `ABORTED`
- readiness status: `ABORTED`
- operational readiness: `FAIL`

## Go / No-Go

- NO_GO: the normalized ingress dry run aborted due to `stale_ingest_quote` before an intent-only handoff could be accepted.

## Selected Contract Audit

- symbol: `NIFTY_20260512_25000_PE`
- present in option chain: `False`
- quote present: `True`
- quote fresh at finalize: `False`

## Ingress Health Metrics

- total events: `11`
- processed events: `9`
- stale events: `2`
- late events: `1`
- missing option-chain count: `0`
- missing selected-contract count: `0`
- timezone mismatch count: `0`
- selected-contract availability ratio: `1.00`
- no-trade rate: `0.00`

## Timing Audit

- `0915` effective drift `0.0s`, arrival lag `1.0s`, within threshold `True`
- `ORPT` effective drift `0.0s`, arrival lag `2.0s`, within threshold `True`
- `RC` effective drift `0.0s`, arrival lag `2.0s`, within threshold `True`

## Reasons

- no-trade reasons: `none`
- abort reasons: `stale_ingest_quote`

## Thresholds

- max stale events: `0`
- max timing drift seconds: `5.0`
- max missing chains: `0`
- required selected-contract availability ratio: `1.00`
- max no-trade rate: `0.00`

## Review Artifacts

- review json: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_stale_selected_contract_q0\artifacts\2026-05-08\stale-selected-quote\paper_session_review.json`
- review markdown: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_stale_selected_contract_q0\artifacts\2026-05-08\stale-selected-quote\paper_session_review.md`
- execution summary: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_stale_selected_contract_q0\artifacts\2026-05-08\stale-selected-quote\execution_summary.json`

## Safety Note

- Ingress-only dry run: no order was placed, no fill was simulated, and no lifecycle monitoring occurred.
- Same-day only.
- No real order was placed.
- Broker market-data source used: `broker_fyers_live_paper_ingress`.
