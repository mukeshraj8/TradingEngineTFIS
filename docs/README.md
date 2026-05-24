# TFIS Documentation

This folder contains the TFIS design, governance, importer, and operations documentation.

## Current Project Snapshot

- broker-agnostic architecture is established
- folder-based strategy configuration is established
- all four canonical S23 branches are represented and validated
- workbook cross-check, formula safety, and registry governance layers are in place
- branch selection is available for folder-based monthly-status strategy variants
- offline historical lifecycle backtesting is in place with EOD policies, cost/slippage assumptions, rupee P&L, and equity/drawdown reporting
- monthly-status support now includes thresholds, a diagnostic decision table, a deterministic status engine, a CLI report, manual review scenarios, an opt-in historical branch-selection mode, and an opt-in S23 recalculation path with optional spot intraday sourcing
- historical backtests can now opt into offline option-chain contract selection realism without changing the default path
- reference materials are indexed with review workflow and archive-governance guidance
- current quality snapshot:
  - tests passing: `236`
  - `python scripts/validate_project.py`: passed

## Architecture

- [architecture.md](architecture/architecture.md)
- [architecture_decisions.md](architecture/architecture_decisions.md)
- [monthly_status_engine_design.md](architecture/monthly_status_engine_design.md)
- [monthly_status_reference_terms.md](architecture/monthly_status_reference_terms.md)
- [monthly_status_decision_table.md](architecture/monthly_status_decision_table.md)
- [monthly_status_scenarios.md](architecture/monthly_status_scenarios.md)
- [shared_market_data_strategy.md](architecture/shared_market_data_strategy.md)

## Strategy

- [backtesting_and_experiments.md](strategy/backtesting_and_experiments.md)
- [monthly_option_buying_design.md](strategy/monthly_option_buying_design.md)
- [rollover_rules_design.md](strategy/rollover_rules_design.md)
- [rule_model.md](strategy/rule_model.md)
- [s23_gap_recalculation_design.md](strategy/s23_gap_recalculation_design.md)
- [strategy_config_layout.md](strategy/strategy_config_layout.md)
- [strategy_relevance_and_data_governance.md](strategy/strategy_relevance_and_data_governance.md)

## Importers

- [formula_normalization_rules.md](importers/formula_normalization_rules.md)
- [importer_input_instructions.md](importers/importer_input_instructions.md)
- [premium_formula_open_question.md](importers/premium_formula_open_question.md)
- [S23_branch_mapping.md](importers/S23_branch_mapping.md)
- [S23_excel_mapping.md](importers/S23_excel_mapping.md)

## Reference Materials

- [README.md](reference_materials/README.md)

## Operations

- [current_state.md](operations/current_state.md)
- [milestones.md](operations/milestones.md)
- [next_steps.md](operations/next_steps.md)
- [open_questions.md](operations/open_questions.md)
- [project_rulebook.md](operations/project_rulebook.md)

## Still Pending

- gap-up / gap-down overlay
- fuller missed-entry / recalculation engine
- shared captured-data adapter from `TradingEngine`
- rollover lifecycle module
- monthly option buying engine
- contract-specific option-chain intraday pricing and fuller strike-availability simulation
- broker adapters
- paper and live runtime execution layers
