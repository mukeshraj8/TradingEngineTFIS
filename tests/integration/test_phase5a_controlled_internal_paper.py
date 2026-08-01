from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from tfis.internal_paper.runtime import (
    ControlledInternalPaperRuntime,
    OperatorCommand,
    OperatorCommandType,
    build_default_s23_single_instance_profile,
    build_phase5a_runtime_report_set,
)


@pytest.fixture(scope="module")
def runtime() -> ControlledInternalPaperRuntime:
    return ControlledInternalPaperRuntime()


def _enable() -> tuple[OperatorCommand, ...]:
    return (
        OperatorCommand(
            command_type=OperatorCommandType.ENABLE_INTERNAL_PAPER,
            operator_reference="TEST_OPERATOR",
            timestamp=datetime.fromisoformat("2026-06-05T09:00:00+05:30"),
            reason="Explicit test activation.",
        ),
    )


def test_profile_disabled_by_default_and_explicit_activation_required(runtime: ControlledInternalPaperRuntime) -> None:
    profile = build_default_s23_single_instance_profile()
    preview = runtime.preview()
    blocked = runtime.run(scenario_id="bull_target", commands=())

    assert profile.enabled_by_default is False
    assert profile.authority_mode == "INTERNAL_PAPER_CONTROLLED"
    assert preview.activation_status == "PREVIEW_ONLY"
    assert preview.operational_snapshot["account"]["active_orders"] == 0
    assert blocked.activation_status == "ACTIVATION_BLOCKED"
    assert "EXPLICIT_ENABLE_INTERNAL_PAPER_FLAG_REQUIRED" in blocked.activation_block_reasons


def test_startup_gates_market_input_and_single_instance(runtime: ControlledInternalPaperRuntime) -> None:
    result = runtime.run(scenario_id="bull_target", commands=_enable())

    assert result.startup_assessment["status"] == "PASSED"
    assert result.startup_assessment["schema_version"] >= 6
    assert result.market_input["mode"] == "CERTIFICATION_FIXTURE"
    assert result.market_input["timestamp_policy"] == "EVENT_TIME_ONLY"
    assert result.profile["strategy_instance_id"] == "S23_CALL_SIDE_INTERNAL_PAPER_CONTROLLED"
    assert result.profile["permitted_branches"] == ["BULL_CALL", "BEAR_CALL"]
    second = runtime.run(scenario_id="second_instance_blocked", commands=_enable())
    assert second.activation_status == "ACTIVATION_BLOCKED"
    assert "SECOND_AUTHORITATIVE_INSTANCE_BLOCKED" in second.activation_block_reasons


@pytest.mark.parametrize(
    ("scenario_id", "exit_reason", "runtime_status"),
    [
        ("bull_target", "TARGET", "ACTIVE_INTERNAL_PAPER"),
        ("bear_sl", "ORIGINAL_SL", "ACTIVE_INTERNAL_PAPER"),
        ("gap_revised_sl", "REVISED_SL", "ACTIVE_INTERNAL_PAPER"),
        ("eod_exit", "EOD_EXIT", "ACTIVE_INTERNAL_PAPER"),
    ],
)
def test_controlled_financial_sessions(runtime: ControlledInternalPaperRuntime, scenario_id: str, exit_reason: str, runtime_status: str) -> None:
    result = runtime.run(scenario_id=scenario_id, commands=_enable())

    assert result.activation_status == "CONTROLLED_INTERNAL_PAPER_ACTIVE"
    assert result.operational_snapshot["system"]["runtime_status"] == runtime_status
    assert result.session_audit["trade_facts_pnl_facts"]["exit_reason"] == exit_reason
    assert result.operational_snapshot["accounting"]["realized_pnl"] is not None
    assert result.shutdown_assessment["fabricated_cancellation_or_closure"] is False


def test_partial_fill_carry_and_accounting_projection_update(runtime: ControlledInternalPaperRuntime) -> None:
    partial = runtime.run(scenario_id="partial_fill", commands=_enable())
    carry = runtime.run(scenario_id="carry_recovery", commands=_enable())

    assert partial.operational_snapshot["account"]["fills"]["entry_fills"] >= 1
    assert partial.operational_snapshot["position"]["remaining_quantity"] >= 0
    assert partial.operational_snapshot["accounting"]["projection_watermark"]
    assert carry.operational_snapshot["position"]["carried_status"] == "CARRIED_FORWARD"
    assert carry.operational_snapshot["system"]["runtime_status"] == "POSITION_OPEN"


def test_reconciliation_expired_grant_disable_entry_and_protection(runtime: ControlledInternalPaperRuntime) -> None:
    reconciliation = runtime.run(scenario_id="blocked_reconciliation", commands=_enable())
    expired = runtime.run(scenario_id="expired_grant", commands=_enable())
    disabled = runtime.run(
        scenario_id="disable_entry_open_position",
        commands=_enable()
        + (
            OperatorCommand(
                command_type=OperatorCommandType.DISABLE_NEW_ENTRIES,
                operator_reference="TEST_OPERATOR",
                timestamp=datetime.fromisoformat("2026-06-05T10:00:00+05:30"),
                reason="Disable entries after open position.",
            ),
        ),
    )

    assert reconciliation.activation_status == "ACTIVATION_BLOCKED"
    assert "ADVISORY_RECONCILIATION_BLOCKED" in reconciliation.activation_block_reasons
    assert expired.activation_status == "ACTIVATION_BLOCKED"
    assert "AUTHORITY_GRANT_EXPIRED" in expired.activation_block_reasons
    assert disabled.activation_status == "CONTROLLED_INTERNAL_PAPER_ACTIVE"
    assert disabled.operational_snapshot["system"]["kill_switch_state"]["block_new_entries"] is True
    assert disabled.session_audit["lifecycle_actions"]["protected"] is True


