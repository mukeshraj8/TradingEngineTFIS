from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_SOURCE = REPO_ROOT / "src" / "tfis" / "orchestration" / "offline_strategy_decision.py"


def test_offline_strategy_decision_orchestrator_has_no_strategy_branch_logic() -> None:
    source = ORCHESTRATOR_SOURCE.read_text(encoding="utf-8")

    forbidden_terms = (
        "S21",
        "S23",
        "FYERS",
        "NIFTY",
        "BANKNIFTY",
        "USDINR",
        "CALL",
        "PUT",
        "StrategyEvaluator",
    )
    assert all(term not in source for term in forbidden_terms)


def test_offline_strategy_decision_orchestrator_has_no_broker_paper_live_lifecycle_or_filesystem_imports() -> None:
    tree = ast.parse(ORCHESTRATOR_SOURCE.read_text(encoding="utf-8"), filename=str(ORCHESTRATOR_SOURCE))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    forbidden_prefixes = (
        "tfis.adapters",
        "tfis.paper",
        "tfis.backtest",
        "tfis.execution",
        "tfis.broker",
        "tfis.brokers",
        "tfis.strategy",
        "tfis.rules",
        "pathlib",
        "os",
    )
    assert not any(imported.startswith(prefix) for imported in imports for prefix in forbidden_prefixes)

    source = ORCHESTRATOR_SOURCE.read_text(encoding="utf-8")
    assert "open(" not in source
    assert ".write" not in source
