# S22 Multi-Stock Foundation

Verdict: S22_MULTI_STOCK_FOUNDATION_CONDITIONAL

- Enabled stock: `RELIANCE` only
- Candidate stock 2: `TCS` (disabled, metadata-ready conditional, user-approved, held for baseline unified-session certification)
- Candidate stock 3: `INFY` (disabled, metadata-ready conditional, user-approved, held for baseline unified-session certification)
- Generic capture contract: `scripts/capture_s22_reliance_fyers_snapshot.py --symbol <SYMBOL>`
- Registry config: `config/s22_multi_stock_registry.yaml`
- Sanitized fixtures: `tests/fixtures/s22_multi_stock/`
- External broker-order authority: `NONE`

TCS and INFY are now explicitly approved for controlled S22 internal-paper onboarding, but both remain disabled for the next baseline unified-session certification.
After that certification passes, the approved controlled profile is `RELIANCE + TCS + INFY` on one shared internal-paper account with the existing sequential same-account acceptance rule.
INFY is no longer blocked by uneven strike spacing. Actual listed strike traversal is now proved and the selected contract is `NSE:INFY26AUG1140CE`.
