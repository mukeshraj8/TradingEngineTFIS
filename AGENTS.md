# AGENTS.md — TFIS AI Coding Agent Instructions

## 1. Purpose

This file defines the mandatory operating rules for Codex and every other AI coding agent working in this repository.

The project is a financial trading system. A wrong formula, incorrect rule interpretation, unsafe state transition, duplicate order, missing protection order, incorrect quantity, or incorrect reconciliation decision can cause financial loss. Therefore:

> **Evidence before behavior. Source authority before implementation. Safety before convenience.**

No AI agent may treat this repository as an ordinary application-development project.

---

## 2. Mandatory reading before any change

Before making any code, configuration, script, test, report, migration, or documentation change, read and follow:

- `AGENTS.md`
- `docs/operations/ai_change_agreement.md`
- `docs/operations/project_rulebook.md`
- `docs/operations/current_state.md`
- `docs/operations/next_steps.md`
- `docs/operations/milestones.md`

For architecture or runtime changes, also read the relevant accepted architecture documents and the most recent milestone reports.

For strategy-rule work, also read the relevant authoritative workbook/source files under:

- `TFISRulesAndSpec/`

If a user request conflicts with these repository contracts, stop and report the conflict before changing files.

Do not claim compliance without reading the files.

---

## 3. Repository and environment boundaries

Primary working repository:

- `D:\TradingEngineTFISRefactored`

Reference implementation:

- `D:\TradingEngineTFIS`

The reference implementation is **read-only** unless the user explicitly authorizes a separate task for it.

Authoritative workbook and rule sources:

- `D:\TradingEngineTFISRefactored\TFISRulesAndSpec`

Do not modify authoritative workbook files.

Do not modify unrelated repositories, external data directories, broker installations, production folders, or user machine settings.

Before every task:

1. Confirm the current working directory and branch.
2. Inspect `git status` and `git diff`.
3. Identify accepted but uncommitted work.
4. Commit the previously accepted milestone before beginning the next milestone, when instructed.
5. Never overwrite unrelated user changes.

---

## 4. Source-of-truth hierarchy

When implementing business rules, use this authority order:

1. Exact authoritative workbook cells/formulas/text.
2. Accepted written specification or rule matrix with source trace.
3. Explicit user clarification recorded with a rule ID.
4. Verified strategy configuration generated from authoritative sources.
5. Legacy implementation only as compatibility evidence.
6. Existing tests only as evidence of current behavior, not automatic business authority.

Legacy code, comments, tests, reports, or inferred symmetry must not override authoritative workbook evidence.

If sources disagree:

- do not choose silently;
- record the exact conflict;
- identify files, sheets, cells, code paths, and tests involved;
- fail closed;
- ask one precise question if the source does not resolve it.

Never mark a financially material rule as merely “unresolved” without first searching all relevant workbook sheets, source documents, configs, audits, mappings, tests, and accepted user clarifications.

---

## 5. No assumptions in financial logic

Never assume or infer:

- Call and Put formulas are mirror images;
- Bull and Bear rules are sign-reversed copies;
- one strategy’s rule applies to another;
- one product’s P&L formula applies to another;
- one expiry or strike-selection method applies globally;
- an equality case follows the nearest inequality;
- a missing field may be filled from a later quote;
- first received quote equals official market open;
- `LTP`, bid, ask, high, or low are interchangeable;
- symbol alone identifies a strategy, account, order, or position;
- an acknowledgement means a fill;
- a planned price means an actual fill price;
- broker-observed state is automatically linked to a local PositionCycle;
- a carried position follows the fresh-entry gap path;
- a blocked evaluation is equivalent to a business `NO_TRADE`.

When evidence is missing, produce a precise fail-closed result and explain what is missing and why it matters.

---

## 6. Current project priority

The current priority is vertical delivery, not broad architecture expansion.

The immediate goal is to complete and harden the full S23 strategy end to end, including all authoritative branches:

- `BULL_CALL`
- `BEAR_CALL`
- `BULL_PUT`
- `BEAR_PUT`

