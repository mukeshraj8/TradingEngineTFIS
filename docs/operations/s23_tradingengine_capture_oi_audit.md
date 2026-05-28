# S23 TradingEngine Capture OI Audit

## Scope

- date: `2026-05-28`
- objective: determine whether TradingEngine captured data under `D:\TradingData`
  contains a reliable open-interest (`oi`) source that can satisfy TFIS S23
  ingress-only validation
- constraints:
  - read-only inspection only
  - no modification of `D:\TradingData`
  - no weakening of TFIS guardrails
  - no S23 formula changes

## Conclusion

Recommendation: `not usable for ingress acceptance`

The TradingEngine captures remain usable for the S23 **market-data leg**:

- NIFTY underlying timing windows exist
- option quote archives exist
- selected contract quotes can be converted and paired with TFIS preludes
- ORPT / RC timing and artifact generation work

They are **not usable for S23 ingress acceptance** in their current form because
the dry-run path still requires selected-contract `oi`, and the audited capture
sources do not provide it in a selected-contract-safe way.

The direct quote archives contain an `oi` column, but it is blank throughout the
audited files, including the decision windows. The only alternate OI-like source
found is `option_positioning` summary data inside session journals, but that is
not a safe substitute for selected-contract OI at `09:15`, `ORPT`, `RC`, or
final decision time.

## Files Inspected

### Quote archives

- `D:\TradingData\data\nifty\20260515\options\index\NIFTY50_option_quotes_20260515.csv`
- `D:\TradingData\data\nifty\20260520\options\index\NIFTY50_option_quotes_20260520.csv`
- `D:\TradingData\data\nifty\20260522\options\index\NIFTY50_option_quotes_20260522.csv`
- `D:\TradingData\data\nifty\20260525\options\index\NIFTY50_option_quotes_20260525.csv`
- `D:\TradingData\data\nifty\20260526\options\index\NIFTY50_option_quotes_20260526.csv`
- `D:\TradingData\data\nifty\20260527\options\index\NIFTY50_option_quotes_20260527.csv`

### Context sessions

- `D:\TradingData\captures\context_sessions\2026-05-15\live_20260515_090505_dev_pid19604\ticks_context.csv`
- `D:\TradingData\captures\context_sessions\2026-05-20\live_20260520_090803_dev_pid18976\ticks_context.csv`
- `D:\TradingData\captures\context_sessions\2026-05-22\live_20260522_090536_dev_pid7604\ticks_context.csv`
- `D:\TradingData\captures\context_sessions\2026-05-25\live_20260525_090715_dev_pid15480\ticks_context.csv`
- `D:\TradingData\captures\context_sessions\2026-05-26\live_20260526_090536_dev_pid14808\ticks_context.csv`
- `D:\TradingData\captures\context_sessions\2026-05-27\live_20260527_090535_dev_pid16276\ticks_context.csv`

### Session artifacts

- `D:\TradingData\captures\sessions\2026-05-15\live_20260515_090505_dev_pid19604\events.jsonl`
- `D:\TradingData\captures\sessions\2026-05-27\live_20260527_090535_dev_pid16276\events.jsonl`
- `D:\TradingData\captures\sessions\2026-05-27\live_20260527_090535_dev_pid16276\trades.jsonl`
- `D:\TradingData\captures\sessions\2026-05-27\live_20260527_090535_dev_pid16276\session_manifest.json`

### Truth replay metadata

- `D:\TradingData\captures\truth_replay\2026-05-20\live_20260520_090803_dev_pid18976\truth_replay_manifest.json`
- `D:\TradingData\captures\truth_replay\2026-05-27\live_20260527_090535_dev_pid16276\truth_replay_manifest.json`

### TFIS derived evidence

- `D:\TradingEngineTFIS\tmp\s23_tradingengine_capture_dry_runs\summary.json`
- `D:\TradingEngineTFIS\tmp\s23_tradingengine_capture_dry_runs\summary.md`
- `D:\TradingEngineTFIS\tmp\s23_tradingengine_capture_dry_runs\<date>\<session>\market_events.jsonl`

