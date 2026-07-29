from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BUSINESS_ENGINE_SOURCE = REPO_ROOT / "src" / "tfis" / "domain" / "business_engine.py"
GAP_MISSED_ENTRY_SOURCE = REPO_ROOT / "src" / "tfis" / "domain" / "gap_missed_entry.py"
CATALOG_SOURCE = REPO_ROOT / "config" / "business_engines" / "catalog.yaml"


def test_business_engine_contract_has_no_runtime_broker_or_legacy_imports() -> None:
    imports = []
    for path in (BUSINESS_ENGINE_SOURCE, GAP_MISSED_ENTRY_SOURCE):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

    forbidden_prefixes = (
        "tfis.paper",
        "tfis.backtest",
        "tfis.execution",
        "tfis.broker",
        "tfis.brokers",
        "tfis.adapters",
        "tfis.rules.s21",
        "tfis.rules.s23",
        "tfis.strategy.s23",
    )
    assert not any(
        imported.startswith(prefix)
        for imported in imports
        for prefix in forbidden_prefixes
    )


def test_business_engine_contract_and_catalog_are_strategy_neutral() -> None:
    forbidden_terms = (
        "S21",
        "S23",
        "FYERS",
        "NIFTY",
        "BANKNIFTY",
        "StrategyEvaluator",
        "S23PaperContractSelector",
        "legacy_policies",
        "paper_lifecycle",
        "live_order",
    )
    for path in (BUSINESS_ENGINE_SOURCE, GAP_MISSED_ENTRY_SOURCE, CATALOG_SOURCE):
        source = path.read_text(encoding="utf-8")
        assert all(term not in source for term in forbidden_terms), path
