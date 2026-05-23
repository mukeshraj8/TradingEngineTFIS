# Rule Model

## Source Of Truth

The TFIS workbook is the business-facing source of truth.

## Normalization Flow

1. Read workbook sheets and named ranges.
2. Normalize formulas, rule groups, thresholds, and field mappings.
3. Emit YAML or JSON artifacts with stable schemas.
4. Load those artifacts into a generic runtime engine.

## Runtime Philosophy

- Rules should be declarative where possible.
- Formula evaluation should be isolated from orchestration.
- Strategy configuration should describe behavior without requiring engine rewrites.
- Interfaces should make later integration possible without coupling this project to another engine implementation.
