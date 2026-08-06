# Paper Broker Live-Paper Ingress Preflight

- provider: `fyers`
- session id: `cli-fyers-preflight`
- session date: `2026-05-08`
- local operator date: `2026-08-06`
- preflight status: `WARNING`
- can run: `true`
- uses payload fixture: `true`
- would connect to broker: `false`

## Scope Checks

- artifact root: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_run_s23_fyers_paper_ingre1\artifacts`
- artifact root writable: `true`
- strategy: `S23`
- symbol: `NIFTY`
- contract cycle: `WEEKLY`
- mode: `paper`
- paper mode enabled: `true`
- no live orders allowed: `true`
- kill switch enabled: `true`
- session kill switch active: `false`
- ingress-only mode confirmed: `true`
- fill simulation enabled: `false`
- lifecycle simulation enabled: `false`

## Market Inputs

- selected contract: `NIFTY_20260512_25000_PE`
- weekly expiry: `2026-05-12`
- subscribed symbols: `NIFTY, NIFTY_20260512_25000_PE`
- required snapshots: `0915, ORPT, RC`
- present snapshots: `0915, ORPT, RC`
- credentials present: `false`
- expected session directory: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_run_s23_fyers_paper_ingre1\artifacts\2026-05-08\cli-fyers-preflight`

## Issues

- `WARNING` `payload_fixture_mode_enabled`: Payload fixture mode is enabled; preflight is safe, but this is not a live FYERS data run.

## Safety Note

- Preflight validates S23 paper ingress safety only. It never connects to FYERS, never places orders, and never enables fill or lifecycle simulation.
- Preflight only never connects to the configured broker and never places orders.