@pytest.mark.parametrize("scenario_id", ["restart_after_partial_fill", "restart_protected_position"])
def test_restart_resume_is_deterministic(runtime: ControlledInternalPaperRuntime, scenario_id: str) -> None:
    result = runtime.run(
        scenario_id=scenario_id,
        commands=_enable()
        + (
            OperatorCommand(
                command_type=OperatorCommandType.RESUME_AFTER_RECOVERY,
                operator_reference="TEST_OPERATOR",
                timestamp=datetime.fromisoformat("2026-06-05T10:01:00+05:30"),
                reason="Explicit resume.",
            ),
        ),
    )

    assert result.activation_status == "CONTROLLED_INTERNAL_PAPER_ACTIVE"
    assert result.operational_snapshot["system"]["runtime_status"] == "RECOVERY_REQUIRED"
    assert result.shutdown_assessment["shutdown_mode"] == "CRASH_RECOVERY_TEST"
    assert result.operational_snapshot["system"]["kill_switch_state"]["read_only_recovery_mode"] is True


def test_duplicate_replay_account_halt_global_halt_and_read_only_recovery(runtime: ControlledInternalPaperRuntime) -> None:
    duplicate = runtime.run(scenario_id="duplicate_replay", commands=_enable())
    account_halt = runtime.run(
        scenario_id="account_halt",
        commands=_enable()
        + (
            OperatorCommand(
                command_type=OperatorCommandType.ACCOUNT_HALT,
                operator_reference="TEST_OPERATOR",
                timestamp=datetime.fromisoformat("2026-06-05T10:02:00+05:30"),
                reason="Account halt.",
            ),
        ),
    )
    global_halt = runtime.run(
        scenario_id="global_halt",
        commands=_enable()
        + (
            OperatorCommand(
                command_type=OperatorCommandType.GLOBAL_HALT,
                operator_reference="TEST_OPERATOR",
                timestamp=datetime.fromisoformat("2026-06-05T10:03:00+05:30"),
                reason="Global halt.",
            ),
        ),
    )

    assert duplicate.activation_status == "CONTROLLED_INTERNAL_PAPER_ACTIVE"
    assert duplicate.session_audit["orders_events_fills"]["internal_paper_result_hash"]
    assert account_halt.operational_snapshot["system"]["runtime_status"] == "ACCOUNT_BLOCKED"
    assert account_halt.session_audit["kill_switch_actions"][0]["action"] == "ACCOUNT_HALT"
    assert global_halt.operational_snapshot["system"]["runtime_status"] == "GLOBAL_BLOCKED"


def test_operational_snapshot_session_audit_shutdown_and_limitations(runtime: ControlledInternalPaperRuntime) -> None:
    result = runtime.run(scenario_id="bull_target", commands=_enable())
    snapshot = result.operational_snapshot
    audit = result.session_audit

    assert snapshot["system"]["external_authority"]["live_submission"] == "NONE"
    assert snapshot["strategy"]["current_plan"]["plan_hash"]
    assert snapshot["position"]["position_cycle_id"]
    assert audit["audit_hash"]
    assert audit["operator_actions"]
    assert result.shutdown_assessment["runtime_checkpoint_persisted"] is True
    assert any(item["limitation"] == "27 legacy full-suite failures remain" for item in result.known_limitations)


def test_reports_are_generated(tmp_path: Path) -> None:
    written = build_phase5a_runtime_report_set(tmp_path)

    expected = {
        "phase5a_runtime_profile.json",
        "phase5a_activation_contract.json",
        "phase5a_preview_result.json",
        "phase5a_bull_target_session.json",
        "phase5a_bear_sl_session.json",
        "phase5a_gap_revised_sl_session.json",
        "phase5a_partial_fill_session.json",
        "phase5a_eod_exit_session.json",
        "phase5a_carry_recovery_session.json",
        "phase5a_blocked_reconciliation_session.json",
        "phase5a_expired_grant_session.json",
        "phase5a_disable_entry_open_position.json",
        "phase5a_restart_session.json",
        "phase5a_kill_switch_session.json",
        "phase5a_operational_snapshot.json",
        "phase5a_session_audit.json",
        "phase5a_performance_metrics.json",
        "phase5a_known_limitations.json",
        "phase5a_gap_register.json",
        "phase5a_summary.md",
    }
    assert expected.issubset(set(written))
    profile = json.loads((tmp_path / "phase5a_runtime_profile.json").read_text(encoding="utf-8"))
    assert profile["enabled_by_default"] is False
