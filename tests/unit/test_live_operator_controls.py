from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from tfis.broker import (
    LiveKillSwitchState,
    LiveOperatorApproval,
    LiveOperatorControlAction,
    LiveOperatorControlStore,
    validate_live_operator_controls,
)


NOW = datetime(2026, 7, 22, 8, 45, tzinfo=timezone.utc)


def test_live_operator_controls_store_approval_and_kill_switch_audit(
    tmp_path: Path,
) -> None:
    store = LiveOperatorControlStore()

    approval = store.approve_live_mode(
        tmp_path,
        actor="operator",
        reason="approved_live_dry_run_window",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=8),
    )
    active = store.activate_kill_switch(
        tmp_path,
        actor="operator",
        reason="risk_stop",
        occurred_at=NOW + timedelta(minutes=1),
    )
    cleared = store.clear_kill_switch(
        tmp_path,
        actor="operator",
        reason="risk_clear",
        occurred_at=NOW + timedelta(minutes=2),
    )

    assert store.load_approval(tmp_path) == approval
    assert store.load_kill_switch(tmp_path) == cleared
    assert active.active is True
    assert cleared.active is False
    events = store.load_events(tmp_path)
    assert [event.action for event in events] == [
        LiveOperatorControlAction.APPROVE_LIVE_MODE,
        LiveOperatorControlAction.ACTIVATE_KILL_SWITCH,
        LiveOperatorControlAction.CLEAR_KILL_SWITCH,
    ]


def test_live_operator_controls_validation_passes_with_unexpired_approval() -> None:
    validation = validate_live_operator_controls(
        approval=LiveOperatorApproval(
            approved=True,
            approved_by="operator",
            approved_at=NOW,
            expires_at=NOW + timedelta(hours=8),
            reason="approved_live_window",
            audit_event_id="approval-event",
        ),
        kill_switch=LiveKillSwitchState(
            available=True,
            active=False,
            updated_at=NOW,
            updated_by="operator",
            reason="armed",
            audit_event_id="kill-switch-event",
        ),
        now=NOW,
    )

    assert validation.status == "PASS"
    assert validation.issue_count == 0
    assert "approval is explicit, unexpired, audited" in validation.message


def test_live_operator_controls_validation_fails_missing_or_expired_approval() -> None:
    validation = validate_live_operator_controls(
        approval=LiveOperatorApproval(
            approved=False,
            approved_by=None,
            approved_at=None,
            expires_at=NOW - timedelta(minutes=1),
            reason=None,
            audit_event_id=None,
        ),
        kill_switch=LiveKillSwitchState(
            available=True,
            active=False,
            updated_at=NOW,
            updated_by="operator",
            reason="armed",
            audit_event_id="kill-switch-event",
        ),
        now=NOW,
    )

    assert validation.status == "FAIL"
    assert {issue.code for issue in validation.issues} >= {
        "LIVE_OPERATOR_APPROVAL_MISSING",
        "LIVE_OPERATOR_APPROVER_MISSING",
        "LIVE_OPERATOR_APPROVAL_EXPIRED",
        "LIVE_OPERATOR_APPROVAL_AUDIT_MISSING",
    }


def test_live_operator_controls_validation_fails_active_or_unaudited_kill_switch() -> None:
    validation = validate_live_operator_controls(
        approval=LiveOperatorApproval(
            approved=True,
            approved_by="operator",
            approved_at=NOW,
            expires_at=NOW + timedelta(hours=8),
            reason="approved_live_window",
            audit_event_id="approval-event",
        ),
        kill_switch=LiveKillSwitchState(
            available=False,
            active=True,
            updated_at=NOW,
            updated_by="operator",
            reason="risk_stop",
            audit_event_id=None,
        ),
        now=NOW,
    )

    assert validation.status == "FAIL"
    assert {issue.code for issue in validation.issues} >= {
        "LIVE_KILL_SWITCH_UNAVAILABLE",
        "LIVE_KILL_SWITCH_ACTIVE",
        "LIVE_KILL_SWITCH_AUDIT_MISSING",
    }