A captured or replayed session may naturally resolve to CE or PE. Therefore Call-only support is not complete S23 support.

Until complete S23 certification and observation are accepted:

- do not onboard S21;
- do not onboard Futures;
- do not onboard Option Buying;
- do not onboard Equity;
- do not add external broker write authority;
- do not broaden into SaaS, multi-user, distributed, AI, or optimization work.

Every task must visibly move the complete S23 vertical toward reliable operation.

---

## 7. Vertical-slice priority gate

Before adding any contract, table, repository, service, framework, adapter, report, or abstraction, answer:

> Which immediate S23 end-to-end capability consumes this?

Allowed immediate consumers include:

- source verification;
- strategy resolution;
- pre-market planning;
- contract selection;
- Entry;
- Gap/Missed-Entry;
- EffectiveExecutionPlan;
- runtime coordination;
- recovery;
- reconciliation;
- ExecutionIntent and risk validation;
- AccountCoordinator;
- ClientOrder and order state;
- fills;
- PositionCycle;
- lifecycle/protection;
- TradeFact/PnLFact;
- controlled internal-paper runtime;
- complete S23 branch certification and observation.

If the component is only for future analytics, multi-broker scale, distributed infrastructure, advanced optimization, or later strategies, document the extension point and defer implementation.

Prefer the smallest safe implementation over the most general implementation.

---

## 8. Plug-and-play strategy architecture

The target architecture is:

> **Common operational platform + verified strategy configuration/policies + evidence/tests = onboarded strategy.**

Generic components must not contain strategy-code branching such as:

- `if strategy == "S23"`
- `if strategy == "S21"`

Strategy-specific formulas and mappings belong in strategy configuration or strategy-specific policy/adaptor boundaries.

The following must remain reusable and strategy-neutral:

- strategy identity/versioning;
- market-data normalization and routing;
- runtime coordination;
- persistence and recovery;
- reconciliation;
- ExecutionIntent;
- generic risk validation;
- AccountCoordinator;
- order state machine;
- fill handling;
- PositionCycle;
- lifecycle orchestration;
- accounting and projections;
- operator controls;
- evidence/audit infrastructure.

When onboarding a new strategy:

1. Attempt configuration and existing policy composition first.
2. Add a strategy-specific policy only when verified rules genuinely differ.
3. Modify generic engines only for a reusable capability absent from the model.
4. Report every generic file changed and justify why configuration/policy composition was insufficient.
5. Reject duplicated account/order/position/persistence/accounting paths.

---

## 8A. GENERIC BUSINESS ENGINE INDEPENDENCE

Monthly Status, Market Structure, Contract Selection, Gap/Missed Entry,
Entry, Risk, Lifecycle, and Accounting capabilities must remain
strategy-independent where their business responsibility is generic.

Strategies consume typed engine outputs through configuration and
strategy-specific policy composition.

No generic engine may contain strategy-code branching such as:

- `if strategy == "S21"`
- `if strategy == "S22"`
- `if strategy == "S23"`

Any strategy-specific interpretation belongs in a strategy policy or adapter.

### APS APPLICABILITY RULE

APS is a generic trading capability. Applicability is determined by strategy
configuration, not by engine type.

Configured trading quantity = 1 lot:

- APS is not applicable.
- Use a single Target.
- Use a single PositionCycle quantity.
- Do not create staged exits.
- Do not create APS-specific protection adjustment.

Configured trading quantity > 1 lot:

- APS may apply only if the authoritative workbook defines APS behavior for
  that strategy.
- Do not infer APS merely because quantity is greater than one lot.

APS always requires workbook authority for:

- quantity allocation;
- Target allocation;
- protection-adjustment rules.

If APS authority is absent, fail closed.

Do not implement APS inside generic PositionCycle or lifecycle logic for S21,
S22, or S23. Option Selling strategies with one lot continue to use Target,
Original SL/MSL, Revised SL/FSL/TRP, EOD, and carry-forward without APS.

### MONTHLY STATUS INDEPENDENCE

