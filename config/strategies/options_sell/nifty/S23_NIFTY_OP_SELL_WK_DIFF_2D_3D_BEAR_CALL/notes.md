# S23 Bear Call Notes

This folder represents the `S23` Bear / Bear CF Call branch.

Source workbook anchors:

- `AB2!B28` metadata
- `AB6 OS!C163` / `AB6 OS!C164` shared S23 identity block
- `AB6 OS!D168` monthly status family (`BEAR / BEAR CF`)
- `AB6 OS!F168` option type
- `AB6 OS!G168` start strike
- `AB6 OS!G169` end strike
- `AB6 OS!H168` ideal premium
- `AB6 OS!H169` minimum premium
- `AB6 OS!I168` minimum OI
- `AB6 OS!M168` entry formula
- `AB6 OS!O168` target formula
- `AB6 OS!M169` stoploss formula

Notes:

- This folder is a normalized branch-specific strategy derived from the shared S23 workbook block.
- The normalized `unique_code` appends `_BEAR_CALL` so this branch can exist as its own folder-based `StrategyRule`.
- Spot/reference formulas intentionally use `PRV_*` aliases:
  - `PRV_2DLL` for strike and premium references
- Option-premium formulas intentionally use `OPT_*` aliases:
  - `OPT_PRV_2DLL` for entry
  - `OPT_PRV_3DHH` for stoploss reference
- Excel stoploss reference for this branch is `+10.00%`, so `sl_reference_pct` is set to `10.0`.
