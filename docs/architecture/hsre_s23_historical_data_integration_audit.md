# HSRE S23 Historical Data Integration Audit

Date: 2026-08-09

Status: AUDIT / DESIGN ONLY. No production code, strategy YAML, formulas,
policies, paper/live runtime, broker code, or tests were changed for this
audit.

## Scope

TFIS is starting a Historical Strategy Research Engine (HSRE) using local
NIFTY historical minute data under `D:\HistoricalData\Nifty`.

The first S23 objective is to feed the existing corrected S23 rule/config/
policy path from the new files without creating a second S23 implementation.
Generic historical infrastructure must stay strategy-neutral.

## Data Source Observed

Sample files inspected:

- `D:\HistoricalData\Nifty\spot\2024\1\nifty_spot01_01_2024.csv`
- `D:\HistoricalData\Nifty\options\2024\1\nifty_options_01_01_2024.csv`

Observed spot schema:

```text
date,time,symbol,open,high,low,close
```

Observed option schema:

```text
date,time,symbol,open,high,low,close,oi,volume
```

Observed option symbol example:

```text
NIFTY04JAN2418300PE
```

Symbol parsing required:

- underlying: `NIFTY`
- expiry token: `04JAN24`
- strike: `18300`
- option side: `PE`

The sample option OI values are positive absolute-looking quantities, so HSRE
must treat OI as usable and enforce S23 minimum OI normally. This differs from
the discarded earlier BANKNIFTY dataset where OI was explicitly disabled.

## Current Historical Flow

Current CLI and runner flow:

```text
scripts/run_backtest.py
  -> parse explicit normalized CSV inputs or --shared-data-root
  -> load daily.csv through load_daily_bars_csv
  -> load option_levels.csv through load_option_levels_series_csv
  -> optionally load option_intraday.csv, spot_intraday.csv
  -> optionally load monthly.csv, weekly.csv
  -> optionally load option_chain.csv, contract_intraday.csv
  -> HistoricalBacktestRunner.run
       -> load_strategy_rule or select strategy branches by monthly status
       -> MarketStructureCalculator.build_market_levels
       -> StrategyEvaluator.evaluate
       -> optional S23 ORPT missed-entry/recalculation
       -> optional option-chain selection
       -> optional contract-specific lifecycle series
       -> TradeLifecycleSimulator.simulate
       -> CostModel and report/equity metrics
```

Current branch-aware monthly-status flow:

```text
HistoricalBacktestRunner.run
  -> build_monthly_status_context
       -> MonthlyStatusLookbackResolver / MonthlyStatusEngine
       -> StrategyBranchSelector
  -> select S23 branch folders under config/strategies/options_sell/nifty
  -> evaluate each selected branch independently
```

Current report flow:

```text
HistoricalCandidateResult
  -> build_realized_equity_curve
  -> HistoricalBacktestMetrics
  -> scripts/run_backtest.py JSON/Markdown rendering
```

## Existing Input Contracts

The existing historical runner consumes normalized, already-prepared files:

| Contract | Loader | Required shape | Current use |
|---|---|---|---|
| `daily.csv` | `load_daily_bars_csv` | `timestamp,open,high,low,close[,volume]` | completed-prior-day NIFTY references and current-day context |
| `option_levels.csv` | `load_option_levels_series_csv` | `timestamp,opt_prv_2dhh,opt_prv_2dll,opt_prv_3dhh,opt_prv_3dll` | selected/final option reference levels used by S23 entry/SL formulas |
| `option_intraday.csv` | `load_intraday_option_bars_csv` | `timestamp,open,high,low,close[,volume]` | generic lifecycle and current S23 ORPT/RC snapshots |
| `spot_intraday.csv` | `load_intraday_spot_bars_csv` | `timestamp,open,high,low,close[,volume]` | S23 ORPT/RC spot snapshots when recalculation is enabled |
| `monthly.csv` | `load_monthly_bars_csv` | `timestamp,open,high,low,close` | monthly-status engine |
| `weekly.csv` | `load_weekly_bars_csv` | `timestamp,open,high,low,close` | monthly-status engine |
| `option_chain.csv` | `load_option_chain_csv` | `timestamp,symbol,option_type,strike,expiry,bid,ask,ltp,oi,volume` | opt-in S23 contract selection |
| `contract_intraday.csv` | `load_contract_intraday_bars_csv` | `timestamp,symbol,open,high,low,close[,volume]` | selected-contract lifecycle pricing |

The new daily HistoricalData files do not directly match these contracts, but
they can be adapted into them without changing S23 business logic.

## Proposed Flow

Add a historical data adapter layer before the existing runner:

```text
D:\HistoricalData\Nifty spot/options daily files
  -> HSRE NIFTY historical data provider
       -> parse trading-day files
       -> parse option symbols and expiries
       -> build completed daily/weekly/monthly references
       -> build 09:16 option chain with actual premium and OI
       -> build selected-contract OPT_PRV references after selection
       -> build selected-contract ORPT/RC/lifecycle minute bars
  -> existing normalized in-memory/file contracts
  -> existing HistoricalBacktestRunner
  -> existing S23 configs/formulas/policies
  -> existing report/equity/P&L code
```

For Milestone 1, prefer an in-memory adapter consumed by a new command or a
thin HSRE runner wrapper. Only persist normalized CSV/debug artifacts when the
operator asks for evidence. Do not make `HistoricalBacktestRunner` parse raw
HistoricalData files directly.

## Existing Modules To Reuse Unchanged

These should remain the business path:

- `scripts/run_backtest.py` for existing normalized CSV runs.
- `src/tfis/backtest/historical_runner.py` for orchestration.
- `src/tfis/strategy/strategy_evaluator.py` for formula execution.
- `src/tfis/strategy/s23_recalculation.py` and
  `src/tfis/backtest/recalculation.py` for corrected S23 recalculation rules.
- `src/tfis/backtest/entry_missed.py` for ORPT entry-missed checks. The S23
  workbook authority is resolved as LOW-based for both CALL and PUT:
  `09:24:59 AM LL < <Option> Sell Entry`.
- `src/tfis/backtest/option_chain.py` for actual premium + OI selection.
- `src/tfis/backtest/trade_lifecycle.py` for first-pass same-day lifecycle.
- `src/tfis/backtest/contract_intraday.py` for selected-contract lifecycle
  series lookup.
- `src/tfis/backtest/monthly_status_context.py` and `src/tfis/monthly_status/*`
  for independent monthly status.
