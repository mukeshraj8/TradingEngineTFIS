# TFIS Manual Operator Guide

This guide explains **how to use TFIS manually for S23** in plain language.

It is written for someone who wants to:

- understand what each TFIS workflow is for
- know when to use each command
- know what inputs are required
- know what outputs to inspect
- know what “good” and “bad” results look like

This guide is intentionally user-friendly first. It does not assume you already
know TFIS internals.

## 1. What TFIS Is Doing For S23

TFIS is the safe, reviewable implementation of the `S23` weekly NIFTY
options-selling strategy.

Very simply, TFIS helps you do four kinds of work:

1. **Check that the S23 logic is loaded correctly**
   - “Can TFIS read the strategy and compute a trade plan at all?”
2. **Run historical simulations**
   - “What would S23 have done on past dates?”
3. **Run paper-mode simulations**
   - “If we pretend to trade, what plan / fill / exit would TFIS produce?”
4. **Run ingress-only validations**
   - “Can TFIS safely consume incoming market data and reach a valid decision,
     without trading yet?”

That means TFIS is not just “one command.” It is a set of controlled stages.

## 2. The S23 Journey Inside TFIS

If you are new, think of S23 in TFIS like this:

### Stage A: Strategy logic

TFIS reads the S23 formulas and decides things like:

- should this be a Call or Put branch?
- what strike range is valid?
- what is the ideal premium?
- what is the minimum premium?
- what is the entry price?
- what is the target?
- what is the stoploss?

### Stage B: Historical simulation

TFIS applies that plan to past market data and checks:

- was entry touched?
- was target hit?
- was stoploss hit?
- was the position squared off at EOD?

### Stage C: Paper-mode simulation

TFIS does the same thing in a controlled “paper” environment:

- create the session
- review the plan
- optionally simulate fill/no-fill
- optionally simulate same-day lifecycle
- compare result to historical expectation

### Stage D: Ingress-only validation

TFIS checks whether incoming market data is healthy enough to make a safe S23
decision:

- is data fresh?
- did the option chain arrive?
- did the selected contract quote arrive?
- are ORPT and RC timings inside threshold?

This stage is deliberately safer than paper fills. It stops at the planning
decision unless you explicitly use later paper tools.

## 3. Important S23 Terms In Plain English

Before the commands, here are the terms you will keep seeing.

### Monthly Status

This is the market classification that decides which S23 branch is active.

Examples:

- `BULL`
- `BULL_CF`
- `BEAR`
- `BEAR_CF`

This matters because S23 has four main branch variants.

### Branch

A branch is one specific S23 rule family.

Examples:

- Bull / Bull CF Call
- Bull / Bull CF Put
- Bear / Bear CF Call
- Bear / Bear CF Put

### ORPT

This is the first main S23 decision time:

- `09:24:59`

In practice:

- base entry is checked here
- some current-day logic also uses the ORPT snapshot

### RC

This is the recalculation time:

- `09:29:59`

In practice:

- if entry was missed at ORPT, recalculation may be done here
- some current-day `FSL / TRP` logic uses this snapshot

### Option Chain

This is the set of available option contracts at a time.

TFIS uses it to choose a real tradeable contract instead of just a theoretical
strike range.

### Selected Contract

This is the actual option contract chosen by TFIS after filtering the option
chain.

Example:

- `NIFTY_20260528_22400_PE`

### Contract-Specific Lifecycle

Instead of simulating exits using generic option bars, TFIS can use the exact
selected contract’s own intraday series.

That is more realistic.

### Prelude JSONL

This is a normalized TFIS event file that carries the **non-broker strategy
context** for a session.

It can contain things like:

- calendar info
- monthly status
- required snapshots
- trade-plan input
- selected contract identity if needed

Think of it as:

- “strategy context prepared for TFIS”

### Ingress-Only

Ingress-only means:

- TFIS reads incoming data
- validates it
- makes the S23 decision
- stops there

It does **not**:

- place orders
- simulate fills
- simulate lifecycle

### PASS / WARNING / NO_GO

This is the operational safety result for ingress-style runs.

- `PASS`: clean session
- `WARNING`: usable but needs review
- `NO_GO`: unsafe or incomplete

### MATCH / MISMATCH

This is used when TFIS compares paper behavior to historical expectation.

- `MATCH`: same result
- `MATCH_WITH_ACCEPTABLE_DRIFT`: small bounded difference
- `PARTIAL_MATCH`: mostly aligned but not fully clean
- `MISMATCH`: real disagreement
- `UNCOMPARABLE`: not enough comparable evidence

