# S23 Bull Put Notes

This folder represents the `S23` Bull / Bull CF Put branch.

Source workbook anchors:

- `AB2!B28` metadata
- `AB6 OS!C163` / `AB6 OS!C164` shared S23 identity block
- `AB6 OS!D162` monthly status family (`BULL / BULL CF`)
- `AB6 OS!F165` option type
- `AB6 OS!G165` start strike
- `AB6 OS!G166` end strike
- `AB6 OS!H165` ideal premium
- `AB6 OS!H166` minimum premium
- `AB6 OS!I165` minimum OI
- `AB6 OS!M165` entry formula
- `AB6 OS!O165` target formula
- `AB6 OS!M166` stoploss formula

Notes:

- This folder is a normalized branch-specific strategy derived from the shared S23 workbook block.
- The normalized `unique_code` appends `_BULL_PUT` so this branch can exist as its own folder-based `StrategyRule`.
- Spot/reference formulas intentionally use `PRV_*` aliases:
  - `PRV_2DHH` for strike and premium references
- Option-premium formulas intentionally use `OPT_*` aliases:
  - `OPT_PRV_2DLL` for entry
  - `OPT_PRV_3DHH` for stoploss reference
- Excel stoploss reference for this branch is `+10.00%`, so `sl_reference_pct` is set to `10.0`.
