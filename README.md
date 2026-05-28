# TradingEngineTFIS

TFIS is a clean Python project for workbook-backed, config-driven trading
research and bounded paper-trading simulation around the `S23` weekly NIFTY
options-selling family.

This repository is intentionally separate from `TradingEngine` and
`TradingEngineProd`. It focuses on deterministic offline validation, auditable
historical research, safe paper-trading foundations, and broker-agnostic
market-data ingress. It does not place live orders.

## Current Position

S23 is now mature as a workbook-backed offline research system and has a
substantial paper-trading MVP foundation.

Current status:

- workbook-backed S23 strategy logic is stable
- historical backtest, mode comparison, and provenance tooling are strong
- option-chain and contract-specific lifecycle realism are in place
- deterministic fixture-backed selected-contract lifecycle coverage is
  `10 / 10` with `0` fallback
- same-day paper fill and lifecycle simulation now exist for S23 in bounded
  paper mode
- normalized live-paper ingress-only dry runs, operator close-out policy, and
  broker-agnostic market-data ingress now exist
- FYERS is the first market-data adapter, but order placement remains blocked
- TradingEngine capture conversion and ingress-only pairing now exist, but that
  path is currently `NO_GO` for ingress acceptance because selected-contract
  `oi` is unavailable at decision time
- current operational disposition is:
  - archive-backed paper lifecycle validation: `LIMITED_GO`
  - ingress-only validation: `LIMITED_GO`
  - broad live-paper rollout: `NO_GO`

The center of gravity has shifted from formula correctness to operational
readiness, ingress confidence, and broader real/archive data coverage.

## Scope

Current scope:

- workbook-backed TFIS strategy normalization and governance
- config-driven strategy definitions
- deterministic offline evaluation and historical backtesting
- monthly-status-driven branch selection for S23
- workbook-backed S23 recalculation and current-day overlays
- option-chain selection realism
- contract-specific lifecycle realism
- S23-only paper-trading simulation and operator workflow scaffolding
- broker-agnostic market-data adapters and ingress-only paper dry runs

Explicitly out of scope for the current implementation:

- real-money live trading
- broker order placement
- broker-connected fill or lifecycle execution
- non-S23 strategy expansion
- unsupported workbook-path inference

## Runtime Direction

The intended workflow remains:

1. Excel workbook is the source specification for strategy rules.
2. Workbook logic is normalized into YAML, JSON, or other explicit artifacts.
3. TFIS consumes the normalized artifacts plus market data inputs.
4. Research, backtesting, and later paper-mode orchestration stay config-driven
   and auditable instead of Excel-coupled or broker-coupled.

## Core Architecture Rules

- TFIS stays separate from `TradingEngine` and `TradingEngineProd`.
- Excel is the source specification for workbook-backed rules.
- Runtime uses normalized artifacts, not direct fragile Excel access.
- Strategy, rule, market-data, lifecycle, and scheduler modules remain
  broker-agnostic.
- S23 must consume only normalized TFIS events, never raw broker payloads.
- No direct broker SDK imports are allowed in TFIS core strategy logic.
- Unsupported workbook paths must be blocked explicitly, not guessed.
- Reference materials and neighboring engine artifacts are evidence, not
  automatic executable specs.

## Current S23 Status

Implemented and stable today:

- all four canonical S23 branches are represented and validated
- monthly-status thresholds, decision-table grounding, and deterministic monthly
  status engine
- optional monthly-status-driven historical branch selection
- ORPT missed-entry detection and opt-in recalculation
- spot intraday sourcing for opt-in recalculation with explicit fallback audit
- workbook-backed current-day `FSL / TRP missed / not-missed` handling for the
  confirmed `AB6 OS` rows `183-188`
- workbook-backed current-day option-entry overrides from `AB6 OS!Z183:Z186`
  for supported rows `183-186`
- option-chain contract selection realism with spread, OI, and premium-aware
  ranking
