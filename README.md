# TradingEngineTFIS

TFIS is a clean Python project for workbook-backed, config-driven trading
research around the `S23` weekly NIFTY options-selling family.

This repository is intentionally separate from `TradingEngine` and
`TradingEngineProd`. It focuses on deterministic offline validation, auditable
historical research, and safe paper-trading readiness foundations without
pulling in broker or live-runtime code.

## Current Position

S23 is now in a mature offline state:

- workbook-backed strategy logic is stable
- historical backtest and comparison tooling are strong
- option-chain and contract-specific lifecycle realism are in place
- current deterministic fixture coverage for selected-contract lifecycle is
  `10 / 10` with `0` fallback
- paper trading is still explicitly `NO-GO` until runtime data contracts,
  session orchestration, journaling, failure handling, and operator controls
  are implemented

The center of gravity has shifted from formula correctness to runtime readiness
and broader real/archive data coverage.

## Scope

Current scope:

- workbook-backed TFIS strategy normalization and governance
- config-driven strategy definitions
- deterministic offline evaluation and historical backtesting
- monthly-status-driven branch selection for S23
- workbook-backed S23 recalculation and current-day overlays
- option-chain selection realism
- contract-specific lifecycle realism
- audit-first paper-trading readiness planning

Explicitly out of scope for the current implementation:

- broker integrations
- real-money live trading
- production paper runtime loop
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
- No direct broker SDK imports are allowed in TFIS core.
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
- read-only shared captured-data adapter for normalized CSV roots

Blocked or intentionally deferred:

- workbook-unconfirmed next-day continuation logic from `AB6 OS!190:191`
- unsupported current-day FSL / TRP paths that do not have confirmed workbook
  rows
- raw capture-format adapters beyond normalized CSV roots
- paper and live runtime execution layers

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
- the current matched comparison isolates one small believable lifecycle-source
  P&L delta rather than broad uncontrolled divergence

That means the remaining realism gap is primarily broader archive depth, not
core S23 logic quality.

## Paper-Trading Readiness

Current readiness disposition: `NO-GO`

Paper trading is intentionally blocked until TFIS has:

- normalized live-paper data contracts
- an S23-only session state machine
- schema validation and no-trade guards
- session manifests and paper decision journals
- operator-visible warnings and kill-switch behavior
- replayability from paper sessions back to expected S23 logic

The paper-mode blueprint docs now exist:

- [S23 Live-Paper Data Contract](docs/operations/s23_live_paper_data_contract.md)
- [S23 Paper Session State Machine](docs/operations/s23_paper_session_state_machine.md)
- [S23 Paper Trading Readiness Audit](docs/operations/s23_paper_trading_readiness_audit.md)

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

## Quality Snapshot

Current repo health:

- tests passing: `274`
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

## Next Recommended Priorities

- S23 live-paper schema scaffolding and required-field validation
- S23 paper-session orchestrator skeleton and session manifest writer
- S23 paper execution journaling and operator-facing session artifacts
- broader real/archive contract-specific coverage pilot
- raw shared capture-format adapters beyond normalized CSV roots

## Still Intentionally Pending

- workbook-unconfirmed next-day continuation logic
- broader real/archive contract-specific coverage beyond the current fixture set
- raw shared capture-format adapters beyond normalized CSV roots
- broker adapters
- paper runtime
- live runtime