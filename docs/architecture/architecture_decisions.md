# Architecture Decisions

## ADR-001: Clean Separate TFIS Project

Decision:
Use `D:\TradingEngineTFIS` as a separate project instead of removing pieces from existing TradingEngine.

Reason:
Current TradingEngine is evidence/replay/scoring-heavy. TFIS is rule-engine-first.

## ADR-002: Spreadsheet as Source Specification

Decision:
Treat Excel workbook as source specification, then convert to normalized YAML/JSON for runtime.

Reason:
Direct Excel runtime dependency is fragile. Normalized configs are easier to test, version, and validate.

## ADR-003: Broker-Agnostic Core

Decision:
Core TFIS modules must not directly depend on Fyers or any broker SDK.

Reason:
Same strategy should run with mock, paper, Fyers, Zerodha, or future brokers using adapters.

## ADR-004: Future Scoring Integration

Decision:
Existing TradingEngine scoring model can later be used as optional confirmation/filter via interface.

Reason:
Avoid mixing systems early while preserving future integration path.
