# Reference Materials

This directory stores TFIS archival materials that help with later design,
validation, and workbook-tracing work.

These files are intentionally discoverable, but they are not automatically
trusted implementation specs.

## Index And Workflow

- archive index: [index.yaml](index.yaml)
- review workflow: [review_workflow.md](review_workflow.md)

## Review Statuses

- `reference_only`
  - archival only, not normalized, not implementation-approved
- `partially_reviewed`
  - some concepts have been extracted or documented, but more validation is
    still required
- `reviewed`
  - reviewed as a reference input, but still not automatic market approval

## How To Add New Materials

1. Place the file in the closest matching subfolder under
   `docs/reference_materials/`.
2. Add an entry to [index.yaml](index.yaml) with:
   - filename
   - type
   - status
   - related topics
3. Use the most conservative review status that is still accurate.
4. If the material influences future implementation work, document the review
   trail before changing runtime strategy configs.

## Relationship To Implemented Strategy Configs

Reference materials are archival inputs.

Implemented TFIS runtime behavior should still come from validated,
folder-based strategy configs under `config/strategies/`, not directly from raw
screenshots, spreadsheets, templates, or handwritten notes.

That means reference materials do not bypass:

- Excel cross-check requirements
- formula safety validation
- strategy registry governance
- backtest acceptance gates

## Current Coverage

The archive currently includes materials related to:

- monthly status
- option selling
- option buying
- rollover
- BankNifty backtesting
- companies list / stock universe
- session notes
- bulk templates
- equity all-time-high exercises
