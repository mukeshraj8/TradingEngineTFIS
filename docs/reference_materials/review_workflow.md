# Reference Material Review Workflow

## Purpose

Reference materials are archival inputs for TFIS design work. They are not
automatically trusted implementation specifications.

## Core Rule

A screenshot, note, spreadsheet, or template in `docs/reference_materials/`
does not become executable TFIS logic just because it exists in the archive.

It remains archival until it passes the normal TFIS implementation gates.

## Implementation Requirements

Before a reference material can influence implemented strategy behavior, it
should move through these checks:

1. Excel cross-check
   - workbook formulas, branches, or examples are tied back to explicit source
     cells where possible
2. Market relevance validation
   - the instrument family, contract structure, and current-market relevance are
     checked before calling a strategy active
3. Strategy registry classification
   - the strategy is classified through `config/strategy_registry.yaml`
4. Test coverage
   - the resulting strategy/config/loader behavior has deterministic tests

## Review Status Meanings

- `reference_only`
  - archival only
  - not normalized
  - not trusted for direct implementation
- `partially_reviewed`
  - some concepts have been extracted, documented, or cross-checked
  - still not complete enough for blind implementation
- `reviewed`
  - fully reviewed as a reference input
  - still does not automatically imply live-market approval

## Relationship To Implemented Strategy Configs

Implemented strategy folders under `config/strategies/` must remain the
normalized runtime source of truth for TFIS.

Reference materials support that process by:

- preserving raw screenshots, notes, templates, and spreadsheets
- making the archive discoverable
- giving future importer and design work a stable place to trace back to

Reference materials should never bypass:

- folder-based strategy validation
- formula safety validation
- registry governance
- backtest acceptance checks

## Adding New Materials

When adding a new archival material:

1. place the file in the closest matching subfolder under
   `docs/reference_materials/`
2. add or update its entry in `docs/reference_materials/index.yaml`
3. choose a conservative review status
4. add related topics that make later review easier
5. avoid implying that the material is already implementation-approved

## Unresolved Notes

If a material is ambiguous, incomplete, handwritten, or not yet reconciled with
workbook evidence, it should stay `reference_only`.

That is the safe default.
