# S22 Multi-Stock Foundation

Verdict: S22_MULTI_STOCK_FOUNDATION_CONDITIONAL

- Enabled stock: `RELIANCE` only
- Candidate stock 2: `TCS` (disabled, metadata-ready conditional, approval not granted)
- Candidate stock 3: `INFY` (disabled, blocked on strike-interval evidence)
- Generic capture contract: `scripts/capture_s22_reliance_fyers_snapshot.py --symbol <SYMBOL>`
- Registry config: `config/s22_multi_stock_registry.yaml`
- Sanitized fixtures: `tests/fixtures/s22_multi_stock/`
- External broker-order authority: `NONE`

TCS remains a candidate-only stock pending one exact gap: simultaneous-acceptance priority authority.
INFY remains blocked for enablement because read-only capture shows irregular strike spacing and safe strike traversal is not yet proved.