## 4. Safest Reading Order For A New User

If you are using TFIS for the first time, use this order:

1. Validate the repo
2. Run a tiny sample backtest
3. Run a normal historical backtest
4. Run a historical comparison
5. Review an existing paper session
6. Run a normalized ingress-only dry run
7. Run FYERS preflight only
8. Only later try real market-hours ingress-only

That order helps you understand the system progressively.

## 5. Safety Rules You Should Never Ignore

Before every section, remember:

- work from `D:\TradingEngineTFIS`
- TFIS is currently paper/research focused
- do not add or enable order-routing code
- do not bypass `missing_contract_oi`
- do not write anything into `D:\TradingData`
- do not invent unimplemented carry-forward or rollover logic

## 6. Basic Repo Validation

### What this is for

Use this when you want to confirm the repo is in a healthy state before trusting
any result.

### When to use it

- before a serious review session
- after pulling or changing code
- before comparing outputs

### Command

```powershell
cd D:\TradingEngineTFIS
python scripts/validate_strategy_configs.py
python scripts/validate_project.py
python -m pytest tests/unit tests/architecture tests/integration -q
```

### What success looks like

- strategy config validation passes
- project validation passes
- test suite passes

### What failure means

If this fails, do not trust later outputs until the failure is understood.

## 7. Minimal Sample Run

### What this is for

This is the smallest possible “does S23 load at all?” check.

It does **not** prove market realism. It only proves:

- strategy config loads
- formulas evaluate
- a trade plan can be built

### When to use it

- first check after changes
- first sanity check on a new machine
- when you suspect a config break

### Command

```powershell
python scripts/run_backtest.py `
  --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D `
  --sample `
  --out tmp/S23_sample_backtest.json
```

### Example of what you are checking

You are asking TFIS:

- “Can you load the S23 Bull/Bull CF Call branch and compute its formulas?”

### What success looks like

- output JSON is created
- strategy fields are populated
- entry / target / stoploss exist

### What this is **not**

This is not a historical simulation and not a realistic trading result.

## 8. Historical Monthly-Status Run

### What this is for

This is the first meaningful historical S23 run.

It answers:

- “Using monthly status and past market data, what branch would S23 choose and
  what would happen?”

### When to use it

- when you want baseline historical S23 behavior
- before testing recalculation or current-day overlays

### Command

```powershell
python scripts/run_backtest.py `
  --strategy-root config/strategies/options_sell/nifty `
  --use-monthly-status-engine `
  --monthly-csv tests/fixtures/backtest/s23_monthly.csv `
  --weekly-csv tests/fixtures/backtest/s23_weekly.csv `
  --daily-csv tests/fixtures/backtest/s23_daily_multi.csv `
  --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv `
  --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv `
  --historical `
  --eod-policy square_off_at_close `
  --out tmp/S23_historical_monthly_status_backtest.json `
  --markdown-out tmp/S23_historical_monthly_status_backtest.md
```

### What the inputs mean

- `monthly-csv`
  - monthly status reference data
- `weekly-csv`
  - weekly reference levels
- `daily-csv`
  - daily spot/reference levels
- `option-levels-csv`
  - option reference values used in formulas
- `option-intraday-csv`
  - intraday option bars used for entry/target/stoploss/EOD lifecycle

### What success looks like

The Markdown report should tell you:

- which S23 branch was selected
- what entry/target/stoploss were
- whether entry happened
- whether target, stoploss, or EOD square-off happened

### Simple interpretation example

If the report says:

- branch = `Bear / Bear CF Put`
- selected option type = `PUT`
- exit reason = `TARGET_HIT`

that means TFIS found a bearish monthly status path and the simulated short put
trade reached target.

## 9. Historical Recalculation Run

### What this is for

This run turns on the ORPT missed-entry recalculation logic.

It answers:

- “If the original S23 entry was missed at 09:24:59, what would the
  recalculated trade look like at 09:29:59?”

### When to use it

- when you want to test gap or missed-entry behavior
- when reviewing whether recalculation changes the trade plan

### Command

```powershell
python scripts/run_backtest.py `
  --strategy-root config/strategies/options_sell/nifty `
  --use-monthly-status-engine `
  --monthly-csv tests/fixtures/backtest/s23_monthly.csv `
  --weekly-csv tests/fixtures/backtest/s23_weekly.csv `
  --daily-csv tests/fixtures/backtest/s23_daily_multi.csv `
  --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv `
  --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv `
  --spot-intraday-csv tests/fixtures/backtest/s23_spot_intraday.csv `
  --historical `
  --eod-policy square_off_at_close `
  --enable-s23-recalculation `
  --out tmp/S23_historical_monthly_status_recalc_backtest.json `
  --markdown-out tmp/S23_historical_monthly_status_recalc_backtest.md
