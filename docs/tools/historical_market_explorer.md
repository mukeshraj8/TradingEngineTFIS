# TFIS Historical Market Explorer

TFIS Historical Market Explorer is a standalone read-only local browser utility
for inspecting historical spot and option CSV data. It is intended for manual
workbook validation and market-data review. It does not run S23 decisions,
`StrategyEvaluator`, contract selection, paper/live logic, broker adapters, or
backtests.

## Launch

```powershell
.\.venv\Scripts\python.exe scripts\run_historical_market_explorer.py
```

Defaults:

- data root: `D:\HistoricalData`
- URL: `http://127.0.0.1:8787/`

Optional:

```powershell
.\.venv\Scripts\python.exe scripts\run_historical_market_explorer.py --data-root D:\HistoricalData --port 8788 --no-open
```

## Supported Data Layout

The explorer supports the current TFIS historical layout:

```text
D:\HistoricalData\Nifty\spot\<YEAR>\<MONTH>\nifty_spotDD_MM_YYYY.csv
D:\HistoricalData\Nifty\options\<YEAR>\<MONTH>\nifty_options_DD_MM_YYYY.csv
```

It also looks for equivalent `BankNifty` / `BANKNIFTY` folders. The backend
uses the existing HSRE historical provider and symbol parser:

- `src/tfis/backtest/nifty_hsre_data_adapter.py`
- `src/tfis/backtest/hsre_option_references.py`

## Layout

The left sidebar contains:

- instrument selector: `NIFTY` / `BANKNIFTY`
- trading date selector
- expiry dropdown populated from actual contracts for that date
- strike input with discovered strike suggestions
- option type selector: CALL / PUT
- optional start and end time filters
- load buttons and previous/next strike/day controls
- golden presets for Jan 17 and Jan 3 review

Manual strike-scan inputs live inside the `Manual Workbench` tab so the
workflow reads in order: set scan inputs, review qualifying strikes, inspect
selected-strike daily history.

The main area has tabs:

- `Overview`: selected contract summary, option candles, volume, and OI
- `Spot`: selected trading day's spot summary and candles
- `Prior History`: exact-contract prior daily table and prior spot table
- `S23 Workbook Validation`: copy-friendly S23 input values, reference only
- `Manual Workbench`: configurable workbook-style strike scan and daily candles
- `Option Chain`: full expiry chain at selected time plus search-order view
- `Multi-Day Contract`: continuous exact-contract candles across prior sessions
- `Data Quality`: concise warnings

Candlestick charts support mouse-wheel zoom, drag panning, hover crosshair, and
copy-friendly timestamp/OHLC/volume/OI tooltips.

## Exact-Contract History

The prior option-history section uses the same exact-contract identity
semantics as HSRE:

- same underlying
- same expiry
- same strike
- same CE/PE
- completed prior sessions only
- no current-day or future data
- no synthesized option minutes

The derived fields are labeled:

```text
Derived using TFIS HSRE exact-contract history semantics
```

Displayed values:

- `OPT_PRV_2DHH`
- `OPT_PRV_2DLL`
- `OPT_PRV_3DHH`
- `OPT_PRV_3DLL`

The most recent three completed exact-contract sessions are highlighted.

## Spot References

The prior spot-history section displays the latest completed spot sessions
before the selected date and derives:

- `PRV_2DHH`
- `PRV_2DLL`
- `PRV_3DHH`
- `PRV_3DLL`
- `PRV_4DHH`
- `PRV_4DLL`

These values are workbook comparison aids only.

## S23 Workbook Validation Tab

This tab is reference only. It does not select strikes or make strategy
decisions.

It displays:

- spot `PRV_*` references
- selected option `OPT_PRV_*` references
- 09:16 premium/OI/volume
- ORPT 09:24 option high/low
- RC 09:29 option high/low
- historical NIFTY lot size for the selected date
- S23 minimum OI units: `500 * lot size`

Use `Copy Workbook Inputs` or `Export Workbook Inputs CSV` for Excel review.

## Option Chain

The option-chain tab shows the full chain for selected date, time, and expiry:

- strike
- CE symbol/LTP/OI/volume
- PE symbol/LTP/OI/volume

The visual threshold fields are not connected to strategy config. They only
highlight rows for manual comparison:

- ideal premium
- minimum premium
- minimum OI
- start strike
- end strike

The search-order panel displays both:

- start -> end
- end -> start

for manual Step 8a/8b validation.

## Manual Workbench

The manual workbench is a read-only calculation aid for TFIS workbook-style
option-selling reviews. It does not run S23 or update any strategy parameters.

Inputs:

- selected instrument, monthly status, trading date, expiry, option side, and
  snapshot time
- lot size and OI multiplier, which auto-calculate minimum OI
- buffer %, strike spot reference value, strike step, start strike, and end
  strike
