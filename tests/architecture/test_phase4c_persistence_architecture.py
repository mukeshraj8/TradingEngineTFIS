from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PERSISTENCE_DIR = ROOT / "src" / "tfis" / "persistence"


def test_persistence_layer_has_no_strategy_formula_or_workbook_dependency() -> None:
    forbidden = ("TFISRulesAndSpec", "openpyxl", "s23_formula", "S23Calculation", "workbook")
    violations: list[str] = []
    for path in PERSISTENCE_DIR.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for term in forbidden:
            if term in content:
                violations.append(f"{path.relative_to(ROOT)} contains {term}")
    assert not violations, "\n".join(violations)


def test_persistence_layer_has_no_broker_write_or_runtime_submission_imports() -> None:
    forbidden = (
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_position",
        "ExecutionIntent",
        "OrderExecutor",
        "PaperBroker",
        "fyers_apiv3",
        "kiteconnect",
    )
    violations: list[str] = []
    for path in PERSISTENCE_DIR.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for term in forbidden:
            if term in content:
                violations.append(f"{path.relative_to(ROOT)} contains {term}")
    assert not violations, "\n".join(violations)


def test_domain_objects_do_not_depend_on_sqlite_or_persistence_infrastructure() -> None:
    violations: list[str] = []
    for path in (ROOT / "src" / "tfis" / "domain").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if "sqlite3" in content or "tfis.persistence" in content:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "\n".join(violations)