```

### What this adds compared to the previous run

Now TFIS checks:

- was entry missed at ORPT?
- if yes, compute a new strike range / premium / entry at RC

### Example

Suppose the base entry should have been `203.5`, but the ORPT option low is
below that level.

Then TFIS may say:

- base plan existed
- entry was missed
- recalculated plan was applied at `09:29:59`

### Important limitation

Current TFIS recalculation changes:

- strike range
- ideal premium
- minimum premium
- entry

It does **not** currently recalculate target and stoploss in the standard ORPT
recalculation path.

## 10. Option-Chain Plus Contract-Specific Lifecycle Run

### What this is for

This is the more realistic historical run.

It answers:

- “Instead of simulating a generic strike idea, can TFIS pick a real option
  contract from the chain and then simulate lifecycle using that exact
  contract?”

### When to use it

- when you want more realistic strike and contract behavior
- when checking contract-specific realism

### Command

```powershell
python scripts/run_backtest.py `
  --strategy-root config/strategies/options_sell/nifty `
  --use-monthly-status-engine `
  --monthly-csv tests/fixtures/backtest/s23_monthly.csv `
  --weekly-csv tests/fixtures/backtest/s23_weekly.csv `
  --daily-csv tests/fixtures/backtest/s23_daily_multi.csv `
  --option-levels-csv tests/fixtures/backtest/s23_option_levels_multi.csv `
  --option-intraday-csv tests/fixtures/backtest/s23_option_intraday.csv `
  --option-chain-csv tests/fixtures/backtest/s23_option_chain.csv `
  --enable-option-chain-selection `
  --contract-intraday-csv tests/fixtures/backtest/s23_contract_intraday.csv `
  --enable-contract-specific-lifecycle `
  --historical `
  --eod-policy square_off_at_close `
  --enable-s23-recalculation `
  --out tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.json `
  --markdown-out tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.md
```

### What this adds

Now TFIS does two extra things:

1. It chooses a **real** contract from the option chain
2. It uses the exact selected contract’s own intraday bars for lifecycle

### How TFIS selects the contract

TFIS filters the option chain by:

- option type
- strike range
- minimum OI
- minimum premium

Then it chooses the best remaining candidate based mainly on:

- closeness to ideal premium
- tighter bid/ask spread
- higher OI

### What success looks like

The report should show:

- selected contract symbol
- contract selection reason
- whether contract-specific bars were found
- lifecycle result using the selected contract

### Why this matters

Without this, S23 may still be logically correct, but less realistic.

## 11. Historical Comparison Reports

### What this is for

Use this when you want to compare multiple S23 historical modes side by side.

It answers:

- “What changed when I enabled recalculation?”
- “What changed when I enabled option-chain selection?”
- “What changed when I enabled contract-specific lifecycle?”

### Command

```powershell
python scripts/compare_backtest_reports.py `
  --report base=tmp/S23_historical_backtest_costed.json `
  --report monthly_status=tmp/S23_historical_monthly_status_backtest.json `
  --report recalculation=tmp/S23_historical_monthly_status_recalc_backtest.json `
  --report current_day_fsl_trp=tmp/S23_historical_current_day_fsl_trp_backtest.json `
  --report option_chain=tmp/S23_historical_monthly_status_recalc_chain_backtest.json `
  --report contract_specific_lifecycle=tmp/S23_historical_monthly_status_recalc_chain_contract_backtest.json `
  --max-trades 200 `
  --timeout-seconds 10 `
  --out tmp/S23_mode_comparison.json `
  --markdown-out tmp/S23_mode_comparison.md
```

### What the comparison helps you see

Examples:

- did the selected contract change?
- did lifecycle source change?
- did P&L change because of contract-specific bars?
- was the comparison apples-to-apples or not?

### What to inspect first

In the Markdown output, first look for:

- apples-to-apples status
- selected contract differences
- P&L deltas
- fallback usage

## 12. Review A Persisted Paper Session

### What this is for

A paper session folder is a saved TFIS run in paper mode.

This review command explains the session in plain output.

### When to use it

- after a paper-mode run
- after an ingress-only run
- when auditing a saved session folder

### Command

```powershell
python scripts/review_paper_session.py `
  --session-dir tmp/s23_live_paper_dry_runs/2026-05-08/s23-archive-ingress-dry-run `
  --out-json tmp/paper_session_review.json `
  --out-md tmp/paper_session_review.md
```

