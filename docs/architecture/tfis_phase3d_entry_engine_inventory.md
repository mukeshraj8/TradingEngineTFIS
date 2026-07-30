# TFIS Phase 3D Entry Engine Inventory

Status: Phase 3D Milestone 1 business capability discovery. No Entry Engine is
implemented in this milestone.

Date: Wednesday, July 29, 2026

Verdict: `MILESTONE_ACCEPT`

## Scope

This inventory defines what Entry means as a TFIS business capability before
the Entry Engine contract is designed. It separates generic Entry concepts from
strategy-specific rules and records where the current implementation provides
behavioral evidence.

This milestone does not:

- implement an Entry Engine
- migrate runtime
- modify strategy config
- modify formulas
- modify policies
- resolve open business-rule questions
- revisit Phase 3C Gap/Missed-Entry certification

## Files Inspected

Architecture and planning:

- `docs/architecture/tfis_business_capability_master_plan.md`
- `docs/architecture/tfis_phase3c_gap_missed_entry_engine.md`
- `docs/architecture/tfis_phase3b_business_engine_framework.md`
- `docs/architecture/tfis_phase3a_strategy_identity_and_configuration.md`
- `docs/architecture/tfis_phase2b_s21_s23_policy_adapters.md`
- `docs/architecture/tfis_phase2d1_decision_evidence_packet.md`
- `docs/architecture/s23_weekly_option_selling_engine_contract.md`
- `docs/architecture/s21_banknifty_monthly_option_selling_contract.md`

Configuration and workbook-derived rule folders:

- `config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D*/`
- `config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_*/`
- `config/strategy_definitions/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D/`
- `config/strategy_definitions/S21_BANKNIFTY_OP_SELL_MONTHLY/`
- `config/strategy_instances/S23_NIFTY_ACCOUNT_A_PAPER.yaml`
- `config/strategy_instances/S21_BANKNIFTY_ACCOUNT_A_PAPER.yaml`
- `config/business_engines/catalog.yaml`

Current implementation evidence:

- `src/tfis/decision/models.py`
- `src/tfis/decision/engine.py`
- `src/tfis/adapters/legacy_policies/policies.py`
- `src/tfis/strategy/strategy_evaluator.py`
- `src/tfis/strategy/s23_recalculation.py`
- `src/tfis/backtest/entry_missed.py`
- `src/tfis/backtest/historical_runner.py`
- `src/tfis/paper/live_prelude.py`
- `src/tfis/paper/runtime_contract_adapters.py`
- `src/tfis/domain/decision_evidence.py`

Tests and reports:

- `tests/unit/test_tfis_decision_engine.py`
- `tests/unit/test_strategy_evaluator.py`
- `tests/unit/test_strategy_folder_loader.py`
- `tests/unit/test_s23_recalculation.py`
- `tests/unit/test_phase3c_gap_missed_entry_*`
- `reports/phase3c/gap_missed_entry_parity_summary.md`
- `reports/phase3c/phase3c_certification_summary.md`

## 1. What Exactly Is Entry?

Entry is the business capability that decides whether a strategy has a valid
entry price and entry qualification after upstream market context,
monthly-status context, and Gap/Missed-Entry evidence are known.

Entry answers these business questions:

- What is the base entry reference for this strategy branch?
- Is that entry reference valid and tradeable?
- Did upstream Gap/Missed-Entry evidence require a recalculated entry path?
- If recalculation exists, is it authoritative, compatibility-only, missing,
  blocked, or deferred?
- What effective entry should downstream Contract Selection use?
- If no entry can be produced, what no-trade reason must be reported?

Entry is separate because it is the first point where strategy formula evidence
becomes an actionable business threshold. Market Structure and Monthly Status
prepare context. Gap/Missed-Entry explains timing and missed-entry effects.
Entry turns those inputs into an entry decision that downstream engines can use
without understanding workbook formula internals.

### Why Entry Is Not Gap

Gap/Missed-Entry classifies timing, observations, comparison source/operator,
missed-entry status, and recalculation instruction. It does not own final entry
authority.

Entry consumes Gap/Missed-Entry output. If Gap/Missed-Entry says
`NOT_MISSED`, Entry may keep the base entry path. If it says `MISSED` with a
usable recalculation instruction, Entry may produce an effective recalculated
entry. If it says unresolved or fail-closed, Entry must block or reject the
entry path.

### Why Entry Is Not Contract Selection

Entry decides the price/threshold and qualification state. Contract Selection
uses the entry state, premium ranges, strike ranges, option-chain/product
universe, expiry rules, and OI/premium filters to select a concrete contract.

Entry should not scan option chains, select strikes, choose near/next expiry,
or validate broker symbols.

### Why Entry Is Not Risk

Entry produces entry price and entry qualification. Risk uses selected contract
and effective entry context to derive target, stop, MSL, TSL, APS, FSL, sizing,
and risk state. Current `StrategyEvaluator` returns target and stop together
with entry, but Phase 3D should not preserve that coupling inside the generic
Entry Engine.

## 2. Input Inventory

Inputs are grouped by business category. The future contract may structure them
differently, but it should not lose these concepts.

### Mandatory Inputs

- strategy family id
- strategy definition id
- strategy version
- strategy instance id
- evaluation id
- resolved configuration hash
- product type
- instrument/symbol identity
- strategy branch or branch key
- evaluation timestamp
- trading/session date
- entry policy key
- entry formula or policy reference
- required market reference values for the entry formula
- formula parameters such as entry discount/buffer values
- Monthly Status when the strategy is monthly-status driven
- Market Structure references required by the configured entry policy
- Gap/Missed-Entry result or explicit `NOT_APPLICABLE` evidence
- evidence provenance for every supplied value

