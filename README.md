# TradingEngineTFIS

A clean Python project for a lightweight TFIS rule-based trading engine.

This repository is intentionally separate from `TradingEngine` and `TradingEngineProd`. It is a fresh starting point for building a config-driven rule engine around TFIS concepts without copying existing runtime, broker, scoring, dashboard, or replay code.

## Scope

Current scope:
- define the project skeleton
- document the rule-engine architecture
- support config-driven runtime inputs
- prepare import/test validation

Explicitly out of scope for this initial version:
- live trading
- broker integrations
- FYERS or other exchange adapters
- dashboards
- replay certification
- current-engine scoring logic

## Runtime Direction

The intended workflow is:
1. Excel workbook acts as the source specification for formulas and rules.
2. A normalization step exports YAML or JSON artifacts.
3. The TFIS engine consumes those normalized artifacts at runtime.
4. Strategy behavior remains config-driven instead of hard-coded into the engine.

## Core Architecture Rules

- TFIS is a clean separate project from `TradingEngine` and `TradingEngineProd`.
- Excel/strategy sheet is the source specification.
- Runtime should use normalized YAML/JSON strategy definitions, not direct fragile Excel dependency.
- Strategy, formula, rule, market-structure, risk, and scheduler modules must remain broker-agnostic.
- No direct Fyers/Zerodha/Angel/Upstox imports outside broker adapters.
- Real broker integrations must be implemented only through adapter classes.
- Paper/mock broker must be used for tests.
- Existing TradingEngine scoring model may be integrated later only through clean interfaces, not copied directly into TFIS core.

## Current Status

Current state of the project:
- clean project skeleton is in place
- typed domain model is implemented
- safe formula engine is implemented
- S23 strategy evaluation is working offline
- broker-agnostic foundation is in place
- architecture boundary tests are active
- market structure layer is implemented
- order planner is implemented
- risk policy is implemented
- offline strategy pipeline is implemented

## Development

Requirements:
- Python 3.11+
- minimal dependencies only

Validation commands:

```powershell
python scripts/validate_project.py
python -m pytest -q
```
