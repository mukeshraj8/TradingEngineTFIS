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

Completed daily reference semantics:

- `PRV_2DHH`, `PRV_2DLL`, `PRV_3DHH`, `PRV_3DLL`, `PRV_4DHH`, and `PRV_4DLL`
  are always based on completed prior daily bars after close
- the latest/current day bar is excluded from those previous-day calculations
- `CDHH` and `CDLL` are the current-day dynamic references
- gap-up and gap-down logic should be layered on separately later, not folded
  into the meaning of the completed daily references

## Backtest Acceptance Requirements

Before a folder-based strategy can be used in backtesting, it must pass all of these gates:

- folder-based strategy layout only, not legacy YAML
- strategy config validation
- Excel cross-check presence and structure validation
- formula safety validation
- strategy registry status must permit backtesting

Formula safety validation is specifically meant to catch alias mistakes such as using
plain `PRV_*` spot references where the Excel-backed option branch expects `OPT_*`
premium references. `ERROR` findings must stop the backtest. `WARN` findings may be
reported in the backtest output, but they do not block execution.

The same acceptance gate applies during parameter sweeps. Each variant is run through
the normal folder-strategy validation and formula-safety validation before evaluation.

Registry gate:

- `ACTIVE`, `ACTIVE_CANDIDATE`, and `HISTORICAL_BACKTEST_ONLY` are backtest-allowed statuses
- `PLACEHOLDER`, `DISCONTINUED`, and `UNKNOWN_REQUIRES_REVIEW` must be refused by the backtest runner
- missing registry entries may still load structurally for now, but they should be treated as governance gaps and surfaced by validation output

Branch selection:

- when multiple folder strategies represent branches of one workbook strategy block,
  TFIS can filter them by the current `MonthlyStatus`
- this selector only filters configured strategy folders by
  `allowed_monthly_statuses`
- it does not calculate monthly status itself
- it ignores legacy YAML inputs and non-folder strategy sources
- in non-strict mode it skips invalid folder inputs and records warning metadata
- in strict mode it raises immediately on invalid or incomplete strategy folders

Optional monthly-status-driven branch selection:

- the historical backtest runner can now opt into monthly-status-driven branch selection
- this mode requires:
  - `--strategy-root`
  - `--use-monthly-status-engine`
  - `--monthly-csv`
  - `--weekly-csv`
- the default backtest path is unchanged:
  - `--strategy-path` still runs one explicitly chosen folder strategy
- monthly-status mode is additive and audit-focused:
  - it classifies monthly status for each historical step
  - it selects eligible folder branches through `StrategyBranchSelector`
  - it reports monthly status, trigger, reversal dominance, selected branches,
    and decision candidates in the backtest output
- if monthly or weekly reference data is insufficient for a step, that step is skipped
  with a recorded reason instead of forcing a guessed status

Optional S23 missed-entry recalculation:

- historical backtest can now opt into S23 ORPT missed-entry detection and recalculation
- this mode is enabled with:
  - `--enable-s23-recalculation`
- it is available only with `--historical`
- default behavior remains unchanged when the flag is absent
- when enabled:
  - the runner checks the ORPT snapshot at or before `09:24:59`
  - it applies the Excel missed-entry rule `option_low < entry_price`
  - if entry is missed, it checks the recalculation snapshot at or before `09:29:59`
  - it builds an effective recalculated trade plan for lifecycle simulation only
  - it records base-plan and recalculated-plan audit data in the report
- if required ORPT or recalculation snapshots are missing:
  - the candidate is not crashed
  - the base trade plan is kept
  - a clear warning is recorded in the recalculation audit
- if a recalculated put branch touches an unresolved workbook ambiguity:
  - the report includes the linked open-question metadata from
    `config/importer_open_questions.yaml`
- spot intraday sourcing:
  - if `--spot-intraday-csv` is provided, ORPT and recalculation spot high/low come from that intraday spot/index series
  - if it is not provided, spot high/low fall back to current-day market-level highs and lows
  - the report records which source was used so the path remains audit-friendly rather than implicit

