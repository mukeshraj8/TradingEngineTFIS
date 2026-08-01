from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generic_execution_intent_has_no_strategy_formula_or_workbook_dependency() -> None:
    text = "\n".join(
        [
            _read("src/tfis/execution_intent/models.py"),
            _read("src/tfis/execution_intent/composer.py"),
            _read("src/tfis/execution_intent/validation.py"),
        ]
    )

    forbidden = ["S23", "S21", "openpyxl", "workbook", "eval(", "exec(", "fyers", "kiteconnect", "ClientOrder", "BrokerOrder"]
    assert [item for item in forbidden if item in text] == []


def test_s23_adapter_does_not_duplicate_formulas_or_create_orders() -> None:
    text = _read("src/tfis/adapters/phase4e/s23_execution_intent.py")

    assert "EntryEngine" not in text
    assert "StrategyEvaluator" not in text
    assert "ClientOrder" not in text
    assert "BrokerOrder" not in text
    assert "submit" not in text.lower()


def test_persistence_has_no_submission_statuses_for_phase4e() -> None:
    text = _read("src/tfis/persistence/migrations.py") + _read("src/tfis/persistence/repositories.py")

    assert "SUBMISSION_PENDING" not in text
    assert "ACKNOWLEDGED" not in text
    assert "broker_submission_permitted = True" not in text
