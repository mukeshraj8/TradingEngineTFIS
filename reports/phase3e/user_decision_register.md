# Phase 3E User Decision Register

Date: Saturday, August 1, 2026

Only material Version 1 decisions are listed here. Decisions that are needed
only before paper authority do not block the first captured/replay shadow
implementation.

| Decision | Recommended default | Consequence | Blocking phase | Can defer |
| --- | --- | --- | --- | --- |
| Realized cost basis | Weighted average per `PositionCycle` | Handles multiple fills with simpler V1 accounting than lot slices | Before paper authority | No |
| Unrealized mark policy | Conservative executable-side mark: bid for long, ask for short, LTP fallback only with downgraded quality | Risk/PnL views are cautious and label weak data | Before paper authority | No |
| Provisional charges | Allow estimates intraday, superseded by broker-confirmed/contract-note charges | PnL is visible before final charges but clearly provisional | Before paper authority | No |
| First paper broker/account | User-selected account with read-only reconciliation proven first | Keeps authority scoped to one controlled route | Before paper authority | Yes for P4A shadow |
| Internal simulator vs broker sandbox | Internal simulator for deterministic development; broker sandbox for adapter testing where available | Separates deterministic proof from broker integration proof | Before paper authority | Yes for P4A shadow |
| Provisional first-10 slate | Accept the readiness-slot slate, not as immediate implementation approval | Avoids false readiness for source-only strategies | Before Wave 2 expansion | Yes |
| Equity inclusion | Keep one equity/stock-oriented slot conditional; do not force equity if it delays first paper trade | Preserves architecture coverage without slowing the critical path | Before first-10 finalization | Yes |
| Risk limits before paper | Start with strict per-account, per-strategy, per-day loss and active-order limits | Prevents portfolio expansion before controls are measured | Before paper authority | No |
| Protection mechanism | Prefer broker-hosted OCO if proven; otherwise application-managed linked protection with strict idempotency | Keeps protection capability explicit and broker-configurable | Before paper authority | No |
| Automatic reconciliation repair | Default to classify and block; automatic repair requires explicit approved rule per mismatch class | Prevents hidden mutation from uncertain broker truth | Before paper/live authority | No |