Optional S23 current-day FSL / TRP handling:

- historical backtest can now opt into workbook-backed S23 current-day
  `FSL / TRP missed / not-missed` handling
- this mode is enabled with:
  - `--enable-s23-current-day-fsl-trp`
- it is available only with `--historical`
- it currently requires:
  - `--option-intraday-csv`
  - `--spot-intraday-csv`
- it is separate from the older ORPT missed-entry recalculation path:
  - `--enable-s23-current-day-fsl-trp` cannot be combined with
    `--enable-s23-recalculation`
- the layer uses aggregated current-day snapshots at:
  - `09:15:00`
  - `09:24:59`
  - `09:29:59`
- the workbook-backed implementation scope is intentionally narrow:
  - row `183`: Bull / Bull CF Call, `FSL / TRP not missed`
  - row `184`: Bull / Bull CF Call, `FSL / TRP missed`, using the workbook's
    Put-side `Q/R/S/U/W` family exactly as confirmed
  - row `185`: Bear / Bear CF Call, `FSL / TRP missed`
  - row `186`: Bear / Bear CF Put, `FSL / TRP not missed`
  - row `187`: Bull / Bull CF Put, `FSL-only`
  - row `188`: Bear / Bear CF Put, `FSL-only`
- when workbook coverage is blank or unsupported for a branch path:
  - TFIS keeps the base trade plan
  - TFIS records a clear audit warning
  - TFIS does not infer missing strike or premium logic
- this layer does not yet represent a complete generic gap-up / gap-down engine

Optional option-chain contract selection:

- historical backtest can now opt into a first-pass option-chain contract selection layer
- this mode is enabled with:
  - `--option-chain-csv`
  - `--enable-option-chain-selection`
- it is available only with `--historical`
- default behavior remains unchanged when the flag is absent
- when enabled:
  - the runner keeps the existing formula-derived strike range and premium values unchanged
  - it filters chain rows by option type, strike range, minimum OI, and minimum premium
  - it prefers the contract whose `ltp` is closest to the computed `ideal_premium`
  - tie-breakers are:
    - smaller bid/ask spread
    - higher OI
    - strike nearest to the strike-range midpoint
  - it reports the selected contract metadata and selection reason in validation audit output
  - if no contract qualifies, the candidate is rejected cleanly instead of silently proceeding
- current limitation:
  - contract selection alone does not change lifecycle pricing
  - symbol-specific lifecycle pricing requires the separate contract-specific lifecycle mode described below

Expiry-day lifecycle review:

- when option-chain selection is enabled, TFIS can now review expiry-day status from the selected contract expiry metadata
- this review is additive and audit-focused
- it does not invent rollover or carry behavior for options
- the report now records:
  - whether the selected contract date was an expiry day
  - whether a full exit requirement applied
  - whether the lifecycle outcome satisfied that full exit requirement
  - warnings when an expiry-day position remained open in diagnostic mode
- this review currently depends on selected contract expiry metadata from the offline option-chain data

Optional contract-specific lifecycle pricing:

- historical backtest can now opt into symbol-specific lifecycle pricing for the actually selected option-chain contract
- this mode is enabled with:
  - `--contract-intraday-csv`
  - `--enable-contract-specific-lifecycle`
- it is available only with `--historical`
- it currently requires option-chain selection mode:
  - `--enable-option-chain-selection`
- default behavior remains unchanged when the flag is absent
- when enabled:
  - TFIS looks up intraday bars matching the selected option-chain `symbol`
  - if symbol-matched bars are found, lifecycle simulation uses that contract-specific series
  - if symbol-matched bars are missing, TFIS falls back to the generic option intraday series
  - the validation audit records:
    - `lifecycle_price_source`
    - selected contract symbol
    - fallback warning when relevant
- current limitation:
  - this is still an offline CSV-only foundation
  - it depends on symbol-keyed intraday archives already being available
  - it does not yet guarantee complete strike/date coverage for every selected contract

Optional shared-data adapter:

- historical and snapshot backtests can now opt into a normalized shared-data root
- this mode is enabled with:
  - `--shared-data-root`
- it remains read-only and offline-only
- current supported layout is normalized CSV folders such as:
  - `shared_root/nifty/daily.csv`
  - `shared_root/nifty/weekly.csv`
  - `shared_root/nifty/monthly.csv`
  - `shared_root/nifty/option_levels.csv`
  - `shared_root/nifty/option_chain.csv`
  - `shared_root/nifty/option_intraday.csv`
- shared-data roots may be:
  - instrument-scoped directly, such as `shared_root/nifty`
  - or a parent root when TFIS can infer the instrument from the strategy path/root
- `--allow-partial-shared-data` lets TFIS accept an incomplete normalized root and rely on explicit CSV flags for the missing pieces
- current limitation:
  - the adapter does not yet parse raw `TradingEngine` or `NiftyTradingEngine` parquet/jsonl/session-capture formats
  - it only consumes normalized CSV exports

Comparison reporting across modes:

- TFIS now includes a read-only comparison tool for existing backtest JSON outputs
- this tool does not rerun backtests or alter strategy logic
- it compares already-generated reports across historical modes such as:
  - monthly-status branch selection only
  - monthly-status plus S23 recalculation
  - monthly-status plus recalculation plus option-chain selection
  - monthly-status plus recalculation plus option-chain plus contract-specific lifecycle pricing
- current comparison output focuses on:
  - aggregate performance metrics
  - audit coverage counts
  - feature flags enabled in each report
- example command:

```powershell
python scripts/compare_backtest_reports.py --report base=tmp/S23_historical_monthly_status_backtest.json --report recalc=tmp/S23_historical_monthly_status_recalc_backtest.json --report chain=tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.json --out tmp/S23_mode_comparison.json --markdown-out tmp/S23_mode_comparison.md
```

## CSV Backtest Input

The current backtest foundation can also run from local CSV files.

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

Option-chain CSV requires:

- `timestamp`
- `symbol`
- `option_type`
- `strike`
- `expiry`
- `bid`
- `ask`
- `ltp`
- `oi`
- `volume`

Contract-specific intraday CSV requires:

- `timestamp`
- `symbol`
- `open`
- `high`
- `low`
- `close`

Optional:

- `volume`

Current example:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --daily-csv tests/fixtures/backtest/s23_daily.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels.csv --out tmp/S23_csv_backtest.json
```

Historical replay example:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --historical --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --out tmp/S23_historical_backtest.json
```

Historical replay with basic lifecycle simulation:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --historical --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --out tmp/S23_historical_backtest.json
```

Historical replay with end-of-day square-off policy:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --historical --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --eod-policy square_off_at_close --out tmp/S23_historical_backtest_eod_squareoff.json
```

Historical replay with markdown summary output:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --historical --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --eod-policy square_off_at_close --out tmp/S23_historical_backtest_eod_squareoff.json --markdown-out tmp/S23_historical_backtest_eod_squareoff.md
```

Historical replay with monthly-status-driven branch selection:

```powershell
python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --historical --eod-policy square_off_at_close --out tmp/S23_historical_monthly_status_backtest.json --markdown-out tmp/S23_historical_monthly_status_backtest.md
```

Historical replay with opt-in S23 missed-entry recalculation:

```powershell
python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --historical --eod-policy square_off_at_close --enable-s23-recalculation --out tmp/S23_historical_monthly_status_recalc_backtest.json --markdown-out tmp/S23_historical_monthly_status_recalc_backtest.md
```

Historical replay with opt-in S23 recalculation plus dedicated spot intraday sourcing:

```powershell
python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --spot-intraday-csv tests/fixtures/backtest/s23_spot_intraday.csv --historical --eod-policy square_off_at_close --enable-s23-recalculation --out tmp/S23_historical_monthly_status_recalc_backtest.json --markdown-out tmp/S23_historical_monthly_status_recalc_backtest.md
```

Historical replay with opt-in S23 current-day FSL / TRP handling:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --spot-intraday-csv tests/fixtures/backtest/s23_spot_intraday.csv --historical --eod-policy square_off_at_close --enable-s23-current-day-fsl-trp --out tmp/S23_historical_current_day_fsl_trp_backtest.json --markdown-out tmp/S23_historical_current_day_fsl_trp_backtest.md
```