### What it tells you

- terminal state
- readiness status
- selected contract
- guardrail issues
- fill status if that session reached fill simulation
- lifecycle and P&L if that session reached lifecycle

### Example

If the review says:

- terminal state = `ORDER_PLANNED`
- readiness = `READY`
- selected contract present = `true`

that means TFIS successfully reached the planning decision and the session can
be studied further.

## 13. Compare Paper Session To Historical Expectation

### What this is for

This checks whether the paper session behaved like TFIS expected historically.

### When to use it

- after a paper pilot
- after fill/lifecycle simulation
- when validating parity before broader rollout

### Command

```powershell
python scripts/compare_paper_to_historical.py `
  --session-dir tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot `
  --historical-report tmp/s23_paper_pilots/2026-05-08/s23-archive-lifecycle-parity-pilot/historical_expectation.json `
  --out-json tmp/paper_vs_historical.json `
  --out-md tmp/paper_vs_historical.md
```

### What success looks like

Good outcomes are:

- `MATCH`
- `MATCH_WITH_ACCEPTABLE_DRIFT`

Less good outcomes:

- `PARTIAL_MATCH`
- `MISMATCH`
- `UNCOMPARABLE`

### Example interpretation

If the result is `MATCH_WITH_ACCEPTABLE_DRIFT`, that usually means:

- logic matched
- contract matched
- lifecycle was comparable
- but fill, exit, or P&L differed slightly within approved tolerance

## 14. Run An Ingress-Only Dry Run From Normalized JSONL

### What this is for

This is the cleanest way to test TFIS decision orchestration without involving
brokers.

It answers:

- “Can TFIS read a normalized stream of market and prelude events and safely
  reach `ORDER_PLANNED`, `NO_TRADE`, or `ABORTED`?”

### Command

```powershell
python scripts/run_s23_paper_ingress_dry_run.py `
  --events-jsonl tests/fixtures/paper/s23_archive_ingress_dry_run.jsonl `
  --artifact-root tmp/s23_live_paper_dry_runs `
  --session-id s23-archive-ingress-dry-run
```

### What this run should create

Useful outputs:

- `session_manifest.json`
- `decision_summary.json`
- `selected_contract_audit.json`
- `paper_session_review.md`

### What this run must **not** create

Because this is ingress-only, it must not create:

- `paper_fill.json`
- `paper_position.json`
- `paper_exit.json`
- `paper_pnl_summary.json`

### Example

If the session ends at `ORDER_PLANNED`, that means:

- TFIS had enough valid data
- branch selection worked
- selected contract selection worked
- safety checks passed

## 15. Run A Generated-Live-Prelude Dry Run

### What this is for

This path proves that TFIS can build the S23 paper prelude from deterministic
runtime inputs and then feed the existing ingress-only orchestrator without any
broker, socket, or live network dependency.

It answers:

- "Can TFIS generate the normalized S23 planning prelude itself and still
  reach `ORDER_PLANNED`, `NO_TRADE`, or `ABORTED` deterministically?"

### Command

```powershell
python scripts/run_s23_live_prelude_dry_run.py `
  --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT `
  --config config/paper.s23.yaml `
  --runtime-fixture <runtime_fixture.json> `
  --market-events-jsonl <normalized_market_events.jsonl> `
  --artifact-root tmp/s23_generated_live_prelude_dry_runs `
  --session-id s23-generated-live-prelude-dry-run
```

Optional explicit smoke override:

```powershell
python scripts/run_s23_live_prelude_dry_run.py `
  --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT `
  --config config/paper.s23.yaml `
  --runtime-fixture <runtime_fixture.json> `
  --market-events-jsonl <normalized_market_events.jsonl> `
  --enable-smoke-override
```

### What this run should create

Useful outputs:

- `generated_live_prelude_events.jsonl`
- `generated_live_prelude_combined_events.jsonl`
- `generated_live_prelude_provenance.json`
- the standard session review and dry-run summary artifacts

### Safety note

- this remains fully offline and deterministic
- no FYERS socket orchestration runs here
- no broker order is placed
- static selected-contract config is used only when the explicit smoke-override
  flag is supplied

## 16. Run A FYERS Snapshot Preflight

### What this is for

