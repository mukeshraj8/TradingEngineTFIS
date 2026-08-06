# Paper Broker Live-Paper Ingress Summary

- broker: `fyers`
- source mode: `broker_fyers_live_paper_ingress`
- session id: `cli-fyers-ingress`
- session date: `2026-05-08`
- selected contract: `NIFTY_20260512_25000_PE`
- weekly expiry: `2026-05-12`
- terminal state: `ORDER_PLANNED`
- readiness status: `READY`
- operational readiness: `PASS`

## Inputs

- config path: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_run_s23_fyers_paper_ingre0\paper.s23.yaml`
- prelude path: `D:\TradingEngineTFISRefactored\tests\fixtures\paper\s23_fyers_prelude.jsonl`
- subscribed symbols: `NIFTY, NIFTY_20260512_25000_PE`

## Outputs

- broker health: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_run_s23_fyers_paper_ingre0\artifacts\2026-05-08\cli-fyers-ingress\broker_health.json`
- normalized events: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_run_s23_fyers_paper_ingre0\artifacts\2026-05-08\cli-fyers-ingress\normalized_events.jsonl`
- selected contract audit: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_run_s23_fyers_paper_ingre0\artifacts\2026-05-08\cli-fyers-ingress\selected_contract_audit.json`
- session review: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_run_s23_fyers_paper_ingre0\artifacts\2026-05-08\cli-fyers-ingress\paper_session_review.md`
- terminal summary: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_run_s23_fyers_paper_ingre0\artifacts\2026-05-08\cli-fyers-ingress\no_trade_or_order_plan_summary.json`

## Safety Note

- Broker market-data only: no order was placed, no fill was simulated, and no lifecycle monitoring occurred.
- Kill switch is expected to remain enabled by default.
- No broker order-placement path exists in this ingress runner.
