from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DECISION_ROOT = REPO_ROOT / "src/tfis/decision"
ADAPTER_ROOT = REPO_ROOT / "src/tfis/adapters/legacy_policies"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_generic_decision_package_remains_free_of_legacy_adapters() -> None:
    for path in DECISION_ROOT.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        imports = _imports(path)
        assert "tfis.adapters.legacy_policies" not in imports
        assert "S21" not in source
        assert "S23" not in source


def test_legacy_policy_adapters_are_the_only_new_s21_s23_policy_boundary() -> None:
    adapter_imports = set()
    for path in ADAPTER_ROOT.glob("*.py"):
        adapter_imports.update(_imports(path))

    assert "tfis.strategy" in adapter_imports
    assert "tfis.paper.contract_selection" in adapter_imports


def test_active_runtime_paths_do_not_import_generic_decision_engine_or_legacy_policies() -> None:
    active_roots = (
        REPO_ROOT / "src/tfis/paper",
        REPO_ROOT / "src/tfis/backtest",
        REPO_ROOT / "src/tfis/execution",
        REPO_ROOT / "src/tfis/broker",
        REPO_ROOT / "src/tfis/brokers",
    )
    forbidden = (
        "tfis.decision",
        "tfis.adapters.legacy_policies",
        "tfis.domain.gap_missed_entry",
        "GapMissedEntryEngine",
        "TFISDecisionEngine",
        "PolicyRegistry",
    )
    for root in active_roots:
        for path in root.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert all(item not in source for item in forbidden), path


def test_active_runtime_paths_do_not_import_or_invoke_gap_missed_entry_engine_recursively() -> None:
    active_roots = (
        REPO_ROOT / "src/tfis/paper",
        REPO_ROOT / "src/tfis/backtest",
        REPO_ROOT / "src/tfis/execution",
        REPO_ROOT / "src/tfis/broker",
        REPO_ROOT / "src/tfis/brokers",
    )
    forbidden = (
        "tfis.domain.gap_missed_entry",
        "tfis.adapters.legacy_policies.gap_missed_entry",
        "GapMissedEntryEngine",
        "evaluate_legacy_gap_missed_entry",
    )
    for root in active_roots:
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert all(item not in source for item in forbidden), path


def test_legacy_adapter_package_has_no_broker_lifecycle_or_persistence_dependencies() -> None:
    forbidden_prefixes = (
        "tfis.broker",
        "tfis.brokers",
        "tfis.execution",
        "tfis.storage",
        "tfis.paper.lifecycle",
        "tfis.paper.position",
        "tfis.paper.order",
        "tfis.dashboard",
    )
    for path in ADAPTER_ROOT.glob("*.py"):
        imports = _imports(path)
        assert not any(
            imported.startswith(prefix)
            for imported in imports
            for prefix in forbidden_prefixes
        ), path
