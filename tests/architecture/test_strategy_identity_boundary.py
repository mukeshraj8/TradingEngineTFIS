from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
IDENTITY_PATH = REPO_ROOT / "src/tfis/domain/strategy_identity.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_strategy_identity_package_has_no_runtime_broker_lifecycle_dependencies() -> None:
    imports = _imports(IDENTITY_PATH)
    forbidden_prefixes = (
        "tfis.paper",
        "tfis.backtest",
        "tfis.execution",
        "tfis.broker",
        "tfis.brokers",
        "tfis.dashboard",
        "tfis.adapters",
    )

    assert not any(
        imported.startswith(prefix)
        for imported in imports
        for prefix in forbidden_prefixes
    )


def test_strategy_identity_package_has_no_strategy_specific_implementation_imports() -> None:
    source = IDENTITY_PATH.read_text(encoding="utf-8")

    assert "legacy_policies" not in source
    assert "StrategyEvaluator" not in source
    assert "S23PaperContractSelector" not in source