- contract-specific lifecycle pricing with explicit provenance
- expiry-day lifecycle review and no-rollover governance for S23 options
- bounded apples-to-apples comparison reporting across historical modes
- broker-agnostic live-paper ingress foundation with FYERS as the first
  market-data adapter
- explicit FYERS ingress preflight-only safety path and market-hours runbook
- read-only TradingEngine capture-session audit, market-event converter, and
  paired TFIS-prelude ingress-only suite
- TradingEngine capture OI audit proving the current raw-capture ingress path
  is `NO_GO` for acceptance because selected-contract `oi` is missing at
  decision time
- S23 paper schema, validation, orchestrator, persistent artifacts, replay
  bundles, review surfaces, order-intent journaling, and guardrails
- S23 paper fillless execution shell through
  `PAPER_EXECUTION_HANDOFF_READY`
- S23 paper Phase 1 fill simulation through:
  - `PAPER_ORDER_PENDING`
  - `PAPER_ORDER_FILLED`
  - `PAPER_ORDER_NOT_FILLED`
  - `PAPER_FILL_ABORTED`
- S23 paper Phase 2 same-day lifecycle through:
  - `PAPER_POSITION_OPEN`
  - `PAPER_EXIT_PENDING`
  - `PAPER_POSITION_CLOSED`
  - `PAPER_EOD_SQUARE_OFF`
  - `PAPER_LIFECYCLE_ABORTED`
- lifecycle-aware paper-vs-historical parity comparison with:
  - `MATCH`
  - `MATCH_WITH_ACCEPTABLE_DRIFT`
  - `PARTIAL_MATCH`
  - `MISMATCH`
  - `UNCOMPARABLE`
- archive-backed S23 lifecycle pilot suite with a current recommendation of
  `LIMITED_GO`
- normalized live-paper ingress-only dry runs and broadened ingress suite with
  explicit `PASS / WARNING / NO_GO` operator classification

Blocked or intentionally deferred:

- workbook-unconfirmed next-day continuation logic from `AB6 OS!190:191`
- unsupported current-day FSL / TRP paths that do not have confirmed workbook
  rows
- broker order placement and real-money execution
- next-day continuation
- multi-position handling
- non-S23 live-paper expansion

## Historical Research Capabilities

Current offline TFIS flow supports:

- `StrategyRule + MarketLevels + runtime values -> TradePlan`
- `TradePlan -> lifecycle backtest outcome`
- sample-mode structural checks
- CSV-driven historical backtests
- monthly-status-driven branch selection
- ORPT missed-entry recalculation overlays
- current-day FSL / TRP overlays
- option-chain contract selection inside computed strike ranges
- contract-specific lifecycle pricing from symbol-keyed intraday bars
- report comparison across historical modes

Historical reports can now include:

- monthly-status result and branch-selection context
- base trade plan versus recalculated effective trade plan
- current-day FSL / TRP workbook row and override provenance
- selected contract metadata and rejection reasons
- contract-specific lifecycle provenance and fallback reasons
- expiry-day compliance review

## S23 Lifecycle Realism

Lifecycle realism is now measurable instead of implicit:

- deterministic fixture-backed lifecycle coverage is `100.0%`
- normalized apples-to-apples comparison for lifecycle-source impact is in place
- the matched comparison isolates small believable lifecycle-source deltas
  instead of broad uncontrolled divergence

That means the remaining realism gap is primarily broader archive depth, not
core S23 logic quality.

## Paper-Trading Readiness

Current readiness disposition:

- archive-backed same-day lifecycle pilot suite: `LIMITED_GO`
- ingress-only operator close-out gate: `LIMITED_GO`
- broad live-paper rollout: `NO_GO`

What now exists in paper mode:

- normalized paper-event schema and validation
- deterministic S23 session orchestrator
- persistent manifests, audit trails, replay bundles, and review summaries
- order-intent, arming, dispatch, and final no-fill handoff shell
- same-day paper fill/no-fill simulation
- same-day paper lifecycle simulation and paper P&L summaries
- paper-vs-historical planning and lifecycle parity comparison
- ingress-only dry-run validation with explicit timing and freshness metrics
- operator close-out policy for `PASS`, `WARNING`, and `NO_GO`
- broker-backed normalized ingress via FYERS market-data mapping
- TradingEngine capture-derived market-event conversion and ingress-only suite
- capture-path OI evidence and acceptance blocker audit