This path is the bridge between the offline generated-prelude dry run and the
future FYERS socket/session orchestrator.

It answers:

- "Can TFIS collect one-shot FYERS-backed normalized snapshot inputs, keep OI
  validation strict, and optionally build the S23 paper prelude without
  starting a stream?"

### Preflight-only command

```powershell
python scripts/run_s23_fyers_snapshot_preflight.py `
  --preflight-only `
  --config config/paper.s23.yaml `
  --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT `
  --artifact-root tmp/s23_fyers_snapshot_preflight `
  --session-id s23-fyers-snapshot-preflight
```

### Collect snapshot inputs and build a generated prelude

```powershell
python scripts/run_s23_fyers_snapshot_preflight.py `
  --dry-run-build-prelude `
  --config config/paper.s23.yaml `
  --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT `
  --runtime-fixture <runtime_fixture.json> `
  --artifact-root tmp/s23_fyers_snapshot_preflight `
  --session-id s23-fyers-snapshot-preflight-build
```

Optional explicit smoke override:

```powershell
python scripts/run_s23_fyers_snapshot_preflight.py `
  --dry-run-build-prelude `
  --config config/paper.s23.yaml `
  --strategy-path config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT `
  --runtime-fixture <runtime_fixture.json> `
  --enable-smoke-override
```

### What this run should create

Useful outputs:

- `normalized_underlying_snapshot.json`
- `normalized_option_chain_snapshot.json`
- `snapshot_preflight_summary.json`
- `generated_live_prelude_events.jsonl` when `--dry-run-build-prelude` is used
- `generated_live_prelude_provenance.json` when `--dry-run-build-prelude` is used

### Safety note

- this does not start the FYERS socket loop
- this does not execute paper lifecycle handling
- this does not place broker orders
- strict option-chain OI validation still applies
- static selected-contract config remains an explicit smoke override only

## 17. FYERS Market-Data Ingress

### What this is for

This is the first broker-backed market-data path.

Important:

- FYERS provides market data only here
- TFIS still consumes only normalized TFIS events
- no order placement is allowed

### 17.1 Safe preflight

#### What this is for

This is the safe “check everything before connecting” step.

#### Command

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl tests/fixtures/paper/s23_fyers_prelude.jsonl `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-preflight `
  --preflight-only `
  --out-json tmp/s23_fyers_paper_ingress/preflight.json `
  --out-md tmp/s23_fyers_paper_ingress/preflight.md
```

#### What it checks

- FYERS credentials for real mode
- S23 only
- NIFTY only
- weekly only
- paper mode only
- no live orders allowed
- fill/lifecycle disabled
- artifact output path writable
- valid timezone
- valid prelude snapshots

#### Why it matters

This is the safest way to catch operational mistakes before any live market-data
ingress session.

### 15.2 Fixture-backed smoke test

#### What this is for

This tests your command path and local setup using fixture-backed FYERS-style
payloads.

#### Command

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl tests/fixtures/paper/s23_fyers_prelude.jsonl `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-fixture-smoke `
  --out-json tmp/s23_fyers_paper_ingress/fixture_smoke.json `
  --out-md tmp/s23_fyers_paper_ingress/fixture_smoke.md
```

#### Why use this first

If this fails, do not proceed to a real market-hours run yet.

### 15.3 Real market-hours ingress-only run

#### What this is for

This is the first real local run using FYERS market data in ingress-only mode.

#### Before you run it

- remove or comment `broker.payload_fixture_path` in `config/paper.s23.yaml`
- set `FYERS_APP_ID`
- set `FYERS_ACCESS_TOKEN`
- prepare a valid prelude JSONL for the current date

#### Command

```powershell
python scripts/run_s23_fyers_paper_ingress.py `
  --config config/paper.s23.yaml `
  --prelude-jsonl <today-normalized-prelude.jsonl> `
  --artifact-root tmp/s23_fyers_paper_ingress `
  --session-id s23-fyers-live-ingress
```

#### What success looks like

Typical good artifacts:

- `broker_health.json`
- `normalized_events.jsonl`
- `ingress_summary.json`
- `selected_contract_audit.json`
- `paper_session_review.md`
- `no_trade_or_order_plan_summary.json`

#### What should **not** happen

This run must not:

- place orders
- create fill artifacts
- create lifecycle artifacts

### How to judge the result

Use:

- [s23_fyers_ingress_live_runbook.md](s23_fyers_ingress_live_runbook.md)
- [s23_operator_closeout_policy.md](s23_operator_closeout_policy.md)

## 16. TradingEngine Capture Conversion

### What this is for

This converts read-only `D:\TradingData` captures into TFIS-style normalized
market events.

### What it is **not**

It is not a full standalone S23 session source.

Why not:

- captures do not contain monthly status
- captures do not contain TFIS trade-plan context
- captures do not contain all strategy-prelude information

### Command

```powershell
python scripts/convert_tradingengine_capture_to_tfis_ingress.py `
  --data-root D:\TradingData `
  --session-date 2026-05-27 `
  --out-root tmp/s23_tradingengine_capture_adapter/2026-05-27
```

