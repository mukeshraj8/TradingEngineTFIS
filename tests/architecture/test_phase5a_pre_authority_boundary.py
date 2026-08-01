from __future__ import annotations

from pathlib import Path

from tfis.internal_paper.end_to_end import CertificationAuthority, build_phase5a_pre_certification


ROOT = Path(__file__).resolve().parents[2]
PHASE5A_FILES = [
    ROOT / "src" / "tfis" / "internal_paper" / "end_to_end" / "certification.py",
    ROOT / "src" / "tfis" / "internal_paper" / "end_to_end" / "runner.py",
    ROOT / "src" / "tfis" / "adapters" / "phase5a_pre" / "s23_certification.py",
]


def test_phase5a_pre_has_no_external_broker_write_imports() -> None:
    forbidden = (
        "place_order",
        "modify_order",
        "cancel_order",
        "fyers_apiv3",
        "kiteconnect",
        "upstox",
        "live_submission_permitted = True",
        "broker_submission_permitted = True",
        "external_order_mutation_permitted=True",
    )
    for path in PHASE5A_FILES:
        text = path.read_text(encoding="utf-8")
        assert not any(item in text for item in forbidden), path


def test_certification_authority_cannot_enable_external_mutation() -> None:
    try:
        CertificationAuthority(
            authority_grant_id="bad",
            broker_account_id="acct",
            trading_session_id="session",
            strategy_instance_id="strategy",
            live_submission_permitted=True,
        )
    except ValueError as exc:
        assert "external mutation" in str(exc)
    else:
        raise AssertionError("CertificationAuthority accepted live submission.")


def test_runtime_certification_reports_no_external_authority() -> None:
    certification = build_phase5a_pre_certification()

    for scenario in certification["scenarios"]:
        authority = scenario["authority"]
        assert authority["authority_mode"] == "INTERNAL_PAPER_CERTIFICATION_ONLY"
        assert authority["external_broker_submission_permitted"] is False
        assert authority["broker_sandbox_submission_permitted"] is False
        assert authority["live_submission_permitted"] is False
        assert authority["external_order_mutation_permitted"] is False
        assert authority["external_position_mutation_permitted"] is False
        assert authority["reusable_as_live_authority"] is False
