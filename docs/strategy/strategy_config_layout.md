# Strategy Configuration Layout

## Purpose

TFIS strategy configuration is moving toward a one-folder-per-strategy layout.

This makes each strategy easier to:

- inspect
- review
- experiment with
- update without editing one long mixed YAML file

## Preferred Layout

Example:

```text
config/
  strategies/
    options_sell/
      nifty/
        S23_NIFTY_OP_SELL_WK_DIFF_2D_3D/
          strategy.yaml
          formulas.yaml
          parameters.yaml
          excel_crosscheck.yaml
          notes.md
```

This folder-based layout is the preferred configuration format for all new TFIS strategies.

When one workbook strategy block contains multiple canonical branches, TFIS may
represent those branches as separate folders so each branch can be validated and
backtested independently.

Current S23 example:

- `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D` as Bull / Bull CF Call
- `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT`
- `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL`
- `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT`

Branch selection:

- branch selection should work only on folder-based strategies
- the selector filters already-configured folders by `allowed_monthly_statuses`
- legacy YAML files are transitional artifacts and should be ignored by branch selection
- monthly status calculation itself belongs elsewhere and is not part of the selector

## What Each File Means

`strategy.yaml`

- stable identity and metadata
- symbol
- segment
- monthly-status scope
- option type
- timings
- minimum OI
- carry-forward flag

`formulas.yaml`

- runtime rule formulas only
- separated from metadata so formula review is easier
- good place to compare strategy variants side by side

`parameters.yaml`

- numeric tunables used by `PARAM(...)`
- default experiment values
- easiest place to modify for controlled backtests

`notes.md`

- human explanation
- workbook source cells
- branch interpretation
- migration notes

`excel_crosscheck.yaml`

- workbook source-cell mapping for the accepted branch
- one or more sample calculations tied back to Excel expectations
- a lightweight acceptance artifact before backtesting

When workbook formulas distinguish spot/reference levels from option-premium levels, the strategy folder should preserve that distinction explicitly.

Examples:

- spot/reference aliases: `PRV_3DLL`, `PRV_2DHH`
- option-premium aliases: `OPT_PRV_3DLL`, `OPT_PRV_2DHH`

For migrated strategies, the folder layout is the preferred place to reflect workbook-correct semantics even if a legacy YAML file still preserves older compatibility behavior.

For S23 specifically, the folder-based config follows the Excel/workbook premium semantics as the source of truth.

Completed daily reference semantics:

- `PRV_2DHH`, `PRV_2DLL`, `PRV_3DHH`, `PRV_3DLL`, `PRV_4DHH`, and `PRV_4DLL`
  are references to completed prior daily candles only
- the current/latest day is not part of those previous-day calculations
- `CDHH` and `CDLL` are separate current-day dynamic references
- gap-up and gap-down interpretation should be handled separately in a later
  importer and strategy-normalization phase

## How To Modify Parameters For Experiments

Use `parameters.yaml` for default values such as:

- `strike_buffer_pct`
- `target_pct`
- `sl_entry_pct`

This keeps formulas stable while allowing experiments to vary only the numeric inputs.

## How Backtest Overrides Work

Recommended flow:

1. Load the base strategy folder.
2. Read `parameters.yaml`.
3. Apply runtime overrides through `runtime_values["PARAMS"]`.
4. Evaluate the strategy with the overridden values.

This supports parameter sweeps without rewriting base config files.

## Why Formulas Are Separated From Parameters

Separating formulas from parameters improves:

- readability
- experiment safety
- diff quality in version control
- review of logic versus tuning

It also helps us keep a clean line between:

- structural rule intent
- numeric calibration

## Backward Compatibility

Legacy single-file YAML strategies are transitional only and should live under:

- `config/strategies/legacy/`

The loader currently supports both:

- `config/strategies/legacy/*.yaml`
- folder-based strategies with `strategy.yaml`, `formulas.yaml`, and `parameters.yaml`

Rule going forward:

- new strategies must use the folder-based layout
- legacy single-file YAML should not be added at the root of `config/strategies`
- each strategy folder should include `excel_crosscheck.yaml` before being accepted for backtesting

Important note:

- a folder-based strategy may intentionally differ from its legacy YAML counterpart when the folder version is correcting workbook semantics
- when that happens, the difference should be documented and covered by tests

## Backtest Acceptance Requirements

Folder-based strategies are eligible for backtesting only when:

- `strategy.yaml` exists
- `formulas.yaml` exists
- `parameters.yaml` exists
- `notes.md` exists
- `excel_crosscheck.yaml` exists
- the Excel cross-check test passes
- source workbook cells are documented in the strategy folder artifacts
