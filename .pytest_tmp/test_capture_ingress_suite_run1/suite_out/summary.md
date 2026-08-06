# S23 TradingEngine Capture Ingress Dry-Run Suite

- data root: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_run1\TradingData`
- out root: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_run1\suite_out`
- total sessions: `1`
- PASS: `0`
- WARNING: `1`
- NO_GO: `0`
- pass rate: `0.0%`
- selected-contract availability rate: `0.0%`
- max ORPT lag: `n/a`
- max RC lag: `n/a`
- rollout recommendation: `NO_GO`

## Per Session

### 2026-05-27 / context_session

- conversion status: `AUDIT_ONLY`
- input session folder: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_run1\TradingData\captures\context_sessions\2026-05-27\context_session`
- option quote file: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_run1\TradingData\data\nifty\20260527\options\index\NIFTY50_option_quotes_20260527.csv`
- classification: `WARNING`
- terminal state: `n/a`
- selected contract: `n/a`
- selected contract source: `n/a`
- ORPT lag: `n/a`
- RC lag: `n/a`
- stale events: `n/a`
- late events: `n/a`
- missing chain: `n/a`
- missing selected contract: `n/a`
- timezone mismatches: `n/a`
- unsupported continuation: `n/a`
- no fill/lifecycle artifacts present: `False`
- go/no-go interpretation: `WARNING: audit-only mode did not run the ingress dry run.`
- warnings:
  - Underlying quote gaps reach 550.0s in this session.

## Acceptance Thresholds

- minimum PASS rate: `80%`
- maximum WARNING count: `1`
- maximum NO_GO count: `0`
- hard blockers: `timezone_mismatch, unsupported_continuation, missing_selected_contract, stale_event, late_event, missing_option_chain, orpt_or_rc_lag_above_threshold, unexpected_fill_or_lifecycle_artifact`