Historical replay with opt-in S23 recalculation plus option-chain contract selection:

```powershell
python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --option-chain-csv tests/fixtures/backtest/s23_option_chain.csv --enable-option-chain-selection --historical --eod-policy square_off_at_close --enable-s23-recalculation --out tmp/S23_historical_monthly_status_recalc_chain_backtest.json --markdown-out tmp/S23_historical_monthly_status_recalc_chain_backtest.md
```

Historical replay with opt-in option-chain selection plus contract-specific lifecycle pricing:

```powershell
python scripts/run_backtest.py --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --monthly-csv tests/fixtures/backtest/s23_monthly.csv --weekly-csv tests/fixtures/backtest/s23_weekly.csv --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --option-chain-csv tests/fixtures/backtest/s23_option_chain.csv --contract-intraday-csv tests/fixtures/backtest/s23_contract_intraday.csv --enable-option-chain-selection --enable-contract-specific-lifecycle --historical --eod-policy square_off_at_close --enable-s23-recalculation --out tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.json --markdown-out tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.md
```

Historical replay with normalized shared-data root:

```powershell
python scripts/run_backtest.py --shared-data-root tests/fixtures/shared_data/nifty --strategy-root config/strategies/options_sell/nifty --use-monthly-status-engine --enable-s23-recalculation --enable-option-chain-selection --historical --eod-policy square_off_at_close --out tmp/S23_shared_data_backtest.json --markdown-out tmp/S23_shared_data_backtest.md
```

Historical replay with cost and slippage assumptions:

```powershell
python scripts/run_backtest.py --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D --historical --daily-csv tests/fixtures/backtest/s23_daily_multi.csv --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv --eod-policy square_off_at_close --slippage-points-per-side 1.0 --brokerage-points-per-trade 0.5 --other-cost-points-per-trade 0.5 --out tmp/S23_historical_backtest_costed.json --markdown-out tmp/S23_historical_backtest_costed.md
```

Current offline modes:

- sample mode: one deterministic synthetic evaluation
- snapshot CSV mode: one structural evaluation from local CSV inputs
- historical replay mode: rolling candidate evaluation across chronological CSV rows
- historical replay with intraday option CSV: rolling candidate evaluation plus first-pass lifecycle simulation
- historical replay with opt-in S23 recalculation: the same historical path plus ORPT missed-entry detection and recalculated effective lifecycle plans for S23 branches only
- historical replay with opt-in S23 recalculation plus spot intraday CSV: the recalculation path can use explicit spot/index ORPT and recalculation snapshots instead of market-level fallback values
- historical replay with opt-in S23 current-day FSL / TRP handling: the same historical path can apply workbook-backed `09:15 -> ORPT / RC` current-day branch handling for the confirmed `AB6 OS` rows `183-188`
- historical replay with opt-in option-chain selection: the same historical path can now require an actual contract candidate from offline chain data before the candidate remains accepted
- historical replay with opt-in contract-specific lifecycle pricing: the same historical path can now use symbol-specific intraday bars for the selected contract when those bars are available
- shared-data-root mode: the same snapshot or historical paths can now source normalized CSV inputs from a shared archive root instead of passing each file path separately

This remains a structural backtest only:

- market structure comes from offline daily OHLC
- option reference levels come from offline CSV
- historical mode evaluates candidates row by row, not trades from open to close
- no full option-chain execution engine
- only a first-pass entry/target/stoploss lifecycle simulation when intraday option CSV is provided
- contract-specific lifecycle pricing is still opt-in and only as complete as the available symbol-keyed intraday archive
- no fill simulation
- no real P&L engine yet

