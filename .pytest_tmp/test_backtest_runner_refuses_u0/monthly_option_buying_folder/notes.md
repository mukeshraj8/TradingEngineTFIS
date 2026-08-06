# S23 Notes

This folder represents the `S23` Bull / Bull CF Call branch.

Source workbook anchors:

- `AB2!B28` metadata
- `AB6 OS!C163` / `AB6 OS!C164` identity
- `AB6 OS!D162` monthly status
- `AB6 OS!F162` option type
- `AB6 OS!G162` start strike
- `AB6 OS!G163` end strike
- `AB6 OS!H162` ideal premium
- `AB6 OS!H163` minimum premium
- `AB6 OS!I162` minimum OI
- `AB6 OS!M162` entry formula
- `AB6 OS!O162` target formula
- `AB6 OS!M163` stoploss formula

Notes:

- This folder layout is the preferred long-term strategy format.
- The legacy single-file YAML remains in place during transition.
- Spot/reference levels and option-premium reference levels are intentionally separated:
  - strike and premium formulas use spot/reference aliases such as `PRV_3DLL`
  - entry and stoploss reference formulas use option aliases such as `OPT_PRV_3DLL` and `OPT_PRV_2DHH`
- This folder-based S23 now follows the Excel-discovered premium semantics:
  - `AB6 OS!H162 = SPT : PRV : 3DLL * 1.20%`
  - `AB6 OS!H163 = SPT : PRV : 3DLL * 0.90%`
  - Example: `PRV_3DLL = 22000` gives ideal premium `264` and minimum premium `198`
- Example option-level separation:
  - `OPT_PRV_3DLL = 220` gives entry price `203.5`
  - `OPT_PRV_2DHH = 300` keeps stoploss at `MIN(320, 321) = 320`
- The legacy single-file YAML still preserves the older additive premium behavior and is kept unchanged on purpose.