- `src/tfis/market_structure/structure_calculator.py` for completed-prior-day
  NIFTY market levels.
- `src/tfis/importers/yaml_strategy_loader.py` and the S23 strategy folders for
  config loading.
- `src/tfis/backtest/cost_model.py`, `metrics.py`, and `report_comparison.py`
  for P&L/report support.

## Proposed New Modules

Implemented HSRE modules now include:

- `src/tfis/backtest/nifty_hsre_data_adapter.py`
- `src/tfis/backtest/hsre_market_context.py`
- `src/tfis/backtest/hsre_option_references.py`
- `src/tfis/backtest/hsre_s23_base_decision.py`
- `src/tfis/backtest/hsre_s23_final_order_decision.py`

`hsre_s23_final_order_decision.py` is intentionally a thin orchestration edge:
it starts from the M2 base packet, reads selected-contract and spot evidence
through configured ORPT/RC cutoffs, delegates entry-missed detection to
`S23EntryMissedDetector`, delegates recalculation math to
`S23RecalculationEngine`, delegates RC contract selection to
`OptionChainSelector`, and reruns the M1C exact-contract reference builder only
when a recalculated selection changes the contract.

Milestone 3 stops at final order decision. It does not simulate trigger/fill,
target/SL lifecycle, P&L, or broker behavior.

`hsre_s23_trade_lifecycle.py` is the Milestone 4 result-producing edge for one
accepted final order. It consumes the M3 packet, filters historical option bars
to the exact final contract and to timestamps strictly greater than the final
order-ready timestamp, then delegates entry/target/SL handling to the existing
`TradeLifecycleSimulator` and point-cost handling to `CostModel`. It records
contract-series audit evidence, lifecycle events, same-bar ambiguity handling,
point P&L, rupee-P&L certification status, and a deterministic packet hash. It
does not add a parallel S23 lifecycle, and it does not run all January.

Suggested minimal generic/data-boundary modules:

- `src/tfis/backtest/historical_market_data_provider.py`
  - protocol/dataclasses for provider output if an immediate consumer needs a
    stable abstraction.
- `src/tfis/backtest/nifty_hsre_data_adapter.py`
  - parse `D:\HistoricalData\Nifty` layout, option symbols, session files, and
    produce normalized HSRE day packets.
- `scripts/run_hsre_s23_one_day.py`
  - one-day read-only research runner that calls existing S23 historical
    components. It should not duplicate S23 formulas.

Potential later module:

- `src/tfis/backtest/normalized_historical_dataset_writer.py`
  - optional artifact writer for `daily.csv`, `weekly.csv`, `monthly.csv`,
    `option_levels.csv`, `option_chain.csv`, `spot_intraday.csv`, and
    `contract_intraday.csv` when audit evidence is needed.

## Files That Might Change

Milestone 1 should avoid strategy-specific config changes.

Likely generic additions:

- add one HSRE adapter module under `src/tfis/backtest`
- add one HSRE CLI under `scripts`
- add focused unit tests for symbol parsing, expiry selection, chronology, OI,
  option references, and one-day packet assembly

Possible generic modification:

- `src/tfis/backtest/__init__.py` only if the new adapter must be public.

Possible runner modification:

- `src/tfis/backtest/historical_runner.py` only if the one-day consumer cannot
  pass existing normalized inputs cleanly. The preferred Milestone 1 route is
  to keep it unchanged and adapt data before calling it.

Strategy-specific files expected to change:

- none for Milestone 1.

## Data Model Mapping

Raw spot minute file:

```text
date + time -> timestamp
symbol      -> expected NIFTY
open/high/low/close -> OhlcBar
```

Derived daily NIFTY bars:

```text
group spot minutes by session date
open  = first minute open
high  = max minute high
low   = min minute low
close = last minute close
timestamp = session date close marker, preferably 15:30:00 or last observed minute
```

Derived weekly/monthly bars for monthly status:

```text
group completed derived daily NIFTY bars by ISO week and calendar month
open  = first daily open
high  = max daily high
low   = min daily low
close = last daily close
timestamp = final completed trading day of that week/month
```

Raw option minute rows:

```text
date + time -> timestamp
symbol      -> parse underlying, expiry, strike, CE/PE
CE/PE       -> OptionType.CALL / OptionType.PUT
close       -> ltp for option-chain selection at 09:16
oi          -> absolute OI, required for S23
volume      -> volume
open/high/low/close -> selected-contract references and lifecycle bars
```

Derived `option_chain` rows at S23 selection time:

```text
timestamp = session_date 09:16:00
symbol = raw symbol
option_type = CALL/PUT
strike = parsed strike
expiry = parsed expiry date
bid/ask = ltp unless bid/ask source exists; audit as synthetic spread
ltp = 09:16 close
oi = 09:16 absolute OI
volume = 09:16 volume
```

Milestone 1 should explicitly audit that bid/ask are placeholders if no bid/ask
columns exist, because selection currently does not require spread beyond report
metadata.

Derived `option_levels` for a selected contract:

```text
OPT_PRV_2DHH = max high over the same contract identity's two completed prior sessions
OPT_PRV_2DLL = min low over the same contract identity's two completed prior sessions
OPT_PRV_3DHH = max high over the same contract identity's three completed prior sessions
OPT_PRV_3DLL = min low over the same contract identity's three completed prior sessions
```

Derived selected-contract bars:

```text
spot_intraday.csv       = NIFTY spot minutes for the session
contract_intraday.csv   = minute bars for selected option symbols
option_intraday.csv     = compatibility generic series only after a selected contract exists
```

The long-term HSRE path should prefer `contract_intraday.csv` or in-memory
symbol-keyed bars, because S23 entry, ORPT, RC, and lifecycle semantics depend
on the selected option contract identity.

## Chronology And Lookahead Rules

Required no-lookahead rules:

1. A run for session `D` may use NIFTY spot minutes up to the decision time for
   current-day dynamic spot inputs.
2. `PRV_2D*`, `PRV_3D*`, and `PRV_4D*` spot references must use only completed
   sessions strictly before `D`.
3. Monthly status for `D` may use completed prior month/week references and
   current month/week data only up to the evaluation timestamp.
4. The 09:16 option chain must use only option rows at or before the configured
   chain time. The first implementation should require an exact `09:16:00`
   row and fail closed if missing.
5. Selected-option `OPT_PRV_*` references must be computed only after a
   contract identity is selected, and only from that same symbol's completed
   prior sessions.