Monthly Status is a generic, strategy-independent business engine. It must not
be implemented inside S21, S22, S23, or any other strategy adapter.

The Monthly Status engine must be able to calculate and return Monthly Status
for any supplied eligible instrument using authoritative monthly-data rules.

Required input includes:

- structured instrument identity;
- evaluation trading date/timestamp;
- monthly candle/reference evidence;
- Monthly Status rule version;
- data provenance and quality.

Required output includes:

- instrument identity;
- Monthly Status: `BULL`, `BULL_CF`, `BEAR`, `BEAR_CF`, or an explicit
  unavailable/invalid state;
- source monthly references;
- transition/continuation evidence;
- evaluation timestamp;
- data-quality state;
- warnings/failures;
- deterministic result hash.

Monthly Status Engine owns:

- monthly-reference calculation;
- status classification;
- status transitions;
- evidence validation;
- deterministic result construction.

Strategy policy owns:

- which instrument status is requested;
- how that status maps to a strategy branch;
- whether the strategy trades or blocks for that status.

The Monthly Status engine must not contain:

- S21-specific logic;
- S22-specific logic;
- S23-specific logic;
- option-selling-specific branch selection;
- symbol hardcoding;
- one shared mutable status reused for multiple instruments;
- derived strategy actions.

For S21, agents must independently source-trace generic Monthly Status
calculation rules and separately source-trace the S21 Monthly-Status-to-branch
mapping. Do not combine these into one strategy rule.

For S22, the same Monthly Status engine must calculate status independently for
each enabled F&O stock.

The Monthly Status service must support batch requests, for example:

```python
get_monthly_status([
    NIFTY,
    BANKNIFTY,
    RELIANCE,
    TCS,
    INFY,
])
```

Internally the service may calculate in parallel or reuse cached immutable
results, but each output must remain independently keyed and auditable.

Permanent architecture invariant:

```text
Monthly data store
      |
Generic Monthly Status Engine
      |
Instrument-keyed immutable status results
      |
S21 / S22 / S23 / future strategies
      |
Strategy-specific branch mapping
```

This is a platform invariant, not an S21 implementation detail.

---

## 9. Product-aware trading flow

### 9.1 Pre-market computation

The system is intended to prepare as much as possible before market open.

Before market open, where source data is available, compute or load:

- enabled strategy instances;
- resolved strategy/config versions;
- Monthly Status;
- completed historical references such as `2DHH`, `3DLL`, etc.;
- branch candidates;
- expiry/contract selection inputs;
- option-chain/OI/reference data;
- selected contract;
- Base Entry;
- Target;
- Original SL/MSL;
- ORPT and RC timings;
- quantity and account assignment;
- source rule IDs and evidence hashes.

For options, contract selection and selected-contract references may be prerequisites for Base Entry.

For futures, Base Entry may be computed from futures references before opening.

### 9.2 Market-open handling

At/after market open, evaluate only the opening-dependent evidence:

- official/opening context;
- gap-up/gap-down/normal classification;
- selected-contract opening evidence;
- ORPT observation;
- RC observation;
- fresh-entry missed/not-missed logic;
- Effective Entry and revised values when applicable.

Normal path and gap/recalculation path must remain distinct.

### 9.3 Carried positions

Carried positions are not fresh entries.

They require a separate lifecycle path:

- reconcile carried quantity and contract;
- maintain target protection according to verified rules;
- evaluate opening target/SL conditions;
- if Target is crossed, exit as source-authorized;
- if gap is adverse and original SL is missed, wait until authorized recalculation time and use the verified revised SL/FSL/TRP rule;
- preserve same PositionCycle identity across days;
- follow verified EOD square-off/carry rules;
- equality behavior must follow accepted source/user clarification.

Do not route carried positions through fresh-entry Gap/Missed-Entry logic.

---

## 10. Strategy source-extraction gate

No strategy branch may receive implementation or authority until its source gate is complete.

Required source-extraction outputs:

1. Workbook file and sheet.
2. Exact rows/cells.
3. Original formula/text.
4. Normalized formula.
5. Operands and reference identities.
6. Percentage base.
7. Comparison operator and equality behavior.
8. Timing.
9. Rounding and tick behavior.
10. Expiry and contract selection.
11. Premium/OI constraints.
12. Entry, Target, SL/MSL/FSL/TRP/TSL/APS.
13. Gap and missed-entry behavior.
14. Carry-forward and next-day behavior.
15. P&L quantity/multiplier rules.
16. Source conflicts and exact user questions.
17. Rule IDs linking implementation to authority.

Source statuses must be explicit, for example:

- `WORKBOOK_VERIFIED`
- `USER_CLARIFIED`
- `CONFIG_VERIFIED`
- `LEGACY_ONLY_NOT_AUTHORITY`
- `SOURCE_CONFLICT`
- `SOURCE_CELL_NOT_FOUND`
- `IMPLEMENTATION_MISSING`

No active financial rule may depend solely on `LEGACY_ONLY_NOT_AUTHORITY`.

---

## 10A. NEW STRATEGY SOURCE CLOSURE AND ONBOARDING

Every strategy must be implemented from authoritative workbook rules and
explicit user clarifications. Legacy implementation is never business-rule
authority. Legacy code may be used only after independent source closure, and
only for post-closure discrepancy analysis.

Similar strategies, including S23, are not formula authority for a new
strategy. Before implementation, every financially material business stage must
be one of:

- `WORKBOOK_VERIFIED`
- `USER_CLARIFIED`
- `CONFIG_CROSSCHECKED`
- `NOT_APPLICABLE`

`PARTIAL`, inferred, conflicting, unreadable, or legacy-only rules block
implementation. Missing source authority must fail closed. Financial rules
must never be guessed. Workbook files must not be modified by AI agents.

When source evidence is insufficient, the agent must ask precise user questions
instead of silently marking a rule unresolved. Source questions must cite:

- workbook file
- sheet
- cells
- original formula or process text
- normalized interpretations
- financial consequence
- whether Call and Put may differ

Complete source closure must include branch resolution, contract selection,
entry, gap/ORPT/RC, Target, SL and recalculation, APS/partial exits where
applicable, EOD/carry, next-day lifecycle, quantity, and P&L units.

Onboarding sequence:

1. Complete source closure.
2. Implement one fully verified branch first.
3. Stop for review before implementing remaining branches.
4. Reuse generic runtime, persistence, reconciliation, account, order,
   PositionCycle, lifecycle, and accounting infrastructure.
5. Do not add `if strategy == ...` branching in generic components.
6. Do not duplicate account/order/position/persistence/accounting stacks.
7. Update source trace and rule matrix with every accepted clarification.
8. Preserve milestone gating and require explicit user approval before
   implementation.

Every generic code change during strategy onboarding must explain:

- the missing reusable capability
- why configuration/policy composition was insufficient
- why the change is not strategy-specific
- regression proof for existing strategies

### GLOBAL OPTION SELLING EOD RULE

- At the configured EOD decision time, `Close > Original SL` means `EXIT`.
- At the configured EOD decision time, `Close <= Original SL` means
  `CARRY_FORWARD`.
- Applicability: all Option Selling strategies unless an authoritative
  strategy-specific source explicitly states otherwise.
- Authority: `>` and `<` may be workbook-backed where present; equality is
  `USER_CLARIFIED`.
- Do not apply this global rule to Futures, Option Buying, or Equity without
  separate authority.

Agents must also read and follow `docs/operations/ai_change_agreement.md` and
`docs/operations/project_rulebook.md`. If a user request conflicts with these
repository contracts, stop and report the conflict before changing files.

---

## 11. Identity and state isolation

Never key mutable financial state only by strategy code, symbol, or display name.

Use stable identities including, as applicable:

- broker account;
- trading session/date;
- strategy family;
- strategy definition;
- strategy version;
- strategy instance;
- evaluation identity;
- position-cycle identity;
- execution-intent identity;
- client order identity;
- broker order/fill identity;
- protection generation;
- contract identity.

