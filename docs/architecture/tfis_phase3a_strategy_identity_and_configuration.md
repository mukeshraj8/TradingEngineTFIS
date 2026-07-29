# TFIS Phase 3A Strategy Identity and Configuration

Date: 2026-07-29

## Purpose

Phase 3A establishes a generic strategy identity and configuration-resolution
foundation. It separates broad strategy family concepts from individual
business strategies, immutable versions, deployed instances, evaluation
attempts, and position cycles.

No active paper, live, replay, backtest, broker, lifecycle, persistence, or
execution path is migrated in this phase.

## Identity Hierarchy

```text
StrategyFamilyDefinition
  -> StrategyDefinition
  -> StrategyVersion
  -> StrategyInstanceDefinition
  -> StrategyEvaluationIdentity
  -> PositionCycleIdentity
```

Meaning:

- family: broad product/capability group, such as Option Selling or Futures
- definition: exact business rule set
- version: immutable published configuration/formula/policy snapshot
- instance: one deployed use of one strategy version for an account/portfolio,
  instrument, mode, schedule, and risk/capital references
- evaluation: one deterministic evaluation attempt
- position cycle: one lifecycle identity for a trade opened from an evaluation

Mutable runtime state must be keyed by at least:

```text
strategy_instance_id + trading_date + position_cycle_id
```

It must not be keyed only by family, underlying, account, display name, or
workbook row.

## Models

Generic models live in `src/tfis/domain/strategy_identity.py`.

Core models:

- `StrategyFamilyDefinition`
- `StrategyDefinition`
- `StrategyVersion`
- `StrategyInstanceDefinition`
- `ResolvedStrategyConfiguration`
- `StrategyEvaluationIdentity`
- `PositionCycleIdentity`
- `StrategyConfigurationResolver`

The generic module imports no paper, live, broker, lifecycle, dashboard, or
legacy-policy implementation modules.

## Configuration Layout

Phase 3A adds the minimal non-destructive layout:

```text
config/strategy_families/
  option_selling.yaml
  option_buying.yaml
  futures.yaml
  equity.yaml

config/strategy_definitions/
  S23_NIFTY_OP_SELL_WK_DIFF_2D_3D/
    strategy.yaml
    versions/1.0.0.yaml
  S21_BANKNIFTY_OP_SELL_MONTHLY/
    strategy.yaml
    versions/1.0.0.yaml

config/strategy_instances/
  S23_NIFTY_ACCOUNT_A_PAPER.yaml
  S21_BANKNIFTY_ACCOUNT_A_PAPER.yaml
```

Existing legacy S21/S23 strategy folders remain unchanged.

`config/strategy_policy_composition.yaml` keeps the existing Phase 2
`strategies:` mapping and adds `identity_compositions:` keyed by:

```text
strategy_definition_id@strategy_version
```

No composition is resolved by family or display name.

## Resolution Rules

Resolution is deterministic:

```text
family defaults
  + definition identity/config references
  + version values
  + declared instance overrides
  = ResolvedStrategyConfiguration
```

Rules:

- unknown YAML keys fail validation
- missing mandatory keys fail validation
- missing family/definition/version/composition references fail validation
- forbidden instance overrides fail validation
- product/segment/family mismatches fail validation
- unsupported required capabilities fail validation
- retired versions cannot be selected by a new instance
- resolved configuration is immutable and hashed
- instance overrides cannot change strategy business identity

Accepted instance override examples:

- lots
- capital limit
- account reference
- execution mode
- enablement
- schedule reference

Forbidden identity-changing examples:

- entry formula
- Monthly Status rule
- strike formula
- target formula
- MSL formula
- policy implementation key

## S21 and S23 Examples

Generated report:

- `reports/phase3a/strategy_identity_report.json`
- `reports/phase3a/strategy_identity_summary.md`

Resolved examples:

| Instance | Definition | Version | Entry policy | Hash prefix |
| --- | --- | --- | --- | --- |
| `S23_NIFTY_ACCOUNT_A_PAPER` | `S23_NIFTY_OP_SELL_WK_DIFF_2D_3D` | `1.0.0` | `legacy.s23.option_selling.entry` | `d182d62ea73b` |
| `S21_BANKNIFTY_ACCOUNT_A_PAPER` | `S21_BANKNIFTY_OP_SELL_MONTHLY` | `1.0.0` | `legacy.s21.option_selling.entry` | `3f13d88b4a9c` |

Both use the Option Selling family and can share the same logical account
reference, but their strategy instance IDs and resolved configuration hashes
are distinct.

## Evaluation Identity

`StrategyEvaluationIdentity.deterministic()` hashes:

- strategy instance
- strategy definition
- explicit version
- trading date
- evaluation timestamp
- sequence
- trigger type
- resolved configuration hash
- optional correlation/causation IDs

It has no filesystem path, process ID, random number, or wall-clock dependency
when replay inputs are deterministic.

## Position Cycle Identity

`PositionCycleIdentity.deterministic()` hashes:

- strategy instance
- trading date
- cycle sequence
- entry evaluation ID
- product/instrument identity
- optional parent/re-entry context

The `state_isolation_key` is:

```text
(strategy_instance_id, trading_date, position_cycle_id)
```

This defines the contract needed for future deduplication and lifecycle state
isolation, but Phase 3A does not implement lifecycle behavior.

## Decision Integration

`TFISRuntimeInput` and `TFISDecision` now carry optional authoritative identity
fields:

- `strategy_family_id`
- `strategy_definition_id`
- `strategy_instance_id`
- `resolved_configuration_hash`

`TFISDecision` also carries `strategy_version_identity`. Existing constructors
remain backward compatible through defaults. The generic decision engine passes
these fields through when present and remains strategy-neutral.

`TFISDecisionEvidencePacket` already contains strategy definition/version and
instance identity in its identity section; Phase 3A packet-to-runtime adapters
now preserve those fields.

## Validation

Structured errors include:

- code
- location
- identity
- field
- message
- severity

Covered codes include duplicate IDs, unknown references, unknown keys, missing
mandatory values, version/content conflicts, unsupported product/family
combination, missing capability, composition mismatch, forbidden override,
retired version selection, invalid effective range, and missing composition.

## Performance

Measured by `scripts/run_phase3a_strategy_identity_report.py`:

- families: 4
- definitions: 2
- versions: 2
- instances: 2
- load and validation: `0.11254440000084287s`
- first single-instance resolution: `0.0048908000007941155s`
- cached resolution: `0.0000032999996619764715s`
- current memory: `35216` bytes
- peak memory: `171183` bytes

Design implication: load and validate once, cache immutable resolved
configuration, and avoid YAML parsing during decision execution.

## Migration Considerations

Phase 3A intentionally does not rename, delete, or move existing S21/S23
strategy folders. The new hierarchy wraps them as versioned strategy
definitions and instances. Later phases can gradually migrate runtime callers
to require resolved identity without changing formulas.

## Known Limitations

- Only example S21/S23 instances are present.
- Futures, Option Buying, and Equity families are capability placeholders only;
  no formulas or strategy definitions were invented.
- Runtime state isolation is defined by identity contract but not implemented.
- Active runtime paths still use the legacy S21/S23 flow.
- The four S23 start-strike expectation failures remain pre-existing workbook
  verification items.

## Verdict

`PHASE_3A_ACCEPT` for configuration/domain foundation.

Phase 3B should use this foundation to design disabled runtime resolution and
state-key adoption, still without changing strategy formulas or execution
behavior.