6. ORPT and RC snapshots must use the selected contract and NIFTY spot minutes
   at or before `09:24:59` and `09:29:59` respectively.
7. Lifecycle simulation may use later selected-contract minutes only after the
   order time/effective lifecycle start.
8. Expiry progression must come from parsed option symbols and available daily
   chains, not from a hardcoded January 2024 table beyond tests/fixtures.

## OI Rules

For this NIFTY HSRE dataset:

- OI is mandatory for S23 option-chain qualification.
- OI must parse as a non-negative integer or integer-equivalent numeric value.
- Negative, blank, or non-numeric OI fails the row or day audit.
- Minimum OI authority is `500 lots * effective NIFTY lot size for the session
  date`. The static `32500` branch-config value corresponds to January 2026+
  NIFTY lot size `65`; it is not valid for all historical sessions.
- January 2024 HSRE contract selection uses NIFTY lot size `50`, so
  `minimum_oi_units = 25000`.
- Do not introduce an OI-disabled fallback for this dataset.

## Expiry Rules

The option daily file contains the currently traded weekly chain for the
session. HSRE should:

- parse expiry from every option symbol
- derive available expiries for the session from the parsed chain
- search near weekly expiry first through `OptionChainSelector`
- search next weekly expiry only if present and only according to existing S23
  selection semantics
- respect S23 paper/live operating rules separately for expiry-day runtime
  behavior; the historical research slice should report expiry and expiry-day
  state but not silently change rollover or carry-forward policy

The verified January 2024 progression is useful as a fixture expectation:

```text
2024-01-01 .. 2024-01-04 -> 04JAN24
2024-01-05 .. 2024-01-11 -> 11JAN24
2024-01-12 .. 2024-01-18 -> 18JAN24
2024-01-19 .. 2024-01-25 -> 25JAN24
2024-01-29 .. 2024-01-31 -> 01FEB24
```

## S23 Branch Rules Authority

S23 authority remains:

- `docs/architecture/s23_weekly_option_selling_engine_contract.md`
- `src/tfis/rules/s23_rule_matrix.py`
- the four folder strategies under
  `config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D*`

Do not alter S23 formulas, branch mappings, OI thresholds, entry, target, SL,
ORPT, RC, or lifecycle behavior during HSRE adapter work.

## Answers To Audit Questions

A. Current execution flow is documented above from `scripts/run_backtest.py` to
metrics/report generation.

B. Current expected normalized inputs are `daily.csv`, `option_levels.csv`,
`option_intraday.csv`, `spot_intraday.csv`, `monthly.csv`, `weekly.csv`,
`option_chain.csv`, and `contract_intraday.csv`.

C. Yes. The new daily HistoricalData files can be adapted into those contracts
without changing business logic. The key missing piece is selected-contract
reference generation after contract selection.

D. Missing abstraction: a historical market data provider/adapter that can
produce one session packet from raw daily files. Add a formal protocol only if
the first S23 one-day consumer needs it.

E. Reusable modules are listed in "Existing Modules To Reuse Unchanged".

F. Generic additions are likely needed under `src/tfis/backtest` plus a CLI.
`historical_runner.py` should change only if in-memory one-day consumption
cannot be expressed through existing contracts.

G. Strategy-specific file changes should be none for Milestone 1.

H. Completed-prior-day references come from spot minute files aggregated into
daily bars and filtered strictly before the session date.

I. `OPT_PRV_2DHH`, `OPT_PRV_2DLL`, `OPT_PRV_3DHH`, and `OPT_PRV_3DLL` come
from the same selected option symbol across the prior two or three completed
sessions. If that exact symbol did not trade on enough prior sessions, fail
closed with explicit evidence instead of borrowing from another strike/expiry.

J. ORPT/RC should be driven from selected-contract minute bars and NIFTY spot
minute bars at the existing S23 cutoffs. Use existing `S23EntryMissedDetector`
and `S23RecalculationEngine`; do not duplicate formulas.

K. Contract selection should build actual `OptionChainContract` rows at 09:16
with parsed expiry/strike/side, `ltp=close`, and absolute OI. Then call
`OptionChainSelector`.

L. Smallest safe vertical slice: one session day, one known January 2024 date
with enough prior spot and selected-contract history, branch-aware monthly
status enabled, 09:16 option-chain selection enabled, selected-contract
OPT_PRV references generated, ORPT/RC evidence audited, and contract-specific
lifecycle run for the selected contracts.

## Risk Areas

- The existing historical runner expects `option_levels` before strategy
  evaluation, but true S23 selected-contract option references are only known
  after contract selection. Milestone 1 must avoid a circular dependency by
  doing a two-pass one-day evaluation: compute spot formulas and candidate
  range, select contract from 09:16 chain, compute selected-contract
  `OPT_PRV_*`, then evaluate final trade levels through existing formulas.
- Current normalized `option_intraday.csv` is generic. HSRE should use
  selected-contract symbol-keyed bars to avoid lifecycle prices from the wrong
  option.
- Raw option files do not contain bid/ask. If existing audit structures require
  bid/ask, placeholders must be explicit and must not influence selection.
- Existing S23 recalculation code path should continue to consume the resolved
  LOW-based ORPT entry-missed result for both CALL and PUT before applying RC
  formulas.
- Performance may matter: daily option files are full chains. The adapter
  should index by session date, expiry, strike, side, symbol, and timestamp
  rather than repeatedly scanning all rows.
- Weekly/monthly aggregation must handle exchange holidays and short weeks by
  grouping observed trading days, not calendar assumptions.
- Exact prior same-contract history may be unavailable around new expiries; the
  correct behavior is an auditable no-trade/no-reference result.

## Known Pre-Existing Failures / Drift

Keep separate from HSRE regressions:

- `tests/unit/test_s23_all_branches.py` has known stale expected start-strike
  samples that conflict with later workbook-certified S23 evidence.
- During this audit, a focused historical/option-chain baseline exposed
  existing drift in `test_option_chain_selection.py` and
  `test_historical_backtest_monthly_status_mode.py`: some tests expect
  "closest to ideal premium" / spread tie-break wording while the current
  selector implementation reports rule-sheet search-order selection. This
  should not be fixed as part of the audit.

## Milestone Plan

### Milestone 1: One-Day HSRE S23 Packet

Acceptance criteria:

- Parse one NIFTY spot file and one option daily file.
- Parse option symbols into expiry, strike, and CALL/PUT.
- Derive completed prior NIFTY daily references without lookahead.
- Build 09:16 option-chain rows with actual premium and absolute OI.
- Select the S23 contract through the existing selector and S23 configs.
- Compute selected-contract `OPT_PRV_*` only from the same contract identity.
- Drive ORPT/RC snapshots from selected-contract and spot minute data.
- Run the existing S23 one-day historical path without changing formulas.
- Emit an audit payload showing chronology, selected contract, OI, references,
  ORPT/RC, lifecycle source, and no-lookahead proof.

Recommendation: GO for Milestone 1 design/implementation after this audit, with
the constraint that no S23 strategy config or formula files change.

### Milestone 2: Normalized Dataset Writer

Acceptance criteria:

- Produce normalized CSV/debug artifacts equivalent to current runner inputs.
- Re-run the same one-day result from persisted normalized artifacts.
- Include OI and expiry audit summaries.

### Milestone 3: January 2024 Month Run

Acceptance criteria:

- Run all eligible January 2024 sessions.
- Validate expiry progression from parsed symbols.
- Report skipped days separately from rejected/no-entry trades.
- Produce JSON and Markdown research reports with P&L/equity metrics.

### Milestone 4: Performance And Multi-Month Runs

Acceptance criteria:

- Add indexing/caching sufficient for multi-month runs.
- Preserve deterministic output.
- Keep all unit tests network-free and broker-free.

## Files Inspected

- `AGENTS.md` instructions supplied in the session
- `docs/operations/ai_change_agreement.md`
- `docs/operations/project_rulebook.md`
- `docs/operations/next_steps.md`
- `docs/architecture/s23_weekly_option_selling_engine_contract.md`
- `docs/architecture/monthly_status_engine_design.md`
- `scripts/run_backtest.py`
- `src/tfis/backtest/historical_runner.py`
- `src/tfis/backtest/csv_loader.py`
- `src/tfis/backtest/option_chain.py`
- `src/tfis/backtest/contract_intraday.py`
- `src/tfis/backtest/trade_lifecycle.py`
- `src/tfis/backtest/entry_missed.py`
- `src/tfis/backtest/recalculation.py`
- `src/tfis/backtest/monthly_status_context.py`
- `src/tfis/backtest/shared_data_adapter.py`
- `src/tfis/strategy/strategy_evaluator.py`
- `src/tfis/strategy/s23_recalculation.py`
- `src/tfis/market_structure/structure_calculator.py`
- `src/tfis/monthly_status/*`
- `src/tfis/importers/__init__.py`
- `src/tfis/importers/yaml_strategy_loader.py`
- `src/tfis/domain/strategy_rule.py`
- `src/tfis/rules/s23_rule_matrix.py`
- all four S23 strategy folders under `config/strategies/options_sell/nifty`
- `tests/unit/test_historical_runner.py`
- `tests/unit/test_option_chain_selection.py`
- `tests/integration/test_historical_backtest_monthly_status_mode.py`
- `tests/integration/test_historical_backtest_s23_recalculation_mode.py`
- `tests/integration/test_contract_specific_lifecycle_mode.py`
- sample files under `D:\HistoricalData\Nifty`

## Baseline Tests For This Audit

Read-only baseline commands run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_s21_historical_replay.py tests\unit\test_s21_pure_strategy_engine.py tests\unit\test_csv_historical_market_data.py -q
```

Result: failed during collection because
`tests/unit/test_s21_historical_replay.py` imports `S21ReplayEngine`, while the
current committed `tfis.replay.s21_replay` exposes the sealed-evidence
`run_s21_replay` path.

```powershell
powershell -ExecutionPolicy Bypass -File .\VALIDATE_TFIS_HISTORICAL_CSV_ADAPTER_V1.ps1
```

Result before this audit: syntax and focused adapter tests passed, BANKNIFTY
audit ran, then the probe exceeded the 120 second command timeout. A direct
probe completed later in about 75 seconds. This is unrelated to the new NIFTY
HSRE dataset but supports the performance risk noted above.

Additional HSRE/S23 baseline tests should be run after this document is written
and recorded in the task close-out.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_historical_runner.py tests\unit\test_option_chain_selection.py tests\integration\test_historical_backtest_monthly_status_mode.py tests\integration\test_historical_backtest_s23_recalculation_mode.py tests\integration\test_contract_specific_lifecycle_mode.py -q
```

Result: `21 passed, 7 failed`.

Observed failures:

- monthly-status historical mode now reports `12` evaluations where tests
  expected `10`
- option-chain monthly-status fixture test expected a selected first contract,
  but current selection returned no selected contract for that fixture path
- one S23 recalculation fixture expected start strike `21708`, while current
  code returned `22576`
- contract-specific lifecycle fixture tests expected selected CE/PE contracts
  and full contract-specific coverage, but current option-chain selection
  yielded `None` selected contracts in those paths

These are recorded as baseline drift for HSRE planning. They were not fixed in
this audit.

## Milestone 1A Implementation: Historical NIFTY Market Data Provider

Implemented on 2026-08-09 as data infrastructure only.

Files added:

- `src/tfis/backtest/nifty_hsre_data_adapter.py`
- `tests/unit/test_nifty_hsre_data_adapter.py`
- `tests/integration/test_nifty_hsre_real_data.py`
- `VALIDATE_HSRE_M1A_NIFTY_DATA_PROVIDER.ps1`

Files modified:

- `src/tfis/backtest/__init__.py`
- `docs/architecture/hsre_s23_historical_data_integration_audit.md`
- `docs/operations/current_state.md`
- `docs/operations/next_steps.md`
- `docs/operations/milestones.md`

Architecture chosen:

- one strategy-neutral provider, `NiftyHsreHistoricalMarketDataProvider`
- immutable dataclasses for raw historical spot bars, option identities, option
  minute observations, option-chain observations, daily aggregation, and audit
  summaries
- bounded per-session LRU caches for spot and option files, defaulting to 8
  sessions, so repeated access to the same day does not reparse full option
  files while multi-year data is not preloaded
- exact reads only for option-chain snapshots; non-exact chain reads fail
  closed rather than substituting another minute

The provider does not:

- run S23 end to end
- select an S23 contract
- compute S23 entry, target, stoploss, ORPT, RC, lifecycle, or P&L
- apply S23 minimum OI or any strategy threshold
- modify S23 YAML, formulas, rule matrix, monthly-status rules, broker code, or
  paper/live runtime

Provider capabilities:

- parse option symbols such as `NIFTY04JAN2421700CE`,
  `NIFTY04JAN2421700PE`, and `NIFTY01FEB2422000CE`