State isolation for strategy evaluation/position cycles must preserve:

`strategy_instance_id + trading_date/session + position_cycle_id`

Multiple accounts, strategies, orders, positions, instruments, expiries, and contracts must remain isolated.

One account/strategy/position failure must not corrupt unrelated streams.

---

## 12. Truth and ownership boundaries

Keep these truth categories separate:

- business decision truth;
- local expected execution state;
- broker-observed state;
- reconciled state;
- internal-paper simulated state;
- PositionCycle state;
- accounting facts;
- analytical projections.

Never silently overwrite one truth with another.

Ownership rules:

- Business engines own calculations and decisions.
- Reconciliation compares local expected and broker-observed truth.
- AccountCoordinator owns account-level sequencing and ClientOrders.
- Order state machine owns order lifecycle.
- PositionCycleCoordinator owns confirmed quantity, average entry, remaining quantity, protection/lifecycle/carry/closure state.
- Accounting owns immutable TradeFact/PnLFact and read-only projections.
- Analytics never mutates trading state.

Avoid a giant `OrderManager` or `PositionManager` owning unrelated concerns.

---

## 13. Authority ladder and safety boundaries

Authority must be explicit and incremental.

Typical ladder:

- `CONFIG_ONLY`
- `UNIT_TEST_ONLY`
- `OFFLINE_FIXTURE`
- `CAPTURED_REPLAY_SHADOW`
- `LIVE_DATA_SHADOW`
- `INTERNAL_PAPER`
- `BROKER_PAPER_SANDBOX`
- `CONTROLLED_LIVE`
- `GENERAL_LIVE`

No level may be skipped.

Unless the task explicitly authorizes otherwise:

- broker submission = false;
- external paper submission = false;
- live submission = false;
- external order mutation = false;
- external position mutation = false.

A validated `ExecutionIntent` is not a `ClientOrder`.

A `ClientOrder` is not a `BrokerOrder`.

An acknowledgement is not a fill.

A simulated fill is not broker-confirmed accounting truth.

Do not expose write methods through a read-only broker boundary.

Do not import or call broker write SDKs in shadow/internal-paper work.

---

## 14. Order, fill, protection, and PositionCycle invariants

Mandatory invariants:

- No order from an unvalidated intent.
- No ClientOrder without explicit authority grant in internal-paper mode.
- No open PositionCycle from acknowledgement alone.
- Position opens only from confirmed fill.
- Filled quantity never exceeds requested quantity.
- Exit quantity never exceeds remaining quantity.
- Protection quantity never exceeds confirmed remaining quantity.
- Partial fills receive protection only for confirmed quantity.
- Duplicate identical events are idempotent.
- Conflicting duplicates fail closed.
- Protection generations are explicit.
- Stale protection generation cannot overwrite current protection.
- Old SL fills during cancel/replace must be recorded honestly.
- Position closes only when confirmed remaining quantity reaches zero.
- Disabling fresh entries must not abandon open-position protection.
- Strategy disable and lifecycle protection are separate controls.
- Open positions must remain visible and recoverable after restart.

---

## 15. Persistence, recovery, and reconciliation rules

Operational financial state must use transactional persistence, not ad hoc JSON/CSV authority.

Required patterns:

- deterministic schema migrations;
- append-only facts/events;
- versioned current-state projections;
- canonical serialization;
- scoped idempotency;
- optimistic concurrency;
- atomic UnitOfWork boundaries;
- rollback without partial state;
- integrity checks;
- recovery assessment;
- broker reconciliation before future external authority.

Broker observations must not automatically create or mutate authoritative local orders or PositionCycles.

Ambiguous linkage must remain:

- unknown;
- blocked;
- or manual review required.

Never match broker state to a strategy or PositionCycle from symbol alone.

No retry may create a second financial action.

---

## 16. Market-data, time, and performance rules

Preserve distinct timestamps:

- source/exchange timestamp;
- captured/received timestamp;
- replay dispatch timestamp;
- event effective timestamp;
- processing timestamp.

