# TFIS Manual Operator Guide

This guide explains how to use TFIS manually for the common S23 workflows that
exist today.

Scope of this guide:

- S23 only
- NIFTY only
- weekly options only
- historical research
- paper-mode review and replay
- ingress-only dry runs
- no live orders
- no broker order placement

## Safety First

Before running anything:

- work from `D:\TradingEngineTFIS`
- treat TFIS as paper-only and research-only
- do not add or enable any order-routing code
- do not relax current guardrails for unsupported continuation or missing OI
- do not write anything inside `D:\TradingData`

The current hard safety boundary is:

`Broker Adapter -> Normalized Market Event Layer -> TFIS Paper Engine`

S23 must consume only normalized TFIS events.

## Repo Setup

Open PowerShell and move into the repo:

```powershell
cd D:\TradingEngineTFIS
```

Useful first checks:

```powershell
python --version
git status --short
```

## Core Validation

Run these before or after meaningful work:

```powershell
python scripts/validate_strategy_configs.py
python scripts/validate_project.py
python -m pytest -q
```

If you only want the normal test sweep used in recent S23 work:

```powershell
python -m pytest tests/unit tests/architecture tests/integration -q
```

## Historical S23 Backtests

### 1. Minimal sample run

Use this to confirm a strategy loads and computes structurally:

```powershell
python scripts/run_backtest.py `
  --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D `
  --sample `
  --out tmp/S23_sample_backtest.json
```

### 2. Historical monthly-status run

```powershell
python scripts/run_backtest.py `
  --strategy-root config/strategies/options_sell/nifty `
  --use-monthly-status-engine `
  --monthly-csv tests/fixtures/backtest/s23_monthly.csv `
  --weekly-csv tests/fixtures/backtest/s23_weekly.csv `
  --daily-csv tests/fixtures/backtest/s23_daily_multi.csv `
  --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv `
  --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv `
  --historical `
  --eod-policy square_off_at_close `
  --out tmp/S23_historical_monthly_status_backtest.json `
  --markdown-out tmp/S23_historical_monthly_status_backtest.md
```

### 3. Historical recalculation run

```powershell
python scripts/run_backtest.py `
  --strategy-root config/strategies/options_sell/nifty `
  --use-monthly-status-engine `
  --monthly-csv tests/fixtures/backtest/s23_monthly.csv `
  --weekly-csv tests/fixtures/backtest/s23_weekly.csv `
  --daily-csv tests/fixtures/backtest/s23_daily_multi.csv `
  --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv `
  --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv `
  --spot-intraday-csv tests/fixtures/backtest/s23_spot_intraday.csv `
  --historical `
  --eod-policy square_off_at_close `
  --enable-s23-recalculation `
  --out tmp/S23_historical_monthly_status_recalc_backtest.json `
  --markdown-out tmp/S23_historical_monthly_status_recalc_backtest.md
```

### 4. Option-chain plus contract-specific lifecycle run

```powershell
python scripts/run_backtest.py `
  --strategy-root config/strategies/options_sell/nifty `
  --use-monthly-status-engine `
  --monthly-csv tests/fixtures/backtest/s23_monthly.csv `
  --weekly-csv tests/fixtures/backtest/s23_weekly.csv `
  --daily-csv tests/fixtures/backtest/s23_daily_multi.csv `
  --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv `
  --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv `
  --option-chain-csv tests/fixtures/backtest/s23_option_chain.csv `
  --enable-option-chain-selection `
  --contract-intraday-csv tests/fixtures/backtest/s23_contract_intraday.csv `
  --enable-contract-specific-lifecycle `
  --historical `
  --eod-policy square_off_at_close `
  --enable-s23-recalculation `
  --out tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.json `
  --markdown-out tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.md
