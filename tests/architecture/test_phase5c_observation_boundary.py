from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PHASE5C_FILES = [
    ROOT / "src" / "tfis" / "internal_paper" / "observation" / "__init__.py",
    ROOT / "src" / "tfis" / "internal_paper" / "observation" / "phase5c_complete_s23.py",
    ROOT / "scripts" / "run_phase5c_complete_s23_observation.py",
]


def test_phase5c_observation_has_no_external_broker_or_live_authority() -> None:
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
    for path in PHASE5C_FILES:
        text = path.read_text(encoding="utf-8")
        assert not any(item in text for item in forbidden), path


def test_phase5c_does_not_add_strategy_formula_or_generic_trading_stack() -> None:
    text = (ROOT / "src" / "tfis" / "internal_paper" / "observation" / "phase5c_complete_s23.py").read_text(encoding="utf-8")

    assert "eval(" not in text
    assert "exec(" not in text
    assert "class AccountCoordinator" not in text
    assert "class PositionCycle" not in text
    assert "class TradeFact" not in text
    assert "PARAM(" not in text
    assert "entry_discount_pct" not in text


def test_phase5c_runner_does_not_accept_manual_call_put_flags() -> None:
    script = (ROOT / "scripts" / "run_phase5c_complete_s23_observation.py").read_text(encoding="utf-8")

    assert "--run-call" not in script
    assert "--run-put" not in script
    assert "--branch" not in script
    assert "--option-type" not in script