- resolve daily spot/options files by parsed session date
- load chronological spot minute bars with provenance
- read exact spot bars and spot bars through a cutoff without lookahead
- load chronological option minute bars with parsed identity, OI, volume, and
  provenance
- discover available expiries from option symbols
- build exact timestamp option-chain observations with `ltp=close`,
  `bid=None`, `ask=None`, and no synthetic bid/ask source
- retrieve same-contract session bars by exact underlying, expiry, strike, and
  option type
- aggregate spot and same-contract option daily OHLC with completeness metadata
- retrieve prior completed same-contract daily bars without crossing current
  session, expiry, strike, or CE/PE
- audit a real option session for row count, contract count, CE/PE count,
  strike range, OI min/max, negative/zero OI count, exact-chain count, and
  available expiries

Real Jan-1 dataset observation from `D:\HistoricalData\Nifty`:

```text
session=2024-01-01
spot_minute_count=375
option_row_count=39215
contract_count=167
CE=73
PE=94
strike_range=18300-23300
oi_min=0
oi_max=11728950
negative_oi_count=0
zero_oi_count=15
chain_0916_contract_count=124
available_expiries=['2024-01-04']
```

Validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\VALIDATE_HSRE_M1A_NIFTY_DATA_PROVIDER.ps1
```

Result:

- syntax passed
- focused provider unit tests: `13 passed`
- optional real-data Jan-1 smoke: `1 passed`
- baseline regression comparison preserved the known drift:
  `7 failed, 21 passed`

## Milestone 1B Implementation: Historical Market Context Builder

Implemented on 2026-08-09 as data/context infrastructure only.

Files added:

- `src/tfis/backtest/hsre_market_context.py`
- `tests/unit/test_hsre_market_context.py`
- `tests/integration/test_hsre_market_context_real_data.py`
- `VALIDATE_HSRE_M1B_HISTORICAL_MARKET_CONTEXT.ps1`

Files modified:

- `src/tfis/backtest/__init__.py`
- `docs/architecture/hsre_s23_historical_data_integration_audit.md`
- `docs/operations/current_state.md`
- `docs/operations/next_steps.md`
- `docs/operations/milestones.md`

Pre-implementation cache review:

- 1A provider cache identity is safe for this milestone: spot and option caches
  live on the provider instance, so separate roots/instruments cannot
  contaminate each other unless a caller deliberately reuses the same provider.
- 09:16/09:25 views are derived by filtering immutable full-session tuples
  through the requested timestamp; no mutable business snapshot is cached.
- 1B adds a builder-local completed-daily aggregation cache keyed by session
  date for the same provider instance only. This improves January discovery
  performance without changing provider cache identity or crossing data roots.

Architecture chosen:

- one strategy-neutral context builder, `NiftyHsreMarketContextBuilder`
- one packet dataclass, `HsreMarketContextPacket`, with status, market levels,
  current-day high/low through evaluation, daily provenance, current-day
  provenance, weekly/monthly grouped provenance, monthly status diagnostics,
  and explicit no-lookahead assertions
- existing `MarketStructureCalculator.build_market_levels` is reused for
  PRV/current-day market levels
- existing `build_monthly_status_context` and `MonthlyStatusEngine` are reused
  for independent monthly status; no monthly-status formulas were duplicated
- weekly bars are grouped by observed ISO-week trading sessions; monthly bars
  are grouped by observed calendar-month trading sessions
- fail-closed statuses are explicit:
  `INSUFFICIENT_DAILY_LOOKBACK`, `INSUFFICIENT_WEEKLY_LOOKBACK`,
  `INSUFFICIENT_MONTHLY_LOOKBACK`, and
  `INSUFFICIENT_MONTHLY_STATUS_LOOKBACK`
- deterministic packet hashing is provided by JSON-normalizing the packet and
  hashing with SHA-256

The builder does not:

- run S23 end to end
- select an S23 contract
- compute S23 entry, target, stoploss, ORPT, RC, lifecycle, P&L, or equity
- compute selected-contract `OPT_PRV_*`
- change S23 YAML, formulas, rule matrix, monthly-status rules, broker code, or
  paper/live runtime
- fix the known `7 failed, 21 passed` historical baseline drift

Real January 2024 context discovery from `D:\HistoricalData\Nifty` at 09:16:

```text
first_underlying_lookback_ready=2024-01-01
first_monthly_status_ready=2024-01-01
first_fully_context_ready=2024-01-01
status=READY
monthly_status=BULL_CF
monthly_trigger=LOOKBACK::BULL_CF_CONTINUES
hash=1a74f0e72a5788f920dfd143f1964721c790a7dce8c6797b75771b5da9930d3d
completed_prior=2023-12-26,2023-12-27,2023-12-28,2023-12-29
PRV_2DHH=21798.6
PRV_2DLL=21676.9
PRV_3DHH=21798.6
PRV_3DLL=21495.8
PRV_4DHH=21798.6
PRV_4DLL=21329.45
current_high=21737.35
current_low=21695.05
current_last=2024-01-01T09:16:00
```

No-lookahead evidence:

- completed prior sessions for the first ready packet are strictly before
  `2024-01-01`
- current-day provenance ends exactly at `2024-01-01T09:16:00`
- unit tests prove later 09:17 and 09:26 extremes do not enter 09:16/09:25
  packets
- grouped weekly/monthly provenance is built from the exact observed daily
  inputs used for the context packet, including the partial current day, rather
  than re-reading full current-day data

Validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\VALIDATE_HSRE_M1B_HISTORICAL_MARKET_CONTEXT.ps1
```

Result:

- syntax passed
- focused 1B unit tests: `8 passed`
- no-lookahead and partial-view tests: `2 passed, 6 deselected`
- insufficient-lookback fail-closed tests: `3 passed, 5 deselected`
- deterministic packet hash test: `1 passed, 7 deselected`
- optional real-data January context smoke: `1 passed`
- baseline regression comparison preserved the known drift:
  `7 failed, 21 passed`

Recommendation for next milestone: conditional GO for a narrowly scoped
Milestone 2 design of the first historical S23 decision packet, but NO-GO for
S23 execution until it explicitly proves selected-contract option references,
option-chain chronology, ORPT/RC chronology, and lifecycle-source identity
without changing S23 strategy YAML, formulas, rule matrix, monthly-status
business logic, paper/live runtime, or broker behavior.

## Milestone 1C Implementation: Selected-Contract Historical Reference Builder

