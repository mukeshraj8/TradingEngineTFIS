# TradingEngineTFIS

A clean Python project for a lightweight TFIS rule-based trading engine.

This repository is intentionally separate from `TradingEngine` and `TradingEngineProd`. It is a fresh starting point for building a config-driven rule engine around TFIS concepts without copying existing runtime, broker, scoring, dashboard, or replay code.

## Scope

Current scope:
- define and document a clean TFIS rule-engine core
- support config-driven strategy definitions
- validate strategy configs against workbook-derived metadata
- run deterministic offline evaluation, backtests, and parameter sweeps
- prepare Excel-to-config import tooling without coupling runtime to Excel

Explicitly out of scope for this initial version:
- live trading
- broker integrations
- FYERS or other exchange adapters
- dashboards
- replay certification
- current-engine scoring logic

## Runtime Direction

The intended workflow is:
1. Excel workbook acts as the source specification for formulas and rules.
2. A normalization step exports YAML or JSON artifacts.
3. The TFIS engine consumes those normalized artifacts at runtime.
4. Strategy behavior remains config-driven instead of hard-coded into the engine.

## Core Architecture Rules

- TFIS is a clean separate project from `TradingEngine` and `TradingEngineProd`.
- Excel/strategy sheet is the source specification.
- Runtime should use normalized YAML/JSON strategy definitions, not direct fragile Excel dependency.
- Strategy, formula, rule, market-structure, risk, and scheduler modules must remain broker-agnostic.
- No direct Fyers/Zerodha/Angel/Upstox imports outside broker adapters.
- Real broker integrations must be implemented only through adapter classes.
- Paper/mock broker must be used for tests.
- Existing TradingEngine scoring model may be integrated later only through clean interfaces, not copied directly into TFIS core.

## Current Status

Current state of the project:
- broker-agnostic architecture is in place
- typed domain model and safe formula engine are in place
- parameterized formulas and SPT vs OPT alias separation are enforced
- folder-based strategy config layout is in place
- all four canonical S23 branches are represented as validated strategy folders
- Excel cross-checks and formula safety validation are in place
- branch selector is implemented for folder-based monthly-status strategy variants
- strategy registry governance is in place
- strategy registry enforcement is in place
- shared market-data reuse direction is documented
- reference materials are indexed and governed through a review workflow
- historical lifecycle backtesting is in place
- EOD policies are in place
- cost/slippage assumptions are in place
- rupee P&L reporting is in place
- equity curve and drawdown reporting are in place
- monthly-status thresholds are captured
- monthly-status decision table is implemented as a diagnostic foundation
- monthly-status engine is implemented for the confirmed threshold rules
- monthly-status CLI report is implemented
- monthly-status manual review scenarios are in place
- optional monthly-status-driven branch selection is available for historical backtests
- opt-in S23 missed-entry detection and recalculation is available for historical backtests
- the opt-in S23 recalculation path can consume dedicated spot intraday CSV inputs while preserving an explicit fallback audit path when none is supplied
- opt-in offline option-chain contract selection is available for historical backtests

## Strategy Configuration Layout

TFIS is moving toward a one-folder-per-strategy layout so metadata, formulas, parameters, and notes are easier to review independently.

Preferred strategy layout:
- `strategy.yaml` for identity and metadata
- `formulas.yaml` for rule logic
- `parameters.yaml` for experiment-friendly numeric tunables
- `notes.md` for workbook source notes and branch context
- `excel_crosscheck.yaml` for workbook source cells and sample expected outputs

Legacy single-file strategy YAML remains supported during transition.

Folder-based strategies are the accepted path for backtesting. A folder strategy must pass:
- strategy config validation
- Excel cross-check validation
- formula safety validation

## Strategy Relevance And Governance

TFIS distinguishes between a strategy being structurally valid and a strategy being current-market relevant.

- the Excel workbook is a historical/source specification, not automatic market approval
- strategies should be classified through a registry before implementation or promotion
- current classifications include `ACTIVE_CANDIDATE`, `HISTORICAL_BACKTEST_ONLY`, and `UNKNOWN_REQUIRES_REVIEW`
- shared captured market data should be reused where possible instead of building a duplicate live capture stack

