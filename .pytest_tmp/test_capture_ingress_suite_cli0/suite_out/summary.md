# S23 TradingEngine Capture Ingress Dry-Run Suite

- data root: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\TradingData`
- out root: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\suite_out`
- total sessions: `1`
- PASS: `1`
- WARNING: `0`
- NO_GO: `0`
- pass rate: `100.0%`
- selected-contract availability rate: `100.0%`
- max ORPT lag: `0.0`
- max RC lag: `0.0`
- rollout recommendation: `GO_FOR_CONTROLLED_PAPER`

## Per Session

### 2026-05-27 / context_session

- conversion status: `SUCCESS`
- input session folder: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\TradingData\captures\context_sessions\2026-05-27\context_session`
- option quote file: `D:\TradingEngineTFISRefactored\.pytest_tmp\test_capture_ingress_suite_cli0\TradingData\data\nifty\20260527\options\index\NIFTY50_option_quotes_20260527.csv`
- classification: `PASS`
- terminal state: `ORDER_PLANNED`
- selected contract: `NIFTY_20260602_23200_PE`
- selected contract source: `auto_min_spread`
- ORPT lag: `0.0`
- RC lag: `0.0`
- stale events: `0`
- late events: `0`
- missing chain: `0`
- missing selected contract: `0`
- timezone mismatches: `0`
- unsupported continuation: `0`
- no fill/lifecycle artifacts present: `False`
- go/no-go interpretation: `GO: normalized S23 live-paper ingress satisfied the dry-run thresholds and reached ORDER_PLANNED without fill or lifecycle execution.`

## Acceptance Thresholds

- minimum PASS rate: `80%`
- maximum WARNING count: `1`
- maximum NO_GO count: `0`
- hard blockers: `timezone_mismatch, unsupported_continuation, missing_selected_contract, stale_event, late_event, missing_option_chain, orpt_or_rc_lag_above_threshold, unexpected_fill_or_lifecycle_artifact`