Implemented on 2026-08-09 as explicit-contract reference infrastructure only.

Files added:

- `src/tfis/backtest/hsre_option_references.py`
- `tests/unit/test_hsre_option_references.py`
- `tests/integration/test_hsre_option_references_real_data.py`
- `VALIDATE_HSRE_M1C_SELECTED_CONTRACT_REFERENCES.ps1`

Files modified:

- `src/tfis/backtest/nifty_hsre_data_adapter.py`
- `src/tfis/backtest/__init__.py`
- `docs/architecture/hsre_s23_historical_data_integration_audit.md`
- `docs/operations/current_state.md`
- `docs/operations/next_steps.md`
- `docs/operations/milestones.md`

Existing TFIS reference model reused:

- `src/tfis/backtest/csv_loader.py::OptionLevelsSnapshot`
- aliases: `OPT_PRV_2DHH`, `OPT_PRV_2DLL`, `OPT_PRV_3DHH`,
  `OPT_PRV_3DLL`
- `StrategyEvaluator` receives these through `runtime_values`; Milestone 1C
  proves conversion to the existing input shape but does not call
  `StrategyEvaluator`

Architecture chosen:

- one strategy-neutral builder,
  `NiftyHsreSelectedContractReferenceBuilder`
- the builder accepts an explicit `HistoricalOptionIdentity`; it never chooses
  or ranks contracts for S23
- exact identity matching includes underlying, expiry, strike, and CE/PE
- completed prior sessions must be strictly before the requested session
- READY requires at least three exact prior contract sessions so all four
  `OPT_PRV_*` values are available
- insufficient history returns `INSUFFICIENT_OPTION_LOOKBACK` with no default,
  zero, borrowed, reduced, or current-day references
- READY packets convert to `OptionLevelsSnapshot`
- packet hashing is deterministic through canonical JSON plus SHA-256
- provider exact-contract reads were optimized to parse only requested-symbol
  rows when a full session cache is not already loaded; this is a data-access
  optimization only, not a rule change
- 1C discovery uses a configurable recent calendar scan window, defaulting to
  45 days, so weekly option history is inspected from actual files without
  scanning stale years of unrelated contracts

The builder does not:

- run S23 end to end
- select an S23 contract
- choose S23 start/end strike
- compute S23 entry, target, stoploss, FSL, TRP, ORPT, RC, lifecycle, P&L, or
  equity
- change S23 YAML, formulas, rule matrix, monthly-status rules, broker code, or
  paper/live runtime

Reference formula semantics implemented:

```text
OPT_PRV_2DHH = max(high) over the last two completed exact-contract sessions
OPT_PRV_2DLL = min(low)  over the last two completed exact-contract sessions
OPT_PRV_3DHH = max(high) over the last three completed exact-contract sessions
OPT_PRV_3DLL = min(low)  over the last three completed exact-contract sessions
```

Real January 2024 selected-contract discovery from `D:\HistoricalData\Nifty`:

```text
session=2024-01-01
contract=NIFTY04JAN2422250CE
expiry=2024-01-04
strike=22250
side=CALL
prior_available=2023-12-29
two_day_ready=False
three_day_ready=False
status=INSUFFICIENT_OPTION_LOOKBACK

session=2024-01-01
contract=NIFTY04JAN2420400PE
expiry=2024-01-04
strike=20400
side=PUT
prior_available=2023-12-29
two_day_ready=False
three_day_ready=False
status=INSUFFICIENT_OPTION_LOOKBACK

session=2024-01-11
contract=NIFTY11JAN2422200CE
expiry=2024-01-11
strike=22200
side=CALL
prior_available=2024-01-05,2024-01-08,2024-01-09,2024-01-10
two_day_ready=True
three_day_ready=True
status=READY
OPT_PRV_2DHH=3.7
OPT_PRV_2DLL=0.35
OPT_PRV_3DHH=5.35
OPT_PRV_3DLL=0.35
hash=f8d28bfbd9660701e4d2906de6e9f3ed47295a875dc0fdb46c4685911b61dea6

session=2024-01-11
contract=NIFTY11JAN2420850PE
expiry=2024-01-11
strike=20850
side=PUT
prior_available=2024-01-05,2024-01-08,2024-01-09,2024-01-10
two_day_ready=True
three_day_ready=True
status=READY
OPT_PRV_2DHH=2.8
OPT_PRV_2DLL=0.6
OPT_PRV_3DHH=2.8
OPT_PRV_3DLL=0.6

session=2024-01-25
contract=NIFTY25JAN2422300CE
expiry=2024-01-25
strike=22300
side=CALL
prior_available=2024-01-19,2024-01-20,2024-01-23,2024-01-24
two_day_ready=True
three_day_ready=True
status=READY
OPT_PRV_2DHH=5.5
OPT_PRV_2DLL=0.5
OPT_PRV_3DHH=12.0
OPT_PRV_3DLL=0.5
```

No-lookahead and isolation evidence:

- current session rows are excluded from every `OPT_PRV_*` calculation
- future session rows are excluded even when present and extreme
- adversarial tests prove current-day and future-day highs/lows do not alter
  prior references
- expiry isolation rejects `04JAN24` versus `11JAN24`
- strike isolation rejects `21700` versus `21750`
- CE/PE isolation rejects `CE` versus `PE`
- expiry-roll behavior is file-driven: `11JAN24` contracts with actual
  pre-roll rows are READY, while `11JAN24` contracts without exact prior rows
  fail closed

Validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\VALIDATE_HSRE_M1C_SELECTED_CONTRACT_REFERENCES.ps1
```

Result:

- syntax passed
- focused 1C unit tests: `10 passed`
- identity-isolation tests: `1 passed, 9 deselected`
- no-lookahead tests: `2 passed, 8 deselected`
- insufficient-history tests: `2 passed, 8 deselected`
- optional real-data contract-history discovery: `1 passed`
- deterministic hash tests: `1 passed, 9 deselected`
- `OptionLevelsSnapshot` compatibility conversion tests:
  `2 passed, 8 deselected`
- baseline regression comparison preserved the known drift:
  `7 failed, 21 passed`

Recommendation for next milestone: conditional GO to design Milestone 2 as the
first actual historical S23 decision packet, but NO-GO for execution until that
slice proves the complete chronology:

```text
underlying context
-> existing option-chain selection
-> exact selected-contract OPT_PRV references
-> existing StrategyEvaluator input
```

Milestone 2 must still avoid changing S23 YAML, formulas, rule matrix,
monthly-status business logic, paper/live runtime, or broker behavior.

## Milestone 2 Implementation: First Historical S23 Base Decision Packet

Implemented on 2026-08-09 as a read-only historical base-decision packet only.

Files added:

- `src/tfis/backtest/hsre_s23_base_decision.py`
- `tests/unit/test_hsre_s23_base_decision.py`
- `tests/integration/test_hsre_s23_base_decision_real_data.py`
- `VALIDATE_HSRE_M2_S23_BASE_DECISION.ps1`

Files modified:

- `src/tfis/backtest/__init__.py`
- `docs/architecture/hsre_s23_historical_data_integration_audit.md`
- `docs/operations/current_state.md`
- `docs/operations/next_steps.md`
- `docs/operations/milestones.md`

Two-pass architecture:

```text
PASS A
M1B NIFTY context
  -> existing monthly-status branch selection
  -> pre-selection start/end/ideal/minimum premium formulas through FormulaEngine
  -> actual 09:16 historical option chain
  -> existing OptionChainSelector
  -> exact selected contract

