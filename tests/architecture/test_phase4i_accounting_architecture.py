from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_accounting_core_has_no_broker_runtime_or_workbook_dependency() -> None:
    text = "\n".join(
        [
            _read("src/tfis/accounting/models.py"),
            _read("src/tfis/accounting/builders.py"),
            _read("src/tfis/accounting/reports.py"),
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
        "BrokerOrderSnapshot",
        "BrokerFillSnapshot",
        "openpyxl",
        "workbook",
        "dashboard",
        "eval(",
        "exec(",
    ]
    assert [item for item in forbidden if item in text] == []


def test_accounting_does_not_mutate_operational_state() -> None:
    text = "\n".join(
        [
            _read("src/tfis/accounting/builders.py"),
            _read("src/tfis/accounting/reports.py"),
            _read("src/tfis/adapters/phase4i/s23_accounting.py"),
        ]
    )

    assert "internal_position_cycle_projections SET" not in text
    assert "internal_client_order_records SET" not in text
    assert "internal_paper_fills SET" not in text
    assert "broker_submission_permitted=True" not in text
    assert "live_submission_permitted=True" not in text


def test_s23_formula_is_confined_to_phase4i_adapter_and_accounting_policy() -> None:
    adapter = _read("src/tfis/adapters/phase4i/s23_accounting.py")
    generic = _read("src/tfis/accounting/builders.py")

    assert "StrategyEvaluator" not in adapter
    assert "EntryEngine" not in adapter
    assert "short_option_realized_pnl" in generic
    assert "OPTION_SELLING" in adapter