Do not overwrite market time with replay or wall-clock time.

Use supplied deterministic time in tests and replay. Avoid `datetime.now()` in deterministic business logic.

Market-data model:

- normalize once per observation;
- one mutable state owner per instrument;
- immutable consumer snapshots;
- subscription-based selective dispatch;
- ordinary quote/OI updates may be conflated;
- ORPT, RC, EOD, fills, acknowledgements, reconciliation, risk/operator actions, and position transitions are non-conflatable;
- stale/incoherent snapshots fail closed;
- decisions consume one coherent immutable evaluation context.

Do not deduplicate solely by equal price. Preserve source-observation identity where available.

Performance work must remain measurable and honest:

- report fixture/replay measurements as such;
- do not claim production/live throughput without production benchmarks;
- avoid blocking analytics on the order path;
- reuse shared market snapshots across strategy instances;
- isolate mutable per-account/per-strategy/per-position state.

---

## 17. Accounting and analytics rules

Actual or simulated accounting must derive from confirmed fills, not planned prices.

For current internal-paper S23 short-option scope:

- realized gross P&L uses confirmed entry and exit fills with verified quantity/multiplier semantics;
- unrealized P&L uses remaining confirmed quantity and quality-labelled mark policy;
- charges may be provisional but must be labelled;
- corrections supersede facts immutably;
- original facts remain retained;
- projections are rebuildable;
- analytics are read-only;
- accounting/projection failure must not mutate trading state.

Do not generalize product P&L formulas across Futures, Equity, Currency, Commodity, Option Buying, and Option Selling without source verification.

Do not conclude profitability from insufficient or synthetic samples.

Never automatically change strategy rules based on analytics.

---

## 18. Testing and evidence requirements

Every change requires focused tests appropriate to financial risk.

At minimum, consider:

- happy path;
- every branch;
- equality boundaries;
- missing evidence;
- stale evidence;
- wrong account/contract/date;
- duplicate identical event;
- conflicting duplicate;
- partial fill;
- overfill/over-exit;
- protection generation;
- restart/recovery;
- optimistic concurrency;
- transaction rollback;
- multi-account isolation;
- multi-position/order isolation;
- deterministic replay;
- architecture boundary scans;
- source-rule traceability;
- no external authority.

For strategy work, require:

1. Formula/unit tests.
2. Branch tests.
3. Synthetic golden fixtures.
4. Legacy fixture parity.
5. Captured/replay parity where evidence exists.
6. Fail-closed cases.
7. End-to-end trace.
8. Call/Put regression as applicable.
9. Natural branch selection, not forced branch invocation.

Never claim full-suite success unless the full suite was run.

Classify failures honestly:

- new regression;
- pre-existing unrelated;
- relevant blocker;
- unknown requiring review.

Do not dismiss failures merely because focused tests pass.

---

## 19. Validation checklist

Run the validations appropriate to the changed surface. Typical minimum:

- `py_compile` for changed Python files;
- focused unit tests;
- adjacent regression tests;
- architecture/source-boundary tests;
- JSON validation;
- SQLite integrity check when persistence is touched;
- `scripts/validate_strategy_configs.py`;
- `scripts/validate_project.py`;
- `git diff --check`;
- full repository suite when required by the milestone.

Record exact commands and outcomes.

Do not hide CRLF warnings, skipped checks, unavailable tools, or unrun suites.

Generated reports must be deterministic where they contain business hashes. Exclude timing, process ID, output path, and wall-clock diagnostics from business hashes.

---

## 20. Documentation and report discipline

Update only the documents required by the task.

Operational docs normally include:

- `docs/operations/current_state.md`
- `docs/operations/next_steps.md`
- `docs/operations/milestones.md`

Do not rewrite certified architecture unless implementation proves a contradiction.

Reports must distinguish:

- captured evidence;
- source-verified static evidence;
- derived-from-captured evidence;
- derived-from-verified-configuration evidence;
- fixture/synthetic evidence;
- missing evidence;
- not applicable.