What is still intentionally blocking broad rollout:

- broader multi-date ingress-only evidence
- controlled live-like rehearsal evidence beyond the current archive-derived set
- broker order-routing remains disabled
- next-day continuation remains unsupported

The core paper-mode docs now include:

- [S23 Live-Paper Data Contract](docs/operations/s23_live_paper_data_contract.md)
- [S23 Paper Session State Machine](docs/operations/s23_paper_session_state_machine.md)
- [S23 Paper Trading Readiness Audit](docs/operations/s23_paper_trading_readiness_audit.md)
- [S23 Operator Close-Out Policy](docs/operations/s23_operator_closeout_policy.md)
- [S23 Paper Trading MVP v1 Design](docs/operations/s23_paper_trading_mvp_v1_design.md)
- [S23 FYERS Ingress Live Runbook](docs/operations/s23_fyers_ingress_live_runbook.md)
- [TFIS Manual Operator Guide](docs/operations/tfis_manual_operator_guide.md)

## Strategy Configuration Layout

TFIS uses a folder-oriented strategy layout so logic, parameters, and workbook
cross-check context stay reviewable.

Preferred strategy layout:

- `strategy.yaml` for identity and metadata
- `formulas.yaml` for rule logic
- `parameters.yaml` for tunable numeric inputs
- `notes.md` for workbook source notes and branch context
- `excel_crosscheck.yaml` for source cells and expected sample outputs

Legacy single-file strategy YAML remains supported during transition, but
folder-based strategies are the accepted path for serious backtesting.

## Documentation

The documentation hub is [docs/README.md](docs/README.md).

Key operations and S23 docs:

- [Current State](docs/operations/current_state.md)
- [Next Steps](docs/operations/next_steps.md)
- [Milestones](docs/operations/milestones.md)
- [Project Rulebook](docs/operations/project_rulebook.md)
- [S23 Gap Recalculation Design](docs/strategy/s23_gap_recalculation_design.md)
- [S23 Contract Archive Ingestion Plan](docs/strategy/s23_contract_archive_ingestion_plan.md)
- [S23 Live-Paper Data Contract](docs/operations/s23_live_paper_data_contract.md)
- [S23 Paper Session State Machine](docs/operations/s23_paper_session_state_machine.md)
- [S23 Paper Trading Readiness Audit](docs/operations/s23_paper_trading_readiness_audit.md)
- [S23 Operator Close-Out Policy](docs/operations/s23_operator_closeout_policy.md)
- [S23 Paper Trading MVP v1 Design](docs/operations/s23_paper_trading_mvp_v1_design.md)
- [S23 FYERS Ingress Live Runbook](docs/operations/s23_fyers_ingress_live_runbook.md)
- [S23 TradingEngine Capture Adapter Audit](docs/operations/s23_tradingengine_capture_adapter_audit.md)
- [S23 TradingEngine Capture OI Audit](docs/operations/s23_tradingengine_capture_oi_audit.md)
- [TFIS Manual Operator Guide](docs/operations/tfis_manual_operator_guide.md)

## Quality Snapshot

Current repo health:

- tests passing: `426`
- `python scripts/validate_project.py`: passed

## Representative Commands

Validation:

```powershell
python scripts/validate_strategy_configs.py
python scripts/validate_project.py
python -m pytest -q
```

Historical S23 backtests:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --sample --out tmp/S23_sample_backtest.json

python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --historical --eod-policy square_off_at_close --out tmp/S23_historical_monthly_status_backtest.json --markdown-out tmp/S23_historical_monthly_status_backtest.md