PASS B
exact selected contract
  -> M1C selected-contract reference builder
  -> OptionLevelsSnapshot
  -> existing StrategyEvaluator
  -> base Entry / Target / Stoploss
```

Existing TFIS authorities reused:

- `NiftyHsreMarketContextBuilder` for underlying context and monthly status
- `StrategyBranchSelector` for monthly-status branch activation
- `FormulaEngine` for pre-selection S23 formulas needed before contract
  selection
- `OptionChainSelector` for premium/OI/expiry contract selection
- `NiftyHsreSelectedContractReferenceBuilder` for exact selected-contract
  `OPT_PRV_*`
- `OptionLevelsSnapshot` as the compatibility shape
- `StrategyEvaluator` as the authority for base Entry, Target, and Stoploss

The implementation does not:

- run ORPT
- run RC
- run recalculation
- detect entry missed
- trigger or fill an order
- run lifecycle
- calculate P&L or equity
- modify S23 YAML, formulas, parameters, rule matrix, monthly-status formulas,
  market-structure formulas, contract-selection business rules, or
  StrategyEvaluator formulas
- modify paper/live runtime or broker behavior

Contract-selection and history clarification:

- Existing `OptionChainSelector` has no rule to continue searching when the
  premium/OI-selected contract lacks exact option-history references.
- Therefore M2 fails the selected candidate/day closed as
  `INSUFFICIENT_OPTION_LOOKBACK` instead of choosing a different contract for
  history availability.

Real January 2024 discovery from `D:\HistoricalData\Nifty`:

```text
attempt=2024-01-01
monthly_status=BULL_CF
branches=NIFTY_OP_SELL_WK_DIFF_2D_3D,NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT
contract_selection=CALL selected by existing selector; PUT no minimum premium
final_status=INSUFFICIENT_OPTION_LOOKBACK
reason=selected CALL lacked three exact prior contract sessions

attempt=2024-01-02
monthly_status=BULL_CF
branches=NIFTY_OP_SELL_WK_DIFF_2D_3D,NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT
contract_selection=no qualifying contract for either active branch
final_status=NO_QUALIFYING_CONTRACT

attempt=2024-01-03
monthly_status=BULL_CF
branch=NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT
selected=NIFTY04JAN2421900PE
selected_expiry=2024-01-04
selected_strike=21900
selected_option_type=PUT
premium_0916=294.9
oi_0916=1209400
volume_0916=23800
candidate_count=67
premium_rejection_count=4
oi_rejection_count=0
expiry_rejection_count=0
qualified_count=3
prior_exact_contract_sessions=2023-12-29,2024-01-01,2024-01-02
OPT_PRV_2DHH=335.0
OPT_PRV_2DLL=92.55
OPT_PRV_3DHH=335.0
OPT_PRV_3DLL=92.55
base_entry=85.60875
base_target=34.243500000000004
base_stoploss=136.974
packet_hash=cf5f29fb064b156a562a4e23dfee53fff4cc3e160662768805419432310b083a
final_status=READY
```

No-lookahead evidence:

- spot context is limited to the 09:16 evaluation timestamp
- option chain uses exact 09:16 historical option rows only
- bid/ask are populated as `ltp` placeholders only to satisfy the existing
  `OptionChainContract` dataclass; the current selector does not use bid/ask
  for qualification, ranking, tie-breaking, or spread logic
- M1C selected-contract references use completed prior sessions only and
  exclude current/future option rows
- tests include adversarial current-session and future-session option
  extremes that do not alter selected-contract `OPT_PRV_*`

Validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\VALIDATE_HSRE_M2_S23_BASE_DECISION.ps1
```

Result:

- syntax passed
- focused M2 tests: `8 passed`
- no-lookahead tests: `1 passed, 7 deselected`
- option-history insufficiency tests: `1 passed, 7 deselected`
- optional real January S23 base-decision discovery: `1 passed`
- deterministic one-day packet test: `1 passed, 7 deselected`
- focused S23 regression signature preserved:
  `4 failed, 32 passed`
- historical baseline signature preserved:
  `7 failed, 21 passed`

Recommendation for next milestone: conditional GO for Milestone 3 as a
read-only ORPT/RC/recalculation evidence packet, but NO-GO for trigger/fill,
lifecycle, P&L, paper/live runtime, broker behavior, or any S23 rule/config
change until that separate evidence slice is implemented and validated.

## Milestone 5 Implementation: S23 January 2024 End-To-End Month Run

Implemented on 2026-08-09 as a historical reporting layer over the accepted
M1A-M4 pipeline.

Files added:

- `src/tfis/backtest/hsre_s23_month_run.py`
- `scripts/run_hsre_s23_january_2024.py`
- `tests/integration/test_hsre_s23_january_2024_real_data.py`
- `VALIDATE_HSRE_M5_S23_JAN2024.ps1`

Files modified:

- `src/tfis/backtest/__init__.py`
- `docs/architecture/hsre_s23_historical_data_integration_audit.md`
- `docs/operations/current_state.md`
- `docs/operations/next_steps.md`
- `docs/operations/milestones.md`

Report artifacts:

- `reports/hsre/S23/2024-01/daily_decisions.csv`
- `reports/hsre/S23/2024-01/trades.csv`
- `reports/hsre/S23/2024-01/non_trades.csv`
- `reports/hsre/S23/2024-01/rejected_candidates_summary.csv`
- `reports/hsre/S23/2024-01/entry_distance.csv`
- `reports/hsre/S23/2024-01/summary.json`
- `reports/hsre/S23/2024-01/summary.md`

