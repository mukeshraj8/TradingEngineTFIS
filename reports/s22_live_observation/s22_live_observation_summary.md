# S22 RELIANCE Live-Session Read-Only Observation

Verdict: `S22_RELIANCE_LIVE_OBSERVATION_BLOCKED`

Return code: `LIVE_SESSION_WINDOW_UNAVAILABLE`

The observation was evaluated at `2026-08-02T14:20:00+05:30` in
`Asia/Calcutta`. The date is Sunday, so NSE live market-open, ORPT, RC and EOD
evidence cannot be captured. Per the task boundary, no FYERS live read was
attempted and no fixture or deterministic supplement was promoted to captured
evidence.

Accepted baseline remains the one-stock S22 RELIANCE conditional proof in
`reports/s22_reliance/`, with selected contract `NSE:RELIANCE26AUG1260CE` and
external FYERS order authority `NONE`.

No S22 formulas were changed. No second stock was enabled. No FYERS order
operation, external-paper authority, or live authority was added.

Next required action: repeat this exact read-only RELIANCE observation during
the next eligible NSE trading session, preferably before market open so the
PreMarketStrategyPlan can be persisted before opening evaluation.