python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --spot-intraday-csv tests/fixtures/backtest/s23_spot_intraday.csv --historical --eod-policy square_off_at_close --enable-s23-recalculation --out tmp/S23_historical_monthly_status_recalc_backtest.json --markdown-out tmp/S23_historical_monthly_status_recalc_backtest.md

python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --option-chain-csv tests/fixtures/backtest/s23_option_chain.csv --enable-option-chain-selection --contract-intraday-csv tests/fixtures/backtest/s23_contract_intraday.csv --enable-contract-specific-lifecycle --historical --eod-policy square_off_at_close --enable-s23-recalculation --out tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.json --markdown-out tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.md
```

Mode comparison:

```powershell
python scripts/compare_backtest_reports.py --report base=tmp/S23_historical_backtest_costed.json --report monthly_status=tmp/S23_historical_monthly_status_backtest.json --report recalculation=tmp/S23_historical_monthly_status_recalc_backtest.json --report current_day_fsl_trp=tmp/S23_historical_current_day_fsl_trp_backtest.json --report option_chain=tmp/S23_historical_monthly_status_recalc_chain_backtest.json --report contract_specific_lifecycle=tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.json --max-trades 200 --timeout-seconds 10 --out tmp/S23_mode_comparison.json --markdown-out tmp/S23_mode_comparison.md
```

Paper review and parity:

```powershell
python scripts/review_paper_session.py --session-dir tmp/s23_live_paper_dry_runs/2026-05-08/s23-archive-ingress-dry-run --out-json tmp/paper_session_review.json --out-md tmp/paper_session_review.md

python scripts/compare_paper_to_historical.py --session-dir tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot --historical-report tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot/historical_expectation.json --out-json tmp/paper_vs_historical.json --out-md tmp/paper_vs_historical.md
```

Ingress-only dry run from normalized JSONL:

```powershell
python scripts/run_s23_paper_ingress_dry_run.py --events-jsonl tests/fixtures/paper/s23_archive_ingress_dry_run.jsonl --artifact-root tmp/s23_live_paper_dry_runs --session-id s23-archive-ingress-dry-run
```

FYERS preflight and live ingress-only safety run:

```powershell
python scripts/run_s23_fyers_paper_ingress.py --config config/paper.s23.yaml --prelude-jsonl tests/fixtures/paper/s23_fyers_prelude.jsonl --artifact-root tmp/s23_fyers_paper_ingress --session-id s23-fyers-preflight --preflight-only --out-json tmp/s23_fyers_paper_ingress/preflight.json --out-md tmp/s23_fyers_paper_ingress/preflight.md

python scripts/run_s23_fyers_paper_ingress.py --config config/paper.s23.yaml --prelude-jsonl <today-normalized-prelude.jsonl> --artifact-root tmp/s23_fyers_paper_ingress --session-id s23-fyers-live-ingress
```

TradingEngine capture conversion and ingress-only suite:

```powershell
python scripts/convert_tradingengine_capture_to_tfis_ingress.py --data-root D:\TradingData --session-date 2026-05-27 --out-root tmp/s23_tradingengine_capture_adapter/2026-05-27

python scripts/run_s23_tradingengine_capture_ingress_suite.py --data-root D:\TradingData --dates 2026-05-15,2026-05-20,2026-05-22,2026-05-25,2026-05-26,2026-05-27 --out-root tmp/s23_tradingengine_capture_dry_runs
```

## Next Recommended Priorities

- decide whether TradingEngine captures can be enriched with reliable
  selected-contract `oi` before treating that path as ingress-acceptance
  evidence
- broaden broker-backed multi-date ingress-only validation before enabling any
  controlled live-like fill or lifecycle rehearsal
- run the first real local FYERS market-hours ingress-only session under the
  preflight runbook
- widen real/archive contract-specific coverage beyond the current deterministic
  fixture and single-date ingress baselines

## Still Intentionally Pending

- workbook-unconfirmed next-day continuation logic
- broader real/archive contract-specific coverage beyond the current fixture set
- broker order-routing and real-money execution
- next-day continuation
- multi-position paper/live runtime
