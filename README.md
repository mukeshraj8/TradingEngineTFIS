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
- clean project skeleton is in place
- typed domain model is implemented
- safe formula engine is implemented
- parameterized formulas are supported through `PARAM(name)`
- SPT vs OPT alias separation is enforced in formulas
- S23 strategy evaluation is working offline
- S23 workbook profiling, extraction discovery, and mapping docs are in place
- folder-based strategy config layout is implemented
- Excel cross-check artifacts are required for folder strategies
- broker-agnostic foundation is in place
- architecture boundary tests are active
- market structure layer is implemented
- order planner is implemented
- risk policy is implemented
- offline strategy pipeline is implemented
- offline backtest runner is implemented
- parameter sweep runner and ranking report are implemented
- CSV-driven historical backtest input foundation is implemented

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

## Offline Capabilities

Current offline TFIS flow supports:
- `StrategyRule + MarketLevels + runtime values -> TradePlan`
- `TradePlan -> OrderIntent`
- `OrderIntent -> RiskDecision`
- sample-mode structural backtests
- CSV-driven structural backtests using local daily OHLC and option reference-level CSV files
- parameter sweep experiments using runtime `PARAMS` overrides only

Current limits:
- no live broker execution
- no option-chain simulation
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
python scripts/run_parameter_sweep.py --experiment config/experiments/S23_parameter_sweep.yaml --out tmp/S23_parameter_sweep.json --markdown-out tmp/S23_parameter_sweep.md
```

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