Never label fixture evidence as captured.

Never call a comparison parity if authoritative comparison output is absent.

Every material state change or financial fact should trace:

- identity;
- source/actor;
- timestamp;
- rule/config version;
- previous state;
- new state;
- evidence hash.

---

## 21. Git and change hygiene

Before editing:

- inspect status/diff;
- identify unrelated changes;
- create a checkpoint commit when directed.

During editing:

- keep changes scoped;
- avoid mass formatting;
- avoid line-ending churn;
- avoid generated-file drift;
- do not change unrelated tests to make failures disappear;
- do not weaken assertions without source-backed justification;
- do not add broad exclusions to validators.

After editing:

- inspect diff;
- run `git diff --check`;
- ensure source/config/workbook guards pass;
- report whether worktree is clean or changes remain uncommitted;
- do not commit unless instructed or required by the milestone.

If a validation command regenerates unrelated reports, restore unintended drift before completion.

---

## 22. Security and secrets

Never place secrets in:

- domain objects;
- reports;
- fixtures;
- hashes;
- logs;
- exceptions;
- committed config.

Reject or redact fields such as:

- access token;
- refresh token;
- API key/secret;
- password;
- PIN;
- authorization header;
- cookie;
- session token;
- client secret.

Read-only and internal-paper tests must not call real broker APIs unless explicitly approved.

---

## 23. Stop conditions

Stop and ask for clarification before implementation when:

- authoritative workbook/source rules conflict;
- a financially material formula or equality case is missing;
- the requested task would introduce external broker/live authority without an accepted gate;
- the task requires modifying the read-only reference repository;
- an existing relevant regression is unexplained;
- a generic-core change would duplicate strategy-specific behavior;
- a migration or persistence change risks corrupting accepted state;
- source evidence is insufficient to select Call versus Put behavior;
- the requested change conflicts with the repository contracts;
- unexpected unrelated worktree changes appear.

Do not continue by guessing.

---

## 24. Mandatory milestone behavior

For milestone-driven tasks:

1. Follow the requested checkpoints in order.
2. Check in after each milestone/checkpoint when the user requested milestone gating.
3. Do not begin the next milestone without explicit approval.
4. Do not silently broaden scope.
5. State exact runtime impact and authority impact.
6. State exact known limitations.
7. Recommend only one narrow next task aligned to the critical path.

A milestone is accepted only when its acceptance criteria are actually met.

Use conditional or blocked verdicts when evidence is incomplete.

---

## 25. Required final response structure

Unless the task provides a stricter format, report:

- verdict;
- objective achieved;
- pre-task state/commit;
- files reviewed;
- files changed;
- source authority and rule trace;
- behavior implemented;
- architecture boundaries;
- tests and validation;
- full-suite status if run;
- exact runtime impact;
- broker/paper/live authority;
- known limitations;
- worktree/commit status;
- exact next recommendation.

Be precise. Do not overstate readiness.

---

## 26. Core project principles

Every AI agent must follow these principles:

1. **Evidence before behavior.**
2. **Workbook/source authority before legacy behavior.**
3. **No assumptions in financial rules.**
4. **Fail closed when evidence is incomplete.**
5. **Complete vertical slices before broad horizontal expansion.**
6. **Generic operational core; strategy-specific configuration/policies.**
7. **One owner for each mutable state.**
8. **Separate business, broker, reconciled, simulated, position, accounting, and analytical truth.**
9. **No retry may create a duplicate financial action.**
10. **No external authority without explicit staged approval.**
11. **Carried-position lifecycle is separate from fresh-entry logic.**
12. **Pre-market computation should be completed before market open wherever evidence permits.**
13. **Normal, gap, ORPT, RC, and EOD paths must be explicit and source-backed.**
14. **Complete S23 means all four Call/Put branches, not Call-side only.**
15. **Testing, recovery, reconciliation, protection, and accounting are part of correctness—not optional extras.**
16. **Profitability analysis must never silently mutate strategy rules.**
17. **Honest conditional readiness is better than false completion.**