## Fields Found

### Quote archive header

The option quote archives expose this schema:

```text
capture_sequence,timestamp,underlying_symbol,option_chain_symbol,underlying_ltp,
option_symbol,strike,option_type,expiry,ltp,bid,ask,spread_points,volume,oi,
oi_change,iv
```

Findings:

- `bid`, `ask`, `ltp`, `volume` are present
- `oi`, `oi_change`, `iv` columns exist structurally
- for the audited usable dates, `oi` and `oi_change` are blank in the data

### Context session header

The context session rows contain:

- `selected_option_symbol`
- `selected_option_bid`
- `selected_option_ask`
- `selected_option_ltp`
- `selected_option_quote_timestamp`
- option-selection decision metadata

They do **not** contain:

- selected-contract `oi`
- selected-contract `oi_change`
- full option-chain OI snapshots

### Session journal fields

Observed useful OI-related data in `events.jsonl`:

- `option_positioning`
  - contains `near_spot.calls[].oi`
  - contains `near_spot.puts[].oi`
  - contains `oich`

Observed limitations:

- no full raw option symbol
- no expiry field
- only a narrow near-spot basket, not the full chain
- not guaranteed to include the S23 selected contract
- not guaranteed at exact `09:15`, `09:24:59`, or `09:29:59`

Observed non-sources:

- `trades.jsonl` contains selected option symbol and quote fields, but the
  sampled records did not contain `oi`
- `truth_replay_manifest.json` contains analyzer counts such as
  `OptionsOIAnalyzer`, but not per-contract OI values

## Direct OI Availability by Date

The six-date ingress suite selected these contracts:

| Date | Session | Selected Contract | Direct Quote-Archive OI | Decision-Time Status |
| --- | --- | --- | --- | --- |
| `2026-05-15` | `live_20260515_090505_dev_pid19604` | `NIFTY_20260519_24600_PE` | `null` | unavailable |
| `2026-05-20` | `live_20260520_090803_dev_pid18976` | `NIFTY_20260528_22700_CE` | `null` | unavailable |
| `2026-05-22` | `live_20260522_090536_dev_pid7604` | `NIFTY_20260528_24550_PE` | `null` | unavailable |
| `2026-05-25` | `live_20260525_090715_dev_pid15480` | `NIFTY_20260528_23200_CE` | `null` | unavailable |
| `2026-05-26` | `live_20260526_090536_dev_pid14808` | `NIFTY_20260602_24850_PE` | `null` | unavailable |
| `2026-05-27` | `live_20260527_090535_dev_pid16276` | `NIFTY_20260602_23100_CE` | `null` | unavailable |

These values come directly from the converted `SELECTED_CONTRACT_QUOTE` events
that TFIS actually consumed during the paired dry-run suite.

## Whole-File OI Coverage for Usable Dates

The quote archives were also checked at the file level:

| Date | Total Rows | Rows With Non-Blank `oi` | RC Window Rows | RC Window Rows With Non-Blank `oi` |
| --- | ---: | ---: | ---: | ---: |
| `2026-05-15` | `4292` | `0` | `12` | `0` |
| `2026-05-20` | `4282` | `0` | `12` | `0` |
| `2026-05-22` | `4584` | `0` | `12` | `0` |
| `2026-05-25` | `4304` | `0` | `10` | `0` |
| `2026-05-26` | `4445` | `0` | `10` | `0` |
| `2026-05-27` | `4583` | `0` | `10` | `0` |

This means the direct quote archive does not provide usable `oi` at:

- `09:15`
- `ORPT 09:24:59`
- `RC 09:29:59`
- final S23 decision time

It is not merely a selected-contract edge case. It is a whole-file gap on the
audited usable dates.

## Alternate OI Sources

### 1. `option_positioning` in `captures/sessions/*/events.jsonl`

Status: `derived / not safe`

What exists:

- per-event `near_spot` call and put strike baskets with `oi` and `oich`
- PCR-style positioning summaries

Why it is not safe for TFIS S23 selected-contract validation:

- the data is strike-only, not full raw contract symbol
- expiry is not present
- only a small near-spot subset is emitted
- the S23 selected contract can be outside the near-spot basket
- timing is event-driven and not guaranteed to line up exactly with
  `09:15`, `ORPT`, `RC`, or final decision time

Concrete example:

- `2026-05-15` near `09:28:08`
- `option_positioning` emitted OI for strikes `23700`, `23750`, `23800`
- the selected S23 contract for the paired dry run was `24600 PE`
- therefore the event contained OI intelligence, but not for the selected
  contract

Another example:

- `2026-05-27` early-session `option_positioning` emitted near-spot strikes
  around `23850` to `24000`
- the paired dry-run selected contract was `23100 CE`
- again, not selected-contract-safe

Conclusion:

- useful for general market context
- not acceptable as a substitute for selected-contract OI in TFIS ingress
  acceptance

### 2. `ticks_context.csv`

Status: `unavailable`

What exists:

- selected option identity and quote fields
- option-selection metadata

What is missing:

- selected-contract `oi`
- selected-contract `oi_change`

Conclusion:

- enough to help identify selected contract and quote freshness
- not enough to satisfy `missing_contract_oi`

### 3. `trades.jsonl`

Status: `stale / not applicable`

What exists:

- later trade records with option symbol, bid, ask, ltp, fill model, and trade
  outcome

What is missing or unusable for ingress:

- no observed selected-contract `oi` in sampled trade records
- records occur after trade approval or fill, not at pre-decision time

Conclusion:

- not usable for ingress-time OI

### 4. `truth_replay_manifest.json`

Status: `unavailable`

What exists:

- counts and telemetry mentioning `OptionsOIAnalyzer`

What is missing:

- per-contract OI values
- selected-contract OI snapshots

Conclusion:

- useful as evidence that an OI analyzer existed in the separate system
- not usable as an enrichment source for TFIS

## Usable Dates / Sessions

For the market-data leg only, these remain the usable dates already identified
by the earlier adapter audit:

- `2026-05-15`
- `2026-05-20`
- `2026-05-22`
- `2026-05-25`
- `2026-05-26`
- `2026-05-27`

For **S23 ingress acceptance requiring selected-contract OI**, all six are
currently `NO_GO`.

## Safe Enrichment Path

If OI is to be restored safely in the future, the enrichment path should be:

`TradingEngine capture market events`
`+ direct selected-contract or chain snapshot OI source`
`-> TFIS normalized ingress JSONL`

Requirements for a future enrichment source:

- exact raw option symbol or TFIS-normalizable contract identity
- expiry present
- timestamp within S23 decision-time freshness limits
- available at `09:15`, `ORPT`, `RC`, and final decision time
- read-only source extraction
- no inference from neighboring strikes
- no backfilling from post-trade artifacts

## Recommendation

Current recommendation: `partially usable`

Interpretation:

- usable for market-data timing validation
- not usable for ingress acceptance
- do not bypass `missing_contract_oi`
- do not weaken TFIS guardrails

Until a direct OI-bearing source exists, TradingEngine captures should be
treated as:

`market-data-leg validation only`

and not as a full ingress-acceptance source for S23 dry runs.

## Follow-Up Recommendation

Recommended future TradingEngine enhancement:

- persist selected-contract OI and/or full option-chain snapshot OI at:
  - `09:15`
  - `ORPT 09:24:59`
  - `RC 09:29:59`
  - final S23 decision time

Preferred shapes:

- selected contract snapshot with raw symbol, expiry, strike, option type, bid,
  ask, ltp, volume, `oi`, and `oi_change`
- or a full chain snapshot with the same fields

Until then, keep the TFIS S23 TradingEngine-capture ingress path at:

- ingress operational classification: `NO_GO`
- capture utility classification: `market-data-leg timing validation only`
