from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PHASE5B_FILES = [
    ROOT / "src" / "tfis" / "adapters" / "phase5b" / "__init__.py",
    ROOT / "src" / "tfis" / "adapters" / "phase5b" / "s23_put_four_branch.py",
    ROOT / "src" / "tfis" / "internal_paper" / "runtime" / "profile.py",
]


def test_phase5b_has_no_external_broker_or_live_authority() -> None:
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
    for path in PHASE5B_FILES:
        text = path.read_text(encoding="utf-8")
        assert not any(item in text for item in forbidden), path


def test_phase5b_does_not_add_formula_eval_or_domain_coordinators() -> None:
    adapter = (ROOT / "src" / "tfis" / "adapters" / "phase5b" / "s23_put_four_branch.py").read_text(encoding="utf-8")

    assert "eval(" not in adapter
    assert "exec(" not in adapter
    assert "class AccountCoordinator" not in adapter
    assert "class PositionCycle" not in adapter
    assert "class TradeFact" not in adapter


def test_phase5b_records_unresolved_or_deferred_gaps_without_activation() -> None:
    adapter = (ROOT / "src" / "tfis" / "adapters" / "phase5b" / "s23_put_four_branch.py").read_text(encoding="utf-8")

    assert "PHASE5B_REAL_CAPTURE_BREADTH" in adapter
    assert "DEFER_TO_MULTI_SESSION_OBSERVATION" in adapter
    assert "PHASE5B_EXTERNAL_AUTHORITY_NONE" in adapter
