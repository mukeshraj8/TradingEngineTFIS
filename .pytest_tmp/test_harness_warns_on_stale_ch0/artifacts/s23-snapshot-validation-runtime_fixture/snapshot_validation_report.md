# S23 Snapshot Validation Harness

## Overview
- Session ID: `s23-snapshot-validation-runtime_fixture`
- Strategy Path: `strategy`
- Config Path: `config\paper.s23.yaml`
- Runtime Fixture: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_harness_warns_on_stale_ch0\runtime_fixture.json`
- Requested Samples: `2`
- Interval Seconds: `0`

## Aggregate Metrics
- Successful Samples: `1`
- Failed Samples: `1`
- Contract Change Count: `0`
- Stable Selection Count: `1`
- Stale Chain Count: `1`
- Empty Chain Count: `0`
- Missing OI Count: `0`
- Prelude Build Failure Count: `1`
- Average Premium Drift: `n/a`
- Max Premium Drift: `n/a`
- Average OI Drift: `n/a`
- Max OI Drift: `n/a`

## Samples
### Sample 1
- Snapshot Timestamp: `2026-05-08T09:30:01+05:30`
- Selected Contract: `NIFTY_20260512_22400_PE`
- Selected Premium: `200.0`
- Selected OI: `1200.0`
- Expiry Used: `2026-05-12`
- Next Expiry Required: `False`
- Selected Contract Changed: `False`
- Premium Drift: `n/a`
- OI Drift: `n/a`
- Expiry Transition State: `CURRENT_EXPIRY_ACTIVE`
- Chain Completeness: `1.00`
- Rejected Candidate Counts: `{'option_type_mismatch': 1}`
- Warnings: `STALE_CHAIN`
### Sample 2
- Snapshot Timestamp: `2026-05-08T09:30:03+05:30`
- Selected Contract: `n/a`
- Selected Premium: `n/a`
- Selected OI: `n/a`
- Expiry Used: `n/a`
- Next Expiry Required: `n/a`
- Selected Contract Changed: `False`
- Premium Drift: `n/a`
- OI Drift: `n/a`
- Expiry Transition State: `UNKNOWN`
- Chain Completeness: `0.00`
- Rejected Candidate Counts: `{}`
- Warnings: `PRELUDE_BUILD_FAILURE`
- Warning Message: Blocked workbook path.

## Disclaimer
- Snapshot validation harness collects repeated one-shot FYERS snapshots for S23 paper readiness only. It does not start a socket loop, execute lifecycle logic, or place broker orders.
