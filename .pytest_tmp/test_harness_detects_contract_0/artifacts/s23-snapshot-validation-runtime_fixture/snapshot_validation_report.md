# S23 Snapshot Validation Harness

## Overview
- Session ID: `s23-snapshot-validation-runtime_fixture`
- Strategy Path: `strategy`
- Config Path: `config\paper.s23.yaml`
- Runtime Fixture: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_harness_detects_contract_0\runtime_fixture.json`
- Requested Samples: `2`
- Interval Seconds: `0`

## Aggregate Metrics
- Successful Samples: `2`
- Failed Samples: `0`
- Contract Change Count: `1`
- Stable Selection Count: `1`
- Stale Chain Count: `0`
- Empty Chain Count: `0`
- Missing OI Count: `0`
- Prelude Build Failure Count: `0`
- Average Premium Drift: `1.0`
- Max Premium Drift: `1.0`
- Average OI Drift: `200.0`
- Max OI Drift: `200.0`

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
- Warnings: `none`
### Sample 2
- Snapshot Timestamp: `2026-05-08T09:31:01+05:30`
- Selected Contract: `NIFTY_20260512_22500_PE`
- Selected Premium: `199.0`
- Selected OI: `1400.0`
- Expiry Used: `2026-05-12`
- Next Expiry Required: `False`
- Selected Contract Changed: `True`
- Premium Drift: `-1.0`
- OI Drift: `200.0`
- Expiry Transition State: `CURRENT_EXPIRY_ACTIVE`
- Chain Completeness: `1.00`
- Rejected Candidate Counts: `{'option_type_mismatch': 1}`
- Warnings: `CONTRACT_OSCILLATION`

## Disclaimer
- Snapshot validation harness collects repeated one-shot FYERS snapshots for S23 paper readiness only. It does not start a socket loop, execute lifecycle logic, or place broker orders.
