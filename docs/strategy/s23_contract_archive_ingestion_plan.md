# S23 Contract Archive Ingestion Plan

## Purpose

This document defines the next safe step after fixture-backed S23 lifecycle
coverage reached 100%.

The goal is not to change S23 logic. The goal is to expand contract-specific
intraday realism from deterministic fixtures to broader real/archive data while
keeping:

- S23 formulas unchanged
- workbook mappings unchanged
- lifecycle simulation behavior unchanged
- fallback behavior explicit

## Current Accepted TFIS Schema

TFIS can already consume contract-specific intraday bars through:

- `src/tfis/backtest/contract_intraday.py`

Current accepted CSV contract:

- required columns:
  - `timestamp`
  - `symbol`
  - `open`
  - `high`
  - `low`
  - `close`
- optional column:
  - `volume`

Current loader behavior:

- timestamps are parsed with `datetime.fromisoformat`
- rows are sorted by `(timestamp, symbol)`
- bars are grouped by:
  - session date
  - exact symbol string
- lifecycle lookup can filter bars after a cutoff timestamp

Current accepted runtime model:

- `ContractIntradayBar`
- `build_contract_intraday_lookup(...)`
- `resolve_contract_intraday_bars(...)`

This means TFIS already has a stable normalized ingestion target. The missing
work is archive normalization, not a new lifecycle model.

## Current Non-Fixture Input Shapes Observed

### Raw NiftyTradingEngine capture session

Observed local session root:

- `D:\NiftyTradingEngine\captures\sessions\2026-04-06\replay_20260406_213926\`

Observed files:

- `events.jsonl`
- `session_manifest.json`
- `ticks.csv`
- `trades.jsonl`
- `snapshots/config_snapshot.yaml`

Observed `ticks.csv` header:

- `timestamp,symbol,ltp,qty,vtt,volume`

Observed `events.jsonl` shape:

- top-level keys such as:
  - `ts`
  - `event`
  - `data`

Implication:

- raw capture sessions are not already in TFIS OHLC form
- they need symbol-aware aggregation and normalization before TFIS should use
  them for contract lifecycle simulation

### TradingEngineProd trade ledger / archive references

Observed file:

- `D:\TradingEngineProd\docs\trade_ledger_2026-05-01_to_2026-05-31.csv`

Observed symbol examples:

- `NSE:NIFTY2650524900PE`
- `NSE:NIFTY2650523450CE`

Implication:

- neighboring engine ecosystems already track real selected option symbols
- the symbol format differs from TFIS normalized contract symbols
- ledger files are useful for provenance and pilot selection, but they are not
  themselves a contract-specific intraday OHLC source

## What TFIS Can Already Consume

TFIS contract-specific lifecycle mode can already consume:

1. normalized CSV intraday contract bars
2. exact contract symbols matching the selected option-chain contract
3. per-bar OHLC data sufficient for lifecycle replay after the selected cutoff

TFIS cannot yet consume directly:

1. raw `events.jsonl` sessions
2. raw `ticks.csv` quote streams
3. parquet archives
4. broker-exported CSV variants with non-normalized symbols and timestamps

## Feasible Real / Archive Sources To Adapt Next

### 1. Normalized CSV export from raw capture sessions

Feasibility:

- high

Why:

- matches the current TFIS loader contract directly
- preserves TFIS core as read-only and broker-agnostic
- lets normalization live outside TFIS runtime

Recommended use:

- first pilot

### 2. Broker-exported option intraday CSVs

Feasibility:

- medium to high

Why:

- many brokers export timestamped intraday rows already close to OHLC format
- may still require:
  - symbol normalization
  - column remapping
  - timezone cleanup

Recommended use:

- good second source after normalized-capture export

### 3. Shared Parquet archives

Feasibility:

- medium

Why:

- efficient for larger coverage
- not yet supported in TFIS loaders
- needs explicit schema and normalization contracts first

Recommended use:

- second-stage adapter after CSV normalization contracts are stable

### 4. Raw NiftyTradingEngine / TradingEngine capture sessions

Feasibility:

- medium, but higher risk if used directly

Why:

- local evidence shows raw sessions exist
- current raw shapes are event and tick oriented, not ready-made lifecycle bars
- direct parsing would couple TFIS to volatile upstream capture details

Recommended use:

- indirect only for the first pilot
- normalize externally into TFIS contract CSV, do not add direct runtime parsing
  yet

## Required Symbol Normalization

Current TFIS normalized examples:

- `NIFTY_20260528_22400_PE`
- `NIFTY_20260528_22100_CE`

Observed neighboring engine examples:

- `NSE:NIFTY2650524900PE`
- `NSE:NIFTY2650523450CE`

Normalization requirements:

1. remove exchange prefix when present, for example `NSE:`
2. extract underlying, expiry, strike, and option side
3. normalize option side:
   - `CE -> CE`
   - `PE -> PE`
4. normalize expiry into a stable canonical form:
   - preferred TFIS display/storage target: `YYYYMMDD`
5. preserve the original raw symbol in provenance

Guardrail:

- never guess expiry semantics from partial symbol text alone if an authoritative
  expiry field exists elsewhere
- if normalization is ambiguous, reject the row and surface a data-quality error

## Required Timestamp / Timezone Normalization

Current TFIS fixtures use naive ISO-like local timestamps such as:

- `2026-05-21T09:25:00`

Observed neighboring artifacts also use offset timestamps such as:

- `2026-05-08T10:19:15+05:30`

Normalization policy for the first archive pilot:

1. normalize all contract lifecycle bars to one consistent local trading
   timezone:
   - `Asia/Kolkata`
2. do not mix timezone-aware and naive timestamps inside one normalized TFIS
   dataset
3. preserve original raw timestamp text in provenance or manifest metadata
4. ensure session-date grouping uses normalized local session date, not UTC date

Safe first pilot recommendation:

- export normalized TFIS contract bars as naive `YYYY-MM-DDTHH:MM:SS` local
  trading timestamps, because that matches current TFIS fixtures and avoids
  aware-vs-naive comparison bugs

## Required Data-Quality Checks Before Backtest Use

Archive data should not be used for S23 lifecycle simulation unless it passes:

### Structural checks

- file exists
- non-empty rows
- required columns present
- symbol non-empty
- timestamps parse cleanly
- OHLC values parse as numeric

### OHLC sanity checks

- `high >= low`
- `high >= open`
- `high >= close`
- `low <= open`
- `low <= close`

### Ordering and duplication checks

- bars sorted monotonically by timestamp within symbol/date
- no duplicate `(timestamp, symbol)` rows unless explicitly resolved

### Session checks

- rows fall within the intended market session
- normalized session date matches the backtest trade date
- post-cutoff usable bars count is measurable

### Coverage checks

- selected contract symbol exists in archive
- at least one usable bar exists after lifecycle cutoff when contract-specific
  mode is enabled
- gaps are recorded explicitly, not silently ignored

### Provenance checks

- raw source path recorded
- adapter version recorded
- symbol normalization rule recorded
- timezone normalization rule recorded
- synthetic vs real/archive source recorded

## Fallback Policy For Partial Archive Coverage

Current TFIS behavior is correct and should remain the baseline:

- if contract-specific bars exist and are usable after cutoff:
  - use `contract_specific_series`
- otherwise:
  - fall back to `generic_option_series`
- always record:
  - selected contract symbol
  - bars available
  - bars usable after cutoff
  - fallback used or not
  - fallback reason
  - lifecycle source actually used

Recommended rule for archive pilots:

- partial archive coverage is acceptable only if fallback remains explicit and
  the report marks the comparison as partial where appropriate
- no silent fallback
- no fake backfilling from unrelated symbols

## Proposed Adapter Interfaces

The first step should stay outside core S23 logic.

### Stage 1: external normalization

Recommended interface:

- raw source -> normalized `contract_intraday.csv`
- optional sidecar manifest such as:
  - `contract_intraday_manifest.json`

Suggested manifest fields:

- `source_type`
- `source_root`
- `source_files`
- `session_dates`
- `timezone_policy`
- `symbol_normalization_policy`
- `row_count`
- `symbol_count`
- `generated_at`
- `synthetic_fixture_data_used`

### Stage 2: optional TFIS adapter abstraction

If archive sources multiply, add a read-only adapter layer such as:

- `ContractIntradayArchiveAdapter`

Possible responsibilities:

- discover source artifacts
- normalize symbols
- normalize timestamps
- export or stream `ContractIntradayBar`
- emit validation findings and provenance metadata

Guardrail:

- do not make TFIS runtime depend directly on `TradingEngine` or
  `NiftyTradingEngine` Python modules

## First Pilot Recommendation

### Pilot goal

Prove that one real/archive source can be normalized into TFIS contract-specific
lifecycle input without changing S23 logic.

### Recommended first pilot source

Use one small normalized export derived from:

- `D:\NiftyTradingEngine\captures\sessions\2026-04-06\...`

Why this is the safest first pilot:

- raw source is present locally
- session layout is concrete and inspectable
- it avoids inventing data
- it exercises symbol and timestamp normalization explicitly

### Recommended pilot output

Produce a separate archive trial dataset, for example:

- `tmp` or `tests/_tmp_archive_pilot/contract_intraday.csv`
- matching manifest documenting provenance

### Pilot acceptance criteria

- at least one real contract symbol normalizes cleanly into TFIS format
- at least one selected contract has usable post-cutoff bars
- fallback remains explicit for uncovered symbols
- comparison/reporting can distinguish:
  - real archive bars used
  - generic fallback used
- no S23 formula or lifecycle logic changes are required

## Risks And Guardrails

### Risks

- symbol normalization mistakes can map bars to the wrong contract
- timezone mismatches can shift session date or cutoff ordering
- tick-to-bar aggregation can create inconsistent OHLC if not defined clearly
- archive completeness may be overstated if only pre-cutoff bars exist
- raw capture formats may drift over time

### Guardrails

- normalize into the existing TFIS CSV schema first
- preserve original raw symbol and timestamp provenance
- reject ambiguous symbol mappings
- reject mixed timezone styles inside one normalized dataset
- keep archive ingestion read-only
- keep comparison integrity checks enabled
- do not treat archive coverage as complete unless coverage metrics prove it

## Current Conclusion

S23 no longer needs more fixture work before archive planning.

The next safe step is:

1. keep TFIS runtime on the current normalized CSV contract
2. build a small real/archive normalization pilot outside S23 logic
3. measure coverage and fallback explicitly
4. only then decide whether a broader adapter belongs in TFIS core
