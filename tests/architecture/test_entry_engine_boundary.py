from __future__ import annotations

import ast
from pathlib import Path

from tfis.domain import BusinessEngineCapability, load_business_engine_registry


REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRY_DOMAIN_SOURCE = REPO_ROOT / "src" / "tfis" / "domain" / "entry.py"
ENTRY_ENGINE_SOURCE = REPO_ROOT / "src" / "tfis" / "entry" / "engine.py"
GAP_SOURCE = REPO_ROOT / "src" / "tfis" / "domain" / "gap_missed_entry.py"
CATALOG_SOURCE = REPO_ROOT / "config" / "business_engines" / "catalog.yaml"


def test_entry_source_has_no_strategy_broker_runtime_or_legacy_imports() -> None:
    imports: list[str] = []
    for path in (ENTRY_DOMAIN_SOURCE, ENTRY_ENGINE_SOURCE):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
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
        "tfis.risk",
        "tfis.rules.s21",
        "tfis.rules.s23",
        "tfis.strategy.s23",
    )
    assert not any(imported.startswith(prefix) for imported in imports for prefix in forbidden_prefixes)


def test_entry_source_is_strategy_neutral_and_does_not_own_risk_lifecycle_or_option_chain() -> None:
    forbidden_terms = (
        "S21",
        "S23",
        "FYERS",
        "NIFTY",
        "BANKNIFTY",
        "USDINR",
        "StrategyEvaluator",
        "option_chain",
        "target",
        "stoploss",
        "MSL",
        "FSL",
        "TSL",
        "APS",
        "TRP",
        "paper_lifecycle",
        "live_order",
        "open(",
        "Path(",
    )
    for path in (ENTRY_DOMAIN_SOURCE, ENTRY_ENGINE_SOURCE):
        source = path.read_text(encoding="utf-8")
        assert all(term not in source for term in forbidden_terms), path


def test_phase3c_source_does_not_depend_on_entry() -> None:
    source = GAP_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(GAP_SOURCE))
    imports: list[str] = []
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
            imported_names.extend(alias.name for alias in node.names)

    assert "tfis.domain.entry" not in imports
    assert "entry" not in imports
    assert not any(name.startswith("Entry") for name in imported_names)


def test_business_engine_catalog_entry_dependency_graph_is_acyclic_and_entry_capabilities_are_explicit() -> None:
    registry = load_business_engine_registry(CATALOG_SOURCE)
    entry = registry.get("entry")
    contract_selection = registry.get("contract_selection")

    assert registry.execution_order.index("entry") < registry.execution_order.index("risk")
    assert "contract_selection" not in entry.dependencies
    assert "entry" not in contract_selection.dependencies
    assert BusinessEngineCapability.BASE_ENTRY in entry.provided_capabilities
    assert BusinessEngineCapability.EFFECTIVE_ENTRY in entry.provided_capabilities
    assert BusinessEngineCapability.ENTRY_QUALIFICATION in entry.provided_capabilities
    assert BusinessEngineCapability.RECALCULATED_ENTRY in entry.provided_capabilities