### Optional Inputs

- current-day high
- current-day low
- previous 1D/2D/3D/4D high/low references
- premium references
- option reference levels such as `OPT_PRV_3DLL` and `OPT_PRV_2DLL`
- ORPT observation
- RC observation
- bid/ask/LTP
- higher-timeframe context
- captured decision packet references
- replay/captured evidence classification
- operator notes for review-only runs

### Strategy-Specific Inputs

- S21 monthly BankNifty branch identity
- S23 weekly NIFTY branch identity
- option side, such as CALL or PUT
- trade direction and execution side
- configured workbook row/rule reference
- strategy-specific entry discount percentage
- strategy-specific premium reference aliases
- strategy-specific branch mapping from Monthly Status
- strategy-specific unresolved rule flags
- compatibility policy profile

### Derived Inputs

- base trade plan from current formula evaluation
- base entry price
- gap classification
- missed-entry status
- recalculation instruction
- recalculated entry candidate
- recalculated strike/premium candidate values, as supplied by upstream
  compatibility evidence
- effective formula input map after upstream substitutions
- data-quality classification

### Current Evidence From S21/S23 Rules

S21 and S23 option-selling branches share a broad shape:

- monthly status selects bullish or bearish rule groups
- CE and PE legs are independent
- entry formula uses an option premium reference minus configured discount
- target and stop are currently evaluated alongside entry by
  `StrategyEvaluator`, but those belong to later Risk migration
- contract selection happens after formula output

Known examples from folder rules:

- S23 Bull Call and S21 Bull Call use `OPT_PRV_3DLL - PARAM(entry_discount_pct)%`
- S23 Bull Put uses `OPT_PRV_2DLL - PARAM(entry_discount_pct)%`
- S21 Bear Put uses `OPT_PRV_3DLL - PARAM(entry_discount_pct)%`

These examples are evidence, not a full generic rule. Phase 3D must not infer
that every future strategy uses option previous-low references or a 7.5 percent
discount.

## 3. Output Inventory

Entry outputs should be business concepts, not just variables.

### Base Entry

The entry derived directly from the configured strategy branch before
Gap/Missed-Entry recalculation effects are applied.

Required evidence:

- policy key
- formula reference
- input values
- intermediate values
- result value
- quality

### Effective Entry

The entry that downstream engines should consume after Gap/Missed-Entry output
is applied.

Possible sources:

- base entry
- recalculated entry
- explicit compatibility output
- unavailable due to missing evidence
- blocked due to unresolved rule

### Entry Qualified

The strategy has a usable effective entry and may proceed to Contract
Selection.

This does not mean an order should be placed. It means the entry threshold is
valid enough for the next engine.

### Entry Blocked

Entry evaluation intentionally stops because required evidence, policy, or
authority is missing. Downstream engines must not execute.

### Entry Rejected

Entry formula/policy evaluated safely and determined that no trade should
continue. Rejection should preserve business reason and evidence.

### Entry Recalculated

Entry used an upstream recalculation instruction to produce an effective entry.
The result must distinguish authoritative future behavior from compatibility
outputs.

### Entry Deferred

Entry cannot make an authority decision yet but may emit evidence-only output
for offline reports. Runtime and paper authority must treat deferred executable
behavior as blocked unless explicitly approved.

### Entry Invalid

Inputs are contradictory, formula output is invalid, chronology is unsafe, or
the policy output cannot be trusted.

### No Trade

A business no-trade decision caused by entry failure, unsupported status,
missing evidence, unresolved upstream rule, or rejected qualification.

### Entry Evidence

The full audit packet fragment for entry:

- formula
- references
- inputs
- intermediate values
- base/effective entry
- source of effective entry
- warnings
- failures
- quality
- provenance

## 4. State Ownership

Entry should remain stateless.

Entry may consume state-derived facts, but it should not own mutable state. For
example:

- existing position state belongs to Lifecycle/runtime state
- waiting paper order state belongs to paper lifecycle/order storage
- carry-forward state belongs to Lifecycle/runtime state
- broker order state belongs to execution/reconciliation services
- operator controls belong to runtime governance

If current code appears to combine entry with lifecycle state, Phase 3D should
split the concepts. Entry may be told that a position already exists or that a
strategy instance is blocked, but it should not persist or mutate that state.

The state isolation key established by Phase 3A remains:

```text
strategy_instance_id + trading_date + position_cycle_id
```

Entry should include these identity values in evidence, but state persistence
belongs outside the engine.

## 5. Dependencies

### Upstream Providers

Entry consumes:

- Strategy Identity and Configuration Resolution
- Market Structure
- Monthly Status
- Gap/Missed-Entry
- formula/policy registry
- normalized price and reference evidence
- Decision Evidence Packet inputs when running replay/parity

### Downstream Consumers

Entry provides inputs to:

- Contract Selection
- Risk
- Lifecycle, indirectly through downstream plans
- Decision composition
- Decision Evidence Packet
- runtime shadow reports

### Dependency Diagram

```text
Strategy Identity
  -> Resolved Strategy Configuration
    -> Market Structure
      -> Monthly Status
        -> Gap/Missed-Entry
          -> Entry
            -> Contract Selection
              -> Risk
                -> Lifecycle
                  -> Execution Intent
                    -> Decision
```

Entry must not depend on Contract Selection, Risk, Lifecycle, Execution Intent,
paper runtime, live runtime, or broker adapters.

## 6. Business Rules

This inventory separates generic Entry concepts from strategy rules.

### Generic Entry Concepts

Generic Entry concepts:

- base entry
- effective entry
- entry source
- entry qualification
- entry blocked
- entry rejected
- entry recalculated
- entry deferred
- entry invalid
- no-trade reason
- entry evidence

Generic Entry should understand:

- whether an entry value exists
- whether it is supplied, calculated, recalculated, or unavailable
- whether upstream Gap/Missed-Entry permits use
- whether missing or unresolved evidence requires fail-closed behavior
- whether downstream engines may proceed

Generic Entry should not contain:

- S21 branch formulas
- S23 branch formulas
- option-chain scanning
- target/stop formulas
- lifecycle transition rules
- broker/paper order creation

### Strategy Rules

Strategy rules remain behind explicit policy keys. Current evidence shows:

- S21 and S23 option-selling entry formulas are workbook-derived.
- S23 recalculation can supply recalculated entry values after missed-entry
  detection.
- S23 current-day FSL/TRP handling can supply an entry override for certain
  workbook-backed paths, but unresolved/blank workbook branches must not be
  inferred.
- S21 ORPT/RC applicability remains unresolved and must not be guessed.

### Base Entry

Base Entry is the configured strategy branch's initial entry result. In current
S21/S23 option-selling evidence, it is usually an option premium reference less
an entry discount. Future strategies may use different formulas.

### Gap-Adjusted Entry

Gap-adjusted entry is a concept, not yet a confirmed universal formula. It
means Entry may receive upstream gap evidence that changes whether the base
entry remains valid. Phase 3D must not invent a gap-adjusted formula unless
the workbook/config confirms it.

### Missed Entry

Missed-entry classification belongs upstream in Gap/Missed-Entry. Entry
consumes the result and decides whether the effective entry remains base,
recalculated, blocked, or deferred.

### Recalculated Entry

Recalculated Entry is an effective entry derived from an upstream
recalculation instruction. For S23, current behavior has branch-specific RC
recalculation evidence. Entry should consume those outputs; it should not own
ORPT/RC detection.

### Blocked Entry

Blocked Entry is a fail-closed result when required evidence or authority is
missing.

### Rejected Entry

Rejected Entry is a safe no-trade result where the entry policy evaluated but
business criteria are not met.

## 7. Strategy Differences

| Area | S21 | S23 | Future Option Sell | Option Buy | Futures | Equity |
| --- | --- | --- | --- | --- | --- | --- |
| Entry concept | Shared option-selling concept | Shared option-selling concept plus missed-entry recalculation evidence | Shared if explicitly defined | Unknown | Unknown | Unknown |
| Monthly Status dependency | Required by contract if strategy is active | Required | Strategy-specific | Unknown | Strategy-specific | Strategy-specific |
| Gap/Missed-Entry dependency | Unknown/exvidence-only for ORPT/RC | Certified offline; runtime deferred | Strategy-specific | Unknown | Strategy-specific | Usually unknown |
| Base entry formula | Workbook-derived; branch-specific | Workbook-derived; branch-specific | Must be defined | Not defined here | Not defined here | Not defined here |
| Recalculated entry | Unknown | Supported as compatibility evidence for S23 paths | Unknown | Unknown | Unknown | Unknown |
| Contract selection dependency | Monthly option contract selection required later | Weekly option contract selection required later | Required for options | Required for options | Product reference required | Symbol/security validation required |
| Risk coupling today | Target/SL formula evaluated with entry | Target/SL formula evaluated with entry | Should be split | Unknown | Unknown | Unknown |
| Runtime authority | Not active for generic Entry | Not migrated to generic Entry | Not supported | Not supported | Not supported | Not supported |

Shared:

- Entry should be strategy-version keyed.
- Entry should preserve formula references, inputs, and intermediate values.
- Entry should fail closed when mandatory evidence is missing.
- Entry should remain broker-agnostic and stateless.

Different:

- branch formula references
- product family
- option side semantics
- premium/reference aliases
- recalculation applicability
- expiry/contract selection needs

Unknown:

- S21 ORPT/RC use
- future Option Buy/Futures/Equity formulas
- whether any future strategy has gap-adjusted entry formulas
- whether current-day FSL/TRP entry override should become Entry-owned or stay
  in a separate risk/lifecycle-related policy

## 8. Evidence Requirements

Entry should produce evidence that allows a reviewer to reconstruct why an
entry was qualified, blocked, rejected, recalculated, or deferred.

Required evidence:

- engine id
- schema version
- strategy family/definition/version/instance
- evaluation id
- resolved configuration hash
- entry policy key
- policy/profile version
- branch key
- product type
- formula reference
- requirement IDs
- formula expression
- raw input references
- provenanced observed/reference values
- parameter values
- intermediate values
- base entry value
- effective entry value
- effective entry source
- Gap/Missed-Entry dependency status
- recalculation dependency status
- warnings
- failures
- quality
- no-trade reason where applicable
- downstream permission

Evidence quality classifications should include:

- `VALID`
- `PARTIAL`
- `DEGRADED`
- `INVALID`
- `NOT_APPLICABLE`

Evidence classifications for parity should include:

- full captured parity
- partial captured parity
- synthetic golden parity
- captured with synthetic supplement
- legacy fixture parity
- unsupported for parity

## 9. Validation And Fail-Closed Conditions

Entry should fail closed or reject safely for:

- missing strategy identity
- missing strategy version
- missing resolved configuration hash
- missing entry policy key
- unknown policy key
- unresolved policy profile
- missing Monthly Status for monthly-status driven strategies
- `UNKNOWN` Monthly Status
- missing required Market Structure references
- missing required premium references
- missing formula
- unsupported formula syntax
- formula evaluation error
- non-numeric entry result where numeric entry is required
- invalid negative/zero entry where product policy disallows it
- missing Gap/Missed-Entry result when configured as required
- Gap/Missed-Entry fail-closed status
- unresolved missed-entry authority
- recalculation required but missing recalculation output
- recalculation output incompatible with policy
- invalid timing/chronology propagated from upstream evidence
- unsupported strategy family
- unsupported product
- contradictory base/effective entry evidence
- nondeterministic policy timestamp
- stale supplied reference evidence when freshness is required

Validation outcomes should distinguish:

- blocked: cannot safely continue
- rejected: evaluated no-trade
- unavailable: evidence missing or incomplete
- deferred: evidence-only, no authority
- invalid: contradictory or unsafe
- passed: downstream engines may proceed

## 10. Downstream Impact

### Contract Selection

Contract Selection needs:

- effective entry
- entry qualification status
- strike range and premium thresholds only if those remain part of Entry output
  for compatibility
- no-trade/block reason
- formula/policy provenance

If Entry is blocked, Contract Selection must not run.

### Risk

Risk needs:

- effective entry
- entry source
- selected contract from Contract Selection
- formula references for risk calculations

Risk should own target, stop, MSL, TSL, APS, FSL, and sizing. Current
`StrategyEvaluator` coupling is evidence of existing behavior, not the desired
future boundary.

### Lifecycle

Lifecycle needs:

- selected contract
- effective entry
- risk plan
- waiting/open state
- lifecycle state

Entry should not decide whether a waiting paper order fills. It supplies the
entry threshold that lifecycle/paper execution can use.

### Decision

Decision composition needs:

- entry status
- base/effective entry
- no-trade reason
- warnings/failures
- evidence fragment
- downstream permission

### Execution

Execution should not consume Entry directly. It consumes Execution Intent after
Contract Selection, Risk, Lifecycle, and Decision gates.

## 11. Migration Complexity

Overall complexity: High.

Reasons:

- Entry is the first downstream consumer of Phase 3C Gap/Missed-Entry output.
- Current legacy formula evaluation returns entry, target, stop, strike, and
  premium values together.
- Future Entry must split entry authority from Contract Selection and Risk
  without changing behavior.
- S21 and S23 share option-selling shape but differ in unresolved operational
  status and timing evidence.
- S23 missed-entry recalculation can alter effective entry and downstream
  contract selection/risk/lifecycle behavior.
- Full captured evidence is still incomplete.
- Current generic decision engine has an older policy order where Entry runs
  before Gap/Missed-Entry; Phase 3D must define the future business-engine
  order without breaking existing offline adapters.

Sub-area complexity:

| Area | Complexity | Reason |
| --- | --- | --- |
| Generic contract | Medium | Shape is clear from Phase 3B/3C patterns |
| S21/S23 inventory | Medium | Formulas are configured, but S21 timing is unresolved |
| Effective entry semantics | High | Must consume recalculation without owning missed-entry |
| Evidence packet integration | Medium | Existing packet has calculated decision entry and Gap/Missed-Entry fragments |
| Parity harness | High | Legacy evaluator couples entry with strike/target/stop |
| Runtime shadow | High | Requires captured evidence and no-op runtime observer |
| Paper authority | Very High | Requires Contract Selection, Risk, Lifecycle, and Execution Intent maturity |

## 12. Open Rules

Open items:

- S23 PUT missed-entry authoritative comparison remains unresolved.
- S21 ORPT/RC applicability remains unresolved.
- Full captured Gap/Missed-Entry parity remains incomplete.
- Whether current-day FSL/TRP entry override belongs to Entry, Risk, or a
  separate compatibility policy requires design review.
- Current `StrategyEvaluator` computes target/stop together with entry; Phase
  3D must avoid treating target/stop as Entry-owned.
- Future Option Buy, Futures, and Equity entry rules are not defined.
- Monthly-status expectation drift remains outside Phase 3D but affects
  upstream readiness.
- S23 workbook/strike expectation failures remain workbook-verification
  pending and must not be silently fixed in Entry.
- Captured evidence for full Entry parity is incomplete.

## 13. Recommended Engine Boundary

### Belongs Inside Entry Engine

- base entry evaluation
- effective entry selection
- entry status classification
- entry policy resolution by definition/version
- formula reference preservation
- entry input validation
- entry output evidence
- no-trade/block/reject reason for entry-stage failures
- consumption of Gap/Missed-Entry recalculation instructions
- distinction between authoritative and compatibility-only entry outputs
- deterministic serialization
- immutable result construction

### Belongs Outside Entry Engine

- Market Structure calculation
- Monthly Status calculation
- Gap classification
- missed-entry detection
- ORPT/RC capture
- contract selection
- option-chain scanning
- expiry selection
- target/stop/MSL/TSL/APS/FSL
- lifecycle state transitions
- waiting-order fills
- paper order persistence
- broker order routing
- broker SDK calls
- dashboard rendering
- runtime process management
- live-money readiness gates

## 14. Recommended Contract Shape

No implementation is performed in Milestone 1. The following contract names are
recommended for Milestone 2 design.

### EntryInput

Recommended fields:

- strategy identity fields
- product type
- evaluation timestamp
- policy key
- monthly status
- market structure references
- gap/missed-entry result
- recalculation instruction
- formula references
- formula input map
- strategy parameters
- optional captured/replay evidence references
- provenance

### EntryResult

Recommended fields:

- engine id
- status
- quality
- validation
- base entry
- effective entry
- effective entry source
- entry qualification
- no-trade reason
- downstream permission
- evidence
- warnings
- failures
- metrics
- provenance

### EntryEvidence

Recommended fields:

- policy key
- profile/version
- formula expression
- formula references
- requirement references
- input values
- intermediate values
- base entry value
- effective entry value
- recalculation source
- upstream Gap/Missed-Entry dependency status
- data quality
- warnings
- failures
- provenance

### EntryValidation

Recommended fields:

- issues
- unresolved issues
- passed flag
- blocking flag
- downstream permission

### EntryFailure

Recommended enum candidates:

- `MISSING_REQUIRED_INPUT`
- `MISSING_MONTHLY_STATUS`
- `UNKNOWN_MONTHLY_STATUS`
- `MISSING_MARKET_REFERENCE`
- `MISSING_PREMIUM_REFERENCE`
- `MISSING_ENTRY_FORMULA`
- `UNSUPPORTED_FORMULA`
- `FORMULA_EVALUATION_ERROR`
- `INVALID_ENTRY_VALUE`
- `GAP_MISSED_ENTRY_BLOCKED`
- `RECALCULATION_REQUIRED_BUT_MISSING`
- `UNRESOLVED_ENTRY_POLICY`
- `UNSUPPORTED_PRODUCT`
- `UNSUPPORTED_STRATEGY_FAMILY`
- `STRATEGY_COMPOSITION_MISMATCH`
- `NONDETERMINISTIC_TIMESTAMP`

### EntryQuality

Recommended values:

- `VALID`
- `PARTIAL`
- `DEGRADED`
- `INVALID`
- `NOT_APPLICABLE`

### EntryMetrics

Recommended fields:

- validation seconds
- policy resolution seconds
- formula evaluation seconds
- evidence serialization seconds
- input count
- missing input count
- output size bytes
- deterministic output hash

### EntryPolicy

Recommended protocol:

```text
EntryPolicy.evaluate(EntryInput) -> EntryPolicyOutcome
```

Policy responsibility:

- strategy-specific formula interpretation
- profile-specific effective-entry behavior
- formula input mapping
- compatibility output mapping

Generic engine responsibility:

- validation
- immutable result assembly
- fail-closed behavior
- evidence normalization
- deterministic serialization

### EntryCapability

Recommended capabilities:

- `ENTRY`
- `BASE_ENTRY`
- `EFFECTIVE_ENTRY`
- `RECALCULATED_ENTRY`
- `ENTRY_QUALIFICATION`

## 15. Recommended Migration Plan

Use the same successful shape as Phase 3C.

### Milestone 2: Generic Entry Contract

Objective:

- define immutable Entry input/result/evidence/validation/failure/quality
  contracts
- keep generic engine strategy/broker/runtime agnostic
- define how Gap/Missed-Entry output is consumed

Deliverables:

- Entry Engine contract specification
- domain contract models
- catalog metadata update if needed
- architecture tests
- focused contract tests

No runtime activation.

### Milestone 3: Compatibility Policies

Objective:

- add S21/S23 compatibility policies behind the generic Entry contract
- preserve current supported behavior without moving formulas into generic
  code

Deliverables:

- S21 evidence profile
- S23 branch/profile compatibility policies
- explicit policy composition by strategy definition/version
- tests for missing inputs and fail-closed behavior

No formula redesign.

### Milestone 4: Parity And Evidence Integration

Objective:

- prove supported Entry behavior against current legacy evidence
- integrate typed Entry evidence into decision packets/reports

Deliverables:

- deterministic parity cases
- JSON/CSV/Markdown reports
- evidence packet fragment
- mismatch taxonomy
- performance measurements

No runtime activation.

### Milestone 5: Certification

Objective:

- certify Entry as offline-complete for supported behavior
- document readiness levels separately
- define runtime shadow blockers

Deliverables:

- authoritative Entry Engine specification
- open-rule register updates
- certification JSON/Markdown
- runtime readiness matrix
- recommended next phase

Stop after certification and wait for approval.

## 16. Milestone 1 Findings

### Key Finding 1: Entry Is A Qualification Capability

Entry is not just `entry_price`. It is the capability that decides whether a
strategy has a valid base/effective entry and whether downstream engines may
continue.

### Key Finding 2: Current Entry Evidence Is Coupled

Current `StrategyEvaluator` produces start/end strike, ideal/minimum premium,
entry, target, and stoploss in one trade plan. Phase 3D must preserve behavior
without making the new Entry Engine own Contract Selection or Risk.

### Key Finding 3: Future Entry Must Consume Phase 3C Output

The future business-engine pipeline places Entry after Gap/Missed-Entry. This
is different from the older Phase 2 generic decision policy order and must be
handled as a migration boundary, not a silent rewrite.

### Key Finding 4: Runtime Authority Is Not Ready

Entry can be designed and tested offline next, but runtime shadow, paper
authority, and live authority remain blocked until later milestones and broader
pipeline certification.

## 17. Cross-Strategy Rule-Sheet Addendum

Status: Phase 3D Milestone 1A addendum. This section incorporates
user-provided rule-sheet screenshots supplied after the initial inventory.

Evidence status:

- `IMAGE_CONFIRMED`: visible in the provided rule images.
- `IMAGE_VERIFICATION_REQUIRED`: present in the image set but not fully
  readable enough to transcribe as an implementation formula.
- `WORKBOOK_CONFIRMATION_REQUIRED`: must be confirmed from source workbook or
  normalized strategy definition before implementation.
- `IMPLEMENTATION_CONFIRMED`: already represented in existing TFIS code,
  config, tests, or Phase 3C evidence.
- `INSUFFICIENT_EVIDENCE`: no reliable user/repository evidence yet.

This addendum supersedes the earlier universal dependency assumption that
Entry always follows Gap/Missed-Entry and always precedes Contract Selection.
The corrected dependency is product-aware.

