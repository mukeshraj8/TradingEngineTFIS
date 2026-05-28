# S23 TradingEngine Capture Adapter Audit

## Scope

- audit target: `D:\TradingData`
- strategy scope: `S23` only
- instrument scope: `NIFTY` weekly options only
- runtime scope: paper dry-run inputs only
- safety boundary:
  - read-only inspection of `D:\TradingData`
  - no files were modified under `D:\TradingData`
  - all derived outputs stay under `D:\TradingEngineTFIS\tmp`

## Conclusion

Recommendation: `partially_usable`

The TradingEngine capture estate is usable for the **market-data leg** of S23 TFIS dry runs, but it is **not** a full standalone S23 session source yet.

What is usable now:
- NIFTY underlying quote coverage from `ticks_context.csv`
- RC-window option-chain reconstruction from `NIFTY50_option_quotes_YYYYMMDD.csv`
- selected-contract quote reconstruction when the contract symbol is supplied externally
- 09:15 / ORPT / RC underlying snapshot derivation from context ticks on the better sessions

What is still missing from TradingEngine captures alone:
- `MONTHLY_STATUS_INPUT`
- workbook-backed `TRADE_PLAN_INPUT`
- TFIS paper config and cost/slippage prelude
- reliable decision-time selected contract embedded at `RC`

So the safe adapter shape is:

`TradingEngine capture market data -> TFIS normalized market events JSONL`

paired with

`TFIS prelude JSONL -> calendar + monthly status + session config + costs + trade plan`

## Discovered Locations

Top-level:
- `D:\TradingData\captures\context_sessions`
- `D:\TradingData\captures\sessions`
- `D:\TradingData\data\nifty`

Relevant capture/session files:
- `D:\TradingData\captures\context_sessions\<date>\<session>\ticks_context.csv`
- `D:\TradingData\captures\context_sessions\<date>\<session>\session_manifest.json`
- `D:\TradingData\captures\context_sessions\<date>\<session>\ticks_context_parquet\part-*.parquet`
- `D:\TradingData\captures\sessions\<date>\<session>\events.jsonl`
- `D:\TradingData\captures\sessions\<date>\<session>\trades.jsonl`
- `D:\TradingData\captures\sessions\<date>\<session>\snapshots\config_snapshot.yaml`

Relevant market-data archives:
- `D:\TradingData\data\nifty\YYYYMMDD\options\index\NIFTY50_option_quotes_YYYYMMDD.csv`
- `D:\TradingData\data\nifty\YYYYMMDD\index\NIFTY50_5m_YYYYMMDD.csv`

## Columns Found

### `ticks_context.csv`

Required and useful fields found:
- `capture_sequence`
- `timestamp`
- `symbol`
- `ltp`
- `volume`
- `selected_option_symbol`
- `selected_option_ltp`
- `selected_option_bid`
- `selected_option_ask`
- `selected_option_quote_timestamp`
- `selected_option_quote_sequence`
- `selected_option_quote_freshness_seconds`
- `selected_option_quote_source`
- `orb_high`
- `orb_low`

Additional later-schema fields found on some dates:
- `option_selection_decision_timestamp`
- `option_selection_direction`
- `option_selection_underlying_price`
- `option_selection_initial_candidate_symbol`
- `option_selection_rejected_candidates`
- `option_selection_final_selected_symbol`
- `option_selection_final_bid`
- `option_selection_final_ask`
- `option_selection_final_ltp`
- `option_selection_final_spread`
- `option_selection_final_selection_reason`

### `NIFTY50_option_quotes_YYYYMMDD.csv`

Required and useful fields found:
- `capture_sequence`
- `timestamp`
- `underlying_symbol`
- `option_symbol`
- `strike`
- `option_type`
- `expiry`
- `ltp`
- `bid`
- `ask`
- `spread_points`
- `volume`
- `oi`

### Missing as standalone capture artifacts

Not found under `D:\TradingData` during this audit:
- `monthly_status.json`
- standalone TFIS-ready `TRADE_PLAN_INPUT`
- standalone TFIS-ready `PAPER_SESSION_CONFIG`
- standalone TFIS-ready `COST_SLIPPAGE_SETTINGS`

## Symbol Mapping Feasibility

Underlying mapping is straightforward:
- TradingEngine / Fyers: `NSE:NIFTY50-INDEX`
- TFIS normalized: `NIFTY`

Option mapping is feasible, but two raw symbol styles exist:

Weekly-style examples:
- raw: `NSE:NIFTY2660223200CE`
- expiry field: `26602`
- normalized: `NIFTY_20260602_23200_CE`

Monthly-style examples:
- raw: `NSE:NIFTY26MAY22650CE`
- expiry field: `26MAY`
- normalized: `NIFTY_20260528_22650_CE`

Mapping rule used by the prototype:
- weekly numeric expiry codes:
  - `YYMDD`, where month is `1-9`, `O`, `N`, or `D`
- monthly text expiry codes:
  - `YYMMM`, mapped to the last Thursday of that month for NIFTY monthly expiry

This is good enough for the audited two-week window. If later raw data introduces another symbol convention, the adapter should be extended before production use.

## Coverage by Date / Session

Using the prototype's exact S23 dry-run window checks:

Usable market-leg sessions:
- `2026-05-15` -> `live_20260515_090505_dev_pid19604`
- `2026-05-20` -> `live_20260520_090803_dev_pid18976`
- `2026-05-22` -> `live_20260522_090536_dev_pid7604`
- `2026-05-25` -> `live_20260525_090715_dev_pid15480`
- `2026-05-26` -> `live_20260526_090536_dev_pid14808`
- `2026-05-27` -> `live_20260527_090535_dev_pid16276`

Partially usable:
- `2026-05-19` -> `live_20260519_091533_dev_pid14696`
  - covers ORPT and RC
  - misses the strict `09:15:00` snapshot window because the session starts at `09:15:39`

Not usable for S23 dry-run decision windows:
- `2026-05-18`
- `2026-05-21`

Special warning sessions:
- `2026-05-22` early `07:08` / `07:21` sessions include stale prior-day rows and are not market-hours candidates

Important shared finding:
- on all audited root-selected sessions, `selected_option_symbol` was `null` during the RC window
- some dates do embed selected-option fields later in the day
- therefore TFIS must not rely on TradingEngine context data alone for RC-time selected-contract identity

## Data Quality Findings

### Good

- `capture_sequence` is monotonic in sampled sessions
- timestamps include timezone offsets like `+05:30`
- full-day sessions exist for several dates
- option quote archives exist for every audited trading date
- option quote files are rich enough to reconstruct an RC option chain and selected-contract quote

### Warnings

- `ticks_context.csv` is not always globally timestamp-sorted
  - safe interpretation: sort by `capture_sequence` and explicit timestamps during normalization
- underlying quote gaps can reach roughly `40-70s` on sampled full-day sessions
  - dry-run acceptance should freshness-bound snapshot and selected-contract use
- some dates have no embedded selected-option rows at all
- some dates have embedded selected-option rows only later in the session, not at RC
- some context sessions are midday restarts and do not cover `09:15 / ORPT / RC`

### Practical impact

The raw capture is strong enough for:
- underlying snapshots
- RC underlying quote
- RC option chain
- RC selected-contract quote when the contract is supplied externally

The raw capture is not strong enough by itself for:
- monthly status
- S23 workbook trade plan
- deterministic selected contract at RC without TFIS-side help

## Prototype Adapter

Implemented prototype:
- [tradingengine_capture_adapter.py](/D:/TradingEngineTFIS/src/tfis/paper/tradingengine_capture_adapter.py)
- [convert_tradingengine_capture_to_tfis_ingress.py](/D:/TradingEngineTFIS/scripts/convert_tradingengine_capture_to_tfis_ingress.py)

Prototype scope:
- read-only input
- market events only
- supports:
  - `UNDERLYING_SNAPSHOT`
  - `UNDERLYING_QUOTE`
  - `OPTION_CHAIN_SNAPSHOT`
  - `SELECTED_CONTRACT_QUOTE`
- does **not** emit:
  - `CALENDAR_CONTEXT`
  - `MONTHLY_STATUS_INPUT`
  - `PAPER_SESSION_CONFIG`
  - `COST_SLIPPAGE_SETTINGS`
  - `TRADE_PLAN_INPUT`

That omission is intentional.

The prototype is designed to be merged with an existing TFIS prelude JSONL rather than pretending TradingEngine captures contain S23 workbook logic.

## Real Local Prototype Run

Read-only local audit output created during this task:
- [capture_audit.json](/D:/TradingEngineTFIS/tmp/s23_tradingengine_capture_adapter/2026-05-27/capture_audit.json)

Read-only local single-session conversion output created during this task:
- [market_events.jsonl](/D:/TradingEngineTFIS/tmp/s23_tradingengine_capture_adapter/2026-05-27/market_events.jsonl)

Real session used:
- date: `2026-05-27`
- context session:
  - `D:\TradingData\captures\context_sessions\2026-05-27\live_20260527_090535_dev_pid16276`
- option archive:
  - `D:\TradingData\data\nifty\20260527\options\index\NIFTY50_option_quotes_20260527.csv`

Prototype result:
- audit: succeeded
- conversion: succeeded
- emitted events: `6`
- selected contract supplied externally for proof-of-concept conversion:
  - `NSE:NIFTY2660223100CE`
  - normalized to `NIFTY_20260602_23100_CE`

## Safe Converter Design

Recommended flow:

1. choose one usable `context_session` folder
2. pair it with the matching `NIFTY50_option_quotes_YYYYMMDD.csv`
3. derive:
   - `0915` underlying snapshot
   - `ORPT` underlying snapshot
   - `RC` underlying snapshot
   - `RC` underlying quote
   - `RC` option chain snapshot
   - `RC` selected contract quote
4. merge those market events with a TFIS-generated prelude containing:
   - calendar context
   - monthly status
   - paper config
   - cost/slippage settings
   - workbook-backed trade plan

Output location rule:
- write only under `D:\TradingEngineTFIS\tmp` or fixture folders
- never inside `D:\TradingData`

## Recommendation

Overall recommendation: `partially_usable`

Meaning:
- `usable` as a read-only market-data adapter for S23 dry runs
- `not usable` as a standalone end-to-end S23 session source

Recommended next step:
- use the prototype to convert a small set of the usable dates into TFIS market-event JSONL
- pair each with a TFIS prelude JSONL
- run ingress-only dry runs before attempting any fill or lifecycle replay from TradingEngine captures
