# Shared Market Data Strategy

## Current Direction

- `TradingEngine` already captures NIFTY, BANKNIFTY, and option market data.
- TFIS should reuse validated captured data from that ecosystem where possible.
- TFIS should avoid building a second independent live market-data capture framework.
- The TFIS project should stay focused on rule evaluation, offline replay, backtesting, and strategy configuration.

## Proposed Future Model

- Maintain one shared market-data archive or root location.
- The data producer can be:
  - the existing `TradingEngine`, or
  - a future `SharedCaptureService` if capture is later extracted into a separate system.
- TFIS should consume local archived datasets such as CSV, Parquet, and manifest-backed files for backtesting and replay.
- `TradingEngine` and TFIS should remain decoupled through file-level and data-contract boundaries rather than direct runtime dependencies.

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

## Later Decision

- A later architecture decision should determine whether market-data capture stays inside `TradingEngine` or is extracted into a shared package or service.
- Until that decision is made, TFIS should treat captured market data as an external validated input, not as an internal subsystem to rebuild.
- Existing `TradingEngine` captured Nifty and BankNifty data should be explicitly evaluated for reuse before any new capture work is considered.