## Documentation

The TFIS docs are organized by area under [docs/README.md](docs/README.md):
- architecture
- strategy
- importers
- reference materials
- operations

## Quality Snapshot

Current repo health:
- tests passing: `236`
- `python scripts/validate_project.py`: passed

Next recommended priorities:
- shared captured-data adapter from `TradingEngine`
- rollover lifecycle module
- gap-up / gap-down refinement
- broader missed-entry / recalculation engine
- contract-specific option-chain intraday pricing and strike-availability realism
- monthly option buying engine

Still intentionally pending:
- shared captured-data adapter from `TradingEngine`
- rollover lifecycle module
- gap-up / gap-down refinement
- broader missed-entry / recalculation engine
- monthly option buying engine
- contract-specific option-chain intraday pricing and fuller strike-availability simulation
- broker adapters
- paper runtime
- live runtime

## Offline Capabilities

Current offline TFIS flow supports:
- `StrategyRule + MarketLevels + runtime values -> TradePlan`
- `TradePlan -> OrderIntent`
- `OrderIntent -> RiskDecision`
- sample-mode structural backtests
- CSV-driven structural backtests using local daily OHLC and option reference-level CSV files
- opt-in offline option-chain contract selection within computed strike ranges
- parameter sweep experiments using runtime `PARAMS` overrides only

Current limits:
- no live broker execution
- no contract-specific option lifecycle simulation yet
- no fill simulation
- no real P&L engine yet

## Excel Source Workflow

The workbook remains the source of truth for strategy intent.

Current Excel-related tooling includes:
- workbook profiling
- S23 metadata extraction prototype
- S23 formula block discovery
- workbook-to-config mapping documentation

Runtime does not depend directly on Excel. The intended flow remains:
1. inspect and validate workbook structure
2. normalize workbook content into config artifacts
3. run TFIS from normalized config plus offline inputs

## Backtesting And Experiments

Backtesting is currently deterministic and offline only.

Supported modes:
- `--sample` for synthetic structural checks
- `--daily-csv` plus `--option-levels-csv` for local CSV-driven structural backtests
- `--historical` with `--strategy-root` plus `--use-monthly-status-engine` for opt-in monthly-status-driven branch selection across eligible folder strategies
- `--historical` plus `--enable-s23-recalculation` for opt-in ORPT missed-entry detection and recalculated effective trade plans
- `--historical` plus `--option-chain-csv` and `--enable-option-chain-selection` for opt-in contract selection realism inside computed strike ranges

Parameter sweeps:
- use folder-based strategies only
- apply runtime `PARAMS` overrides without mutating strategy files
- produce JSON reports
- can also produce markdown ranking summaries

Representative commands:

```powershell
python scripts/validate_strategy_configs.py
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --sample --out tmp/S23_sample_backtest.json
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --daily-csv tests/fixtures/backtest/s23_daily.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels.csv --out tmp/S23_csv_backtest.json
python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --option-chain-csv tests/fixtures/backtest/s23_option_chain.csv --enable-option-chain-selection --historical --eod-policy square_off_at_close --enable-s23-recalculation --out tmp/S23_historical_monthly_status_recalc_chain_backtest.json --markdown-out tmp/S23_historical_monthly_status_recalc_chain_backtest.md
python scripts/run_parameter_sweep.py --experiment config/experiments/S23_parameter_sweep.yaml --out tmp/S23_parameter_sweep.json --markdown-out tmp/S23_parameter_sweep.md
```

Current historical audit outputs can include:
- monthly-status result, trigger, and candidate rows
- selected eligible S23 branches
- base trade plan versus recalculated trade plan for S23 missed-entry cases
- selected option-chain contract metadata and rejection reasons when contract selection is enabled

## Development

Requirements:
- Python 3.11+
- minimal dependencies only

Validation commands:

```powershell
python scripts/validate_strategy_configs.py
python scripts/validate_project.py
python -m pytest -q
```
