from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generic_account_and_adapter_have_no_s23_formulas_or_broker_write_imports() -> None:
    text = "\n".join(
        [
            _read("src/tfis/internal_paper/models.py"),
            _read("src/tfis/internal_paper/coordinator.py"),
            _read("src/tfis/internal_paper/adapter.py"),
            _read("src/tfis/internal_paper/recovery.py"),
        ]
    )

    forbidden = ["S23", "S21", "fyers", "kiteconnect", "upstox", "place_order", "modify_order", "cancel_order", "exit_position", "BrokerOrderSnapshot", "openpyxl", "workbook", "eval(", "exec("]
    assert [item for item in forbidden if item in text] == []


def test_s23_phase4f_adapter_stays_outside_generic_modules_and_has_no_formula_engine() -> None:
    text = _read("src/tfis/adapters/phase4f/s23_internal_paper.py")

    assert "EntryEngine" not in text
    assert "StrategyEvaluator" not in text
    assert "formula" not in text.lower()
    assert "place_order" not in text


def test_no_position_cycle_mutation_or_external_broker_submission() -> None:
    text = "\n".join(
        [
            _read("src/tfis/internal_paper/models.py"),
            _read("src/tfis/internal_paper/coordinator.py"),
            _read("src/tfis/internal_paper/adapter.py"),
            _read("src/tfis/persistence/repositories.py"),
        ]
    )

    assert "update_permitted: bool = True" not in text
    assert "live_submission_permitted=True" not in text
    assert "broker_submission_permitted=True" not in text
    assert "BrokerObservedState" not in text
