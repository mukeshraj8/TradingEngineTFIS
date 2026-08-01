from __future__ import annotations

import inspect
from pathlib import Path

from tfis.broker.read_boundary import BrokerReadAdapter, FyersReadOnlyFixtureAdapter


ROOT = Path(__file__).resolve().parents[2]
BOUNDARY_PATH = ROOT / "src" / "tfis" / "broker" / "read_boundary.py"
CORE_DIRS = [
    ROOT / "src" / "tfis" / "domain",
    ROOT / "src" / "tfis" / "strategy",
    ROOT / "src" / "tfis" / "formulas",
    ROOT / "src" / "tfis" / "risk",
]
WRITE_METHODS = {
    "place_order",
    "modify_order",
    "cancel_order",
    "exit_position",
    "square_off",
    "convert_position",
    "transfer_funds",
}


def test_phase4b_protocol_and_adapter_do_not_expose_write_methods() -> None:
    protocol_methods = {
        name
        for name, value in inspect.getmembers(BrokerReadAdapter)
        if inspect.isfunction(value) and not name.startswith("_")
    }
    adapter_methods = {
        name
        for name, value in inspect.getmembers(FyersReadOnlyFixtureAdapter)
        if inspect.isfunction(value) and not name.startswith("_")
    }

    assert not WRITE_METHODS & protocol_methods
    assert not WRITE_METHODS & adapter_methods


def test_broker_neutral_contracts_do_not_import_broker_sdks_or_runtime_authority() -> None:
    content = BOUNDARY_PATH.read_text(encoding="utf-8").lower()

    assert "fyers_apiv3" not in content
    assert "kiteconnect" not in content
    assert "smartconnect" not in content
    assert "executionintent" not in content
    assert "orderstate" not in content
    assert "positioncycle" not in content


def test_core_strategy_modules_do_not_depend_on_phase4b_broker_read_boundary() -> None:
    violations: list[str] = []
    for directory in CORE_DIRS:
        for path in directory.rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            if "read_boundary" in content or "BrokerReadAdapter" in content:
                violations.append(str(path.relative_to(ROOT)))

    assert not violations, "\n".join(violations)