```

## Historical Comparison Reports

Use this when you want apples-to-apples differences between S23 historical
modes:

```powershell
python scripts/compare_backtest_reports.py `
  --report base=tmp/S23_historical_backtest_costed.json `
  --report monthly_status=tmp/S23_historical_monthly_status_backtest.json `
  --report recalculation=tmp/S23_historical_monthly_status_recalc_backtest.json `
  --report current_day_fsl_trp=tmp/S23_historical_current_day_fsl_trp_backtest.json `
  --report option_chain=tmp/S23_historical_monthly_status_recalc_chain_backtest.json `
  --report contract_specific_lifecycle=tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.json `
  --max-trades 200 `
  --timeout-seconds 10 `
  --out tmp/S23_mode_comparison.json `
  --markdown-out tmp/S23_mode_comparison.md
```

## Review A Persisted Paper Session

If a paper session folder already exists, create review output like this:

```powershell
python scripts/review_paper_session.py `
  --session-dir tmp/s23_live_paper_dry_runs/2026-05-08/s23-archive-ingress-dry-run `
  --out-json tmp/paper_session_review.json `
  --out-md tmp/paper_session_review.md
```

This is the fastest way to inspect:

- terminal state
- selected contract
- guardrail results
- fill or lifecycle status if present
- no-trade or abort reason
- replay-bundle validation status

## Compare Paper Session To Historical Expectation

Use this to check whether a paper session matches historical expectation:

```powershell
python scripts/compare_paper_to_historical.py `
  --session-dir tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot `
  --historical-report tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot/historical_expectation.json `
  --out-json tmp/paper_vs_historical.json `
  --out-md tmp/paper_vs_historical.md
```

Possible high-level results:

- `MATCH`
- `MATCH_WITH_ACCEPTABLE_DRIFT`
- `PARTIAL_MATCH`
- `MISMATCH`
- `UNCOMPARABLE`

## Run An Ingress-Only Dry Run From Normalized JSONL

This is the cleanest non-broker ingress path.

```powershell
python scripts/run_s23_paper_ingress_dry_run.py `
  --events-jsonl tests/fixtures/paper/s23_archive_ingress_dry_run.jsonl `
  --artifact-root tmp/s23_live_paper_dry_runs `
  --session-id s23-archive-ingress-dry-run
```

This path must stop at:

- `ORDER_PLANNED`
- `NO_TRADE`
- `ABORTED`

It must not create:

- `paper_fill.json`
- `paper_position.json`
- `paper_exit.json`
- `paper_pnl_summary.json`

## FYERS Market-Data Ingress

The FYERS path is broker-backed for market data only.

Important:

- no order placement
- no fills by default
- no lifecycle by default
- S23 still consumes normalized TFIS events only

### 1. Safe preflight

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl tests/fixtures/paper/s23_fyers_prelude.jsonl `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-preflight `
  --preflight-only `
  --out-json tmp/s23_fyers_paper_ingress/preflight.json `
  --out-md tmp/s23_fyers_paper_ingress/preflight.md
```

This checks:

- FYERS credentials for real mode
- paper mode only
- S23 only
- NIFTY only
- weekly only
- no live orders allowed
- fill and lifecycle disabled
- writable artifact root
- valid timezone and session-date alignment

### 2. Fixture-backed smoke test

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl tests/fixtures/paper/s23_fyers_prelude.jsonl `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-fixture-smoke `
  --out-json tmp/s23_fyers_paper_ingress/fixture_smoke.json `
  --out-md tmp/s23_fyers_paper_ingress/fixture_smoke.md
```

### 3. Real market-hours ingress-only run

Before this run:

- remove or comment `broker.payload_fixture_path` in `config/paper.s23.yaml`
- export `FYERS_APP_ID`
- export `FYERS_ACCESS_TOKEN`
- use a valid prelude JSONL for the current date

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl <today-normalized-prelude.jsonl> `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-live-ingress
```

Reference:

- [s23_fyers_ingress_live_runbook.md](s23_fyers_ingress_live_runbook.md)
- [s23_operator_closeout_policy.md](s23_operator_closeout_policy.md)

