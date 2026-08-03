from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_unified_runtime_has_no_strategy_code_branching_in_generic_coordinator() -> None:
    text = (ROOT / "src" / "tfis" / "runtime" / "multi_strategy" / "coordinator.py").read_text(encoding="utf-8")

    assert 'if strategy == "S21"' not in text
    assert 'if strategy == "S22"' not in text
    assert 'if strategy == "S23"' not in text
    assert '"BANKNIFTY"' not in text
    assert '"RELIANCE"' not in text
    assert '"NIFTY"' not in text
    assert "BANKNIFTY24JAN47000CE" not in text
    assert "NSE:RELIANCE26AUG1260CE" not in text
    assert "NIFTY_PHASE5C_PUT_FIXTURE" not in text
    assert "fyers.place_order" not in text.lower()
    assert "place_order(" not in text


def test_dashboard_frontend_uses_projection_not_business_formulas() -> None:
    frontend = (ROOT / "dashboard" / "frontend" / "app.js").read_text(encoding="utf-8")

    forbidden = ["original_sl_formula", "base_entry_formula", "eval(", "new Function", "placeOrder", "cancelOrder"]
    for token in forbidden:
        assert token not in frontend


def test_command_contract_rejects_broker_order_mutations() -> None:
    text = (ROOT / "src" / "tfis" / "dashboard" / "commands" / "audit.py").read_text(encoding="utf-8")

    assert "FYERS_PLACE_ORDER" in text
    assert "REJECTED_COMMAND_NOT_AUTHORIZED" in text
    assert "broker_order_authority" in text
