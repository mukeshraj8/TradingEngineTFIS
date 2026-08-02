# FYERS Authentication And S22 RELIANCE Capture Summary

Verdict: `FYERS_AUTH_AND_S22_RELIANCE_CONDITIONAL`

Canonical auth flow: `scripts/fyers_token_refresh.py --prepare` using `src/tfis/brokers/fyers_token.py` and `data/token_store.json`.

The sandboxed refresh attempt was blocked by outbound socket permissions. The approved escalated run completed the existing FYERS OTP/TOTP/PIN/auth-code/token flow, wrote the canonical local token store, and validated the profile without persisting raw secrets in reports.

Read-only diagnostics are healthy: configuration `READY`, credentials `PRESENT`, authentication `AUTHENTICATED`, reference data/history/quote/option chain `READABLE`, and order writes `NOT_AUTHORIZED`.

S22 RELIANCE capture completed from snapshot `s22-reliance-fyers-20260802T124359+0530`. Sanitized fixture: `tests\fixtures\s22_reliance\s22_reliance_fyers_snapshot_2026-08-02_sanitized.json`.

S22 implementation did not start in this authentication/capture milestone. The metadata gate is now passed and the next narrow task is S22 RELIANCE one-stock internal-paper implementation from the sanitized fixture.
