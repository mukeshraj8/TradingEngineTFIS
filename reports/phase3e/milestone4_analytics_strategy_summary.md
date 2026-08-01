# Phase 3E Milestone 4 Analytics And Strategy Summary

Date: Friday, July 31, 2026

Verdict: `MILESTONE_CONDITIONAL`

Milestone 4 defines the minimum Version 1 analytics/accounting fact model and
the first-10 strategy candidate/onboarding roadmap. The conditional verdict is
intentional: S23/S21 option-selling sources are strongest, while futures,
option-buying, and equity source sheets are available but not yet extracted into
implementation-ready rule matrices and normalized configs.

No analytics service, P&L code, dashboard, strategy config, broker integration,
runtime authority, paper authority, live authority, order mutation, or position
mutation was added.

## Accounting Truth

```text
broker-confirmed fills
+ contract metadata
+ charges/taxes
+ position quantity state
+ market marks
= accounting truth
```

Accounting truth feeds immutable `TradeFact` and `PnLFact` records, then
rebuildable analytical projections.

## Files Created

- `reports/phase3e/trade_fact_catalog.json`
- `reports/phase3e/pnl_fact_catalog.json`
- `reports/phase3e/analytics_metric_catalog.json`
- `reports/phase3e/strategy_inventory.json`
- `reports/phase3e/first_10_strategy_candidate_matrix.json`
- `reports/phase3e/strategy_onboarding_gate.json`

## P&L Decisions

- Version 1 cost basis: weighted average cost per `PositionCycle`.
- Historical P&L facts are not overwritten; corrections create superseding
  facts.
- Charges source priority: broker-confirmed charges, contract note/ledger
  import, configured estimate, unknown.
- Estimated charges must be labelled.
- Unrealized P&L mark policy remains a user decision before paper authority;
  recommended default is risk-conservative bid/ask.

## Strategy Inventory Result

Observed source/config coverage:

- S23 NIFTY weekly option-selling Call-side is the strongest candidate.
- S23 Put-side configs exist but require full vertical parity/source closure.
- S21 BankNifty monthly option-selling scaffolds exist but require source
  verification and ORPT/RC closure.
- Futures, Option Buying, and Equity source files exist in `TFISRulesAndSpec`,
  but exact implementation-ready rows/formulas/configs are not extracted.

## Candidate First 10

Recommended candidate slate:

1. S23 NIFTY Bull Call.
2. S23 NIFTY Bear Call.
3. S23 NIFTY Bull Put, conditional.
4. S23 NIFTY Bear Put, conditional.
5. S21 BankNifty monthly Bull Call, conditional.
6. S21 BankNifty monthly Bear Put, conditional.
7. One futures candidate from `AB6 Fut.xlsx`, conditional.
8. One option-buying candidate from `AB8 OB.xlsx`, conditional.
9. One equity candidate from `AB9 Equity.xlsx`, conditional.
10. One remaining S21 branch after first S21 proof, conditional.

## Onboarding Gate

Every strategy must pass source workbook identification, exact cell/formula
extraction, authoritative rule matrix completion, user-question closure,
definition/version/instance creation, policy composition, formula and branch
tests, synthetic golden fixtures, legacy/captured parity, performance profile,
fail-closed tests, shadow, paper readiness, controlled paper rollout,
operational acceptance, profitability review, and rollout/disable decision.

## Profitability Review

Technical correctness and profitability are separate. A technically correct but
unprofitable strategy may continue, observe longer, reduce paper allocation,
disable, investigate execution, investigate source/configuration, propose a
research experiment, or request user approval for a rule change.

Analytics must never automatically alter strategy rules.

## Next Milestone

Milestone 5 should finalize the complete Phase 3E roadmap, critical path, user
decisions, diagrams, and certification.
