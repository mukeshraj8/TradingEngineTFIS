from __future__ import annotations

from pathlib import Path


def test_generic_captured_replay_adapter_has_no_strategy_or_authority_dependencies() -> None:
    source = Path("src/tfis/runtime/replay/captured_stream.py").read_text(encoding="utf-8")

    assert "S23" not in source
    assert "S21" not in source
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "paper" not in source.lower()
    assert "fyers" not in source.lower()
    assert "kiteconnect" not in source.lower()
    assert "eval(" not in source
    assert "exec(" not in source


def test_s23_replay_shadow_does_not_import_broker_or_order_authority() -> None:
    source = Path("src/tfis/adapters/legacy_policies/s23_replay_shadow.py").read_text(encoding="utf-8")

    forbidden = [
        "fyers",
        "kiteconnect",
        "place_order",
        "cancel_order",
        "modify_order",
        "OrderStateMachine",
        "ExecutionIntent",
        "PaperOrder",
        "PaperBroker",
    ]
    for token in forbidden:
        assert token not in source


def test_phase4a_report_authority_boundary_is_explicit() -> None:
    import json

    path = Path("reports/phase4a/phase4a_shadow_result.json")
    if not path.exists():
        from tfis.adapters.legacy_policies.s23_replay_shadow import write_phase4a_reports

        write_phase4a_reports()
    data = json.loads(path.read_text(encoding="utf-8"))
    authority = data["authority"]

    assert data["authority_mode"] == "SHADOW_ONLY"
    assert authority["broker_submission_permitted"] is False
    assert authority["paper_submission_permitted"] is False
    assert authority["live_submission_permitted"] is False
    assert authority["order_creation_permitted"] is False
    assert authority["order_mutation_permitted"] is False
    assert authority["position_mutation_permitted"] is False
    assert authority["square_off_permitted"] is False
    assert authority["carry_persistence_permitted"] is False