## TradingEngine Capture Conversion

Use this only for read-only conversion from `D:\TradingData` into TFIS market
events.

```powershell
python scripts/convert_tradingengine_capture_to_tfis_ingress.py `
  --data-root D:\TradingData `
  --session-date 2026-05-27 `
  --out-root tmp/s23_tradingengine_capture_adapter/2026-05-27
```

Important boundary:

- converter output is written only under `tmp`
- nothing must be written back into `D:\TradingData`
- this produces market events only, not full S23 strategy context

## TradingEngine Capture Plus TFIS Prelude Ingress Suite

Use this when you want to pair capture-derived market events with TFIS prelude
inputs:

```powershell
python scripts/run_s23_tradingengine_capture_ingress_suite.py `
  --data-root D:\TradingData `
  --dates 2026-05-15,2026-05-20,2026-05-22,2026-05-25,2026-05-26,2026-05-27 `
  --out-root tmp/s23_tradingengine_capture_dry_runs
```

Current known outcome:

- the paired path is operationally read-only and deterministic
- conversion works
- prelude pairing works
- timing works
- selected-contract identity pairing works
- ingress acceptance is still `NO_GO` because selected-contract `oi` is missing
  in the quote archives

Read these before relying on that path:

- [s23_tradingengine_capture_adapter_audit.md](s23_tradingengine_capture_adapter_audit.md)
- [s23_tradingengine_capture_oi_audit.md](s23_tradingengine_capture_oi_audit.md)

## Where To Look For Outputs

Common output roots:

- historical backtests:
  - `tmp/*.json`
  - `tmp/*.md`
- paper ingress dry runs:
  - `tmp/s23_live_paper_dry_runs/<date>/<session_id>/`
- FYERS ingress runs:
  - `tmp/s23_fyers_paper_ingress/`
- paper pilots:
  - `tmp/s23_paper_pilots/<date>/<session_id>/`
- pilot suites:
  - `tmp/s23_paper_pilot_suite/<date>/<suite_id>/`
- TradingEngine capture conversion:
  - `tmp/s23_tradingengine_capture_adapter/<date>/`
- TradingEngine capture ingress suite:
  - `tmp/s23_tradingengine_capture_dry_runs/`

Key artifacts you will commonly inspect:

- `session_manifest.json`
- `audit_events.jsonl`
- `decision_summary.json`
- `paper_session_review.md`
- `paper_order_plan.json`
- `paper_order_intent.json`
- `execution_summary.json`
- `replay_bundle_manifest.json`
- `ingress_summary.json`
- `selected_contract_audit.json`
- `paper_fill.json`
- `paper_position.json`
- `paper_exit.json`
- `paper_pnl_summary.json`

## How To Interpret Session Quality

Ingress-only sessions are classified as:

- `PASS`
- `WARNING`
- `NO_GO`

Paper-vs-historical parity may classify sessions as:

- `MATCH`
- `MATCH_WITH_ACCEPTABLE_DRIFT`
- `PARTIAL_MATCH`
- `MISMATCH`
- `UNCOMPARABLE`

Use these documents for the final interpretation:

- [s23_operator_closeout_policy.md](s23_operator_closeout_policy.md)
- [s23_paper_trading_readiness_audit.md](s23_paper_trading_readiness_audit.md)

## What Not To Do

Do not:

- add broker order placement
- bypass `missing_contract_oi`
- enable next-day continuation
- write inside `D:\TradingData`
- treat TradingEngine captures as ingress-acceptance evidence until a safe OI
  source exists
- infer unsupported workbook behavior

## Practical Starting Sequence

If you are operating TFIS manually for the first time, this is the safest path:

1. Run repo validation.
2. Run one historical S23 backtest.
3. Review one existing paper session.
4. Run one normalized JSONL ingress-only dry run.
5. Run FYERS preflight only.
6. Read the close-out policy.
7. Only then attempt a real market-hours ingress-only run.
