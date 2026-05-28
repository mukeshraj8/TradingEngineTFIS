# TFIS Documentation

This folder contains the TFIS design, governance, importer, strategy, and
operations documentation.

## Current Project Snapshot

- broker-agnostic architecture is established
- folder-based strategy configuration is established
- all four canonical S23 branches are represented and validated
- workbook cross-check, formula safety, and registry governance layers are in
  place
- branch selection is available for folder-based monthly-status strategy
  variants
- offline historical lifecycle backtesting is in place with EOD policies,
  cost/slippage assumptions, rupee P&L, and equity/drawdown reporting
- monthly-status support includes thresholds, a deterministic status engine,
  branch selection, an opt-in S23 recalculation path, and workbook-backed
  current-day `FSL / TRP` handling
- historical backtests can opt into option-chain selection realism and
  contract-specific lifecycle pricing; the deterministic fixture-backed
  selected-contract archive currently covers all `10` selected-contract
  evaluations with no fallback
- historical backtests can review expiry-day full-exit compliance from selected
  contract expiry metadata
- bounded comparison tooling is available for generated historical backtest mode
  reports
- S23 paper mode now includes:
  - schema and validation
  - deterministic session orchestration
  - persistent session artifacts
  - replay bundles and review surfaces
  - order-intent and execution-journal shell
  - same-day fill/no-fill simulation
  - same-day lifecycle and paper P&L summaries
  - lifecycle-aware paper-vs-historical parity comparison
  - ingress-only dry-run validation and operator close-out policy
- broker-agnostic market-data ingress is now implemented with FYERS as the
  first adapter, while order placement remains blocked
- TradingEngine capture-session audit, read-only market-event conversion, and
  paired TFIS-prelude ingress-only validation now exist
- TradingEngine captures are currently usable for the market-data leg only; the
  capture-path OI audit keeps ingress acceptance at `NO_GO` because
  selected-contract `oi` is missing at decision time
- current operational paper status:
  - archive-backed lifecycle validation: `LIMITED_GO`
  - ingress-only validation: `LIMITED_GO`
  - broad live-paper rollout: `NO_GO`
- current quality snapshot:
  - tests passing: `426`
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
- [s23_contract_archive_ingestion_plan.md](strategy/s23_contract_archive_ingestion_plan.md)
- [s23_gap_recalculation_design.md](strategy/s23_gap_recalculation_design.md)
- [strategy_config_layout.md](strategy/strategy_config_layout.md)
- [strategy_relevance_and_data_governance.md](strategy/strategy_relevance_and_data_governance.md)

## Strategy Implementation

- [s23_strategy_implementation.md](strategy_implementation/s23_strategy_implementation.md)

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
- [s23_live_paper_data_contract.md](operations/s23_live_paper_data_contract.md)
- [s23_carry_forward_runtime_gap.md](operations/s23_carry_forward_runtime_gap.md)
- [s23_operator_closeout_policy.md](operations/s23_operator_closeout_policy.md)
- [s23_paper_session_state_machine.md](operations/s23_paper_session_state_machine.md)
- [s23_paper_trading_mvp_v1_design.md](operations/s23_paper_trading_mvp_v1_design.md)
- [s23_paper_trading_readiness_audit.md](operations/s23_paper_trading_readiness_audit.md)
- [s23_fyers_paper_ingress_design.md](operations/s23_fyers_paper_ingress_design.md)
- [s23_fyers_ingress_live_runbook.md](operations/s23_fyers_ingress_live_runbook.md)
- [s23_tradingengine_capture_adapter_audit.md](operations/s23_tradingengine_capture_adapter_audit.md)
- [s23_tradingengine_capture_oi_audit.md](operations/s23_tradingengine_capture_oi_audit.md)
- [tfis_manual_operator_guide.md](operations/tfis_manual_operator_guide.md)

## Recommended Reading Order

If you are getting oriented manually, start here:

1. [current_state.md](operations/current_state.md)
2. [next_steps.md](operations/next_steps.md)
3. [project_rulebook.md](operations/project_rulebook.md)
4. [tfis_manual_operator_guide.md](operations/tfis_manual_operator_guide.md)
5. [s23_paper_trading_readiness_audit.md](operations/s23_paper_trading_readiness_audit.md)
6. [s23_operator_closeout_policy.md](operations/s23_operator_closeout_policy.md)

## Still Pending

- broader real/archive contract-specific coverage beyond the current fixture set
- broker order-routing and real-money execution
- multi-session carry-forward and expiry-aware rollover runtime support
- multi-position paper/live runtime
- broader raw capture ingestion beyond the current read-only TradingEngine
  market-event adapter
