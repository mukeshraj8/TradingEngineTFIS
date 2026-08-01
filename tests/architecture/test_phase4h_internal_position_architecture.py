from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_generic_internal_position_has_no_strategy_formula_or_broker_write_dependency() -> None:
    text = "\n".join(
        [
            _read("src/tfis/internal_position/models.py"),
            _read("src/tfis/internal_position/coordinator.py"),
        ]
    )

    forbidden = [
        "fyers",
        "kiteconnect",
        "upstox",
        "place_order",
        "modify_order",
        "cancel_order",
        "exit_position",
        "BrokerFillSnapshot",
        "BrokerOrderSnapshot",
        "openpyxl",
        "workbook",
        "eval(",
        "exec(",
    ]
    assert [item for item in forbidden if item in text] == []


def test_s23_position_adapter_stays_outside_generic_modules_and_has_no_formula_engine() -> None:
    text = _read("src/tfis/adapters/phase4h/s23_position_cycle.py")

    assert "EntryEngine" not in text
    assert "StrategyEvaluator" not in text
    assert "formula" not in text.lower()
    assert "place_order" not in text
    assert "live_submission_permitted\": True" not in text
    assert "broker_submission_permitted\": True" not in text


def test_account_and_position_ownership_boundaries_remain_separate() -> None:
    account_text = _read("src/tfis/internal_paper/coordinator.py")
    position_text = _read("src/tfis/internal_position/coordinator.py")

    assert "lifecycle_state" not in account_text
    assert "available_paper_margin" not in position_text
    assert "real_position_mutation_permitted" not in position_text
    assert "broker_reconciliation_authority=True" not in position_text
