from __future__ import annotations

import ast
from dataclasses import MISSING
from pathlib import Path

from tfis.decision import DecisionPolicySet


REPO_ROOT = Path(__file__).resolve().parents[2]
DECISION_ROOT = REPO_ROOT / "src/tfis/decision"


def _sources() -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in DECISION_ROOT.glob("*.py")
    }


def test_generic_decision_package_has_no_strategy_or_broker_dependencies() -> None:
    forbidden_import_prefixes = (
        "tfis.paper",
        "tfis.backtest",
        "tfis.execution",
        "tfis.broker",
        "tfis.brokers",
        "tfis.rules.s21",
        "tfis.rules.s23",
        "tfis.strategy.s23",
    )
    forbidden_terms = ("S21", "S23", "FYERS", "NIFTY", "BANKNIFTY")

    for path, source in _sources().items():
        tree = ast.parse(source, filename=str(path))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(
            imported.startswith(prefix)
            for imported in imports
            for prefix in forbidden_import_prefixes
        ), path
        assert all(term not in source for term in forbidden_terms), path


def test_engine_contains_no_strategy_code_conditionals_or_side_defaults() -> None:
    engine_path = DECISION_ROOT / "engine.py"
    source = engine_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(engine_path))

    conditional_sources = (
        ast.get_source_segment(source, node.test) or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
    )
    assert all("strategy_code" not in condition for condition in conditional_sources)
    assert "TFISDirection.LONG" not in source
    assert "TFISDirection.SHORT" not in source
    assert "TFISExecutionSide.BUY" not in source
    assert "TFISExecutionSide.SELL" not in source
    assert "TFISProductType.OPTION" not in source


def test_all_policy_dependencies_are_required_constructor_arguments() -> None:
    assert DecisionPolicySet.__dataclass_fields__["product"].default is MISSING
    assert DecisionPolicySet.__dataclass_fields__["entry"].default is MISSING
    assert DecisionPolicySet.__dataclass_fields__["gap"].default is MISSING
    assert DecisionPolicySet.__dataclass_fields__["missed_entry"].default is MISSING
    assert (
        DecisionPolicySet.__dataclass_fields__["contract_selection"].default
        is MISSING
    )
    assert DecisionPolicySet.__dataclass_fields__["target"].default is MISSING
    assert DecisionPolicySet.__dataclass_fields__["msl"].default is MISSING