### Rule-Sheet Groups Covered

The current conversation supplied images for:

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

No source code, runtime config, strategy YAML, or policy implementation is
changed by this addendum.

### Corrected Product-Aware Pipeline

Option Buying and Option Selling:

```text
Strategy Identity
  -> Resolved Strategy Configuration
    -> Monthly Status
      -> Strategy Branch Resolution
        -> Underlying reference collection
          -> Strike range calculation
            -> Contract/Instrument Selection
              -> selected option contract references
                -> Base Entry
                  -> Gap/Missed-Entry, when applicable
                    -> Effective Entry
                      -> Risk
                        -> Lifecycle
                          -> Execution Intent
                            -> Decision
```

Futures:

```text
Strategy Identity
  -> Resolved Strategy Configuration
    -> Monthly Status, when strategy requires it
      -> Strategy Branch Resolution
        -> Futures reference collection
          -> Base Entry
            -> ORPT missed-entry check
              -> RC recalculation, when missed
                -> Effective Entry
                  -> Risk
                    -> Lifecycle
                      -> Execution Intent
                        -> Decision
```

Equity:

```text
Strategy Identity
  -> Resolved Strategy Configuration
    -> Instrument Resolution
      -> Base Entry, only where an explicit strategy definition exists
        -> Gap/Missed-Entry, only if configured
          -> Effective Entry
            -> Risk
```

The graphs above are acyclic. The important correction is that option Entry
cannot own strike search, expiry fallback, OI filtering, or premium
qualification because those steps are prerequisites for selected-contract
historical references used by the visible entry formulas.

### Reference Instrument Model

Entry contracts must use explicit reference identities. Ambiguous aliases such
as `previous_2dhh` are not sufficient.

| Reference example | Instrument/source identity | Timeframe/reference type | Formula role | Evidence |
| --- | --- | --- | --- | --- |
| Spot Previous 2DHH | `UNDERLYING_SPOT` | Previous 2-day high-high | Strike range or option-buy branch reference | `IMAGE_CONFIRMED` |
| Spot Previous 4DLL | `UNDERLYING_SPOT` | Previous 4-day low-low | Strike range or option-buy branch reference | `IMAGE_CONFIRMED` |
| FUT:PRV:1DHH | `UNDERLYING_FUTURE` | Previous 1-day high-high | Futures base entry or gap recalculation reference | `IMAGE_CONFIRMED` |
| FUT:PRV:2DLL | `UNDERLYING_FUTURE` | Previous 2-day low-low | Futures base entry or gap recalculation reference | `IMAGE_CONFIRMED` |
| Previous 2DHH of Final Strike | `SELECTED_OPTION_CONTRACT` | Previous 2-day high-high of selected option | Option entry or risk reference | `IMAGE_CONFIRMED` |
| Previous 3DLL of Final Strike | `SELECTED_OPTION_CONTRACT` | Previous 3-day low-low of selected option | Option sell base entry reference | `IMAGE_CONFIRMED` |
| Final Strike * percentage | `FINAL_STRIKE_VALUE` | Static selected strike value | Percentage base for entry/target/SL formulas | `IMAGE_CONFIRMED` |
| Current Market Price of Final Strike | `SELECTED_OPTION_CONTRACT` | Rollover-day current premium | Rollover entry evidence | `IMAGE_CONFIRMED` |
| Equity previous HH/LL | `EQUITY_INSTRUMENT` | Product-specific historical reference | Entry/risk if a strategy defines it | `INSUFFICIENT_EVIDENCE` |

### Capability Ownership Matrix

| Capability | Owns | Does not own |
| --- | --- | --- |
| Branch Resolver | Monthly-status branch, product leg, trade side labels such as Bull/Bull CF, Bear/Bear CF, Call Buy, Put Sell, Futures Long, Futures Short | Formula execution, strike scanning, order placement |
| Contract Selection | Strike factor, start/end strike, rounding, midpoint handling, near/next fallback, OI filters, ideal/minimum premium qualification, final strike/contract | Base entry authority, target/SL, ORPT/RC missed-entry detection |
| Entry | Base entry candidate, effective entry trigger, entry qualification, entry formula evidence, entry block/reject/no-trade reason | Contract selection, risk, lifecycle state, broker orders |
| Gap/Missed Entry | ORPT observation, RC timing, HH/LL comparison, missed/not-missed status, recalculation instruction/result | Strategy branch resolution, strike selection, target/SL |
| Risk | Targets, stop loss, MSL/FSL/TSL, APS, TRP, sizing | Base entry discovery, missed-entry detection |
| Lifecycle | Position open/exited state, rollover authorization, same-day re-entry eligibility, waiting/order lifecycle | Entry formula ownership, risk formula ownership |

### Base Entry Versus Effective Entry

`BaseEntryCandidate` is the initial configured threshold for a resolved
strategy branch and selected instrument/contract.

For option strategies, base entry usually cannot be calculated until after
Contract Selection because the formula references the selected final strike or
the selected option contract's historical premium references.

For futures, base entry can be calculated directly from futures historical
references because the traded instrument is already known.

`EffectiveEntryTrigger` is the value downstream engines should use after
Gap/Missed-Entry evidence is applied. It may equal the base entry, or it may be
the result of an RC recalculation rule. If a recalculation is required but the
source rule is unreadable, unsupported, or not configured, Entry must block or
defer authority rather than inventing a formula.

Same-day re-entry after position exit is not Entry-owned. It is Lifecycle
authorization that may request a new Entry evaluation using explicit
re-entry context.

### Product-Specific Entry Inventory

