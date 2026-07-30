# Phase 3D Entry Inventory Summary

Verdict: `MILESTONE_ACCEPT`

Milestone 1 is complete as business capability discovery only. No Entry Engine
was implemented, no runtime path was migrated, and no strategy formulas,
configs, or policies were changed.

Milestone 1A adds the cross-strategy rule-sheet review. The initial inventory
required revision because new option-buying, option-selling, and futures rule
images show that Entry cannot be modeled as one universal linear step after
Gap/Missed-Entry and before Contract Selection.

## Business Capability Definition

Entry is the TFIS capability that determines whether a strategy has a valid
base and effective entry after the product-specific prerequisites are known.

Entry is not Gap/Missed-Entry, Contract Selection, Risk, Lifecycle, Decision,
or Execution. It consumes upstream context and produces an entry qualification
result for downstream engines.

## Inputs

Mandatory inputs include strategy identity, strategy version, resolved
configuration hash, product type, branch key, evaluation timestamp, entry
policy key, entry formula/reference, required market/premium references,
Monthly Status where applicable, Market Structure references, Gap/Missed-Entry
result, and provenance.

Optional or strategy-specific inputs include current-day HH/LL, previous HH/LL,
ORPT/RC observations, premium references, buffers, option side, workbook row,
compatibility profile, and captured/replay evidence classification.

## Outputs

Expected business outputs include:

- Base Entry
- Effective Entry
- Entry Qualified
- Entry Blocked
- Entry Rejected
- Entry Recalculated
- Entry Deferred
- Entry Invalid
- No Trade
- Entry Evidence

## Corrected Product-Aware Dependencies

Option strategies:

```text
Monthly Status
  -> Branch Resolution
    -> Underlying References
      -> Contract Selection
        -> Selected Contract References
          -> Base Entry
            -> Gap/Missed-Entry, where applicable
              -> Effective Entry
                -> Risk
```

Futures:

```text
Monthly Status or strategy context
  -> Branch Resolution
    -> Futures References
      -> Base Entry
        -> ORPT/RC Gap/Missed-Entry
          -> Effective Entry
            -> Risk
```

Equity remains evidence-limited and should use only explicit strategy
definitions.

The corrected graphs are acyclic. Option Contract Selection precedes base
Entry because selected-contract historical references are required by the
visible rule sheets.

## Rule-Sheet Groups Covered

- Stock Option Buying Monthly Rules
- Stock Option Buying Rules
- Stock Option Selling Rules
- BankNifty Monthly Option Selling Rules
- BankNifty Weekly Option Selling Rules
- Nifty Monthly Option Selling Rules
- Nifty Weekly Option Selling Rules
- BankNifty Futures examples
- USDINR Futures examples
- Stock Option Buying Monthly rollover evidence

Unclear screenshot values are marked `IMAGE_VERIFICATION_REQUIRED` in the
inventory and matrix instead of being implemented or inferred.

## Reference Model

Entry contracts must distinguish:

- `UNDERLYING_SPOT`
- `UNDERLYING_FUTURE`
- `SELECTED_OPTION_CONTRACT`
- `EQUITY_INSTRUMENT`
- `FINAL_STRIKE_VALUE`
- `OTHER_EXPLICIT_REFERENCE`

Examples such as Spot Previous 2DHH, FUT:PRV:1DHH, Previous 3DLL of Final
Strike, and Final Strike percentage have different source identities and must
not collapse into ambiguous aliases like `previous_2dhh`.

## Strategy Differences

S21 and S23 share an option-selling entry pattern, but they are not identical
authority cases. S23 has certified offline Gap/Missed-Entry compatibility
evidence and branch-specific missed-entry recalculation evidence. S21 ORPT/RC
applicability remains unresolved.

The new rule sheets add evidence for Option Buying, Stock Option Selling,
BankNifty/Nifty option selling variants, and Futures. They do not authorize
source-code formulas yet; exact formulas require workbook confirmation where
image text is ambiguous.

## State Ownership

Entry should remain stateless. Runtime state, waiting orders, open positions,
carry-forward state, broker state, and operator controls belong to Lifecycle,
runtime storage, execution/reconciliation, or governance layers.

## Evidence

Entry evidence should include policy key, formula expression, requirement IDs,
input values, intermediate values, base entry, effective entry, entry source,
Gap/Missed-Entry dependency status, recalculation source, warnings, failures,
quality, and provenance.

## Validation

Entry should fail closed for missing identity/configuration, missing policy,
missing Monthly Status, `UNKNOWN` Monthly Status, missing market or premium
references, missing/unsupported formulas, formula errors, invalid entry values,
blocked Gap/Missed-Entry, missing required recalculation output, unresolved
entry policy, unsupported product/family, composition mismatch, nondeterminism,
or stale required evidence.

## Open Rules

- S23 PUT missed-entry authoritative comparison remains unresolved.
- S21 ORPT/RC applicability remains unresolved.
- Full captured Gap/Missed-Entry parity remains incomplete.
- ORPT/RC applicability for the newly supplied option-buying and
  option-selling sheets is not proven.
- Exact branch-to-reference mapping for several image formulas is
  `IMAGE_VERIFICATION_REQUIRED`.
- Final Strike versus Entry as the percentage base must be preserved per
  formula and confirmed before implementation.
- Same-day re-entry and rollover are Lifecycle concerns, but exact
  authorization rules need workbook/user confirmation.
- Current-day FSL/TRP entry override ownership needs design review.
- Target/stop coupling in current `StrategyEvaluator` must be split without
  changing behavior.
- Equity entry rules remain undefined.
- Monthly-status expectation drift and S23 workbook/strike expectation
  failures remain separate open items.

## Recommended Boundary

Inside Entry:

- base entry
- effective entry
- entry qualification
- formula/policy evidence
- no-trade/block/reject reason
- consumption of Gap/Missed-Entry recalculation instruction

Outside Entry:

- Gap/Missed-Entry detection
- contract selection
- target/stop/risk
- lifecycle
- execution intent
- paper/live runtime
- broker adapters

## Migration Complexity

Overall complexity: High.

The main reason is existing coupling: current formula evaluation returns entry,
strike, premium, target, and stop together, while future Entry must isolate
entry authority and consume Phase 3C Gap/Missed-Entry output without changing
legacy behavior.

## Recommended Milestone 2

Proceed to Phase 3D Milestone 2: Generic Entry Contract design.

Milestone 2 should define `EntryInput`, `EntryResult`, `EntryEvidence`,
`EntryValidation`, `EntryFailure`, `EntryQuality`, `EntryMetrics`,
`EntryPolicy`, and `EntryCapability`. It should model Base Entry and Effective
Entry as explicit stages inside one Entry Engine while continuing to integrate
with the separate Phase 3C Gap/Missed-Entry Engine. It should remain
offline-only and must not activate runtime behavior.
