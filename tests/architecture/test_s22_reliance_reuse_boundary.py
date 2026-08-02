from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
S22_FILES = [
    ROOT / "src" / "tfis" / "adapters" / "phase5e" / "__init__.py",
    ROOT / "src" / "tfis" / "adapters" / "phase5e" / "s22_reliance.py",
]


def test_s22_reliance_has_no_external_broker_or_live_authority() -> None:
    forbidden = (
        "place_order(",
        "modify_order(",
        "cancel_order(",
        "fyers_apiv3",
        "kiteconnect",
        "upstox",
        "live_writes_enabled=True",
        "external_broker_enabled=True",
        "broker_sandbox_enabled=True",
    )
    for path in S22_FILES:
        text = path.read_text(encoding="utf-8")
        assert not any(item in text for item in forbidden), path


def test_s22_reliance_does_not_copy_generic_platform_classes() -> None:
    adapter = (ROOT / "src" / "tfis" / "adapters" / "phase5e" / "s22_reliance.py").read_text(encoding="utf-8")

    assert "eval(" not in adapter
    assert "exec(" not in adapter
    assert "class AccountCoordinator" not in adapter
    assert "class PositionCycle" not in adapter
    assert "class TradeFact" not in adapter
    assert "class PnLFact" not in adapter


def test_s22_reliance_does_not_add_strategy_branching_to_generic_engines() -> None:
    generic_roots = [
        ROOT / "src" / "tfis" / "monthly_status",
        ROOT / "src" / "tfis" / "execution_intent",
        ROOT / "src" / "tfis" / "internal_paper",
        ROOT / "src" / "tfis" / "internal_position",
        ROOT / "src" / "tfis" / "accounting",
    ]
    forbidden = ("strategy == \"S22\"", "strategy == 'S22'", "if strategy ==")
    for root in generic_roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert not any(item in text for item in forbidden), path