- configurable lookback sessions for option `DLL` / `DHH`
- direct ideal/minimum premium thresholds, or `Premium Spot Ref Value` with
  ideal and minimum percentage factors such as `1.20` and `0.90`
- optional minimum OI

The Manual Workbench has its own instrument selector. It stays synchronized
with the left sidebar selector. For `NIFTY` and `BANKNIFTY`, lot size is loaded
from the date-effective TFIS lot-size schedule using the selected expiry date.
For example, a January 2024 NIFTY expiry resolves to lot size `50`, not the
current lot size, and a January 2024 BankNifty expiry resolves to lot size
`15`.

The OI multiplier defaults to `400`, and minimum OI is calculated as:

```text
minimum OI = lot size * OI multiplier
```

Lot size, multiplier, and minimum OI remain editable so future exchange
lot-size changes or rule experiments can be tested without changing strategy
configuration.

Monthly status plus CE/PE side tells the operator which completed spot
reference to enter for strike-range calculation:

- `BULL` / `BULL_CF` + `CALL`: `Previous 3DLL of Spot`
- `BULL` / `BULL_CF` + `PUT`: `Previous 2DHH of Spot`
- `BEAR` / `BEAR_CF` + `CALL`: `Previous 2DLL of Spot`
- `BEAR` / `BEAR_CF` + `PUT`: `Previous 3DHH of Spot`

`Strike Spot Ref Value` is the actual completed spot reference value, not the
number of DLL/DHH days. With buffer `5.00` and strike step `50`, the workbench
uses:

```text
CALL start = round_down(strike spot ref * (1 + buffer / 100))
CALL end   = round_down(strike spot ref) - strike step

PUT start  = round_down(strike spot ref * (1 - buffer / 100))
PUT end    = round_down(strike spot ref) + strike step
```

For example, a CALL strike spot reference of `21715.15` with `5.00%` buffer
and `50` strike step gives adjusted value `22800.90`, start `22800`, and end
`21650`.

`Premium Spot Ref Value` means the calculated spot reference value used by the
premium threshold formula. It is not the number of DLL/DHH days and it is not
the percentage. For example, if a rule says:

```text
3DLL of Final Strike >= 1.20% of 3DLL of Spot
```

Do not enter `3`. First get the actual `3DLL of Spot` price, such as
`21715.15`, and enter that value in `Premium Spot Ref Value`. Enter `1.20`
in `Ideal Premium %`. The tool calculates:

```text
premium threshold = premium spot ref value * percent / 100
```

If you already know the final premium threshold, enter it directly in `Ideal
Premium Threshold` or `Minimum Premium Threshold` and leave the base/percent
fields empty. If you enter `Premium Spot Ref Value` plus ideal/minimum
percentages, the threshold fields are populated automatically.

The scan walks from start strike to end strike and reports every available
strike in the range with:

- snapshot premium, OI, and volume
- computed `OPT_PRV_DHH` and `OPT_PRV_DLL` across the requested lookback
- lookback sessions available and sessions used
- `meets_ideal`, `meets_minimum`, `meets_oi`, selected flag, and reason

Selection is intentionally simple and auditable:

1. choose the first strike in start-to-end order that passes ideal premium and
   OI
2. if no ideal strike qualifies, choose the first strike in start-to-end order
   that passes minimum premium and OI
3. if neither pass exists, report no qualifying strike

The selected-strike daily-history panel can show either the last N available
option sessions through the trade date or an explicit calendar range. Dates
without data or without the selected exact contract are shown as `MISSING`;
the utility does not forward-fill or substitute another contract.

## Exports

The server can export:

- selected exact-contract daily history
- visible option-chain snapshot
- S23 workbook-validation input row
- manual workbench strike scan
- selected-strike daily option history

Exports are generated from in-memory read-only payloads. The explorer never
writes to `D:\HistoricalData`.

## Data Quality Warnings

Warnings include:

- missing selected option minute at 09:16
- missing ORPT 09:24 minute
- missing RC 09:29 minute
- duplicate selected-contract timestamps
- duplicate spot timestamps
- negative OI if encountered by the parser
- insufficient exact-contract lookback
- missing spot file
- missing option file

The explorer does not repair, forward-fill, or silently substitute missing
minutes.

## Performance And Cache Behavior

The backend uses the existing bounded HSRE provider cache. It does not load all
years into memory. Date, expiry, and chain reads are fast for normal daily
inspection.

Exact-contract prior references intentionally use the certified HSRE
`NiftyHsreSelectedContractReferenceBuilder`. On large real option files, the
first load for a contract can take several minutes because the certified path
scans prior daily option CSVs to prove exact-contract history. Later reads in
the same process benefit from provider caching.

## Read-Only Guarantee

The explorer:

- reads historical spot/options CSV files
- serves local JSON/HTML/CSV responses
- may export CSV responses through the browser

It does not:

- mutate `D:\HistoricalData`
- write strategy YAML
- run S23
- run backtests
- run paper/live/broker code
- place or simulate orders
