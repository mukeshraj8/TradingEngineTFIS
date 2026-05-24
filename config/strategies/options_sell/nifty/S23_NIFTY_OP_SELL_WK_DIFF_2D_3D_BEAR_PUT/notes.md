# S23 Bear Put Notes

This folder represents the `S23` Bear / Bear CF Put branch.

Source workbook anchors:

- `AB2!B28` metadata
- `AB6 OS!C163` / `AB6 OS!C164` shared S23 identity block
- `AB6 OS!D168` monthly status family (`BEAR / BEAR CF`)
- `AB6 OS!F171` option type
- `AB6 OS!G171` start strike
- `AB6 OS!G172` end strike
- `AB6 OS!H171` ideal premium
- `AB6 OS!H172` minimum premium
- `AB6 OS!I171` minimum OI
- `AB6 OS!M171` entry formula
- `AB6 OS!O171` target formula
- `AB6 OS!M172` stoploss formula

Notes:

- This folder is a normalized branch-specific strategy derived from the shared S23 workbook block.
- The normalized `unique_code` appends `_BEAR_PUT` so this branch can exist as its own folder-based `StrategyRule`.
- Spot/reference formulas intentionally use `PRV_*` aliases:
  - `PRV_3DHH` for strike and premium references
- Option-premium formulas intentionally use `OPT_*` aliases:
  - `OPT_PRV_3DLL` for entry
  - `OPT_PRV_2DHH` for stoploss reference
- Excel stoploss reference for this branch is `+7.00%`, so `sl_reference_pct` is set to `7.0`.