#### Option Buying

Observed branches and legs:

- Bullish/Bullish Confirmed: Call Buy and Put Buy.
- Bearish/Bearish Confirmed: Call Buy and Put Buy.

Contract selection dependencies:

- underlying spot historical references such as Spot Previous 2DHH, 4DLL,
  4DHH, and 2DLL;
- strike factor;
- start strike, end strike, and last-choice strike;
- rounding direction and midpoint handling;
- minimum OI;
- near contract first, then next contract if near does not qualify;
- no-order behavior when neither contract qualifies.

Entry evidence:

- Option-buy entries reference previous HH/LL values of the selected final
  strike and add a percentage of final strike.
- Visible examples include formulas shaped like
  `Previous 2DHH of Final Strike + 5%`,
  `Previous 4DHH of Final Strike + 7%`, and other branch-specific selected
  option references.
- Exact branch-to-reference mapping must remain
  `IMAGE_VERIFICATION_REQUIRED` until source workbook or higher-resolution OCR
  confirms every cell.

Gap/Missed-Entry evidence:

- The option-buy rule images primarily show base entry, target, stop, strike
  selection, and no-qualifying-strike behavior.
- ORPT/RC missed-entry applicability for option-buy strategies is
  `INSUFFICIENT_EVIDENCE`.

Exclusions:

- Target and stop formulas are Risk.
- Rollover action matrices are Lifecycle plus Contract Selection, not Entry.

#### Option Selling

Observed groups:

- Stock Option Selling Rules.
- BankNifty Monthly Option Selling Rules.
- BankNifty Weekly Option Selling Rules.
- Nifty Monthly Option Selling Rules.
- Nifty Weekly Option Selling Rules.
- Existing S21/S23 repository evidence.

Contract selection dependencies:

- underlying spot references such as 2DLL, 3DLL, 4DLL, 2DHH, 3DHH, and 4DHH;
- product-specific strike range percentages;
- round-up/round-down behavior and one-strike offsets;
- minimum OI thresholds;
- ideal and minimum premium thresholds;
- search direction from start to end or end to start;
- near contract first, then next contract fallback;
- no-order behavior when neither contract qualifies.

Entry evidence:

- Stock option selling uses selected-contract historical references discounted
  by a percentage, visibly shaped as `Previous <n>DHH/DLL of Final Strike -
  percentage`.
- BankNifty and Nifty option selling sheets show product/timeframe-specific
  percentages such as 7.5 percent entry discounts for several visible option
  selling rows.
- Existing S21/S23 implementation confirms workbook-derived option-selling
  entry formulas such as selected option previous-low references minus a
  configured discount.
- Exact mappings across every stock, BankNifty, and Nifty monthly/weekly image
  remain `WORKBOOK_CONFIRMATION_REQUIRED`.

Gap/Missed-Entry evidence:

- Existing Phase 3C confirms S23 offline Gap/Missed-Entry contracts and
  compatibility evidence.
- S21 ORPT/RC applicability remains unresolved.
- The newly supplied option-selling images do not establish ORPT/RC
  applicability for all option-selling strategies.

Exclusions:

- Ideal/minimum premium and OI filters are Contract Selection.
- Target, stop loss, MSL, FSL, APS, and TRP are Risk.

#### Futures

Observed examples:

- USDINR Futures.
- BankNifty Futures.
- Nifty Futures and stock futures examples visible in the conversation.

Branch evidence:

- Futures sheets distinguish Bull/Bull CF and Bear/Bear CF contexts.
- Long and short entries are separate branch outcomes.
- Buy and sell rows carry independent Entry and SL/TRP references.

Base entry evidence:

- Futures base entries use `UNDERLYING_FUTURE` references such as
  `FUT:PRV:1DHH`, `FUT:PRV:2DHH`, `FUT:PRV:2DLL`, and `FUT:PRV:4DLL` plus or
  minus product/strategy-specific buffers.
- The visible sheets show formula families such as reference plus percentage
  and reference minus percentage, but several exact values require
  `IMAGE_VERIFICATION_REQUIRED`.

Effective entry evidence:

- ORPT and RC times are shown.
- Missed-entry checks compare observed HH/LL against the base long or short
  entry.
- When missed, recalculation uses RC-time HH/LL plus or minus buffer, often
  inside `Max(...)` for long entry and `Min(...)` for short entry.
- FSL/TRP missed after position open is Lifecycle/Risk evidence, not base
  Entry evidence.

Exclusions:

- Targets, SL after entry, FSL/TRP, APS, and position-open handling belong to
  Risk and Lifecycle.

#### Equity

No new equity-specific rule sheet was supplied. Equity remains
`INSUFFICIENT_EVIDENCE` except where a future normalized strategy definition
explicitly provides instrument references and entry formulas.

### Formula Taxonomy