Architecture:

- `HsreS23January2024Runner` discovers observed January 2024 spot sessions from
  `D:\HistoricalData\Nifty`.
- Each session is evaluated through `HsreS23TradeLifecycleBuilder`, which in
  turn reuses the accepted M1A-M4 components.
- The month runner only aggregates evidence and writes reports. It does not
  alter S23 formulas, branch selection, premium/OI selection, ORPT/RC,
  recalculation, target/SL, paper lifecycle, broker behavior, or workbook
  authority.
- Point P&L is authoritative for the historical lifecycle output. Rupee P&L is
  explicitly `NOT_CERTIFIED` because Jan-2024 lot size/quantity effective-date
  treatment is outside M5.

January 2024 result:

```text
observed_trading_days=22
date_coverage=2024-01-01..2024-01-31
observed_sessions=2024-01-01,2024-01-02,2024-01-03,2024-01-04,2024-01-05,
  2024-01-08,2024-01-09,2024-01-10,2024-01-11,2024-01-12,2024-01-15,
  2024-01-16,2024-01-17,2024-01-18,2024-01-19,2024-01-20,2024-01-23,
  2024-01-24,2024-01-25,2024-01-29,2024-01-30,2024-01-31
final_orders_ready=8
normal_orders_ready=8
recalculated_orders_ready=0
entry_missed_at_orpt=0
entries_triggered=1
entries_not_triggered=7
closed_trades=1
incomplete_trades=0
trade=2024-01-17 NIFTY18JAN2421650CE TARGET_HIT
net_point_pnl=90.4095
profit_factor=null because there were no losing trades
max_drawdown_points=0.0
rupee_pnl_status=NOT_CERTIFIED
```

CE/PE breakdown:

```text
CALL orders_ready=3 entries_triggered=1 trades=1 wins=1 losses=0 net_points=90.4095
PUT  orders_ready=5 entries_triggered=0 trades=0 wins=0 losses=0 net_points=0.0
```

Entry-distance summary:

```text
rows=8
entry_touched=1
not_touched=7
min_abs_points=0.0
max_abs_points=345.7
average_abs_points=93.54703125
```

Deterministic CSV signatures:

```text
daily_decisions.csv=1ec05964521cb3a1608d28c49785f8eed45c49493db6b4c8ef6ed4af7f0844f3
trades.csv=13750a4a68c7b306092ae28ebc0c96dcf056f7cf1d0e451dd22282a818d521aa
non_trades.csv=bafebb3786f68ca1cdba0dbea9647cdd24afcf3b56c54974c1c622a6aba2fd64
rejected_candidates_summary.csv=c1d3c6d73d6b02f3cd4bcf6a09b6a7d44a712366acb28784b40d011d8f63cdab
entry_distance.csv=c1f21db21151c62284adebfec2ef3dd089de864d1e19277394994f001956032b
```

Validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\VALIDATE_HSRE_M5_S23_JAN2024.ps1
```

Result:

- syntax checks passed
- focused S23 authority / recalculation / paper parity tests: `24 passed`
- M4 Jan-3 lifecycle regression: `1 passed`
- M5 January regression: `1 passed`
- authoritative January report generated in `247.619s`
- determinism rerun generated in `249.528s`
- repeat-run CSV hashes matched

Recommendation for next milestone: conditional GO for the next HSRE reporting
or certification slice, but NO-GO for rupee P&L certification, quantity/lot-size
assumptions, multi-month portfolio conclusions, or live/paper rule changes
without a separate scoped request.

## S23 Rule-Authority Correction And January 2024 Rerun

Implemented on 2026-08-09 as a narrow authority alignment after Milestone 5.

Authoritative corrections:

- strike buffer remains `1.2%`
- ideal premium is `reference * 1.60%`
- minimum premium is `reference * 1.20%`
- minimum OI is `500 lots * effective historical NIFTY lot size`
- January 2024 NIFTY lot size is `50`, so minimum OI units are `25000`
- January 2026 NIFTY lot size is `65`, so minimum OI units are `32500`
- selected-contract `OPT_PRV_*` remains exact same-final-contract and
  fail-closed
- ORPT entry-missed remains LOW-based for both CALL and PUT

Files added for this correction:

- `src/tfis/market_metadata/lot_size.py`
- `tests/unit/test_market_metadata_lot_size.py`
- `scripts/compare_hsre_s23_january_rule_correction.py`
- `VALIDATE_S23_RULE_AUTHORITY_AND_HSRE_JAN2024_RERUN.ps1`

Corrected January artifacts:

- `reports/hsre/S23/2024-01-rule-corrected/daily_decisions.csv`
- `reports/hsre/S23/2024-01-rule-corrected/trades.csv`
- `reports/hsre/S23/2024-01-rule-corrected/non_trades.csv`
- `reports/hsre/S23/2024-01-rule-corrected/rejected_candidates_summary.csv`
- `reports/hsre/S23/2024-01-rule-corrected/entry_distance.csv`
- `reports/hsre/S23/2024-01-rule-corrected/summary.json`
- `reports/hsre/S23/2024-01-rule-corrected/before_after_rule_correction.md`

Before/after result:

```text
old_final_orders_ready=8
corrected_final_orders_ready=8
old_call_ready=3
corrected_call_ready=2
old_put_ready=5
corrected_put_ready=6
old_entries_triggered=1
corrected_entries_triggered=0
old_trades=1
corrected_trades=0
old_net_points=90.4095
corrected_net_points=0.0
old_average_entry_distance_points=93.54703125
corrected_average_entry_distance_points=134.1534375
old_orpt_misses=0
corrected_orpt_misses=0
old_recalculations=0
corrected_recalculations=0
```

Validation:

```powershell
powershell -ExecutionPolicy Bypass -File .\VALIDATE_S23_RULE_AUTHORITY_AND_HSRE_JAN2024_RERUN.ps1
```

Result:

- syntax passed
- focused rule-authority / lot-size / premium / OI / exact-history / ORPT
  tests: `49 passed`
- authority and paper-parity suite: `48 passed`
- historical baseline expected signature preserved: `7 failed, 21 passed`
- focused S23 expected signature preserved: `4 failed, 32 passed`
- corrected January rerun generated 22 sessions, 8 ready orders, 0 triggers,
  and 0 trades
- deterministic rerun matched hashes for daily decisions, trades, non-trades,
  rejected-candidate summary, entry distance, and `summary.json`
