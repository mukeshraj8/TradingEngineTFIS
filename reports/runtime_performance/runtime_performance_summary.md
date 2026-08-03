# Runtime Performance Summary

- Current live supervisor session: `NSE:2026-08-03:UNIFIED_INTERNAL_PAPER`
- Live evidence type: `PASSIVE_MEASURED_PRE_OPTIMIZATION_PROCESS`
- Configured poll interval: `5s`
- Observed heartbeat publish gaps: `[76.604, 346.986]`
- Observed snapshot publish gaps: `[76.878, 346.641]`
- Current verdict: `BLOCKED_BY_RUNTIME_CADENCE`

## Proven bottlenecks

- broker authentication was executed every cycle before the fix
- recovery and integrity scans were executed in the hot loop before the fix
- NSEFO symbol-master data was reloaded every cycle before the fix
- RELIANCE option-chain reads were repeated every cycle before the fix
- live-supervisor report generation re-ran preflight work inside the hot loop before the fix
- checkpoint, SQLite projection, and dashboard snapshot writes were repeated even when nothing meaningful changed

## Implemented reusable fixes

- bounded FYERS provider-call timeouts
- cached successful broker authentication for 300 seconds
- cached recovery snapshot for 60 seconds
- cached session-scoped NSEFO symbol master
- cached RELIANCE option chain for 60 seconds
- removed explicit preflight regeneration from the live hot loop
- skipped unchanged snapshot/checkpoint/SQLite writes within bounded intervals
- added stage-level hot-path instrumentation excluded from business hashes

## Immediate status

The running live supervisor remains on the earlier process image and still shows cadence overruns. The next real proof point is one complete before-market-open session on the updated code path.