Because there is no fill model yet, the script still uses a deterministic runtime
`ENTRY` placeholder value for downstream target and stoploss formulas.

Current lifecycle limits:

- carry-forward is not implemented yet
- no partial exits
- no slippage
- if target and stoploss are both touched in the same bar, the conservative stoploss result is used

S23 option lifecycle governance:

- S23 option selling exits the full lot on target
- S23 option selling exits the full lot on stoploss
- expiry-day handling is an exit or square-off decision, not an option rollover
- S23 does not carry or roll to the next option contract
- any later S23 trade must come from a fresh calculation and a fresh position
- this same no-rollover rule also applies to TFIS option buying strategies
- when option-chain expiry metadata is available, historical reports can now explicitly review whether expiry-day positions were fully closed

Lifecycle interpretation notes:

- current lifecycle simulation assumes an options-sell trade shape
- entry is considered hit when the intraday option bar touches the configured `entry_price`
- target is considered hit when option price trades down to or below `target_price`
- stoploss is considered hit when option price trades up to or above `stoploss_price`
- if both target and stoploss are touched inside the same bar, the simulator keeps the conservative stoploss result
- `max_favorable_excursion` for options sell means the best downward move in option price after entry, measured as `entry_price - bar.low`
- `max_adverse_excursion` for options sell means the worst upward move in option price after entry, measured as `bar.high - entry_price`
- `average_pnl_points` currently averages closed trades only
- `win_rate` and `loss_rate` currently use closed trades only
- `no_entry_rate` is measured across all evaluated candidates
- `no_exit_rate` is measured across entered trades only
- carry-forward remains pending, so non-closed rows report excursions but do not simulate a later exit

End-of-day policy options:

- `MARK_NO_EXIT`: diagnostic mode; if entry is hit but no target or stoploss occurs, the trade remains `NO_EXIT` with no realized P&L
- `SQUARE_OFF_AT_CLOSE`: intraday-only assumption; if entry is hit but no target or stoploss occurs, the trade exits at the last available intraday bar close with `EOD_SQUARE_OFF`
- `CARRY_FORWARD_PENDING`: acknowledges carry-forward intent, but still does not simulate the next day; the trade is marked `CARRY_FORWARD_PENDING` with no realized P&L

Cost and slippage assumptions:

- `gross_pnl_points` reflects the lifecycle outcome before trading frictions
- `total_cost_points` is computed as brokerage + other per-trade costs + two-sided slippage
- `net_pnl_points` is `gross_pnl_points - total_cost_points`
- `gross_pnl_rupees`, `cost_rupees`, and `net_pnl_rupees` multiply the corresponding point values by the backtest quantity
- points-based metrics remain the base unit for signal and lifecycle review
- rupee-based metrics are an approximate convenience layer for lot-sized reporting
- cost and slippage are only applied to completed trades such as `TARGET_HIT`, `STOPLOSS_HIT`, or `EOD_SQUARE_OFF`
- `NO_ENTRY`, `NO_EXIT`, and `CARRY_FORWARD_PENDING` remain non-realized outcomes and therefore keep net P&L as null
- brokerage and slippage inputs are still approximate assumptions and should not be treated as production execution estimates

Equity curve and drawdown:

- the historical report builds a realized equity curve from completed trades only
- `cumulative_net_pnl_rupees` increases or decreases after each realized trade with `net_pnl_rupees`
- incomplete outcomes such as `NO_ENTRY`, `NO_EXIT`, and `CARRY_FORWARD_PENDING` are excluded from realized equity updates
- `running_peak_rupees` tracks the highest realized cumulative net P&L reached so far
- `drawdown_rupees` measures the decline from that running realized peak at each completed trade
- `max_drawdown_rupees` is the worst realized rupee drawdown seen across the report
- `max_drawdown_points` is the same idea using realized net point P&L when available

## Compatibility Rule

Existing non-parameterized strategies must continue to work unchanged.

Parameterized support is additive:

- old formulas still evaluate
- old YAML files still load
- parameter-aware backtests can be added incrementally
