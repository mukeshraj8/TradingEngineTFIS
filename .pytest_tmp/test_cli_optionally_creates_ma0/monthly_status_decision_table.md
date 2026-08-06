# Monthly Status Decision Table

- Instrument group: `nifty`
- Threshold a_pct: `0.750`
- Threshold b_pct: `0.750`
- Threshold c_pct: `0.150`

This is diagnostic only and does not select final monthly status.

## Input Levels

- PMH: `100.000`
- PML: `90.000`
- CMH: `102.000`
- CML: `91.000`
- PWH: `101.000`
- PWL: `92.000`
- CWH: `102.000`
- CWL: `93.000`
- current_price: `103.000`
- bullish_value: `-`
- bearish_value: `-`

## Candidate Table

| Trigger | Candidate Status | Threshold | Condition Met | Confidence | Notes |
| --- | --- | ---: | --- | --- | --- |
| BULL_A_THRESHOLD | BULL | 100.750 | True | HIGH | Diagnostic BULL candidate from PMH plus a-percent threshold. |
| BEAR_A_THRESHOLD | BEAR | 89.325 | False | HIGH | Diagnostic BEAR candidate from PML minus a-percent threshold. |
| BULL_CF_B_THRESHOLD | BULL_CF | - | None | LOW | Bullish reference value is not available yet; BULL_CF remains unresolved until the future engine defines or provides it. |
| BEAR_CF_B_THRESHOLD | BEAR_CF | - | None | LOW | Bearish reference value is not available yet; BEAR_CF remains unresolved until the future engine defines or provides it. |
| REVERSAL_BULL_C_THRESHOLD | BULL | 102.153 | True | MEDIUM | Diagnostic reversal BULL candidate from MAX(PWH, CWH) plus c-percent threshold. |
| REVERSAL_BEAR_C_THRESHOLD | BEAR | 91.862 | False | MEDIUM | Diagnostic reversal BEAR candidate from MIN(PWL, CWL) minus c-percent threshold. |
