# Shared Market Data Strategy

## Current Direction

- `TradingEngine` already captures NIFTY, BANKNIFTY, and option market data.
- TFIS should reuse validated captured data from that ecosystem where possible.
- TFIS should avoid building a second independent live market-data capture framework.
- The TFIS project should stay focused on rule evaluation, offline replay, backtesting, and strategy configuration.
- TFIS now has a read-only shared-data adapter foundation for normalized CSV roots.
- That adapter is intentionally file-contract based and does not import `TradingEngine` or `NiftyTradingEngine` code at runtime.

## Proposed Future Model

- Maintain one shared market-data archive or root location.
- The data producer can be:
  - the existing `TradingEngine`, or
  - a future `SharedCaptureService` if capture is later extracted into a separate system.
- TFIS should consume local archived datasets such as CSV, Parquet, and manifest-backed files for backtesting and replay.
- `TradingEngine` and TFIS should remain decoupled through file-level and data-contract boundaries rather than direct runtime dependencies.

Current implemented adapter scope:

- supported now:
  - normalized shared CSV roots such as:
    - `shared_root/nifty/daily.csv`
    - `shared_root/nifty/weekly.csv`
    - `shared_root/nifty/monthly.csv`
    - `shared_root/nifty/option_levels.csv`
    - `shared_root/nifty/option_chain.csv`
    - `shared_root/nifty/option_intraday.csv`
- not supported yet:
  - raw `TradingEngine` or `NiftyTradingEngine` session capture parsing
  - parquet adapters
  - jsonl event or quote reconstruction
  - contract-specific option intraday lifecycle pricing

## Required Data For TFIS Option-Selling Backtests

TFIS backtests for option-selling strategies will eventually need:

- spot or index OHLC data
- option OHLC data or option tick data
- option high/low reference data for `OPT_PRV_*` level construction
- expiry and strike metadata
- timestamp and session-calendar information
- data-quality metadata such as missing intervals, capture gaps, or malformed rows

## Near-Term Rule

- The TFIS backtest layer should consume offline CSV or Parquet readers.
- No Fyers capture code should be added to TFIS core.
- No broker-specific live capture framework should be introduced into TFIS while the shared-data path remains the intended direction.
- Shared-data ingestion should remain read-only.
- The first adapter layer should prefer normalized export folders over direct raw-capture parsing until raw capture contracts are explicitly normalized and documented.

## Later Decision

- A later architecture decision should determine whether market-data capture stays inside `TradingEngine` or is extracted into a shared package or service.
- Until that decision is made, TFIS should treat captured market data as an external validated input, not as an internal subsystem to rebuild.
- Existing `TradingEngine` captured Nifty and BankNifty data should be explicitly evaluated for reuse before any new capture work is considered.
- Future adapter work may add:
  - raw parquet readers
  - raw session-manifest discovery
  - context-session conversion
  - option quote reconstruction
  - archive-quality validation against capture completeness metadata
