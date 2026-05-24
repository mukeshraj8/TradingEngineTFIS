# Backtesting And Experiments

## Why Parameterized Formulas Matter

TFIS strategies should be testable without editing formula text for every experiment.

Parameterized formulas let us keep:

- one stable strategy definition
- one stable rule structure
- multiple numeric experiment variants

This is especially useful in backtesting, where we want to compare rule sensitivity without duplicating dozens of YAML files.

## Parameter Syntax

The formula engine now supports:

- `PARAM(name)`

Examples:

- `PRV_3DLL + PARAM(strike_buffer_pct)%`
- `ENTRY - PARAM(target_pct)%`
- `MIN(ENTRY + PARAM(sl_entry_pct)%, PRV_2DHH + PARAM(sl_reference_pct)%)`

Parameters resolve from:

- `StrategyRule.parameters`
- or runtime overrides through `runtime_values["PARAMS"]`

Runtime overrides should take precedence during experimentation so a backtest runner can sweep parameters without mutating the base strategy file.

## Backtest Experiment Flow

Recommended flow:

1. Load a base strategy config.
2. Read its default `parameters`.
3. Provide any required option-premium reference levels separately from spot/reference market levels.
4. Apply one experiment override combination.
5. Run the offline evaluation pipeline on historical data.
6. Collect performance and rejection metrics.
7. Compare results across parameter combinations.

Parameter sweeps should use runtime `PARAMS` overrides only. They must never edit
`parameters.yaml` or any other strategy file on disk.

## Example Experiment Matrix

Example sweep:

- `strike_buffer_pct`: `[3, 5, 7]`
- `target_pct`: `[40, 50, 60]`
- `sl_entry_pct`: `[40, 50, 60]`

Additional example:

- `sl_reference_pct`: `[7, 10]`

Current sample command:

```powershell
python scripts/run_parameter_sweep.py --experiment config/experiments/S23_parameter_sweep.yaml --out tmp/S23_parameter_sweep.json --markdown-out tmp/S23_parameter_sweep.md
```

## Result Comparison Metrics

Recommended baseline metrics:

- total trades
- win rate
- average profit/loss
- max drawdown
- expectancy
- profit factor
- rejected trades
- risk-rule failures

Recommended secondary metrics:

- average holding time
- average favorable excursion
- average adverse excursion
- missed-entry count
- stoploss-hit count
- target-hit count

## Sample Ranking

Until real option-chain execution and profit/loss simulation exist, parameter sweep ranking is
only a provisional review aid.

The current sample ranking prefers:

1. accepted variants first
2. lower stoploss risk distance first
3. higher reward distance next

Where:

- `risk_distance = abs(stoploss_price - entry_price)`
- `reward_distance = abs(entry_price - target_price)`
- `reward_risk_ratio = reward_distance / risk_distance` when risk distance is non-zero

This is useful for quickly comparing shape differences across variants, but it is not a
substitute for real P&L, fill modeling, or historical outcome simulation.

## Architecture Guidance

The experiment layer should remain:

- offline
- deterministic
- broker-agnostic
- isolated from live execution

That means:

- no broker SDK dependency
- no external API requirement
- no strategy mutation at runtime beyond parameter overrides

It also means spot/reference levels and option-premium reference levels must not be conflated.

Recommended separation:

- `MarketLevels` for spot/index/reference levels such as `PRV_3DLL`
- runtime option-level inputs for aliases such as `OPT_PRV_3DLL` and `OPT_PRV_2DHH`

If a strategy formula uses `OPT_*` aliases, backtests must provide those option-level values explicitly.

## Backtest Acceptance Requirements

Before a folder-based strategy can be used in backtesting, it must pass all of these gates:

- folder-based strategy layout only, not legacy YAML
- strategy config validation
- Excel cross-check presence and structure validation
- formula safety validation

Formula safety validation is specifically meant to catch alias mistakes such as using
plain `PRV_*` spot references where the Excel-backed option branch expects `OPT_*`
premium references. `ERROR` findings must stop the backtest. `WARN` findings may be
reported in the backtest output, but they do not block execution.

The same acceptance gate applies during parameter sweeps. Each variant is run through
the normal folder-strategy validation and formula-safety validation before evaluation.

## CSV Backtest Input

The current historical backtest foundation can also run from local CSV files.

Daily spot/reference OHLC CSV requires:

- `timestamp`
- `open`
- `high`
- `low`
- `close`

Optional:

- `volume`

Option-level CSV requires:

- `timestamp`
- `opt_prv_2dhh`
- `opt_prv_2dll`
- `opt_prv_3dhh`
- `opt_prv_3dll`

Current example:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --daily-csv tests/fixtures/backtest/s23_daily.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels.csv --out tmp/S23_csv_backtest.json
```

This remains a structural backtest only:

- market structure comes from offline daily OHLC
- option reference levels come from offline CSV
- no option-chain simulation
- no fill simulation
- no real P&L engine yet

Because there is no fill model yet, the script still uses a deterministic runtime
`ENTRY` placeholder value for downstream target and stoploss formulas.

## Compatibility Rule

Existing non-parameterized strategies must continue to work unchanged.

Parameterized support is additive:

- old formulas still evaluate
- old YAML files still load
- parameter-aware backtests can be added incrementally