| Family | Left operand | Right operand | Percentage base | Operator | Instrument source | Output meaning |
| --- | --- | --- | --- | --- | --- | --- |
| Historical reference plus same-reference percentage | Historical HH reference | Percent of same historical reference | Historical reference | `+` | `UNDERLYING_FUTURE` or `UNDERLYING_SPOT` | Base or recalculated threshold |
| Historical reference minus same-reference percentage | Historical LL reference | Percent of same historical reference | Historical reference | `-` | `UNDERLYING_FUTURE` or `UNDERLYING_SPOT` | Base or recalculated threshold |
| Selected option reference plus final-strike percentage | Selected option previous HH/LL | Percent of final strike | `FINAL_STRIKE_VALUE` | `+` | `SELECTED_OPTION_CONTRACT` plus final strike | Option-buy base entry or target family |
| Selected option reference minus final-strike percentage | Selected option previous HH/LL | Percent of final strike | `FINAL_STRIKE_VALUE` | `-` | `SELECTED_OPTION_CONTRACT` plus final strike | Option-sell base entry or stop family |
| Entry plus entry percentage | Entry value | Percent of entry | Entry | `+` | Selected contract or future | Risk stop family |
| Entry minus entry percentage | Entry value | Percent of entry | Entry | `-` | Selected contract or future | Risk target family |
| Entry plus final-strike percentage | Entry value | Percent of final strike | `FINAL_STRIKE_VALUE` | `+` | Selected option contract | Option-buy target family |
| Entry minus final-strike percentage | Entry value | Percent of final strike | `FINAL_STRIKE_VALUE` | `-` | Selected option contract | Option-buy stop family |
| Max of base and recalculated threshold | Base entry | RC HH plus buffer | RC/current-day reference | `max` | `UNDERLYING_FUTURE` | Futures long effective entry |
| Min of base and recalculated threshold | Base entry | RC LL minus buffer | RC/current-day reference | `min` | `UNDERLYING_FUTURE` | Futures short effective entry |
| Max/min of entry and market-reference values | Entry-derived value | Historical HH/LL-derived value | Mixed | `max` or `min` | Selected option or future | Risk stop/trailing family |

No generic Entry contract should assume that every percentage is based on
Entry. The percentage base must be explicit per formula component.

### Phase 3C Integration Assessment

Phase 3C should remain intact. It owns Gap/Missed-Entry detection,
classification, ORPT/RC evidence, comparison values, and recalculation
instructions/results.

Entry should provide Phase 3C with:

- strategy identity and branch;
- product;
- base entry candidate;
- long/short or buy/sell direction semantics;
- required comparison reference identity;
- timing context, where already resolved upstream.

Entry should consume from Phase 3C:

- missed/not-missed classification;
- authoritative or compatibility recalculation output;
- block/defer/fail-closed status;
- evidence quality and provenance;
- warnings/open-rule flags.

Likely contract extension:

- add explicit `base_entry_candidate` and `effective_entry_consumer_context`
  fields around Phase 3C integration;
- add product-aware reference identity metadata so futures, option-buy, and
  option-sell paths do not share ambiguous aliases;
- add non-breaking optional fields first. The extension should be additive for
  existing S23 offline certification and should not redesign Phase 3C.

### Master Plan Amendment Recommendation

Do not edit the master plan in Milestone 1A. Proposed amendment:

```text
Replace the single linear dependency "Gap & Missed Entry -> Entry -> Contract
Selection -> Risk" with a product-aware execution model.

For options:
Monthly Status -> Branch Resolution -> Underlying References -> Contract
Selection -> Selected Contract References -> Base Entry -> Gap/Missed Entry
where applicable -> Effective Entry -> Risk.

For futures/equity:
Monthly Status or Instrument Resolution -> Instrument References -> Base Entry
-> Gap/Missed Entry where applicable -> Effective Entry -> Risk.

Define Entry as two explicit internal stages, Base Entry and Effective Entry,
while keeping Gap/Missed Entry as the already-certified separate engine.
```

Recommended architecture: one generic Entry Engine with explicit internal
stages for Base Entry and Effective Entry, integrated with the separate Phase
3C Gap/Missed-Entry Engine. This is smaller than creating three new engines and
preserves the certified Phase 3C boundary.

### Open Rule Register For New Material

| Open rule | Classification | Impact |
| --- | --- | --- |
| Unreadable or ambiguous formulas in screenshots | `IMAGE_VERIFICATION_REQUIRED` | Blocks exact policy implementation |
| Whether ORPT/RC applies to all shown option strategies | `INSUFFICIENT_EVIDENCE` | Blocks generic option missed-entry assumption |
| Exact meaning and completed-day semantics of "Previous 2DHH/3DLL of Final Strike" | `WORKBOOK_CONFIRMATION_REQUIRED` | Blocks selected-contract reference contract precision |
| Target formulas using final strike versus entry as percentage base | `WORKBOOK_CONFIRMATION_REQUIRED` | Risk migration dependency, excluded from Entry |
| Same-day re-entry ownership | `IMAGE_CONFIRMED` plus `USER_CLARIFICATION_REQUIRED` | Belongs to Lifecycle, but exact trigger needs authority |
| FSL/TRP missed ownership | `IMAGE_CONFIRMED` plus `WORKBOOK_CONFIRMATION_REQUIRED` | Risk/Lifecycle boundary, not Entry |
| Near/next expiry fallback applicability by strategy | `IMAGE_CONFIRMED` for shown option sheets, `WORKBOOK_CONFIRMATION_REQUIRED` for implementation | Contract Selection dependency |
| Strike rounding and midpoint behavior | `IMAGE_CONFIRMED`, exact cells `WORKBOOK_CONFIRMATION_REQUIRED` | Contract Selection dependency |
| No qualifying strike behavior | `IMAGE_CONFIRMED` | Contract Selection should produce no-trade evidence |
| Contradiction with initial Entry-before-Contract-Selection assumption | `LEGACY_INCONSISTENCY` | Master plan dependency amendment required |
| S21/S23 current implementation coupling entry/target/stop/strike | `IMPLEMENTATION_CONFIRMED` | Migration must split boundaries without behavior drift |
| Equity entry rules | `INSUFFICIENT_EVIDENCE` | Do not design equity-specific policy yet |

## Final Verdict

`MILESTONE_ACCEPT`

Phase 3D Milestone 1A accepts the inventory with a corrected product-aware
pipeline. Proceed to Milestone 2 only after using this addendum as the contract
design input.