### What this gives you

- TFIS-normalized market events only
- written under `tmp`
- nothing written back into `D:\TradingData`

## 17. TradingEngine Capture Plus TFIS Prelude Ingress Suite

### What this is for

This pairs:

- capture-derived market events
- TFIS prelude events

and then runs the normal ingress-only decision flow.

### Command

```powershell
python scripts/run_s23_tradingengine_capture_ingress_suite.py `
  --data-root D:\TradingData `
  --dates 2026-05-15,2026-05-20,2026-05-22,2026-05-25,2026-05-26,2026-05-27 `
  --out-root tmp/s23_tradingengine_capture_dry_runs
```

### What this proves

This proves whether TradingEngine captures can feed the **market-data leg** of
TFIS ingress.

### Current known result

This path is currently:

- operationally read-only
- deterministic
- good for timing validation
- **not** acceptable yet for ingress acceptance

Why:

- selected-contract `oi` is missing in the quote archives at decision time

### What you should conclude today

Treat this path as:

- market-data-leg validation only

Do **not** treat it as:

- clean S23 ingress acceptance evidence

### Read these before relying on it

- [s23_tradingengine_capture_adapter_audit.md](s23_tradingengine_capture_adapter_audit.md)
- [s23_tradingengine_capture_oi_audit.md](s23_tradingengine_capture_oi_audit.md)

## 18. Where To Look For Outputs

Common output roots:

- historical backtests:
  - `tmp/*.json`
  - `tmp/*.md`
- paper ingress dry runs:
  - `tmp/s23_live_paper_dry_runs/<date>/<session_id>/`
- FYERS ingress runs:
  - `tmp/s23_fyers_paper_ingress/`
- paper pilots:
  - `tmp/s23_paper_pilots/<date>/<session_id>/`
- pilot suites:
  - `tmp/s23_paper_pilot_suite/<date>/<suite_id>/`
- TradingEngine capture conversion:
  - `tmp/s23_tradingengine_capture_adapter/<date>/`
- TradingEngine capture ingress suite:
  - `tmp/s23_tradingengine_capture_dry_runs/`

## 19. What To Inspect In The Output

If you only inspect a few files, start with:

- `paper_session_review.md`
- `decision_summary.json`
- `selected_contract_audit.json`
- `ingress_summary.json`
- `paper_pnl_summary.json` when lifecycle exists
- `paper_vs_historical.md` when parity was run

## 20. Quick “Which Command Do I Need?” Table

| If you want to… | Use this |
| --- | --- |
| verify the repo is healthy | validation commands |
| check that S23 loads | minimal sample run |
| see baseline historical behavior | historical monthly-status run |
| test ORPT missed-entry logic | historical recalculation run |
| test realistic contract selection | option-chain plus contract-specific lifecycle run |
| compare historical modes | compare backtest reports |
| inspect one paper session | review paper session |
| compare paper to historical | compare paper to historical |
| validate normalized ingress only | ingress-only dry run |
| safely prepare a real FYERS run | FYERS preflight |
| run broker-backed market-data ingress only | FYERS real ingress-only run |
| test whether TradingEngine captures can feed TFIS ingress | capture conversion plus capture ingress suite |

## 21. What Not To Do

Do not:

- add broker order placement
- bypass `missing_contract_oi`
- enable next-day continuation
- write inside `D:\TradingData`
- treat TradingEngine captures as ingress-acceptance evidence until a safe OI
  source exists
- infer unsupported workbook behavior

## 22. Safest Starting Sequence For A Human Operator

If you are operating TFIS manually for the first time, use this exact order:

1. Run repo validation
2. Run the minimal sample run
3. Run the historical monthly-status run
4. Run the historical comparison report
5. Review one existing paper session
6. Run one normalized JSONL ingress-only dry run
7. Run FYERS preflight only
8. Read the close-out policy
9. Only then attempt a real market-hours ingress-only run

That path gives you context first, then realism, then operational readiness.
