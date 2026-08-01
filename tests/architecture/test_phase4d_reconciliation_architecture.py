from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECONCILIATION_DIR = ROOT / "src" / "tfis" / "reconciliation"


def test_generic_reconciliation_has_no_strategy_formula_or_workbook_dependency() -> None:
    forbidden = ("TFISRulesAndSpec", "openpyxl", "s23_formula", "S23Calculation", "workbook", "eval(", "exec(")
    violations: list[str] = []
    for path in RECONCILIATION_DIR.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for term in forbidden:
            if term in content:
                violations.append(f"{path.relative_to(ROOT)} contains {term}")
    assert not violations, "\n".join(violations)


def test_reconciliation_layer_has_no_broker_write_or_submission_authority() -> None:
    forbidden = (
        "place_order",
        "modify_order",
        "cancel_order",
        "square_off",
        "OrderExecutor",
        "PaperBroker",
        "fyers_apiv3",
        "kiteconnect",
    )
    violations: list[str] = []
    for path in RECONCILIATION_DIR.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        for term in forbidden:
            if term in content:
                violations.append(f"{path.relative_to(ROOT)} contains {term}")
    assert not violations, "\n".join(violations)


def test_reconciliation_does_not_import_business_formula_modules() -> None:
    violations: list[str] = []
    for path in RECONCILIATION_DIR.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if "tfis.formulas" in content or "tfis.strategy" in content or "tfis.rules" in content:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, "\n".join(violations)
