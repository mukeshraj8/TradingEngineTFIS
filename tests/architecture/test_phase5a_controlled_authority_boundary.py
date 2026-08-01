from __future__ import annotations

from pathlib import Path

from tfis.internal_paper.runtime import ControlledInternalPaperRuntime, build_default_s23_single_instance_profile


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_FILES = [
    ROOT / "src" / "tfis" / "internal_paper" / "runtime" / "application.py",
    ROOT / "src" / "tfis" / "internal_paper" / "runtime" / "profile.py",
    ROOT / "src" / "tfis" / "internal_paper" / "runtime" / "operator.py",
    ROOT / "src" / "tfis" / "internal_paper" / "runtime" / "status.py",
    ROOT / "src" / "tfis" / "internal_paper" / "runtime" / "session_audit.py",
    ROOT / "scripts" / "run_s23_internal_paper.py",
]


def test_phase5a_runtime_has_no_external_broker_write_boundary() -> None:
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
    for path in RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        assert not any(item in text for item in forbidden), path


def test_profile_cannot_enable_external_authority() -> None:
    try:
        profile = build_default_s23_single_instance_profile()
        type(profile)(
            profile_id=profile.profile_id,
            enabled_by_default=False,
            authority_mode=profile.authority_mode,
            logical_paper_account=profile.logical_paper_account,
            strategy_instance_id=profile.strategy_instance_id,
            strategy_definition_id=profile.strategy_definition_id,
            strategy_version=profile.strategy_version,
            trading_session_id=profile.trading_session_id,
            configured_quantity=profile.configured_quantity,
            permitted_branches=tuple(profile.permitted_branches),
            permitted_purposes=tuple(profile.permitted_purposes),
            persistence_database_path=profile.persistence_database_path,
            market_data_source=profile.market_data_source,
            operator_controls=tuple(profile.operator_controls),
            shutdown_behavior=tuple(profile.shutdown_behavior),
            live_writes_enabled=True,
        )
    except ValueError as exc:
        assert "external authority" in str(exc)
    else:
        raise AssertionError("Controlled profile accepted live writes.")


def test_runtime_snapshot_routes_only_internal_paper_authority() -> None:
    result = ControlledInternalPaperRuntime().preview()
    authority = result.operational_snapshot["system"]["external_authority"]

    assert result.profile["authority_mode"] == "INTERNAL_PAPER_CONTROLLED"
    assert authority["external_broker_submission"] == "NONE"
    assert authority["broker_sandbox_submission"] == "NONE"
    assert authority["live_submission"] == "NONE"
    assert authority["external_order_mutation"] == "NONE"
    assert authority["external_position_mutation"] == "NONE"
